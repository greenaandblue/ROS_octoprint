#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROS Node for Enhanced G-code Sender for OctoPrint
增加了M112错误检测和防护机制的ROS节点版本
"""

import rospy  # type: ignore 
from std_msgs.msg import String, Bool, Float32 # type: ignore
from std_srvs.srv import Trigger, TriggerResponse # type: ignore
from gcode_sender_msgs.msg import PrinterStatus, Progress, TemperatureInfo # type: ignore
from gcode_sender_msgs.srv import SendCommand, SendCommandResponse # type: ignore
from gcode_sender_msgs.srv import StartPrint, StartPrintResponse # type: ignore

import requests
import time
import threading
import queue 
import json
import os
from collections import deque
from enum import Enum
from typing import List, Optional, Generator
import re


class PrinterState(Enum):
    """打印机状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    HALTED = "halted"


class GCodeSenderNode:
    """ROS节点版本的G-code发送器"""
    
    def __init__(self):
        """初始化ROS节点"""
        rospy.init_node('gcode_sender_node', anonymous=False)
        
        # 获取ROS参数
        self.octoprint_url = rospy.get_param('~octoprint_url', 'http://192.168.1.100')
        self.api_key = rospy.get_param('~api_key', 'YOUR_API_KEY_HERE')
        self.buffer_size = rospy.get_param('~buffer_size', 20)
        self.publish_rate = rospy.get_param('~publish_rate', 1.0)  # Hz
        
        rospy.loginfo(f"OctoPrint URL: {self.octoprint_url}")
        rospy.loginfo(f"缓冲区大小: {self.buffer_size}")
        
        # 初始化G-code发送器核心
        self.octoprint_url = self.octoprint_url.rstrip('/')
        self.buffer_size = self.buffer_size
        
        # 状态控制
        self.state = PrinterState.IDLE
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event.set()
        
        # 文件和进度控制
        self.gcode_buffer = deque()
        self.current_line = 0
        self.total_lines = 0
        self.file_path = ""
        self.processed_lines = 0
        
        # 线程控制
        self.sender_thread = None
        self.monitor_thread = None
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 错误监控
        self.last_temp_check = 0
        self.temp_check_interval = 2.0
        self.error_count = 0
        self.max_errors = 5
        
        # 安全模式
        self.safe_mode = True
        self.dangerous_patterns = [
            r'^M109\s+S0$',
            r'^M190\s+S0$',
            r'^M84$',
            r'^M18$',
            r'^M112$',
        ]
        
        self.careful_patterns = [
            r'^T\d+$',
            r'^G28',
            r'^M104',
            r'^M109',
            r'^M140',
            r'^M190',
        ]
        
        self.has_active_job = False
        self.last_printer_state = ""
        
        # 初始化ROS Publishers
        self.status_pub = rospy.Publisher('~printer_status', PrinterStatus, queue_size=10)
        self.progress_pub = rospy.Publisher('~progress', Progress, queue_size=10)
        self.temp_pub = rospy.Publisher('~temperature', TemperatureInfo, queue_size=10)
        self.state_pub = rospy.Publisher('~state', String, queue_size=10)
        
        # 初始化ROS Services
        self.start_print_srv = rospy.Service('~start_print', StartPrint, self.handle_start_print)
        self.pause_srv = rospy.Service('~pause', Trigger, self.handle_pause)
        self.resume_srv = rospy.Service('~resume', Trigger, self.handle_resume)
        self.stop_srv = rospy.Service('~stop', Trigger, self.handle_stop)
        self.reset_srv = rospy.Service('~emergency_reset', Trigger, self.handle_emergency_reset)
        self.send_cmd_srv = rospy.Service('~send_command', SendCommand, self.handle_send_command)
        self.diagnose_srv = rospy.Service('~diagnose', Trigger, self.handle_diagnose)
        
        # 初始化ROS Subscribers
        self.gcode_sub = rospy.Subscriber('~gcode_command', String, self.gcode_callback)
        
        # 启动状态发布定时器
        self.status_timer = rospy.Timer(rospy.Duration(1.0 / self.publish_rate), self.publish_status)
        
        rospy.loginfo("G-code Sender ROS节点初始化完成")
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查指令是否危险"""
        command = command.strip().upper()
        for pattern in self.dangerous_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def is_careful_command(self, command: str) -> bool:
        """检查指令是否需要谨慎处理"""
        command = command.strip().upper()
        for pattern in self.careful_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            state_text = status.get('state', {}).get('text', '').lower()
            if 'halt' in state_text or 'kill' in state_text or 'emergency' in state_text:
                rospy.logerr(f"检测到打印机紧急停止状态: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
            self.last_printer_state = state_text
            return status
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            rospy.logerr(f"获取打印机状态失败 ({self.error_count}/{self.max_errors}): {e}")
            
            if self.error_count >= self.max_errors:
                rospy.logerr("连续错误过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return {}
    
    def check_temperatures_safe(self) -> dict:
        """安全的温度检查"""
        try:
            current_time = time.time()
            if current_time - self.last_temp_check < self.temp_check_interval:
                return {}
            
            self.last_temp_check = current_time
            status = self.check_printer_status()
            temps = status.get('temperature', {})
            
            tool_temp = temps.get('tool0', {})
            bed_temp = temps.get('bed', {})
            
            tool_actual = tool_temp.get('actual', 0)
            tool_target = tool_temp.get('target', 0)
            bed_actual = bed_temp.get('actual', 0)
            bed_target = bed_temp.get('target', 0)
            
            if tool_target > 0 and tool_actual > 0:
                temp_diff = abs(tool_actual - tool_target)
                if temp_diff > 15:
                    rospy.logwarn(f"热端温度异常: 实际={tool_actual}°C, 目标={tool_target}°C, 差值={temp_diff}°C")
            
            if bed_target > 0 and bed_actual > 0:
                temp_diff = abs(bed_actual - bed_target)
                if temp_diff > 10:
                    rospy.logwarn(f"热床温度异常: 实际={bed_actual}°C, 目标={bed_target}°C, 差值={temp_diff}°C")
            
            return {
                'tool0': tool_temp,
                'bed': bed_temp,
            }
        except Exception as e:
            rospy.logerr(f"温度检查失败: {e}")
            return {}
    
    def send_single_command(self, command: str, skip_dangerous: bool = True) -> bool:
        """发送单条指令"""
        command = command.strip()
        if not command:
            return True
        
        if self.state == PrinterState.HALTED:
            rospy.logerr("打印机处于紧急停止状态，拒绝发送指令")
            return False
        
        if skip_dangerous and self.is_dangerous_command(command):
            rospy.logwarn(f"跳过危险指令: {command}")
            return True
        
        if self.is_careful_command(command):
            rospy.loginfo(f"发送谨慎指令: {command}")
        
        try:
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=10
            )
            response.raise_for_status()
            
            self.error_count = 0
            rospy.logdebug(f"指令发送成功: {command}")
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            rospy.logerr(f"指令发送失败 '{command}': {e} ({self.error_count}/{self.max_errors})")
            
            if self.error_count >= self.max_errors:
                rospy.logerr("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def send_batch_commands(self, commands: List[str], skip_dangerous: bool = True) -> bool:
        """批量发送指令"""
        if not commands:
            return True
        
        if self.state == PrinterState.HALTED:
            rospy.logerr("打印机处于紧急停止状态，停止发送")
            return False
        
        try:
            valid_commands = []
            for cmd in commands:
                cmd = cmd.strip()
                if not cmd or cmd.startswith(';'):
                    continue
                
                if skip_dangerous and self.is_dangerous_command(cmd):
                    rospy.logdebug(f"跳过危险指令: {cmd}")
                    continue
                
                valid_commands.append(cmd)
            
            if not valid_commands:
                return True
            
            batch_size = 2
            for i in range(0, len(valid_commands), batch_size):
                if self.stop_event.is_set() or self.state == PrinterState.HALTED:
                    rospy.logwarn("检测到停止信号，中断发送")
                    break
                
                batch = valid_commands[i:i+batch_size]
                data = {"commands": batch}
                response = self.session.post(
                    f'{self.octoprint_url}/api/printer/command',
                    data=json.dumps(data),
                    timeout=10
                )
                response.raise_for_status()
                rospy.logdebug(f"✓ 批量发送 {len(batch)} 条指令成功")
                time.sleep(0.1)
            
            self.error_count = 0
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            rospy.logerr(f"批量发送失败: {e} ({self.error_count}/{self.max_errors})")
            
            if self.error_count >= self.max_errors:
                rospy.logerr("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def load_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """加载G-code文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    yield line.strip()
        except Exception as e:
            rospy.logerr(f"读取文件失败: {e}")
    
    def count_gcode_lines(self, file_path: str) -> int:
        """计算文件行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return sum(1 for _ in file)
        except Exception as e:
            rospy.logerr(f"计算文件行数失败: {e}")
            return 0
    
    def fill_buffer(self, gcode_generator: Generator[str, None, None]) -> bool:
        """填充缓冲区"""
        added_lines = 0
        try:
            while added_lines < self.buffer_size and len(self.gcode_buffer) < self.buffer_size:
                line = next(gcode_generator)
                self.current_line += 1
                
                if line and not line.startswith(';'):
                    self.gcode_buffer.append(line)
                    added_lines += 1
            return True
        except StopIteration:
            rospy.loginfo(f"文件读取完毕，总共读取 {self.current_line} 行")
            return False
    
    def sender_worker(self, file_path: str):
        """发送器工作线程"""
        rospy.loginfo(f"开始处理文件: {file_path}")
        
        if not os.path.exists(file_path):
            rospy.logerr(f"文件不存在: {file_path}")
            self.state = PrinterState.ERROR
            return
        
        self.file_path = file_path
        self.total_lines = self.count_gcode_lines(file_path)
        self.current_line = 0
        self.processed_lines = 0
        self.error_count = 0
        self.state = PrinterState.RUNNING
        
        rospy.loginfo(f"文件总行数: {self.total_lines}")
        
        gcode_generator = self.load_gcode_file(file_path)
        has_more_data = self.fill_buffer(gcode_generator)
        batch_commands = []
        
        try:
            while (self.gcode_buffer or has_more_data) and not self.stop_event.is_set() and not rospy.is_shutdown():
                if self.state == PrinterState.HALTED:
                    rospy.logerr("检测到紧急停止，中断发送")
                    break
                
                self.pause_event.wait()
                
                if self.stop_event.is_set() or rospy.is_shutdown():
                    break
                
                if self.gcode_buffer:
                    command = self.gcode_buffer.popleft()
                    batch_commands.append(command)
                    self.processed_lines += 1
                    
                    if len(batch_commands) >= 2 or (not self.gcode_buffer and batch_commands):
                        self.send_batch_commands(batch_commands, skip_dangerous=True)
                        batch_commands.clear()
                        
                        if self.processed_lines % 200 == 0:
                            progress = (self.current_line / self.total_lines) * 100
                            rospy.loginfo(f"进度: {self.current_line}/{self.total_lines} ({progress:.1f}%)")
                
                if len(self.gcode_buffer) < self.buffer_size // 2 and has_more_data:
                    has_more_data = self.fill_buffer(gcode_generator)
                
                time.sleep(0.05)
            
            if batch_commands and not self.stop_event.is_set() and self.state != PrinterState.HALTED:
                self.send_batch_commands(batch_commands, skip_dangerous=True)
            
            if self.state == PrinterState.HALTED:
                rospy.logerr("文件处理因紧急停止而中断")
            elif self.stop_event.is_set():
                rospy.loginfo(f"处理已停止: {self.processed_lines} 条指令已处理")
            else:
                self.state = PrinterState.IDLE
                rospy.loginfo(f"文件处理完成: {self.processed_lines} 条指令已处理")
                
        except Exception as e:
            rospy.logerr(f"发送过程中出错: {e}")
            self.state = PrinterState.ERROR
    
    def emergency_reset(self) -> bool:
        """紧急复位"""
        rospy.loginfo("尝试紧急复位...")
        
        try:
            response = self.session.post(
                f'{self.octoprint_url}/api/connection',
                data=json.dumps({"command": "disconnect"}),
                timeout=5
            )
            
            time.sleep(2)
            
            response = self.session.post(
                f'{self.octoprint_url}/api/connection',
                data=json.dumps({"command": "connect"}),
                timeout=10
            )
            
            if response.status_code == 204:
                rospy.loginfo("紧急复位成功")
                self.state = PrinterState.IDLE
                self.error_count = 0
                return True
            else:
                rospy.logerr("紧急复位失败")
                return False
                
        except Exception as e:
            rospy.logerr(f"紧急复位过程出错: {e}")
            return False
    
    # ROS Service Handlers
    def handle_start_print(self, req):
        """处理开始打印服务请求"""
        response = StartPrintResponse()
        
        if self.sender_thread and self.sender_thread.is_alive():
            response.success = False
            response.message = "已有任务在运行中"
            return response
        
        self.stop_event.clear()
        self.pause_event.set()
        self.gcode_buffer.clear()
        self.error_count = 0
        
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(req.file_path,),
            daemon=True
        )
        self.sender_thread.start()
        
        response.success = True
        response.message = f"开始打印文件: {req.file_path}"
        rospy.loginfo(response.message)
        return response
    
    def handle_pause(self, req):
        """处理暂停服务请求"""
        response = TriggerResponse()
        
        if self.state == PrinterState.RUNNING:
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            response.success = True
            response.message = "暂停成功"
            rospy.loginfo("打印已暂停")
        else:
            response.success = False
            response.message = f"无法暂停，当前状态: {self.state.value}"
        
        return response
    
    def handle_resume(self, req):
        """处理恢复服务请求"""
        response = TriggerResponse()
        
        if self.state == PrinterState.PAUSED:
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            response.success = True
            response.message = "恢复成功"
            rospy.loginfo("打印已恢复")
        else:
            response.success = False
            response.message = f"无法恢复，当前状态: {self.state.value}"
        
        return response
    
    def handle_stop(self, req):
        """处理停止服务请求"""
        response = TriggerResponse()
        
        self.stop_event.set()
        self.pause_event.set()
        self.state = PrinterState.STOPPED
        
        response.success = True
        response.message = "停止成功"
        rospy.loginfo("打印已停止")
        
        return response
    
    def handle_emergency_reset(self, req):
        """处理紧急复位服务请求"""
        response = TriggerResponse()
        
        success = self.emergency_reset()
        response.success = success
        response.message = "紧急复位成功" if success else "紧急复位失败"
        
        return response
    
    def handle_send_command(self, req):
        """处理发送命令服务请求"""
        response = SendCommandResponse()
        
        success = self.send_single_command(req.command, skip_dangerous=not req.force)
        response.success = success
        response.message = "命令发送成功" if success else "命令发送失败"
        
        return response
    
    def handle_diagnose(self, req):
        """处理诊断服务请求"""
        response = TriggerResponse()
        
        rospy.loginfo("=== 系统诊断 ===")
        
        printer_status = self.check_printer_status()
        temps = self.check_temperatures_safe()
        progress = self.get_progress()
        
        diag_msg = f"""
