#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced G-code Sender for OctoPrint
增加了M112错误检测和防护机制
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
    HALTED = "halted"  # 新增：紧急停止状态


class GCodeSender:
    """增强型G-code发送器 - 带M112错误防护"""
    
    def __init__(self, octoprint_url: str, api_key: str, buffer_size: int = 20):
        """
        初始化G-code发送器 - 降低缓冲区大小防止溢出
        """
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        self.buffer_size = buffer_size  # 进一步降低缓冲区大小
        
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
        self.command_queue = queue.Queue()
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 错误监控
        self.last_temp_check = 0
        self.temp_check_interval = 2.0  # 每2秒检查一次温度
        self.error_count = 0
        self.max_errors = 5
        
        # 安全的指令模式
        self.safe_mode = True
        self.dangerous_patterns = [
            r'^M109\s+S0$',   # 关闭加热器
            r'^M190\s+S0$',   # 关闭热床
            r'^M84$',         # 关闭步进电机
            r'^M18$',         # 关闭步进电机
            r'^M112$',        # 紧急停止（绝对不能发送）
        ]
        
        # 需要谨慎处理的指令
        self.careful_patterns = [
            r'^T\d+$',        # 工具选择
            r'^G28',          # 归零
            r'^M104',         # 设置热端温度
            r'^M109',         # 等待热端加热
            r'^M140',         # 设置热床温度  
            r'^M190',         # 等待热床加热
        ]
        
        self.has_active_job = False
        self.last_printer_state = ""
    
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
        """检查打印机状态，增加错误检测"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            # 检查是否有halt状态
            state_text = status.get('state', {}).get('text', '').lower()
            if 'halt' in state_text or 'kill' in state_text or 'emergency' in state_text:
                logger.error(f"检测到打印机紧急停止状态: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
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
    
    def check_temperatures_safe(self) -> dict:
        """安全的温度检查，增加热失控检测"""
        try:
            current_time = time.time()
            if current_time - self.last_temp_check < self.temp_check_interval:
                return {}
            
            self.last_temp_check = current_time
            
            status = self.check_printer_status()
            temps = status.get('temperature', {})
            
            # 检查温度异常
            tool_temp = temps.get('tool0', {})
            bed_temp = temps.get('bed', {})
            
            tool_actual = tool_temp.get('actual', 0)
            tool_target = tool_temp.get('target', 0)
            bed_actual = bed_temp.get('actual', 0)
            bed_target = bed_temp.get('target', 0)
            
            # 检测可能的热失控
            if tool_target > 0 and tool_actual > 0:
                temp_diff = abs(tool_actual - tool_target)
                if temp_diff > 15:  # 温差超过15度
                    logger.warning(f"热端温度异常: 实际={tool_actual}°C, 目标={tool_target}°C, 差值={temp_diff}°C")
            
            if bed_target > 0 and bed_actual > 0:
                temp_diff = abs(bed_actual - bed_target)
                if temp_diff > 10:  # 热床温差超过10度
                    logger.warning(f"热床温度异常: 实际={bed_actual}°C, 目标={bed_target}°C, 差值={temp_diff}°C")
            
            return {
                'tool0': tool_temp,
                'bed': bed_temp,
            }
        except Exception as e:
            logger.error(f"温度检查失败: {e}")
            return {}
    
    def get_job_status(self) -> dict:
        """获取作业状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/job', timeout=5)
            response.raise_for_status()
            job_data = response.json()
            
            job_state = job_data.get('state', '').lower()
            self.has_active_job = job_state in ['printing', 'paused']
            
            return job_data
        except requests.exceptions.RequestException as e:
            logger.error(f"获取作业状态失败: {e}")
            return {}
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        
        # 检查是否处于错误状态
        error_keywords = ['halt', 'kill', 'emergency', 'error']
        if any(keyword in state for keyword in error_keywords):
            logger.error(f"打印机处于错误状态: {state}")
            return False
        
        ready_states = ['operational', 'ready']
        return any(ready_state in state for ready_state in ready_states)
    
    def send_single_command(self, command: str, skip_dangerous: bool = True) -> bool:
        """发送单条指令，增加安全检查"""
        command = command.strip()
        if not command:
            return True
        
        # 检查打印机状态
        if self.state == PrinterState.HALTED:
            logger.error("打印机处于紧急停止状态，拒绝发送指令")
            return False
        
        # 危险指令检查
        if skip_dangerous and self.is_dangerous_command(command):
            logger.warning(f"跳过危险指令: {command}")
            return True
        
        # 谨慎指令记录
        if self.is_careful_command(command):
            logger.info(f"发送谨慎指令: {command}")
        
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
            logger.debug(f"指令发送成功: {command}")
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"指令发送失败 '{command}': {e} ({self.error_count}/{self.max_errors})")
            
            if self.error_count >= self.max_errors:
                logger.error("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def send_batch_commands(self, commands: List[str], skip_dangerous: bool = True) -> bool:
        """批量发送指令，小批量+延迟防止溢出"""
        if not commands:
            return True
        
        if self.state == PrinterState.HALTED:
            logger.error("打印机处于紧急停止状态，停止发送")
            return False
        
        try:
            valid_commands = []
            skipped_count = 0
            careful_count = 0
            
            for cmd in commands:
                cmd = cmd.strip()
                if not cmd or cmd.startswith(';'):
                    continue
                
                if skip_dangerous and self.is_dangerous_command(cmd):
                    skipped_count += 1
                    logger.debug(f"跳过危险指令: {cmd}")
                    continue
                
                if self.is_careful_command(cmd):
                    careful_count += 1
                    logger.debug(f"谨慎指令: {cmd}")
                
                valid_commands.append(cmd)
            
            if skipped_count > 0:
                logger.info(f"跳过了 {skipped_count} 条危险指令")
            if careful_count > 0:
                logger.info(f"处理了 {careful_count} 条谨慎指令")
            
            if not valid_commands:
                return True
            
            # 极小批次发送，每次只发送1-2条指令
            batch_size = 2
            for i in range(0, len(valid_commands), batch_size):
                if self.stop_event.is_set() or self.state == PrinterState.HALTED:
                    logger.warning("检测到停止信号，中断发送")
                    break
                
                batch = valid_commands[i:i+batch_size]
                
                data = {"commands": batch}
                response = self.session.post(
                    f'{self.octoprint_url}/api/printer/command',
                    data=json.dumps(data),
                    timeout=10
                )
                response.raise_for_status()
                
                logger.debug(f"✓ 批量发送 {len(batch)} 条指令成功")
                
                # 增加延迟，防止打印机缓冲区溢出
                time.sleep(0.1)  # 100ms延迟
            
            # 重置错误计数
            self.error_count = 0
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"批量发送失败: {e} ({self.error_count}/{self.max_errors})")
            
            if self.error_count >= self.max_errors:
                logger.error("连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def printer_monitor_worker(self):
        """打印机状态监控线程"""
        logger.info("启动打印机状态监控")
        
        while not self.stop_event.is_set():
            try:
                # 检查打印机状态
                self.check_printer_status()
                
                # 检查温度
                if self.state == PrinterState.RUNNING:
                    self.check_temperatures_safe()
                
                time.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"监控线程错误: {e}")
                time.sleep(2)
        
        logger.info("打印机状态监控已停止")
    
    def load_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """加载G-code文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    yield line.strip()
        except FileNotFoundError:
            logger.error(f"文件未找到: {file_path}")
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
    
    def count_gcode_lines(self, file_path: str) -> int:
        """计算文件行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return sum(1 for _ in file)
        except Exception as e:
            logger.error(f"计算文件行数失败: {e}")
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
            logger.info(f"文件读取完毕，总共读取 {self.current_line} 行")
            return False
    
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
        
        logger.info(f"文件总行数: {self.total_lines}")
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.printer_monitor_worker, daemon=True)
        self.monitor_thread.start()
        
        gcode_generator = self.load_gcode_file(file_path)
        has_more_data = True
        
        # 预填充缓冲区
        has_more_data = self.fill_buffer(gcode_generator)
        
        batch_commands = []
        consecutive_errors = 0
        
        try:
            while (self.gcode_buffer or has_more_data) and not self.stop_event.is_set():
                # 检查是否被紧急停止
                if self.state == PrinterState.HALTED:
                    logger.error("检测到紧急停止，中断发送")
                    break
                
                # 等待恢复信号
                self.pause_event.wait()
                
                if self.stop_event.is_set():
                    break
                
                # 从缓冲区取指令
                if self.gcode_buffer:
                    command = self.gcode_buffer.popleft()
                    batch_commands.append(command)
                    self.processed_lines += 1
                    
                    # 小批量发送
                    if len(batch_commands) >= 2 or (not self.gcode_buffer and batch_commands):
                        success = self.send_batch_commands(batch_commands, skip_dangerous=True)
                        
                        if not success:
                            consecutive_errors += 1
                            logger.error(f"发送失败 (连续错误: {consecutive_errors})")
                            
                            if consecutive_errors >= 3:
                                logger.error("连续发送失败，停止执行")
                                self.state = PrinterState.ERROR
                                break
                        else:
                            consecutive_errors = 0
                        
                        batch_commands.clear()
                        
                        # 进度报告
                        if self.processed_lines % 200 == 0:
                            progress = (self.current_line / self.total_lines) * 100
                            logger.info(f"📊 进度: {self.current_line}/{self.total_lines} ({progress:.1f}%) - 已处理: {self.processed_lines}")
                
                # 重新填充缓冲区
                if len(self.gcode_buffer) < self.buffer_size // 2 and has_more_data:
                    has_more_data = self.fill_buffer(gcode_generator)
                
                # 增加延迟，确保打印机有时间处理
                time.sleep(0.05)
            
            # 发送剩余指令
            if batch_commands and not self.stop_event.is_set() and self.state != PrinterState.HALTED:
                self.send_batch_commands(batch_commands, skip_dangerous=True)
            
            # 最终状态设置
            if self.state == PrinterState.HALTED:
                logger.error("🚨 文件处理因紧急停止而中断")
            elif self.stop_event.is_set():
                logger.info(f"⏹️ 处理已停止: {self.current_line}/{self.total_lines} 行读取，{self.processed_lines} 条指令已处理")
            else:
                self.state = PrinterState.IDLE
                logger.info(f"✅ 文件处理完成: {self.current_line}/{self.total_lines} 行读取，{self.processed_lines} 条指令已处理")
                
        except Exception as e:
            logger.error(f"发送过程中出错: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str):
        """开始文件打印"""
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("已有任务在运行中")
            return False
        
        # 重置状态
        self.stop_event.clear()
        self.pause_event.set()
        self.gcode_buffer.clear()
        self.error_count = 0
        
        # 启动发送线程
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        return True
    
    def emergency_reset(self):
        """紧急复位 - 尝试恢复打印机"""
        logger.info("尝试紧急复位...")
        
        try:
            # 发送软复位
            response = self.session.post(
                f'{self.octoprint_url}/api/connection',
                data=json.dumps({"command": "disconnect"}),
                timeout=5
            )
            
            time.sleep(2)
            
            # 重新连接
            response = self.session.post(
                f'{self.octoprint_url}/api/connection',
                data=json.dumps({"command": "connect"}),
                timeout=10
            )
            
            if response.status_code == 204:
                logger.info("紧急复位成功，请检查打印机状态")
                self.state = PrinterState.IDLE
                self.error_count = 0
                return True
            else:
                logger.error("紧急复位失败")
                return False
                
        except Exception as e:
            logger.error(f"紧急复位过程出错: {e}")
            return False
    
    def pause(self):
        """暂停"""
        if self.state == PrinterState.RUNNING:
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            logger.info("本地暂停成功")
    
    def resume(self):
        """恢复"""
        if self.state == PrinterState.PAUSED:
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            logger.info("本地恢复成功")
    
    def stop(self):
        """停止"""
        self.stop_event.set()
        self.pause_event.set()
        self.state = PrinterState.STOPPED
        logger.info("本地停止成功")
    
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
    
    def diagnose_system(self):
        """系统诊断"""
        logger.info("=== 🔍 系统诊断 ===")
        
        # 检查打印机状态
        printer_status = self.check_printer_status()
        printer_state = printer_status.get('state', {}).get('text', 'Unknown')
        logger.info(f"打印机状态: {printer_state}")
        
        # 检查是否halt
        if 'halt' in printer_state.lower():
            logger.error("检测到HALT状态！需要手动重置打印机")
            logger.info("解决步骤:")
            logger.info("1. 断开并重新连接打印机USB")
            logger.info("2. 或使用 'reset' 命令尝试软复位")
            logger.info("3. 检查温度传感器和接线")
        
        # 检查温度
        temps = self.check_temperatures_safe()
        if temps:
            tool_temp = temps['tool0']
            bed_temp = temps['bed']
            logger.info(f"热端温度: 实际={tool_temp.get('actual', 'N/A')}°C, 目标={tool_temp.get('target', 'N/A')}°C")
            logger.info(f"热床温度: 实际={bed_temp.get('actual', 'N/A')}°C, 目标={bed_temp.get('target', 'N/A')}°C")
        
        # 检查作业状态
        job_status = self.get_job_status()
        job_state = job_status.get('state', 'Unknown')
        logger.info(f"OctoPrint作业状态: {job_state}")
        
        # 检查错误计数
        logger.info(f"当前错误计数: {self.error_count}/{self.max_errors}")
        
        # 检查当前进度
        progress = self.get_progress()
        logger.info(f"发送进度: {progress['current_line']}/{progress['total_lines']} ({progress['progress_percent']}%)")
    
    def close(self):
        """清理资源"""
        logger.info("正在清理资源...")
        self.stop()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            
        self.session.close()


def interactive_mode():
    """交互模式"""
    OCTOPRINT_URL = "http://192.168.1.100"
    API_KEY = "YOUR_API_KEY_HERE"
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("=== Enhanced G-code Sender v2.2 - 带M112防护 ===")
    print("新增功能:")
    print("- M112紧急停止检测和防护")
    print("- 实时打印机状态监控")
    print("- 热失控预警")
    print("- 连接错误检测")
    print("- 紧急复位功能")
    print()
    print("命令列表:")
    print("  single <command>     - 发送单条指令")
    print("  file <path>          - 开始文件打印")
    print("  pause                - 暂停")
    print("  resume               - 恢复")
    print("  stop                 - 停止")
    print("  reset                - 紧急复位（尝试恢复HALT状态）")
    print("  status               - 打印机状态")
    print("  temps                - 温度信息")
    print("  progress             - 进度信息")
    print("  diagnose             - 系统诊断")
    print("  safe_mode            - 切换安全模式")
    print("  quit                 - 退出")
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
                elif command == 'single':
                    if len(cmd) > 1:
                        result = sender.send_single_command(cmd[1])
                        print(f"发送{'成功' if result else '失败'}")
                    else:
                        print("请提供指令")
                elif command == 'file':
                    if len(cmd) > 1:
                        result = sender.start_file_print(cmd[1])
                        print(f"开始文件打印: {'成功' if result else '失败'}")
                        
                    else:
                        print("请提供文件路径")
                        
                elif command == 'pause':
                    sender.pause()
                elif command == 'resume':
                    sender.resume()
                elif command == 'stop':
                    sender.stop()
                elif command == 'reset':
                    result = sender.emergency_reset()
                    print(f"紧急复位: {'成功' if result else '失败'}")
                elif command == 'status':
                    status = sender.check_printer_status()
                    print(f"打印机状态: {json.dumps(status, indent=2, ensure_ascii=False)}")
                elif command == 'temps':
                    temps = sender.check_temperatures_safe()
                    print(f"温度信息: {json.dumps(temps, indent=2, ensure_ascii=False)}")
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(f"进度信息: {json.dumps(progress, indent=2, ensure_ascii=False)}")
                elif command == 'diagnose':
                    sender.diagnose_system()
                elif command == 'safe_mode':
                    sender.safe_mode = not sender.safe_mode
                    print(f"安全模式: {'开启' if sender.safe_mode else '关闭'}")
                else:
                    print(f"未知命令: {command}")
                    
            except KeyboardInterrupt:
                print("\n正在退出...")
                break
            except Exception as e:
                print(f"错误: {e}")
    
    finally:
        sender.close()
        print("程序已退出")


if __name__ == "__main__":
    interactive_mode()

