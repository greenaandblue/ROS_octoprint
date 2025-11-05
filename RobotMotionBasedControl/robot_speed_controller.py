#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 6: Robot-Motion-Based Pause/Resume Control
基于机器人速度的打印机动态控制系统
机器人速度 > 0.4 m/s → 暂停打印
机器人速度 ≤ 0.4 m/s → 恢复打印
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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RobotSpeedMonitor:
    """机器人速度监控器"""
    
    def __init__(self, speed_source='odom'):
        """
        初始化速度监控器
        speed_source: 'odom' (里程计) 或 'cmd_vel' (速度命令)
        """
        self.current_speed = 0.0
        self.speed_source = speed_source
        self.last_update_time = time.time()
        self.lock = threading.Lock()
        
        # 根据速度源选择订阅话题
        if speed_source == 'odom':
            self.topic = '/odom'
            self.sub = rospy.Subscriber(self.topic, Odometry, self._odom_callback)
            logger.info(f"已订阅话题: {self.topic} (里程计)")
        else:  # cmd_vel
            self.topic = '/cmd_vel'
            self.sub = rospy.Subscriber(self.topic, Twist, self._cmd_vel_callback)
            logger.info(f"已订阅话题: {self.topic} (速度命令)")
    
    def _odom_callback(self, msg):
        """里程计回调 - 计算线速度"""
        try:
            vx = msg.twist.twist.linear.x
            vy = msg.twist.twist.linear.y
            vz = msg.twist.twist.linear.z
            
            # 计算合成速度
            speed = math.sqrt(vx**2 + vy**2 + vz**2)
            
            with self.lock:
                self.current_speed = speed
                self.last_update_time = time.time()
        except Exception as e:
            logger.error(f"里程计回调异常: {e}")
    
    def _cmd_vel_callback(self, msg):
        """速度命令回调 - 计算线速度"""
        try:
            vx = msg.linear.x
            vy = msg.linear.y
            vz = msg.linear.z
            
            # 计算合成速度
            speed = math.sqrt(vx**2 + vy**2 + vz**2)
            
            with self.lock:
                self.current_speed = speed
                self.last_update_time = time.time()
        except Exception as e:
            logger.error(f"速度命令回调异常: {e}")
    
    def get_speed(self):
        """获取当前速度 (m/s)"""
        with self.lock:
            return self.current_speed
    
    def is_alive(self):
        """检查是否收到最近的速度信息"""
        return (time.time() - self.last_update_time) < 2.0


