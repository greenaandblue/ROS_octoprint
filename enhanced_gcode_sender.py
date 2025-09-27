#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced G-code Sender for OctoPrint
结合单指令交互和批量文件执行，支持暂停/恢复和性能优化
"""

import requests
import time
import threading
import queue
import json
from collections import deque
from enum import Enum
from typing import List, Optional, Generator
import logging 

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


class GCodeSender:
    """增强型G-code发送器"""
    
    def __init__(self, octoprint_url: str, api_key: str, buffer_size: int = 100):
        """
        初始化G-code发送器
        
        Args:
            octoprint_url: OctoPrint服务器地址，如 'http://192.168.1.100'
            api_key: OctoPrint API密钥
            buffer_size: 缓冲区大小（预加载的G-code行数）
        """
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        self.buffer_size = buffer_size
        
        # 状态控制
        self.state = PrinterState.IDLE
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event.set()  # 初始设为运行状态
        
        # 文件和进度控制
        self.gcode_buffer = deque()
        self.current_line = 0
        self.total_lines = 0
        self.file_path = ""
        
        # 线程控制
        self.sender_thread = None
        self.command_queue = queue.Queue()
        
        # 请求会话（复用连接提高效率）
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer')
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取打印机状态失败: {e}")
            return {}
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        return 'operational' in state or 'ready' in state
    
    def send_single_command(self, command: str) -> bool:
        """
        发送单条G-code指令
        
        Args:
            command: G-code指令
            
        Returns:
            bool: 发送是否成功
        """
        try:
            data = {"commands": [command.strip()]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.debug(f"发送指令: {command.strip()}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送指令失败 '{command}': {e}")
            return False
    
    def send_batch_commands(self, commands: List[str]) -> bool:
        """
        批量发送G-code指令（提高效率）
        
        Args:
            commands: G-code指令列表
            
        Returns:
            bool: 发送是否成功
        """
        if not commands:
            return True
            
        try:
            # 过滤空行和注释
            valid_commands = [
                cmd.strip() for cmd in commands 
                if cmd.strip() and not cmd.strip().startswith(';')
            ]
            
            if not valid_commands:
                return True
            
            data = {"commands": valid_commands}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.debug(f"批量发送 {len(valid_commands)} 条指令")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"批量发送指令失败: {e}")
            return False
    
    def load_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """
        高效加载G-code文件（使用生成器避免内存占用过大）
        
        Args:
            file_path: G-code文件路径
            
        Yields:
            str: G-code行
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    yield line.strip()
        except FileNotFoundError:
            logger.error(f"文件未找到: {file_path}")
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
    
    def count_gcode_lines(self, file_path: str) -> int:
        """计算G-code文件总行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return sum(1 for _ in file)
        except Exception as e:
            logger.error(f"计算文件行数失败: {e}")
            return 0
    
    def fill_buffer(self, gcode_generator: Generator[str, None, None]) -> bool:
        """
        填充缓冲区
        
        Args:
            gcode_generator: G-code生成器
            
        Returns:
            bool: 是否还有更多数据
        """
        added_lines = 0
        try:
            while added_lines < self.buffer_size and len(self.gcode_buffer) < self.buffer_size * 2:
                line = next(gcode_generator)
                if line and not line.startswith(';'):  # 跳过空行和注释
                    self.gcode_buffer.append(line)
                    added_lines += 1
            return True
        except StopIteration:
            return False  # 文件读取完毕
    
    def sender_worker(self, file_path: str):
        """
        发送器工作线程
        
        Args:
            file_path: G-code文件路径
        """
        logger.info(f"开始处理文件: {file_path}")
        
        # 检查打印机状态
        if not self.is_printer_ready():
            logger.error("打印机未就绪")
            self.state = PrinterState.ERROR
            return
        
        # 初始化
        self.file_path = file_path
        self.total_lines = self.count_gcode_lines(file_path)
        self.current_line = 0
        self.state = PrinterState.RUNNING
        
        gcode_generator = self.load_gcode_file(file_path)
        has_more_data = True
        
        # 预填充缓冲区
        has_more_data = self.fill_buffer(gcode_generator)
        
        batch_commands = []
        batch_size = 10  # 每批发送的指令数
        
        try:
            while (self.gcode_buffer or has_more_data) and not self.stop_event.is_set():
                # 等待恢复信号
                self.pause_event.wait()
                
                if self.stop_event.is_set():
                    break
                
                # 从缓冲区取指令
                if self.gcode_buffer:
                    command = self.gcode_buffer.popleft()
                    batch_commands.append(command)
                    self.current_line += 1
                    
                    # 批量发送或缓冲区即将空时发送
                    if (len(batch_commands) >= batch_size or 
                        (not self.gcode_buffer and batch_commands)):
                        
                        if not self.send_batch_commands(batch_commands):
                            logger.error("发送失败，停止执行")
                            self.state = PrinterState.ERROR
                            break
                        
                        batch_commands.clear()
                        
                        # 进度报告
                        if self.current_line % 50 == 0:
                            progress = (self.current_line / self.total_lines) * 100
                            logger.info(f"进度: {self.current_line}/{self.total_lines} ({progress:.1f}%)")
                
                # 重新填充缓冲区
                if len(self.gcode_buffer) < self.buffer_size // 2 and has_more_data:
                    has_more_data = self.fill_buffer(gcode_generator)
                
                # 避免CPU占用过高
                time.sleep(0.001)
            
            # 发送剩余的批量指令
            if batch_commands and not self.stop_event.is_set():
                self.send_batch_commands(batch_commands)
            
            if not self.stop_event.is_set():
                self.state = PrinterState.IDLE
                logger.info(f"文件处理完成: {self.current_line}/{self.total_lines} 行")
            else:
                logger.info(f"处理已停止: {self.current_line}/{self.total_lines} 行")
                
        except Exception as e:
            logger.error(f"发送过程中出错: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str):
        """
        开始打印G-code文件
        
        Args:
            file_path: G-code文件路径
        """
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("已有任务在运行中")
            return False
        
        # 重置状态
        self.stop_event.clear()
        self.pause_event.set()
        self.gcode_buffer.clear()
        
        # 启动发送线程
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        return True
    
    def pause(self):
        """暂停发送"""
        if self.state == PrinterState.RUNNING:
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            logger.info("已暂停")
    
    def resume(self):
        """恢复发送"""
        if self.state == PrinterState.PAUSED:
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            logger.info("已恢复")
    
    def stop(self):
        """停止发送"""
        self.stop_event.set()
        self.pause_event.set()  # 确保线程能够退出
        self.state = PrinterState.STOPPED
        logger.info("已停止")
    
    def get_progress(self) -> dict:
        """获取进度信息"""
        progress_percent = 0
        if self.total_lines > 0:
            progress_percent = (self.current_line / self.total_lines) * 100
        
        return {
            'state': self.state.value,
            'current_line': self.current_line,
            'total_lines': self.total_lines,
            'progress_percent': round(progress_percent, 1),
            'file_path': self.file_path
        }
    
    def close(self):
        """清理资源"""
        self.stop()
        if self.sender_thread:
            self.sender_thread.join(timeout=5)
        self.session.close()


def interactive_mode():
    """交互模式示例"""
    # 配置信息（请修改为你的实际配置）
    OCTOPRINT_URL = "http://192.168.1.100"  # 修改为你的OctoPrint地址
    API_KEY = "YOUR_API_KEY_HERE"  # 修改为你的API密钥
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("=== Enhanced G-code Sender ===")
    print("命令列表:")
    print("  single <command>  - 发送单条G-code指令")
    print("  file <path>       - 开始发送G-code文件")
    print("  pause             - 暂停发送")
    print("  resume            - 恢复发送")
    print("  stop              - 停止发送")
    print("  status            - 显示打印机状态")
    print("  progress          - 显示进度")
    print("  quit              - 退出程序")
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
                        sender.send_single_command(cmd[1])
                    else:
                        print("请提供G-code指令")
                elif command == 'file':
                    if len(cmd) > 1:
                        sender.start_file_print(cmd[1])
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
                    print(f"打印机状态: {json.dumps(status, indent=2)}")
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(f"进度信息: {json.dumps(progress, indent=2)}")
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