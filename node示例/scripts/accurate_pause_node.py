#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROS Node: G-code Sender with Precise Pause System
Stage 4增强型G-code发送器ROS节点
"""

import rospy # type: ignore
import requests
import time
import threading
import json
import re
from enum import Enum
from typing import Dict, Optional

# ROS消息类型
from std_msgs.msg import String, Float32, Bool # type: ignore
from gcode_sender.msg import PrinterStatus, PrintProgress, TemperatureInfo # type: ignore
from gcode_sender.srv import ( # type: ignore
    StartPrint, StartPrintResponse,
    PausePrint, PausePrintResponse,
    ResumePrint, ResumePrintResponse,
    StopPrint, StopPrintResponse,
    SetSpeed, SetSpeedResponse,
    GetStatus, GetStatusResponse
)


class PrinterState(Enum):
    """打印机状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    HALTED = "halted"
    PAUSING = "pausing"
    RESUMING = "resuming"


class PrintState:
    """打印状态保存类"""
    def __init__(self):
        self.position = {'X': 0, 'Y': 0, 'Z': 0, 'E': 0}
        self.temperatures = {'tool': 0, 'bed': 0}
        self.feedrate = 0
        self.fan_speed = 0
        self.relative_mode = False
        self.line_number = 0
        
    def save_position(self, x, y, z, e):
        self.position = {'X': x, 'Y': y, 'Z': z, 'E': e}
    
    def save_temperatures(self, tool_temp, bed_temp):
        self.temperatures = {'tool': tool_temp, 'bed': bed_temp}


