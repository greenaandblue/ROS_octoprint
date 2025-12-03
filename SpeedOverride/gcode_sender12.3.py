#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced G-code Sender with Dynamic Code Injection
支持：
  • 文件打印
  • 暂停/恢复
  • 暂停时动态输入新 G-code
  • 速度修改（可选集成 gcode_modifier）
"""
'''
使用方式（其中之一，也可以用test demo）
交互式命令行（真实打印机）
bashpython3 gcode_sender.py
然后在终端输入命令：
>>> file sample.gcode       # 开始打印
>>> pause                   # 暂停
>>> inject                  # 输入新代码
  G1 X100 Y100 F1500      # 输入新命令
  M109 S210               # 输入新命令
                          # 空行结束输入
>>> resume                  # 恢复打印

'''
import requests
import time
import threading
import json
import re
from enum import Enum
from typing import Optional, Dict, List
import logging

# 导入修改器
from gcode_modifier import GCodeModifier, OverrideMode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PrinterState(Enum):
    """打印机状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class PrintState:
    """打印状态"""
    def __init__(self):
        self.position = {'X': 0, 'Y': 0, 'Z': 0, 'E': 0}
        self.temperatures = {'tool': 0, 'bed': 0}
        self.line_number = 0


class GCodeSender:
    """G-code 发送器 - 支持动态代码注入"""
    
    def __init__(self, octoprint_url: str, api_key: str):
        """初始化发送器"""
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        
        # 状态
        self.state = PrinterState.IDLE
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.pause_event.set()
        
        # 文件和进度
        self.gcode_lines = []
        self.current_line_index = 0
        self.total_lines = 0
        self.file_path = ""
        self.processed_lines = 0
        
        # 【关键】动态代码注入队列
        self.injected_commands = []  # 暂停时用户输入的新代码
        self.use_injected_code = False  # 是否使用注入的代码
        
        # 线程
        self.sender_thread = None
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 超时和错误
        self.response_timeout = 10.0
        self.error_count = 0
        self.max_errors = 5
        
        # 配置
        self.maintain_temp_on_pause = True
        self.pause_lift_z = 5.0
        self.pause_retract = 5.0
        
        # 模式检查
        self.dangerous_patterns = [r'^M112$']
        self.waiting_patterns = [r'^M109', r'^M190', r'^G28']
        
        self.print_state = PrintState()
        self.last_printer_state = ""
        
        # ✅ 修改器实例
        self.modifier = GCodeModifier()
        
        logger.info("✓ GCodeSender 已初始化")
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查危险指令"""
        command = command.strip().upper()
        return any(re.match(pattern, command) for pattern in self.dangerous_patterns)
    
    def is_waiting_command(self, command: str) -> bool:
        """检查等待指令"""
        command = command.strip().upper()
        return any(re.match(pattern, command) for pattern in self.waiting_patterns)
    
    def send_and_wait(self, command: str, wait_time: float = 0.1) -> bool:
        """发送指令并等待"""
        # 应用速度修改
        command = self.modifier.process_line(command)
        
        command = command.strip()
        if not command or command.startswith(';'):
            return True
        
        if self.is_dangerous_command(command):
            logger.warning(f"跳过危险指令: {command}")
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
            logger.debug(f"✓ 已发送: {command}")
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"✗ 发送失败 '{command}': {e}")
            
            if self.error_count >= self.max_errors:
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {}
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        try:
            status = self.check_printer_status()
            state = status.get('state', {}).get('text', '').lower()
            return 'operational' in state or 'printing' in state
        except:
            return False
    
    def load_gcode_file(self, file_path: str) -> bool:
        """加载 G-code 文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self.gcode_lines = [line.strip() for line in file 
                                   if line.strip() and not line.strip().startswith(';')]
                self.total_lines = len(self.gcode_lines)
                logger.info(f"✓ 加载文件: {self.total_lines} 行")
                return True
        except Exception as e:
            logger.error(f"✗ 加载失败: {e}")
            return False
    
    def get_next_command(self) -> Optional[str]:
        """
        获取下一条要发送的指令
        【关键】优先使用注入的代码，否则使用文件中的代码
        """
        # 如果有注入的代码，优先使用
        if self.injected_commands:
            cmd = self.injected_commands.pop(0)
            logger.info(f"📥 使用注入代码: {cmd}")
            return cmd
        
        # 否则使用文件中的代码
        if self.current_line_index < self.total_lines:
            cmd = self.gcode_lines[self.current_line_index]
            self.current_line_index += 1
            return cmd
        
        return None
    
    def sender_worker(self, file_path: str):
        """发送器线程"""
        logger.info(f"开始打印: {file_path}")
        
        if not self.is_printer_ready():
            logger.error("打印机未就绪")
            self.state = PrinterState.ERROR
            return
        
        if not self.load_gcode_file(file_path):
            self.state = PrinterState.ERROR
            return
        
        self.file_path = file_path
        self.current_line_index = 0
        self.processed_lines = 0
        self.state = PrinterState.RUNNING
        self.modifier.reset_state()
        
        try:
            while not self.stop_event.is_set():
                # 等待恢复信号
                self.pause_event.wait()
                
                if self.stop_event.is_set():
                    break
                
                # 获取下一条命令（可能来自文件或用户输入）
                command = self.get_next_command()
                
                if command is None:
                    break
                
                # 发送并等待
                success = self.send_and_wait(command, wait_time=0.1)
                
                if not success:
                    logger.error(f"发送失败，停止于第 {self.current_line_index} 行")
                    self.state = PrinterState.ERROR
                    break
                
                self.processed_lines += 1
                
                # 进度报告
                if self.processed_lines % 50 == 0:
                    logger.info(f"进度: {self.processed_lines}/{self.total_lines} "
                              f"({self.processed_lines*100//self.total_lines}%)")
            
            if not self.stop_event.is_set():
                self.state = PrinterState.IDLE
                logger.info(f"✓ 打印完成: {self.processed_lines} 条指令")
            
        except Exception as e:
            logger.error(f"发送异常: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str) -> bool:
        """开始打印"""
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("已有任务在运行")
            return False
        
        self.stop_event.clear()
        self.pause_event.set()
        self.injected_commands.clear()
        self.error_count = 0
        
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        return True
    
    def pause(self) -> bool:
        """暂停打印"""
        if self.state != PrinterState.RUNNING:
            logger.warning(f"无法暂停: 当前状态 {self.state.value}")
            return False
        
        logger.info("暂停打印...")
        self.pause_event.clear()
        time.sleep(0.2)
        
        self.state = PrinterState.PAUSED
        logger.info("✓ 已暂停")
        
        # 显示当前状态
        self._show_pause_menu()
        return True
    
    def _show_pause_menu(self):
        """显示暂停菜单和当前状态"""
        print("\n" + "="*70)
        print("📍 打印已暂停")
        print("="*70)
        print(f"当前进度: {self.current_line_index}/{self.total_lines}")
        if self.current_line_index > 0:
            print(f"上一行命令: {self.gcode_lines[self.current_line_index-1]}")
        print("="*70)
        print("选项:")
        print("  1. 输入新 G-code 后恢复打印")
        print("  2. 直接恢复打印")
        print("  3. 停止打印")
        print("="*70)
    
    def inject_gcode(self, commands: List[str]) -> bool:
        """
        【关键】在暂停时注入新的 G-code 命令
        这些命令会在恢复时优先于文件中的原始代码执行
        """
        if self.state != PrinterState.PAUSED:
            logger.warning("只能在暂停时注入代码")
            return False
        
        # 验证和清理命令
        valid_commands = []
        for cmd in commands:
            cmd = cmd.strip()
            if cmd and not cmd.startswith(';'):
                valid_commands.append(cmd)
        
        if not valid_commands:
            logger.warning("没有有效的命令")
            return False
        
        self.injected_commands.extend(valid_commands)
        logger.info(f"✓ 已注入 {len(valid_commands)} 条命令:")
        for cmd in valid_commands:
            logger.info(f"  → {cmd}")
        
        return True
    
    def resume(self) -> bool:
        """恢复打印"""
        if self.state != PrinterState.PAUSED:
            logger.warning(f"无法恢复: 当前状态 {self.state.value}")
            return False
        
        logger.info("恢复打印...")
        self.pause_event.set()
        self.state = PrinterState.RUNNING
        logger.info("✓ 已恢复")
        return True
    
    def stop(self) -> bool:
        """停止打印"""
        logger.info("  停止打印...")
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
        
        logger.info("✓ 已停止")
        return True
    
    def get_progress(self) -> dict:
        """获取进度信息"""
        progress_percent = 0
        if self.total_lines > 0:
            progress_percent = (self.current_line_index / self.total_lines) * 100
        
        return {
            'state': self.state.value,
            'current_line': self.current_line_index,
            'total_lines': self.total_lines,
            'processed_commands': self.processed_lines,
            'progress_percent': round(progress_percent, 1),
            'file_path': self.file_path,
            'injected_commands_pending': len(self.injected_commands),
            'modifier_enabled': self.modifier.override_enabled,
        }
    
    def close(self):
        """清理资源"""
        logger.info("清理资源...")
        self.stop()
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        self.session.close()


def interactive_mode():
    """交互模式"""
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "your_api_key_here" #一定要改API啊啊啊啊啊啊啊
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("\n" + "="*70)
    print("G-code Sender - 交互模式")
    print("="*70)
    print("功能: 文件打印 + 暂停 + 动态注入代码 + 恢复")
    print("="*70)
    print("\n命令列表:")
    print("  file <path>          - 开始打印文件")
    print("  pause                - 暂停打印")
    print("  resume               - 恢复打印")
    print("  inject               - 输入新 G-code（暂停时）")
    print("  status               - 显示状态")
    print("  progress             - 显示进度")
    print("  stop                 - 停止打印")
    print("  quit                 - 退出")
    print("="*70 + "\n")
    
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
                        print(f"{'✓' if result else '✗'} 开始打印")
                    else:
                        print("用法: file <path>")
                
                elif command == 'pause':
                    sender.pause()
                
                elif command == 'inject':
                    if sender.state != PrinterState.PAUSED:
                        print("✗ 只能在暂停时注入代码")
                    else:
                        print("输入 G-code 指令（空行结束）:")
                        commands = []
                        while True:
                            line = input().strip()
                            if not line:
                                break
                            commands.append(line)
                        
                        if commands:
                            sender.inject_gcode(commands)
                            print("输入完成，是否立即恢复? (y/n)")
                            if input().lower() == 'y':
                                sender.resume()
                        else:
                            print("没有输入命令")
                
                elif command == 'resume':
                    sender.resume()
                
                elif command == 'stop':
                    sender.stop()
                
                elif command == 'status':
                    print(json.dumps(sender.get_progress(), indent=2, ensure_ascii=False))
                
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(f"状态: {progress['state']}")
                    print(f"进度: {progress['current_line']}/{progress['total_lines']} "
                          f"({progress['progress_percent']}%)")
                    print(f"已处理: {progress['processed_commands']} 条命令")
                    print(f"待注入: {progress['injected_commands_pending']} 条命令")
                
                else:
                    print(f"✗ 未知命令: {command}")
                
            except KeyboardInterrupt:
                print("\n正在退出...")
                break
            except Exception as e:
                print(f"✗ 错误: {e}")
    
    finally:
        sender.close()
        print("程序已退出")


if __name__ == "__main__":
    interactive_mode()