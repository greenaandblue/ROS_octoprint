#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 6: Robot-Motion-Based Pause/Resume Control - FIXED VERSION
改进：
1. 更好的ROS话题处理
2. 及时的速度信息获取
3. 改进的防抖机制
4. 详细的调试日志
"""

import rospy  # type: ignore
from nav_msgs.msg import Odometry # type: ignore
from geometry_msgs.msg import Twist # type: ignore
import time
import threading
import csv
import os
from datetime import datetime
import math
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RobotSpeedMonitor:
    """机器人速度监控器 - 改进版"""
    
    def __init__(self, speed_source='odom', odom_topic='/odom', cmd_vel_topic='/cmd_vel'):
        """
        初始化速度监控器
        
        Args:
            speed_source: 'odom' 或 'cmd_vel'
            odom_topic: 里程计话题
            cmd_vel_topic: 速度命令话题
        """
        self.current_speed = 0.0
        self.speed_source = speed_source
        self.last_update_time = time.time()
        self.lock = threading.Lock()
        self.message_count = 0
        self.last_speed = 0.0
        
        try:
            if speed_source == 'odom':
                self.sub = rospy.Subscriber(odom_topic, Odometry, self._odom_callback)
                logger.info(f"[SPEED] ✓ 已订阅里程计话题: {odom_topic}")
            else:  # cmd_vel
                self.sub = rospy.Subscriber(cmd_vel_topic, Twist, self._cmd_vel_callback)
                logger.info(f"[SPEED] ✓ 已订阅速度命令话题: {cmd_vel_topic}")
        except Exception as e:
            logger.error(f"[SPEED] 订阅话题失败: {e}")
            raise
    
    def _odom_callback(self, msg):
        """里程计回调 - 计算线速度"""
        try:
            vx = msg.twist.twist.linear.x
            vy = msg.twist.twist.linear.y
            vz = msg.twist.twist.linear.z
            
            # 计算合成速度 (忽略Z轴)
            speed = math.sqrt(vx**2 + vy**2)
            
            with self.lock:
                self.last_speed = self.current_speed
                self.current_speed = abs(speed)  # 取绝对值
                self.last_update_time = time.time()
                self.message_count += 1
            
            if self.message_count % 50 == 0:
                logger.debug(f"[SPEED] 收到里程计: {self.current_speed:.4f} m/s (Vx={vx:.3f}, Vy={vy:.3f})")
                
        except Exception as e:
            logger.error(f"[SPEED] 里程计回调异常: {e}")
    
    def _cmd_vel_callback(self, msg):
        """速度命令回调 - 计算线速度"""
        try:
            vx = msg.linear.x
            vy = msg.linear.y
            vz = msg.linear.z
            
            # 计算合成速度
            speed = math.sqrt(vx**2 + vy**2)
            
            with self.lock:
                self.last_speed = self.current_speed
                self.current_speed = abs(speed)  # 取绝对值
                self.last_update_time = time.time()
                self.message_count += 1
            
            if self.message_count % 50 == 0:
                logger.debug(f"[SPEED] 收到速度命令: {self.current_speed:.4f} m/s (Vx={vx:.3f}, Vy={vy:.3f})")
                
        except Exception as e:
            logger.error(f"[SPEED] 速度命令回调异常: {e}")
    
    def get_speed(self) -> float:
        """获取当前速度 (m/s)"""
        with self.lock:
            return self.current_speed
    
    def is_alive(self) -> bool:
        """检查是否收到最近的速度信息"""
        time_since_update = time.time() - self.last_update_time
        is_alive = time_since_update < 3.0  # 3秒超时
        
        if not is_alive:
            logger.warning(f"[SPEED] ⚠ 距上次更新已 {time_since_update:.1f}s，可能未收到速度信息")
        
        return is_alive
    
    def get_message_count(self) -> int:
        """获取收到的消息数量"""
        with self.lock:
            return self.message_count


class PrinterSpeedController:
    """打印机速度控制器 - 改进版"""
    
    def __init__(self, gcode_sender, speed_threshold=0.04, 
                 debounce_time=0.5, speed_source='odom',
                 odom_topic='/odom', cmd_vel_topic='/cmd_vel'):
        """
        初始化打印机速度控制器
        
        Args:
            gcode_sender: GCodeSender 实例
            speed_threshold: 速度阈值 (m/s) - 默认0.04 m/s
            debounce_time: 防抖时间 (s)
            speed_source: 'odom' 或 'cmd_vel'
            odom_topic: 里程计话题
            cmd_vel_topic: 速度命令话题
        """
        self.sender = gcode_sender
        self.speed_threshold = speed_threshold
        self.debounce_time = debounce_time
        
        # 速度监控
        try:
            self.speed_monitor = RobotSpeedMonitor(
                speed_source=speed_source,
                odom_topic=odom_topic,
                cmd_vel_topic=cmd_vel_topic
            )
        except Exception as e:
            logger.error(f"[CTRL] 初始化速度监控失败: {e}")
            raise
        
        # 状态控制
        self.printer_paused = False
        self.last_action_time = time.time()
        self.control_enabled = False
        
        # 数据日志
        self.log_file = None
        self.log_writer = None
        self.log_lock = threading.Lock()
        
        # 监控线程
        self.monitor_thread = None
        self.stop_flag = False
        
        # 统计数据
        self.pause_count = 0
        self.resume_count = 0
        
        logger.info(f"[CTRL] ✓ 初始化打印机速度控制器")
        logger.info(f"[CTRL]   速度阈值: {self.speed_threshold:.3f} m/s")
        logger.info(f"[CTRL]   防抖时间: {self.debounce_time:.2f} s")
        logger.info(f"[CTRL]   速度源: {speed_source}")
    
    def init_logging(self, log_dir='./logs'):
        """初始化日志文件"""
        try:
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(
                log_dir, 
                f"robot_printer_control_{timestamp}.csv"
            )
            
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'robot_speed_ms',
                    'action',
                    'printer_state',
                    'response_time_ms',
                    'notes'
                ])
            
            logger.info(f"[LOG] ✓ 日志文件已创建: {self.log_file}")
            return True
        except Exception as e:
            logger.error(f"[LOG] ✗ 初始化日志失败: {e}")
            return False
    
    def log_event(self, robot_speed, action, printer_state, 
                  response_time=0.0, notes=""):
        """记录事件到CSV文件"""
        if not self.log_file:
            return
        
        try:
            timestamp = datetime.now().isoformat()
            
            with self.log_lock:
                with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        timestamp,
                        f"{robot_speed:.4f}",
                        action,
                        printer_state,
                        f"{response_time:.0f}",
                        notes
                    ])
        except Exception as e:
            logger.error(f"[LOG] ✗ 写入日志失败: {e}")
    
    def start_control(self):
        """启动速度控制"""
        if self.control_enabled:
            logger.warning("[CTRL] 速度控制已在运行")
            return False
        
        if not self.speed_monitor.is_alive():
            logger.error("[CTRL] ✗ 速度信息未准备好，请检查ROS话题")
            return False
        
        self.control_enabled = True
        self.stop_flag = False
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name='PrinterSpeedControlThread'
        )
        self.monitor_thread.start()
        logger.info("[CTRL] ✓ 速度控制已启动")
        return True
    
    def _control_loop(self):
        """主控制循环"""
        logger.info("[LOOP] 进入控制循环...")
        
        loop_count = 0
        stable_counter = 0
        
        while self.control_enabled and not self.stop_flag:
            try:
                # 检查速度信息是否有效
                if not self.speed_monitor.is_alive():
                    logger.warning("[LOOP] ⚠ 未收到速度信息，停止控制")
                    time.sleep(1)
                    continue
                
                # 获取当前速度
                current_speed = self.speed_monitor.get_speed()
                
                # 决策：是否应该改变打印机状态
                should_pause = current_speed > self.speed_threshold
                
                # 防抖检查
                time_since_last_action = time.time() - self.last_action_time
                
                if time_since_last_action < self.debounce_time:
                    loop_count += 1
                    if loop_count % 20 == 0:
                        logger.debug(
                            f"[LOOP] 防抖中... 速度={current_speed:.4f}m/s "
                            f"状态={'暂停' if self.printer_paused else '运行'} "
                            f"距离上次操作={time_since_last_action:.2f}s"
                        )
                    time.sleep(0.1)
                    continue
                
                # 高速运动 → 暂停打印
                if should_pause and not self.printer_paused:
                    logger.info(
                        f"[ACTION] ⚡ 高速检测: {current_speed:.4f}m/s > {self.speed_threshold:.4f}m/s → 暂停"
                    )
                    
                    start_time = time.perf_counter()
                    success = self.sender.pause()
                    response_time = (time.perf_counter() - start_time) * 1000
                    
                    if success:
                        self.printer_paused = True
                        self.last_action_time = time.time()
                        self.pause_count += 1
                        
                        printer_state = self.sender.state.value
                        self.log_event(
                            current_speed,
                            'PAUSE',
                            printer_state,
                            response_time,
                            f"高速运动: {current_speed:.4f}m/s"
                        )
                        logger.info(
                            f"[ACTION] ✓ 暂停成功 (响应: {response_time:.0f}ms) [{self.pause_count}]"
                        )
                        stable_counter = 0
                    else:
                        logger.error("[ACTION] ✗ 暂停失败")
                        self.log_event(
                            current_speed,
                            'PAUSE_FAILED',
                            self.sender.state.value,
                            response_time,
                            "暂停命令失败"
                        )
                
                # 低速运动 → 恢复打印
                elif not should_pause and self.printer_paused:
                    stable_counter += 1
                    
                    # 需要连续低速确认才恢复 (防止速度波动)
                    if stable_counter >= 3:
                        logger.info(
                            f"[ACTION] 🐢 低速检测: {current_speed:.4f}m/s ≤ {self.speed_threshold:.4f}m/s → 恢复"
                        )
                        
                        start_time = time.perf_counter()
                        success = self.sender.resume()
                        response_time = (time.perf_counter() - start_time) * 1000
                        
                        if success:
                            self.printer_paused = False
                            self.last_action_time = time.time()
                            self.resume_count += 1
                            
                            printer_state = self.sender.state.value
                            self.log_event(
                                current_speed,
                                'RESUME',
                                printer_state,
                                response_time,
                                f"低速运动: {current_speed:.4f}m/s"
                            )
                            logger.info(
                                f"[ACTION] ✓ 恢复成功 (响应: {response_time:.0f}ms) [{self.resume_count}]"
                            )
                            stable_counter = 0
                        else:
                            logger.error("[ACTION] ✗ 恢复失败")
                            self.log_event(
                                current_speed,
                                'RESUME_FAILED',
                                self.sender.state.value,
                                response_time,
                                "恢复命令失败"
                            )
                else:
                    stable_counter = max(0, stable_counter - 1)
                
                loop_count += 1
                if loop_count % 10 == 0:
                    logger.debug(
                        f"[LOOP] 速度={current_speed:.4f}m/s | "
                        f"打印机={'暂停' if self.printer_paused else '运行'} | "
                        f"稳定计数={stable_counter}"
                    )
                
                time.sleep(0.2)  # 监控周期: 200ms
                
            except Exception as e:
                logger.error(f"[LOOP] ✗ 控制循环异常: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
        
        logger.info(f"[LOOP] 控制循环已停止 (暂停{self.pause_count}次, 恢复{self.resume_count}次)")
    
    def stop_control(self):
        """停止速度控制"""
        if not self.control_enabled:
            logger.warning("[CTRL] 速度控制未运行")
            return
        
        self.control_enabled = False
        self.stop_flag = True
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("[CTRL] ✓ 速度控制已停止")
    
    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            'control_enabled': self.control_enabled,
            'printer_paused': self.printer_paused,
            'current_robot_speed': self.speed_monitor.get_speed(),
            'speed_threshold': self.speed_threshold,
            'printer_state': self.sender.state.value,
            'speed_monitor_alive': self.speed_monitor.is_alive(),
            'messages_received': self.speed_monitor.get_message_count(),
            'pause_count': self.pause_count,
            'resume_count': self.resume_count,
        }
    
    def set_speed_threshold(self, threshold: float):
        """设置速度阈值"""
        if threshold > 0:
            self.speed_threshold = threshold
            logger.info(f"[CONFIG] ✓ 速度阈值已更新: {threshold:.4f} m/s")
        else:
            logger.error("[CONFIG] ✗ 速度阈值必须为正数")
    
    def set_debounce_time(self, debounce_time: float):
        """设置防抖时间"""
        if debounce_time >= 0:
            self.debounce_time = debounce_time
            logger.info(f"[CONFIG] ✓ 防抖时间已更新: {debounce_time:.2f} s")
        else:
            logger.error("[CONFIG] ✗ 防抖时间不能为负数")