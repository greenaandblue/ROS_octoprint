#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced G-code Sender for OctoPrint
结合单指令交互和批量文件执行，支持暂停/恢复和性能优化
修复了pause/resume反馈和suppress command问题
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


class GCodeSender:
    """增强型G-code发送器"""
    
    def __init__(self, octoprint_url: str, api_key: str, buffer_size: int = 50):
        """
        初始化G-code发送器
        
        Args:
            octoprint_url: OctoPrint服务器地址，如 'http://192.168.1.100'
            api_key: OctoPrint API密钥
            buffer_size: 缓冲区大小（预加载的G-code行数，降低到50避免过载）
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
        
        # 危险指令过滤器（这些指令可能被OctoPrint抑制）
        self.dangerous_patterns = [
            r'^T\d+$',  # 工具切换指令如T0, T1
            r'^M109',   # 等待加热指令
            r'^M190',   # 等待热床加热指令
            r'^G28',    # 归零指令（在某些情况下可能危险）
        ]
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查指令是否可能被抑制"""
        command = command.strip().upper()
        for pattern in self.dangerous_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer')
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取打印机状态失败: {e}")
            return {}
    
    def get_printer_profiles(self) -> dict:
        """获取打印机配置文件"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printerprofiles')
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取打印机配置失败: {e}")
            return {}
    
    def check_temperatures(self) -> dict:
        """检查温度状态"""
        status = self.check_printer_status()
        temps = status.get('temperature', {})
        return {
            'tool0': temps.get('tool0', {}),
            'bed': temps.get('bed', {}),
        }
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        return 'operational' in state or 'ready' in state
    
    def octoprint_pause_print(self) -> bool:
        """通过OctoPrint API暂停打印"""
        try:
            data = {"command": "pause"}
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.info("向OctoPrint发送暂停指令成功")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送OctoPrint暂停指令失败: {e}")
            return False
    
    def octoprint_resume_print(self) -> bool:
        """通过OctoPrint API恢复打印"""
        try:
            data = {"command": "pause"}  # OctoPrint使用同一个命令来切换暂停/恢复
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.info("向OctoPrint发送恢复指令成功")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送OctoPrint恢复指令失败: {e}")
            return False
    
    def octoprint_cancel_print(self) -> bool:
        """通过OctoPrint API取消打印"""
        try:
            data = {"command": "cancel"}
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.info("向OctoPrint发送取消指令成功")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送OctoPrint取消指令失败: {e}")
            return False
    
    def send_single_command(self, command: str, skip_dangerous: bool = True) -> bool:
        """
        发送单条G-code指令
        
        Args:
            command: G-code指令
            skip_dangerous: 是否跳过可能被抑制的危险指令
            
        Returns:
            bool: 发送是否成功
        """
        command = command.strip()
        
        # 检查是否为危险指令
        if skip_dangerous and self.is_dangerous_command(command):
            logger.warning(f"跳过可能被抑制的指令: {command}")
            return True
        
        try:
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.debug(f"发送指令成功: {command}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送指令失败 '{command}': {e}")
            return False
    
    def send_batch_commands(self, commands: List[str], skip_dangerous: bool = True) -> bool:
        """
        批量发送G-code指令（提高效率）
        
        Args:
            commands: G-code指令列表
            skip_dangerous: 是否跳过可能被抑制的危险指令
            
        Returns:
            bool: 发送是否成功
        """
        if not commands:
            return True
        
        try:
            # 过滤空行、注释和危险指令
            valid_commands = []
            skipped_count = 0
            
            for cmd in commands:
                cmd = cmd.strip()
                if not cmd or cmd.startswith(';'):
                    continue
                
                if skip_dangerous and self.is_dangerous_command(cmd):
                    skipped_count += 1
                    logger.debug(f"跳过可能被抑制的指令: {cmd}")
                    continue
                
                valid_commands.append(cmd)
            
            if skipped_count > 0:
                logger.info(f"跳过了 {skipped_count} 条可能被抑制的指令")
            
            if not valid_commands:
                return True
            
            data = {"commands": valid_commands}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data)
            )
            response.raise_for_status()
            logger.debug(f"批量发送 {len(valid_commands)} 条指令成功")
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
        
        # 检查温度状态
        temps = self.check_temperatures()
        logger.info(f"当前温度 - 热端: {temps['tool0']}, 热床: {temps['bed']}")
        
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
        batch_size = 5  # 减少批量大小，避免缓冲区溢出
        
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
                        
                        if not self.send_batch_commands(batch_commands, skip_dangerous=True):
                            logger.error("发送失败，停止执行")
                            self.state = PrinterState.ERROR
                            break
                        
                        batch_commands.clear()
                        
                        # 进度报告
                        if self.current_line % 100 == 0:
                            progress = (self.current_line / self.total_lines) * 100
                            logger.info(f"进度: {self.current_line}/{self.total_lines} ({progress:.1f}%)")
                
                # 重新填充缓冲区
                if len(self.gcode_buffer) < self.buffer_size // 2 and has_more_data:
                    has_more_data = self.fill_buffer(gcode_generator)
                
                # 增加延迟，避免过快发送导致OctoPrint缓冲区溢出
                time.sleep(0.01)
            
            # 发送剩余的批量指令
            if batch_commands and not self.stop_event.is_set():
                self.send_batch_commands(batch_commands, skip_dangerous=True)
            
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
        """暂停发送（同时发送OctoPrint暂停指令）"""
        if self.state == PrinterState.RUNNING:
            # 暂停本地发送
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            
            # 同时向OctoPrint发送暂停指令
            if self.octoprint_pause_print():
                logger.info("本地暂停并向OctoPrint发送暂停指令成功")
            else:
                logger.warning("本地暂停成功，但向OctoPrint发送暂停指令失败")
    
    def resume(self):
        """恢复发送（同时发送OctoPrint恢复指令）"""
        if self.state == PrinterState.PAUSED:
            # 恢复本地发送
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            
            # 同时向OctoPrint发送恢复指令
            if self.octoprint_resume_print():
                logger.info("本地恢复并向OctoPrint发送恢复指令成功")
            else:
                logger.warning("本地恢复成功，但向OctoPrint发送恢复指令失败")
    
    def stop(self):
        """停止发送（同时发送OctoPrint取消指令）"""
        self.stop_event.set()
        self.pause_event.set()  # 确保线程能够退出
        self.state = PrinterState.STOPPED
        
        # 同时向OctoPrint发送取消指令
        if self.octoprint_cancel_print():
            logger.info("本地停止并向OctoPrint发送取消指令成功")
        else:
            logger.warning("本地停止成功，但向OctoPrint发送取消指令失败")
    
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
            'file_path': self.file_path,
            'buffer_size': len(self.gcode_buffer)
        }
    
    def get_job_status(self) -> dict:
        """获取OctoPrint作业状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/job')
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"获取作业状态失败: {e}")
            return {}
    
    def diagnose_system(self):
        """系统诊断"""
        logger.info("=== 系统诊断 ===")
        
        # 检查打印机状态
        printer_status = self.check_printer_status()
        logger.info(f"打印机状态: {printer_status.get('state', {}).get('text', 'Unknown')}")
        
        # 检查温度
        temps = self.check_temperatures()
        logger.info(f"热端温度: {temps['tool0']}")
        logger.info(f"热床温度: {temps['bed']}")
        
        # 检查作业状态
        job_status = self.get_job_status()
        logger.info(f"作业状态: {job_status.get('state', 'Unknown')}")
        
        # 检查打印机配置
        profiles = self.get_printer_profiles()
        if profiles:
            current_profile = profiles.get('_default', 'Unknown')
            logger.info(f"当前打印机配置: {current_profile}")
    
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
    
    print("=== Enhanced G-code Sender v2.0 ===")
    print("命令列表:")
    print("  single <command>     - 发送单条G-code指令")
    print("  single_force <cmd>   - 强制发送指令（不过滤危险指令）")
    print("  file <path>          - 开始发送G-code文件")
    print("  pause                - 暂停发送（同时暂停OctoPrint）")
    print("  resume               - 恢复发送（同时恢复OctoPrint）")
    print("  stop                 - 停止发送（同时取消OctoPrint打印）")
    print("  status               - 显示打印机状态")
    print("  temps                - 显示温度信息")
    print("  progress             - 显示进度")
    print("  job                  - 显示OctoPrint作业状态")
    print("  diagnose             - 系统诊断")
    print("  quit                 - 退出程序")
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
                        print("请提供G-code指令")
                elif command == 'single_force':
                    if len(cmd) > 1:
                        result = sender.send_single_command(cmd[1], skip_dangerous=False)
                        print(f"强制发送{'成功' if result else '失败'}")
                    else:
                        print("请提供G-code指令")
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
                elif command == 'status':
                    status = sender.check_printer_status()
                    print(f"打印机状态: {json.dumps(status, indent=2)}")
                elif command == 'temps':
                    temps = sender.check_temperatures()
                    print(f"温度信息: {json.dumps(temps, indent=2)}")
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(f"进度信息: {json.dumps(progress, indent=2)}")
                elif command == 'job':
                    job_status = sender.get_job_status()
                    print(f"作业状态: {json.dumps(job_status, indent=2)}")
                elif command == 'diagnose':
                    sender.diagnose_system()
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