打印机状态: {self.last_printer_state}
当前状态: {self.state.value}
错误计数: {self.error_count}/{self.max_errors}
进度: {progress['current_line']}/{progress['total_lines']} ({progress['progress_percent']}%)
        """
        
        response.success = True
        response.message = diag_msg.strip()
        rospy.loginfo(diag_msg)
        
        return response
    
    def gcode_callback(self, msg):
        """处理G-code命令话题"""
        command = msg.data
        success = self.send_single_command(command)
        if not success:
            rospy.logwarn(f"从话题接收的命令发送失败: {command}")
    
    def publish_status(self, event):
        """定时发布状态信息"""
        # 发布状态
        status_msg = PrinterStatus()
        status_msg.state = self.state.value
        status_msg.printer_state = self.last_printer_state
        status_msg.error_count = self.error_count
        status_msg.safe_mode = self.safe_mode
        self.status_pub.publish(status_msg)
        
        # 发布进度
        progress = self.get_progress()
        progress_msg = Progress()
        progress_msg.current_line = progress['current_line']
        progress_msg.total_lines = progress['total_lines']
        progress_msg.processed_commands = progress['processed_commands']
        progress_msg.progress_percent = progress['progress_percent']
        progress_msg.file_path = progress['file_path']
        progress_msg.buffer_size = progress['buffer_size']
        self.progress_pub.publish(progress_msg)
        
        # 发布温度
        temps = self.check_temperatures_safe()
        if temps:
            temp_msg = TemperatureInfo()
            temp_msg.tool_actual = temps['tool0'].get('actual', 0.0)
            temp_msg.tool_target = temps['tool0'].get('target', 0.0)
            temp_msg.bed_actual = temps['bed'].get('actual', 0.0)
            temp_msg.bed_target = temps['bed'].get('target', 0.0)
            self.temp_pub.publish(temp_msg)
        
        # 发布状态字符串
        state_msg = String()
        state_msg.data = self.state.value
        self.state_pub.publish(state_msg)
    
    def get_progress(self) -> dict:
        """获取进度信息"""
        progress_percent = 0
        if self.total_lines > 0:
            progress_percent = (self.current_line / self.total_lines) * 100
        
        return {
            'state': self.state.value,
            'current_line': self.current_line,
            'total_lines': self.total_lines,
            'processed_commands': self.processed_lines,
            'progress_percent': round(progress_percent, 1),
            'file_path': self.file_path,
            'buffer_size': len(self.gcode_buffer),
            'error_count': self.error_count,
            'printer_state': self.last_printer_state
        }
    
    def shutdown(self):
        """清理资源"""
        rospy.loginfo("正在关闭G-code Sender节点...")
        
        self.stop_event.set()
        self.pause_event.set()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        
        self.session.close()
        rospy.loginfo("G-code Sender节点已关闭")
    
    def run(self):
        """运行节点"""
        rospy.loginfo("G-code Sender节点正在运行...")
        rospy.spin()


if __name__ == "__main__":
    try:
        node = GCodeSenderNode()
        rospy.on_shutdown(node.shutdown)
        node.run()
    except rospy.ROSInterruptException:
        pass