class PrinterSpeedController:
    """打印机速度控制器 - 基于机器人速度"""
    
    def __init__(self, gcode_sender, speed_threshold=0.4, 
                 debounce_time=0.5, speed_source='odom'):
        """
        初始化打印机速度控制器
        
        Args:
            gcode_sender: GCodeSender 实例
            speed_threshold: 速度阈值 (m/s) - 超过此值则暂停
            debounce_time: 防抖时间 (s) - 避免频繁切换
            speed_source: 'odom' 或 'cmd_vel'
        """
        self.sender = gcode_sender
        self.speed_threshold = speed_threshold
        self.debounce_time = debounce_time
        
        # 速度监控
        self.speed_monitor = RobotSpeedMonitor(speed_source)
        
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
        
        logger.info(f"初始化打印机速度控制器")
        logger.info(f"  速度阈值: {self.speed_threshold} m/s")
        logger.info(f"  防抖时间: {self.debounce_time} s")
        logger.info(f"  速度源: {speed_source}")
    
    def init_logging(self, log_dir='./logs'):
        """初始化日志文件"""
        try:
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(
                log_dir, 
                f"robot_printer_control_{timestamp}.csv"
            )
            
            with open(self.log_file, 'w', newline='') as f:
                self.log_writer = csv.writer(f)
                self.log_writer.writerow([
                    'timestamp',
                    'robot_speed_ms',
                    'action',
                    'printer_state',
                    'response_time_ms',
                    'notes'
                ])
            
            logger.info(f"日志文件已创建: {self.log_file}")
            return True
        except Exception as e:
            logger.error(f"初始化日志失败: {e}")
            return False
    
    def log_event(self, robot_speed, action, printer_state, 
                  response_time=0.0, notes=""):
        """记录事件到CSV文件"""
        if not self.log_file:
            return
        
        try:
            timestamp = datetime.now().isoformat()
            
            with self.log_lock:
                with open(self.log_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        timestamp,
                        f"{robot_speed:.3f}",
                        action,
                        printer_state,
                        f"{response_time:.0f}",
                        notes
                    ])
        except Exception as e:
            logger.error(f"写入日志失败: {e}")
    
    def start_control(self):
        """启动速度控制"""
        if self.control_enabled:
            logger.warning("速度控制已在运行")
            return False
        
        self.control_enabled = True
        self.stop_flag = False
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self._control_loop,
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("速度控制已启动")
        return True
    
    def _control_loop(self):
        """主控制循环"""
        logger.info("进入控制循环...")
        
        loop_count = 0
        
        while self.control_enabled and not self.stop_flag:
            try:
                # 检查速度信息是否有效
                if not self.speed_monitor.is_alive():
                    logger.warning("未收到速度信息，停止控制")
                    time.sleep(1)
                    continue
                
                # 获取当前速度
                current_speed = self.speed_monitor.get_speed()
                
                # 检查是否应该改变打印机状态
                should_pause = current_speed > self.speed_threshold
                
                # 防抖检查
                time_since_last_action = time.time() - self.last_action_time
                
                if time_since_last_action < self.debounce_time:
                    loop_count += 1
                    if loop_count % 10 == 0:
                        logger.debug(
                            f"速度: {current_speed:.3f} m/s | "
                            f"状态: {'暂停' if self.printer_paused else '运行'} | "
                            f"防抖中..."
                        )
                    time.sleep(0.1)
                    continue
                
                # 决策：是否需要改变状态
                if should_pause and not self.printer_paused:
                    # 高速 → 暂停打印
                    logger.info(
                        f"检测到高速运动: {current_speed:.3f} m/s > "
                        f"{self.speed_threshold} m/s → 暂停打印"
                    )
                    
                    start_time = time.time()
                    success = self.sender.pause()
                    response_time = (time.time() - start_time) * 1000
                    
                    if success:
                        self.printer_paused = True
                        self.last_action_time = time.time()
                        
                        printer_state = self.sender.state.value
                        self.log_event(
                            current_speed,
                            'PAUSE',
                            printer_state,
                            response_time,
                            f"高速运动触发: {current_speed:.3f} m/s"
                        )
                        logger.info(
                            f"✓ 暂停成功 (响应时间: {response_time:.0f}ms)"
                        )
                    else:
                        logger.error("暂停失败")
                        self.log_event(
                            current_speed,
                            'PAUSE_FAILED',
                            self.sender.state.value,
                            response_time,
                            "暂停命令失败"
                        )
                
                elif not should_pause and self.printer_paused:
                    # 低速 → 恢复打印
                    logger.info(
                        f"检测到低速运动: {current_speed:.3f} m/s ≤ "
                        f"{self.speed_threshold} m/s → 恢复打印"
                    )
                    
                    start_time = time.time()
                    success = self.sender.resume()
                    response_time = (time.time() - start_time) * 1000
                    
                    if success:
                        self.printer_paused = False
                        self.last_action_time = time.time()
                        
                        printer_state = self.sender.state.value
                        self.log_event(
                            current_speed,
                            'RESUME',
                            printer_state,
                            response_time,
                            f"低速运动触发: {current_speed:.3f} m/s"
                        )
                        logger.info(
                            f"✓ 恢复成功 (响应时间: {response_time:.0f}ms)"
                        )
                    else:
                        logger.error("恢复失败")
                        self.log_event(
                            current_speed,
                            'RESUME_FAILED',
                            self.sender.state.value,
                            response_time,
                            "恢复命令失败"
                        )
                
                loop_count += 1
                if loop_count % 5 == 0:
                    logger.debug(
                        f"速度: {current_speed:.3f} m/s | "
                        f"打印机: {'暂停' if self.printer_paused else '运行'}"
                    )
                
                time.sleep(0.2)  # 监控周期: 200ms
                
            except Exception as e:
                logger.error(f"控制循环异常: {e}")
                time.sleep(1)
        
        logger.info("控制循环已停止")
    
    def stop_control(self):
        """停止速度控制"""
        if not self.control_enabled:
            logger.warning("速度控制未运行")
            return
        
        self.control_enabled = False
        self.stop_flag = True
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("速度控制已停止")
    
    def get_status(self):
        """获取当前状态"""
        return {
            'control_enabled': self.control_enabled,
            'printer_paused': self.printer_paused,
            'current_robot_speed': self.speed_monitor.get_speed(),
            'speed_threshold': self.speed_threshold,
            'printer_state': self.sender.state.value,
            'speed_monitor_alive': self.speed_monitor.is_alive(),
        }
    
    def set_speed_threshold(self, threshold):
        """设置速度阈值"""
        if threshold > 0:
            self.speed_threshold = threshold
            logger.info(f"速度阈值已更新: {threshold} m/s")
        else:
            logger.error("速度阈值必须为正数")
    
    def set_debounce_time(self, debounce_time):
        """设置防抖时间"""
        if debounce_time >= 0:
            self.debounce_time = debounce_time
            logger.info(f"防抖时间已更新: {debounce_time} s")


