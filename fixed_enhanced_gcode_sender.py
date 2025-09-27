#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced G-code Sender for OctoPrint
修复了挤出、pause/resume反馈和文件处理问题
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


class GCodeSender:
    """增强型G-code发送器"""
    
    def __init__(self, octoprint_url: str, api_key: str, buffer_size: int = 30):
        """
        初始化G-code发送器
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
        self.processed_lines = 0  # 实际处理的行数
        
        # 线程控制
        self.sender_thread = None
        self.command_queue = queue.Queue()
        
        # 请求会话（复用连接提高效率）
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 调整危险指令过滤器 - 只过滤真正危险的指令，保留必要的T指令
        self.dangerous_patterns = [
            r'^M109\s+S0$',   # 关闭加热器的指令
            r'^M190\s+S0$',   # 关闭热床的指令
            r'^M84$',         # 关闭步进电机
            r'^M18$',         # 关闭步进电机
        ]
        
        # 需要特殊处理的指令
        self.special_patterns = [
            r'^T\d+$',        # 工具选择指令 - 不过滤但记录
            r'^G28',          # 归零指令 - 不过滤但记录
            r'^M104',         # 设置热端温度
            r'^M109',         # 等待热端加热
            r'^M140',         # 设置热床温度  
            r'^M190',         # 等待热床加热
        ]
        
        self.has_active_job = False
    
    def is_dangerous_command(self, command: str) -> bool:
        """检查指令是否真正危险（需要过滤）"""
        command = command.strip().upper()
        for pattern in self.dangerous_patterns:
            if re.match(pattern, command):
                return True
        return False
    
    def is_special_command(self, command: str) -> bool:
        """检查指令是否需要特殊处理"""
        command = command.strip().upper()
        for pattern in self.special_patterns:
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
    
    def get_job_status(self) -> dict:
        """获取OctoPrint作业状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/job')
            response.raise_for_status()
            job_data = response.json()
            
            # 检查是否有活动作业
            job_state = job_data.get('state', '').lower()
            self.has_active_job = job_state in ['printing', 'paused']
            
            return job_data
        except requests.exceptions.RequestException as e:
            logger.error(f"获取作业状态失败: {e}")
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
        ready_states = ['operational', 'ready', 'printing', 'paused']
        return any(ready_state in state for ready_state in ready_states)
    
    def send_manual_pause(self) -> bool:
        """发送手动暂停指令（M0）"""
        try:
            result = self.send_single_command("M0", skip_dangerous=False)
            if result:
                logger.info("发送手动暂停指令(M0)成功")
            return result
        except Exception as e:
            logger.error(f"发送手动暂停指令失败: {e}")
            return False
    
    def octoprint_pause_print(self) -> bool:
        """通过OctoPrint API暂停打印"""
        # 先检查作业状态
        job_status = self.get_job_status()
        job_state = job_status.get('state', '').lower()
        
        if job_state == 'printing':
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
                # 尝试发送手动暂停指令
                return self.send_manual_pause()
        else:
            logger.info(f"当前作业状态({job_state})不支持暂停，使用手动暂停")
            return self.send_manual_pause()
    
    def octoprint_resume_print(self) -> bool:
        """通过OctoPrint API恢复打印"""
        job_status = self.get_job_status()
        job_state = job_status.get('state', '').lower()
        
        if job_state == 'paused':
            try:
                data = {"command": "pause"}  # OctoPrint使用同一个命令切换
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
        else:
            logger.info(f"当前作业状态({job_state})不需要恢复")
            return True
    
    def octoprint_cancel_print(self) -> bool:
        """通过OctoPrint API取消打印"""
        job_status = self.get_job_status()
        job_state = job_status.get('state', '').lower()
        
        if job_state in ['printing', 'paused']:
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
        else:
            logger.info(f"当前作业状态({job_state})无需取消")
            return True
    
    def send_single_command(self, command: str, skip_dangerous: bool = True) -> bool:
        """发送单条G-code指令"""
        command = command.strip()
        if not command:
            return True
        
        # 检查是否为真正危险的指令
        if skip_dangerous and self.is_dangerous_command(command):
            logger.warning(f"跳过危险指令: {command}")
            return True
        
        # 记录特殊指令但不跳过
        if self.is_special_command(command):
            logger.info(f"发送特殊指令: {command}")
        
        try:
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=10
            )
            response.raise_for_status()
            logger.debug(f"发送指令成功: {command}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"发送指令失败 '{command}': {e}")
            return False
    
    def send_batch_commands(self, commands: List[str], skip_dangerous: bool = True) -> bool:
        """批量发送G-code指令"""
        if not commands:
            return True
        
        try:
            valid_commands = []
            skipped_count = 0
            special_count = 0
            
            for cmd in commands:
                cmd = cmd.strip()
                if not cmd or cmd.startswith(';'):
                    continue
                
                # 只跳过真正危险的指令
                if skip_dangerous and self.is_dangerous_command(cmd):
                    skipped_count += 1
                    logger.debug(f"跳过危险指令: {cmd}")
                    continue
                
                # 记录特殊指令但不跳过
                if self.is_special_command(cmd):
                    special_count += 1
                    logger.debug(f"处理特殊指令: {cmd}")
                
                valid_commands.append(cmd)
            
            if skipped_count > 0:
                logger.info(f"跳过了 {skipped_count} 条危险指令")
            if special_count > 0:
                logger.info(f"处理了 {special_count} 条特殊指令（工具切换、温度控制等）")
            
            if not valid_commands:
                return True
            
            # 分小批次发送，避免超时
            batch_size = 3
            for i in range(0, len(valid_commands), batch_size):
                batch = valid_commands[i:i+batch_size]
                
                data = {"commands": batch}
                response = self.session.post(
                    f'{self.octoprint_url}/api/printer/command',
                    data=json.dumps(data),
                    timeout=15
                )
                response.raise_for_status()
                logger.debug(f"批量发送 {len(batch)} 条指令成功")
                
                # 小延迟避免过载
                time.sleep(0.02)
            
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"批量发送指令失败: {e}")
            return False
    
    def load_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """高效加载G-code文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
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
        """填充缓冲区"""
        added_lines = 0
        try:
            while added_lines < self.buffer_size and len(self.gcode_buffer) < self.buffer_size * 2:
                line = next(gcode_generator)
                self.current_line += 1  # 移到这里统计总行数
                
                if line and not line.startswith(';'):  # 跳过空行和注释
                    self.gcode_buffer.append(line)
                    added_lines += 1
            return True
        except StopIteration:
            logger.info(f"文件读取完毕，总共读取 {self.current_line} 行")
            return False  # 文件读取完毕
    
    def sender_worker(self, file_path: str):
        """发送器工作线程"""
        logger.info(f"开始处理文件: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            self.state = PrinterState.ERROR
            return
        
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
        self.processed_lines = 0
        self.state = PrinterState.RUNNING
        
        logger.info(f"文件总行数: {self.total_lines}")
        
        gcode_generator = self.load_gcode_file(file_path)
        has_more_data = True
        
        # 预填充缓冲区
        has_more_data = self.fill_buffer(gcode_generator)
        
        batch_commands = []
        
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
                    self.processed_lines += 1
                    
                    # 当批次满或缓冲区空时发送
                    if len(batch_commands) >= 3 or (not self.gcode_buffer and batch_commands):
                        success = self.send_batch_commands(batch_commands, skip_dangerous=True)
                        
                        if not success:
                            logger.error("发送失败，停止执行")
                            self.state = PrinterState.ERROR
                            break
                        
                        batch_commands.clear()
                        
                        # 进度报告
                        if self.processed_lines % 100 == 0:
                            progress = (self.current_line / self.total_lines) * 100
                            logger.info(f"进度: {self.current_line}/{self.total_lines} ({progress:.1f}%) - 已处理指令: {self.processed_lines}")
                
                # 重新填充缓冲区
                if len(self.gcode_buffer) < self.buffer_size // 2 and has_more_data:
                    has_more_data = self.fill_buffer(gcode_generator)
                
                # 适当延迟
                time.sleep(0.05)
            
            # 发送剩余的批量指令
            if batch_commands and not self.stop_event.is_set():
                self.send_batch_commands(batch_commands, skip_dangerous=True)
            
            if not self.stop_event.is_set():
                self.state = PrinterState.IDLE
                logger.info(f"文件处理完成: {self.current_line}/{self.total_lines} 行读取，{self.processed_lines} 条指令已处理")
            else:
                logger.info(f"处理已停止: {self.current_line}/{self.total_lines} 行读取，{self.processed_lines} 条指令已处理")
                
        except Exception as e:
            logger.error(f"发送过程中出错: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str):
        """开始打印G-code文件"""
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
            # 暂停本地发送
            self.pause_event.clear()
            self.state = PrinterState.PAUSED
            
            # 尝试向OctoPrint发送暂停指令
            octo_result = self.octoprint_pause_print()
            
            if octo_result:
                logger.info("✓ 本地暂停成功，OctoPrint暂停指令发送成功")
            else:
                logger.warning("⚠ 本地暂停成功，但OctoPrint暂停指令发送失败")
    
    def resume(self):
        """恢复发送"""
        if self.state == PrinterState.PAUSED:
            # 尝试向OctoPrint发送恢复指令
            octo_result = self.octoprint_resume_print()
            
            # 恢复本地发送
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            
            if octo_result:
                logger.info("✓ 本地恢复成功，OctoPrint恢复指令发送成功")
            else:
                logger.warning("⚠ 本地恢复成功，但OctoPrint恢复指令发送失败")
    
    def stop(self):
        """停止发送"""
        # 尝试向OctoPrint发送取消指令
        octo_result = self.octoprint_cancel_print()
        
        # 停止本地发送
        self.stop_event.set()
        self.pause_event.set()  # 确保线程能够退出
        self.state = PrinterState.STOPPED
        
        if octo_result:
            logger.info("✓ 本地停止成功，OctoPrint取消指令发送成功")
        else:
            logger.warning("⚠ 本地停止成功，但OctoPrint取消指令发送失败")
    
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
            'has_active_octoprint_job': self.has_active_job
        }
    
    def diagnose_system(self):
        """系统诊断"""
        logger.info("=== 系统诊断 ===")
        
        # 检查打印机状态
        printer_status = self.check_printer_status()
        printer_state = printer_status.get('state', {}).get('text', 'Unknown')
        logger.info(f"打印机状态: {printer_state}")
        
        # 检查温度
        temps = self.check_temperatures()
        tool_temp = temps['tool0']
        bed_temp = temps['bed']
        logger.info(f"热端温度: 实际={tool_temp.get('actual', 'N/A')}°C, 目标={tool_temp.get('target', 'N/A')}°C")
        logger.info(f"热床温度: 实际={bed_temp.get('actual', 'N/A')}°C, 目标={bed_temp.get('target', 'N/A')}°C")
        
        # 检查作业状态
        job_status = self.get_job_status()
        job_state = job_status.get('state', 'Unknown')
        logger.info(f"OctoPrint作业状态: {job_state}")
        
        # 检查是否有活动作业
        logger.info(f"是否有活动作业: {self.has_active_job}")
        
        # 检查当前进度
        progress = self.get_progress()
        logger.info(f"当前发送进度: {progress['current_line']}/{progress['total_lines']} ({progress['progress_percent']}%)")
        logger.info(f"已处理指令数: {progress['processed_commands']}")
        
        # 检查网络连接
        try:
            response = self.session.get(f'{self.octoprint_url}/api/version', timeout=5)
            if response.status_code == 200:
                version_info = response.json()
                logger.info(f"OctoPrint版本: {version_info.get('server', 'Unknown')}")
            else:
                logger.warning(f"连接OctoPrint异常，状态码: {response.status_code}")
        except Exception as e:
            logger.error(f"无法连接到OctoPrint: {e}")
    
    def close(self):
        """清理资源"""
        self.stop()
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        self.session.close()


def interactive_mode():
    """交互模式"""
    # 配置信息（请修改为你的实际配置）
    OCTOPRINT_URL = "http://192.168.1.100"  # 修改为你的OctoPrint地址
    API_KEY = "YOUR_API_KEY_HERE"  # 修改为你的API密钥
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("=== Enhanced G-code Sender v2.1 ===")
    print("修复内容:")
    print("- 保留T指令（工具切换）和温度控制指令")
    print("- 改进pause/resume反馈显示")
    print("- 修复文件处理逻辑")
    print("- 增加详细的诊断信息")
    print()
    print("命令列表:")
    print("  single <command>     - 发送单条G-code指令")
    print("  single_force <cmd>   - 强制发送指令（不过滤任何指令）")
    print("  file <path>          - 开始发送G-code文件")
    print("  pause                - 暂停发送（会显示详细反馈）")
    print("  resume               - 恢复发送（会显示详细反馈）")
    print("  stop                 - 停止发送（会显示详细反馈）")
    print("  status               - 显示打印机状态")
    print("  temps                - 显示温度信息")
    print("  progress             - 显示进度")
    print("  job                  - 显示OctoPrint作业状态")
    print("  diagnose             - 系统诊断")
    print("  test_extrude         - 测试挤出（发送E10指令）")
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
                    print(f"打印机状态: {json.dumps(status, indent=2, ensure_ascii=False)}")
                elif command == 'temps':
                    temps = sender.check_temperatures()
                    print(f"温度信息: {json.dumps(temps, indent=2, ensure_ascii=False)}")
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(f"进度信息: {json.dumps(progress, indent=2, ensure_ascii=False)}")
                elif command == 'job':
                    job_status = sender.get_job_status()
                    print(f"作业状态: {json.dumps(job_status, indent=2, ensure_ascii=False)}")
                elif command == 'diagnose':
                    sender.diagnose_system()
                elif command == 'test_extrude':
                    print("测试挤出10mm耗材...")
                    sender.send_single_command("G91", skip_dangerous=False)  # 相对坐标
                    result = sender.send_single_command("G1 E10 F300", skip_dangerous=False)  # 挤出10mm
                    sender.send_single_command("G90", skip_dangerous=False)  # 绝对坐标
                    print(f"测试挤出{'成功' if result else '失败'}")
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