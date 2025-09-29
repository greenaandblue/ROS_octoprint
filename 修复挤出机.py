#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进的G-code Sender - 修复挤出和T指令问题
"""

import requests
import time
import threading
import queue
import json
import os
from collections import deque
from enum import Enum
from typing import List, Optional, Generator
import logging 
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PrinterState(Enum):
    """打印机状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    HALTED = "halted"


class GCodeSender:
    """改进的G-code发送器 - 修复挤出问题"""
    
    def __init__(self, octoprint_url: str, api_key: str, buffer_size: int = 15):
        """初始化G-code发送器"""
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        self.buffer_size = buffer_size
        
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
        self.temp_check_interval = 3.0
        self.error_count = 0
        self.max_errors = 5
        
        # 挤出机状态跟踪
        self.extruder_temp = 0
        self.extruder_target = 0
        self.extruder_ready = False
        self.bed_temp = 0
        self.bed_target = 0
        self.bed_ready = False
        
        # 当前活动工具
        self.active_tool = 0
        self.available_tools = [0]  # Prusa通常是单挤出机
        
        # 指令过滤和处理
        self.dangerous_patterns = [
            r'^M112\s*$',         # 绝对禁止M112
            r'^M84\s*$',          # 关闭所有电机
            r'^M18\s*$',          # 关闭所有电机
        ]
        
        # 需要特殊处理的指令
        self.temperature_commands = [r'^M104', r'^M109', r'^M140', r'^M190']
        self.tool_change_commands = [r'^T\d+']
        self.extrusion_commands = [r'E-?\d+\.?\d*']
        
        self.last_printer_state = ""
        self.heating_phase = False
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查是否是危险指令"""
        command = command.strip().upper()
        for pattern in self.dangerous_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def is_temperature_command(self, command: str) -> bool:
        """检查是否是温度设置指令"""
        command = command.strip().upper()
        for pattern in self.temperature_commands:
            if re.match(pattern, command):
                return True
        return False
    
    def is_tool_change_command(self, command: str) -> bool:
        """检查是否是工具切换指令"""
        command = command.strip().upper()
        for pattern in self.tool_change_commands:
            if re.match(pattern, command):
                return True
        return False
    
    def has_extrusion(self, command: str) -> bool:
        """检查指令是否包含挤出动作"""
        command = command.strip().upper()
        # 检查是否有E参数
        return bool(re.search(r'\bE-?\d+\.?\d*', command))
    
    def parse_tool_number(self, command: str) -> Optional[int]:
        """从T指令中解析工具号"""
        match = re.match(r'^T(\d+)', command.strip().upper())
        if match:
            return int(match.group(1))
        return None
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            # 检查halt状态
            state_text = status.get('state', {}).get('text', '').lower()
            if 'halt' in state_text or 'kill' in state_text or 'emergency' in state_text:
                logger.error(f"检测到打印机紧急停止状态: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
            # 更新温度信息
            temps = status.get('temperature', {})
            if 'tool0' in temps:
                self.extruder_temp = temps['tool0'].get('actual', 0)
                self.extruder_target = temps['tool0'].get('target', 0)
                # 认为温度在目标±2度范围内就算ready
                self.extruder_ready = (
                    self.extruder_target > 0 and 
                    abs(self.extruder_temp - self.extruder_target) < 3
                )
            
            if 'bed' in temps:
                self.bed_temp = temps['bed'].get('actual', 0)
                self.bed_target = temps['bed'].get('target', 0)
                self.bed_ready = (
                    self.bed_target > 0 and 
                    abs(self.bed_temp - self.bed_target) < 5
                )
            
            self.last_printer_state = state_text
            return status
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"获取打印机状态失败 ({self.error_count}/{self.max_errors}): {e}")
            
            if self.error_count >= self.max_errors:
                logger.error("连续错误过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return {}
    
    def wait_for_temperature(self, target_temp: float, is_bed: bool = False, timeout: float = 300):
        """等待温度达到目标"""
        temp_type = "热床" if is_bed else "热端"
        logger.info(f"等待{temp_type}加热到 {target_temp}°C...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.stop_event.is_set():
                logger.warning("加热过程被中断")
                return False
            
            status = self.check_printer_status()
            temps = status.get('temperature', {})
            
            if is_bed:
                current = temps.get('bed', {}).get('actual', 0)
            else:
                current = temps.get('tool0', {}).get('actual', 0)
            
            diff = abs(current - target_temp)
            
            if diff < 3:  # 温度在±3度范围内
                logger.info(f"✓ {temp_type}已达到目标温度: {current}°C")
                return True
            
            # 每5秒报告一次进度
            if int(time.time() - start_time) % 5 == 0:
                logger.info(f"{temp_type}当前: {current}°C / 目标: {target_temp}°C (差值: {diff:.1f}°C)")
            
            time.sleep(1)
        
        logger.error(f"{temp_type}加热超时")
        return False
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        
        error_keywords = ['halt', 'kill', 'emergency', 'error']
        if any(keyword in state for keyword in error_keywords):
            logger.error(f"打印机处于错误状态: {state}")
            return False
        
        ready_states = ['operational', 'ready']
        return any(ready_state in state for ready_state in ready_states)
    
    def send_single_command(self, command: str, wait_for_ok: bool = False) -> bool:
        """发送单条指令"""
        command = command.strip()
        if not command or command.startswith(';'):
            return True
        
        # 检查打印机状态
        if self.state == PrinterState.HALTED:
            logger.error("打印机处于紧急停止状态，拒绝发送指令")
            return False
        
        # 危险指令检查
        if self.is_dangerous_command(command):
            logger.error(f"拒绝发送危险指令: {command}")
            return False
        
        # 工具切换指令特殊处理
        if self.is_tool_change_command(command):
            tool_num = self.parse_tool_number(command)
            if tool_num is not None and tool_num not in self.available_tools:
                logger.warning(f"跳过不支持的工具切换: {command} (可用工具: {self.available_tools})")
                return True
            else:
                logger.info(f"工具切换指令: {command}")
                # 对于单挤出机Prusa，T0通常可以忽略
                if tool_num == 0:
                    logger.debug("单挤出机打印机，跳过T0指令")
                    self.active_tool = 0
                    return True
        
        # 挤出指令检查 - 确保温度足够
        if self.has_extrusion(command):
            if not self.extruder_ready:
                logger.warning(f"挤出机未达到工作温度 (当前: {self.extruder_temp}°C, 目标: {self.extruder_target}°C)")
                # 等待一小段时间
                time.sleep(0.5)
                self.check_printer_status()
                if not self.extruder_ready:
                    logger.error(f"跳过挤出指令 (温度不足): {command}")
                    return False
        
        try:
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=10
            )
            response.raise_for_status()
            
            # 重置错误计数
            self.error_count = 0
            logger.debug(f"✓ 发送: {command}")
            
            # 温度指令需要等待
            if self.is_temperature_command(command) and wait_for_ok:
                time.sleep(0.5)
            
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"指令发送失败 '{command}': {e}")
            
            if self.error_count >= self.max_errors:
                logger.error("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def send_commands_sequential(self, commands: List[str]) -> bool:
        """顺序发送指令 - 用于关键指令"""
        for cmd in commands:
            if self.stop_event.is_set() or self.state == PrinterState.HALTED:
                return False
            
            if not self.send_single_command(cmd, wait_for_ok=True):
                return False
            
            time.sleep(0.05)  # 小延迟确保处理
        
        return True
    
    def preprocess_gcode_line(self, line: str) -> Optional[str]:
        """预处理G-code行"""
        line = line.strip()
        
        # 移除注释
        if ';' in line:
            line = line.split(';')[0].strip()
        
        if not line:
            return None
        
        # 过滤危险指令
        if self.is_dangerous_command(line):
            logger.warning(f"过滤危险指令: {line}")
            return None
        
        return line
    
    def printer_monitor_worker(self):
        """打印机状态监控线程"""
        logger.info("启动打印机状态监控")
        
        while not self.stop_event.is_set():
            try:
                self.check_printer_status()
                
                # 加热阶段更频繁检查
                if self.heating_phase:
                    time.sleep(1)
                else:
                    time.sleep(3)
                
            except Exception as e:
                logger.error(f"监控线程错误: {e}")
                time.sleep(2)
        
        logger.info("打印机状态监控已停止")
    
    def load_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """加载G-code文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    processed = self.preprocess_gcode_line(line)
                    if processed:
                        yield processed
        except FileNotFoundError:
            logger.error(f"文件未找到: {file_path}")
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
    
    def count_gcode_lines(self, file_path: str) -> int:
        """计算有效G-code行数"""
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    if self.preprocess_gcode_line(line):
                        count += 1
        except Exception as e:
            logger.error(f"计算文件行数失败: {e}")
        return count
    
    def sender_worker(self, file_path: str):
        """发送器工作线程"""
        logger.info(f"🚀 开始处理文件: {file_path}")
        
        # 检查文件
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            self.state = PrinterState.ERROR
            return
        
        # 检查打印机状态
        if not self.is_printer_ready():
            logger.error("打印机未就绪")
            self.state = PrinterState.ERROR
            return
        
        # 初始化
        self.file_path = file_path
        self.total_lines = self.count_gcode_lines(file_path)
        self.current_line = 0
        self.processed_lines = 0
        self.error_count = 0
        self.state = PrinterState.RUNNING
        
        logger.info(f"文件有效行数: {self.total_lines}")
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.printer_monitor_worker, daemon=True)
        self.monitor_thread.start()
        
        gcode_generator = self.load_gcode_file(file_path)
        
        # 初始化设置
        logger.info("发送初始化指令...")
        init_commands = [
            "M83",  # 设置挤出机为相对模式
            "G90",  # 设置坐标为绝对模式
        ]
        if not self.send_commands_sequential(init_commands):
            logger.error("初始化失败")
            self.state = PrinterState.ERROR
            return
        
        consecutive_errors = 0
        is_heating = False
        
        try:
            for command in gcode_generator:
                if self.stop_event.is_set() or self.state == PrinterState.HALTED:
                    break
                
                self.pause_event.wait()
                self.current_line += 1
                
                # 温度指令特殊处理
                if self.is_temperature_command(command):
                    is_heating = True
                    self.heating_phase = True
                    logger.info(f"温度设置指令: {command}")
                    
                    # 发送温度指令
                    if not self.send_single_command(command, wait_for_ok=True):
                        consecutive_errors += 1
                        continue
                    
                    # 如果是M109或M190（等待加热），等待温度
                    if command.startswith('M109') or command.startswith('M190'):
                        # 解析目标温度
                        temp_match = re.search(r'S(\d+)', command)
                        if temp_match:
                            target_temp = float(temp_match.group(1))
                            is_bed = command.startswith('M190')
                            self.wait_for_temperature(target_temp, is_bed)
                        
                        is_heating = False
                        self.heating_phase = False
                    
                    consecutive_errors = 0
                    self.processed_lines += 1
                    continue
                
                # 普通指令发送
                success = self.send_single_command(command)
                
                if success:
                    consecutive_errors = 0
                    self.processed_lines += 1
                else:
                    consecutive_errors += 1
                    logger.error(f"发送失败 (连续错误: {consecutive_errors})")
                    
                    if consecutive_errors >= 3:
                        logger.error("连续发送失败，停止执行")
                        self.state = PrinterState.ERROR
                        break
                
                # 进度报告
                if self.processed_lines % 100 == 0:
                    progress = (self.current_line / self.total_lines) * 100
                    logger.info(f"进度: {self.current_line}/{self.total_lines} ({progress:.1f}%) "
                              f"[挤出机: {self.extruder_temp:.1f}°C]")
                
                # 动态延迟
                if is_heating:
                    time.sleep(0.1)
                else:
                    time.sleep(0.02)
            
            # 完成
            if self.state == PrinterState.HALTED:
                logger.error("处理因紧急停止而中断")
            elif self.stop_event.is_set():
                logger.info(f"处理已停止")
            else:
                self.state = PrinterState.IDLE
                logger.info(f"文件处理完成: {self.processed_lines} 条指令")
                
        except Exception as e:
            logger.error(f"发送过程中出错: {e}")
            import traceback
            traceback.print_exc()
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str):
        """开始文件打印"""
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("已有任务在运行中")
            return False
        
        # 重置状态
        self.stop_event.clear()
        self.pause_event.set()
        self.error_count = 0
        
        # 启动发送线程
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        return True
    
    def pause(self):
        """暂停"""
        if self.state == PrinterState.RUNNING:
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            logger.info("暂停")
    
    def resume(self):
        """恢复"""
        if self.state == PrinterState.PAUSED:
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            logger.info("恢复")
    
    def stop(self):
        """停止"""
        self.stop_event.set()
        self.pause_event.set()
        self.state = PrinterState.STOPPED
        logger.info("停止")
    
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
            'extruder_temp': round(self.extruder_temp, 1),
            'extruder_target': round(self.extruder_target, 1),
            'extruder_ready': self.extruder_ready,
            'bed_temp': round(self.bed_temp, 1),
            'bed_target': round(self.bed_target, 1),
            'printer_state': self.last_printer_state
        }
    
    def close(self):
        """清理资源"""
        logger.info("正在清理资源...")
        self.stop()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.session.close()