class GCodeSenderNode:
    """ROS节点封装的G-code发送器"""
    
    def __init__(self):
        """初始化ROS节点"""
        rospy.init_node('gcode_sender_node', anonymous=False)
        
        # 从参数服务器获取配置
        self.octoprint_url = rospy.get_param('~octoprint_url', 'http://octopi.local').rstrip('/')
        self.api_key = rospy.get_param('~api_key', '')
        self.pause_lift_z = rospy.get_param('~pause_lift_z', 5.0)
        self.pause_retract = rospy.get_param('~pause_retract', 5.0)
        self.maintain_temp_on_pause = rospy.get_param('~maintain_temp_on_pause', True)
        self.publish_rate = rospy.get_param('~publish_rate', 1.0)  # Hz
        
        if not self.api_key:
            rospy.logerr("API Key未配置！请设置~api_key参数")
            raise ValueError("Missing API Key")
        
        # 状态控制
        self.state = PrinterState.IDLE
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event.set()
        
        # 打印状态保存
        self.print_state = PrintState()
        
        # 文件和进度控制
        self.gcode_lines = []
        self.current_line_index = 0
        self.total_lines = 0
        self.file_path = ""
        self.processed_lines = 0
        
        # 线程控制
        self.sender_thread = None
        self.lock = threading.Lock()
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 错误监控
        self.error_count = 0
        self.max_errors = 5
        self.consecutive_timeouts = 0
        self.max_timeouts = 3
        self.response_timeout = 10.0
        
        # 速度控制
        self.speed_multiplier = 1.0
        
        self.last_printer_state = ""
        
        # 危险指令模式
        self.dangerous_patterns = [r'^M112$']
        self.waiting_patterns = [r'^M109', r'^M190', r'^G28']
        
        # 初始化ROS发布者
        self.status_pub = rospy.Publisher('~printer_status', PrinterStatus, queue_size=10)
        self.progress_pub = rospy.Publisher('~print_progress', PrintProgress, queue_size=10)
        self.temp_pub = rospy.Publisher('~temperatures', TemperatureInfo, queue_size=10)
        self.state_pub = rospy.Publisher('~state', String, queue_size=10)
        
        # 初始化ROS服务
        self.start_srv = rospy.Service('~start_print', StartPrint, self.handle_start_print)
        self.pause_srv = rospy.Service('~pause_print', PausePrint, self.handle_pause_print)
        self.resume_srv = rospy.Service('~resume_print', ResumePrint, self.handle_resume_print)
        self.stop_srv = rospy.Service('~stop_print', StopPrint, self.handle_stop_print)
        self.speed_srv = rospy.Service('~set_speed', SetSpeed, self.handle_set_speed)
        self.status_srv = rospy.Service('~get_status', GetStatus, self.handle_get_status)
        
        # 启动状态发布定时器
        self.status_timer = rospy.Timer(
            rospy.Duration(1.0 / self.publish_rate), 
            self.publish_status_callback
        )
        
        rospy.loginfo("G-code Sender节点已启动")
        rospy.loginfo(f"OctoPrint URL: {self.octoprint_url}")
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查指令是否危险"""
        command = command.strip().upper()
        for pattern in self.dangerous_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def is_waiting_command(self, command: str) -> bool:
        """检查是否为需要等待的指令"""
        command = command.strip().upper()
        for pattern in self.waiting_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def send_and_wait(self, command: str, wait_time: float = 0.1) -> bool:
        """发送单条指令并等待响应"""
        command = command.strip()
        if not command or command.startswith(';'):
            return True
        
        if self.is_dangerous_command(command):
            rospy.logwarn(f"跳过危险指令: {command}")
            return True
        
        if self.stop_event.is_set():
            return False
        
        try:
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=self.response_timeout
            )
            response.raise_for_status()
            
            if self.is_waiting_command(command):
                time.sleep(0.5)
            else:
                time.sleep(wait_time)
            
            self.error_count = 0
            self.consecutive_timeouts = 0
            
            rospy.logdebug(f"指令已确认: {command}")
            return True
            
        except requests.exceptions.Timeout:
            self.consecutive_timeouts += 1
            rospy.logwarn(f"指令超时 '{command}' ({self.consecutive_timeouts}/{self.max_timeouts})")
            
            if self.consecutive_timeouts >= self.max_timeouts:
                rospy.logerr("连续超时过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
                return False
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            rospy.logerr(f"指令发送失败 '{command}': {e} ({self.error_count}/{self.max_errors})")
            
            if self.error_count >= self.max_errors:
                rospy.logerr("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def execute_printer_pause(self) -> bool:
        """执行打印机级暂停"""
        rospy.loginfo("执行打印机级暂停...")
        
        try:
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps({"command": "pause", "action": "pause"}),
                timeout=5
            )
            
            if response.status_code == 204:
                rospy.loginfo("✓ OctoPrint暂停命令已发送")
                time.sleep(0.5)
            
            if self.pause_lift_z > 0:
                rospy.loginfo(f"抬升喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            if self.pause_retract > 0:
                rospy.loginfo(f"回抽耗材 {self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E-{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            temps = self.check_temperatures_safe()
            if temps:
                tool_target = temps.get('tool0', {}).get('target', 0)
                bed_target = temps.get('bed', {}).get('target', 0)
                self.print_state.save_temperatures(tool_target, bed_target)
                rospy.loginfo(f"已保存温度: 热端={tool_target}°C, 热床={bed_target}°C")
            
            return True
            
        except Exception as e:
            rospy.logerr(f"执行打印机暂停失败: {e}")
            return False
    
    def execute_printer_resume(self) -> bool:
        """执行打印机级恢复"""
        rospy.loginfo("执行打印机级恢复...")
        
        try:
            if self.maintain_temp_on_pause:
                tool_temp = self.print_state.temperatures.get('tool', 0)
                bed_temp = self.print_state.temperatures.get('bed', 0)
                
                if tool_temp > 0:
                    rospy.loginfo(f"恢复热端温度: {tool_temp}°C")
                    self.send_and_wait(f"M109 S{tool_temp}", wait_time=0.5)
                
                if bed_temp > 0:
                    rospy.loginfo(f"恢复热床温度: {bed_temp}°C")
                    self.send_and_wait(f"M190 S{bed_temp}", wait_time=0.5)
            
            if self.pause_retract > 0:
                rospy.loginfo(f"恢复耗材位置 +{self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            if self.pause_lift_z > 0:
                rospy.loginfo(f"降低喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z-{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps({"command": "pause", "action": "resume"}),
                timeout=5
            )
            
            if response.status_code == 204:
                rospy.loginfo("✓ OctoPrint恢复命令已发送")
            
            time.sleep(0.5)
            return True
            
        except Exception as e:
            rospy.logerr(f"执行打印机恢复失败: {e}")
            return False
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            state_text = status.get('state', {}).get('text', '').lower()
            
            if 'halt' in state_text or 'kill' in state_text:
                rospy.logerr(f"检测到紧急停止状态: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
            self.last_printer_state = state_text
            return status
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            rospy.logerr(f"获取打印机状态失败: {e}")
            return {}
    
    def check_temperatures_safe(self) -> dict:
        """安全的温度检查"""
        try:
            status = self.check_printer_status()
            temps = status.get('temperature', {})
            return {
                'tool0': temps.get('tool0', {}),
                'bed': temps.get('bed', {}),
            }
        except Exception as e:
            rospy.logerr(f"温度检查失败: {e}")
            return {}
    
    def load_gcode_file(self, file_path: str) -> bool:
        """加载G-code文件到内存"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self.gcode_lines = [line.strip() for line in file]
                self.total_lines = len(self.gcode_lines)
                rospy.loginfo(f"✓ 文件加载完成: {self.total_lines} 行")
                return True
        except Exception as e:
            rospy.logerr(f"加载文件失败: {e}")
            return False
    
    def sender_worker(self, file_path: str):
        """发送器工作线程"""
        rospy.loginfo(f"开始处理文件: {file_path}")
        
        if not self.load_gcode_file(file_path):
            self.state = PrinterState.ERROR
            return
        
        self.file_path = file_path
        self.current_line_index = 0
        self.processed_lines = 0
        self.error_count = 0
        self.state = PrinterState.RUNNING
        
        try:
            while self.current_line_index < self.total_lines and not self.stop_event.is_set() and not rospy.is_shutdown():
                self.pause_event.wait()
                
                if self.stop_event.is_set() or rospy.is_shutdown():
                    break
                
                line = self.gcode_lines[self.current_line_index]
                
                if not line or line.startswith(';'):
                    self.current_line_index += 1
                    continue
                
                success = self.send_and_wait(line, wait_time=0.1)
                
                if not success:
                    rospy.logerr(f"发送失败，停止于第 {self.current_line_index} 行")
                    self.state = PrinterState.ERROR
                    break
                
                self.current_line_index += 1
                self.processed_lines += 1
                
                if self.processed_lines % 100 == 0:
                    progress = (self.current_line_index / self.total_lines) * 100
                    rospy.loginfo(f"进度: {self.current_line_index}/{self.total_lines} ({progress:.1f}%)")
            
            if self.stop_event.is_set():
                rospy.loginfo(f"打印已停止: {self.current_line_index}/{self.total_lines}")
            elif self.state == PrinterState.ERROR:
                rospy.logerr(f"打印出错: {self.current_line_index}/{self.total_lines}")
            else:
                self.state = PrinterState.IDLE
                rospy.loginfo(f"打印完成: {self.processed_lines} 条指令已执行")
                
        except Exception as e:
            rospy.logerr(f"发送过程异常: {e}")
            self.state = PrinterState.ERROR
    
    # ROS服务处理器
    def handle_start_print(self, req):
        """处理开始打印服务请求"""
        with self.lock:
            if self.sender_thread and self.sender_thread.is_alive():
                return StartPrintResponse(success=False, message="已有任务在运行中")
            
            self.stop_event.clear()
            self.pause_event.set()
            self.error_count = 0
            
            self.sender_thread = threading.Thread(
                target=self.sender_worker,
                args=(req.file_path,),
                daemon=True
            )
            self.sender_thread.start()
            
            return StartPrintResponse(success=True, message=f"开始打印: {req.file_path}")
    
    def handle_pause_print(self, req):
        """处理暂停打印服务请求"""
        with self.lock:
            if self.state != PrinterState.RUNNING:
                return PausePrintResponse(success=False, message=f"当前状态 {self.state.value} 无法暂停")
            
            rospy.loginfo("暂停请求...")
            self.state = PrinterState.PAUSING
            self.pause_event.clear()
            time.sleep(0.2)
            
            if self.execute_printer_pause():
                self.state = PrinterState.PAUSED
                self.print_state.line_number = self.current_line_index
                return PausePrintResponse(success=True, message="暂停成功")
            else:
                self.state = PrinterState.ERROR
                return PausePrintResponse(success=False, message="暂停失败")
    
    def handle_resume_print(self, req):
        """处理恢复打印服务请求"""
        with self.lock:
            if self.state != PrinterState.PAUSED:
                return ResumePrintResponse(success=False, message=f"当前状态 {self.state.value} 无法恢复")
            
            rospy.loginfo("恢复请求...")
            self.state = PrinterState.RESUMING
            
            if self.execute_printer_resume():
                self.pause_event.set()
                self.state = PrinterState.RUNNING
                return ResumePrintResponse(success=True, message="恢复成功")
            else:
                self.state = PrinterState.ERROR
                return ResumePrintResponse(success=False, message="恢复失败")
    
    def handle_stop_print(self, req):
        """处理停止打印服务请求"""
        with self.lock:
            rospy.loginfo("停止请求...")
            self.stop_event.set()
            self.pause_event.set()
            self.state = PrinterState.STOPPED
            
            try:
                self.session.post(
                    f'{self.octoprint_url}/api/job',
                    data=json.dumps({"command": "cancel"}),
                    timeout=5
                )
            except:
                pass
            
            return StopPrintResponse(success=True, message="停止成功")
    
    def handle_set_speed(self, req):
        """处理设置速度服务请求"""
        self.speed_multiplier = max(0.1, min(2.0, req.multiplier))
        rospy.loginfo(f"速度倍率设置为: {self.speed_multiplier}x")
        return SetSpeedResponse(success=True, actual_multiplier=self.speed_multiplier)
    
    def handle_get_status(self, req):
        """处理获取状态服务请求"""
        progress_percent = 0
        if self.total_lines > 0:
            progress_percent = (self.current_line_index / self.total_lines) * 100
        
        return GetStatusResponse(
            state=self.state.value,
            current_line=self.current_line_index,
            total_lines=self.total_lines,
            progress_percent=progress_percent,
            file_path=self.file_path
        )
    
    def publish_status_callback(self, event):
        """定时发布状态信息"""
        # 发布状态
        self.state_pub.publish(String(data=self.state.value))
        
        # 发布进度
        if self.total_lines > 0:
            progress = PrintProgress()
            progress.current_line = self.current_line_index
            progress.total_lines = self.total_lines
            progress.progress_percent = (self.current_line_index / self.total_lines) * 100
            progress.processed_commands = self.processed_lines
            progress.file_path = self.file_path
            self.progress_pub.publish(progress)
        
        # 发布温度
        temps = self.check_temperatures_safe()
        if temps:
            temp_msg = TemperatureInfo()
            tool_data = temps.get('tool0', {})
            bed_data = temps.get('bed', {})
            
            temp_msg.tool_actual = tool_data.get('actual', 0.0)
            temp_msg.tool_target = tool_data.get('target', 0.0)
            temp_msg.bed_actual = bed_data.get('actual', 0.0)
            temp_msg.bed_target = bed_data.get('target', 0.0)
            
            self.temp_pub.publish(temp_msg)
    
    def run(self):
        """运行节点"""
        rospy.spin()
    
    def shutdown(self):
        """关闭节点"""
        rospy.loginfo("正在关闭G-code Sender节点...")
        self.stop_event.set()
        self.pause_event.set()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=5)
        
        if self.status_timer:
            self.status_timer.shutdown()
        
        self.session.close()


if __name__ == '__main__':
    try:
        node = GCodeSenderNode()
        rospy.on_shutdown(node.shutdown)
        node.run()
    except rospy.ROSInterruptException:
        pass
    except Exception as e:
        rospy.logerr(f"节点启动失败: {e}")