def interactive_mode(sender):
    """交互模式 - Stage 6集成"""
    
    print("\n" + "="*60)
    print("Stage 6: 基于机器人速度的打印机控制")
    print("="*60)
    print("\n功能说明:")
    print("  • 监听机器人速度信息")
    print("  • 自动控制打印机暂停/恢复")
    print("  • 记录速度触发事件和响应延迟")
    print("  • 防抖机制避免频繁切换")
    print("\n命令列表:")
    print("  start [source]       - 启动速度控制 (source: odom/cmd_vel)")
    print("  stop                 - 停止速度控制")
    print("  status               - 显示当前状态")
    print("  threshold <value>    - 设置速度阈值 (m/s)")
    print("  debounce <time>      - 设置防抖时间 (s)")
    print("  logs                 - 显示日志文件位置")
    print("  quit                 - 退出")
    print("="*60 + "\n")
    
    controller = None
    
    try:
        while True:
            try:
                cmd = input(">>> ").strip().split(' ', 1)
                if not cmd[0]:
                    continue
                
                command = cmd[0].lower()
                
                if command == 'quit':
                    break
                
                elif command == 'start':
                    if controller:
                        print("控制器已在运行")
                        continue
                    
                    speed_source = cmd[1] if len(cmd) > 1 else 'odom'
                    if speed_source not in ['odom', 'cmd_vel']:
                        print("速度源必须为 'odom' 或 'cmd_vel'")
                        continue
                    
                    controller = PrinterSpeedController(
                        sender, 
                        speed_source=speed_source
                    )
                    controller.init_logging()
                    
                    if controller.start_control():
                        print("✓ 速度控制已启动")
                    else:
                        print("✗ 启动失败")
                
                elif command == 'stop':
                    if controller:
                        controller.stop_control()
                        print("✓ 速度控制已停止")
                        controller = None
                    else:
                        print("控制器未运行")
                
                elif command == 'status':
                    if controller:
                        status = controller.get_status()
                        print("\n当前状态:")
                        for key, value in status.items():
                            print(f"  {key}: {value}")
                        print()
                    else:
                        print("控制器未运行")
                
                elif command == 'threshold':
                    if controller and len(cmd) > 1:
                        try:
                            threshold = float(cmd[1])
                            controller.set_speed_threshold(threshold)
                        except ValueError:
                            print("请输入有效的数值")
                    else:
                        print("请提供阈值数值")
                
                elif command == 'debounce':
                    if controller and len(cmd) > 1:
                        try:
                            debounce = float(cmd[1])
                            controller.set_debounce_time(debounce)
                        except ValueError:
                            print("请输入有效的数值")
                    else:
                        print("请提供防抖时间")
                
                elif command == 'logs':
                    if controller and controller.log_file:
                        print(f"日志文件: {controller.log_file}")
                    else:
                        print("日志未初始化或控制器未运行")
                
                else:
                    print(f"未知命令: {command}")
                    
            except KeyboardInterrupt:
                print("\n正在退出...")
                break
            except Exception as e:
                print(f"错误: {e}")
    
    finally:
        if controller:
            controller.stop_control()
        print("程序已退出")


if __name__ == '__main__':
    # 这个模块应该与 gcode_sender.py 一起使用
    # 示例用法见下方注释
    print("Stage 6: Robot-Motion-Based Printer Control Module")
    print("这个模块应该与 gcode_sender.py 集成使用")
    print("\n集成示例:")
    print("  from gcode_sender import GCodeSender")
    print("  from robot_speed_controller import PrinterSpeedController")
    print("  ")
    print("  sender = GCodeSender(OCTOPRINT_URL, API_KEY)")
    print("  controller = PrinterSpeedController(sender, speed_source='odom')")
    print("  controller.init_logging()")
    print("  controller.start_control()")