def main():
    """主函数 - 示例使用"""
    OCTOPRINT_URL = "http://octopi.local"  
    API_KEY = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("=== 改进的G-code Sender - 挤出问题修复版 ===")
    print("\n主要改进:")
    print("正确处理T指令 单挤出机跳过T0")
    print("挤出前检查温度是否达标")
    print("初始化M83 挤出机相对模式")
    print("顺序发送温度指令并等待")
    print("实时温度监控")
    print("\n命令:")
    print("  file <path>   - 开始打印")
    print("  pause         - 暂停")
    print("  resume        - 恢复")
    print("  stop          - 停止")
    print("  status        - 查看状态")
    print("  progress      - 查看进度")
    print("  quit          - 退出")
    print()
    
    try:
        while True:
            try:
                cmd = input(">>> ").strip().split(' ', 1)
                if not cmd[0]:
                    continue
                
                command = cmd[0].lower()
                
                if command == 'quit':
                    break
                elif command == 'file':
                    if len(cmd) > 1:
                        result = sender.start_file_print(cmd[1])
                        print(f"开始: {'✓' if result else '✗'}")
                    else:
                        print("请提供文件路径")
                elif command == 'pause':
                    sender.pause()
                elif command == 'resume':
                    sender.resume()
                elif command == 'stop':
                    sender.stop()
                elif command == 'status':
                    status = sender.check_printer_status()
                    print(json.dumps(status, indent=2, ensure_ascii=False))
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(json.dumps(progress, indent=2, ensure_ascii=False))
                else:
                    print(f"未知命令: {command}")
                    
            except KeyboardInterrupt:
                print("\n退出中...")
                break
            except Exception as e:
                print(f"错误: {e}")
                import traceback
                traceback.print_exc()
    
    finally:
        sender.close()
        print("已退出")


if __name__ == "__main__":
    main()