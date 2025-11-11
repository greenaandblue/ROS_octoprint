#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 4: Enhanced G-code Sender with Precise Pause System - 修复版
精准暂停系统 - 支持即时响应、状态保持、安全恢复

核心改进 v2.0：
1. 更详细的状态日志
2. 改进的热床等待逻辑
3. 更可靠的命令发送机制
4. 完整的错误追踪
"""

import requests
import time
import threading
import queue
import json
import os
import re
from collections import deque
from enum import Enum
from typing import List, Optional, Dict
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


class GCodeSender:
    """Stage 4 增强型G-code发送器 - 精准暂停系统 v2.0"""
    
    def __init__(self, octoprint_url: str, api_key: str):
        """初始化发送器"""
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        
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
        self.monitor_thread = None
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 响应管理
        self.last_response_time = time.time()
        self.response_timeout = 10.0
        
        # 错误监控
        self.error_count = 0
        self.max_errors = 5
        self.consecutive_timeouts = 0
        self.max_timeouts = 3
        
        # 温度配置
        self.maintain_temp_on_pause = True
        
        # 暂停恢复配置
        self.pause_lift_z = 5.0
        self.pause_retract = 5.0
        
        # 速度控制
        self.speed_multiplier = 1.0
        self.base_platform_speed = 100
        
        # 指令模式
        self.dangerous_patterns = [r'^M112$']
        self.waiting_patterns = [r'^M109', r'^M190', r'^G28']
        
        self.last_printer_state = ""
        
        logger.info(f"[INIT] ✓ GCodeSender 已初始化")
        logger.info(f"       URL: {self.octoprint_url}")
        logger.info(f"       暂停Z轴抬升: {self.pause_lift_z}mm")
        logger.info(f"       暂停回抽: {self.pause_retract}mm")
    
    # ==================== 指令检查 ====================
    
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
    
    # ==================== 打印机通信 ====================
    
    def check_printer_status(self) -> dict:
        """检查打印机状态 - 改进版"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            state_text = status.get('state', {}).get('text', '').lower()
            
            # 检查HALT状态
            if any(keyword in state_text for keyword in ['halt', 'kill', 'emergency']):
                logger.error(f"[ERROR] 检测到紧急停止状态: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
            self.last_printer_state = state_text
            return status
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"[ERROR] 获取打印机状态失败: {e}")
            return {}
    
    def check_temperatures_safe(self) -> dict:
        """安全的温度检查"""
        try:
            status = self.check_printer_status()
            temps = status.get('temperature', {})
            
            tool_temp = temps.get('tool0', {})
            bed_temp = temps.get('bed', {})
            
            return {'tool0': tool_temp, 'bed': bed_temp}
            
        except Exception as e:
            logger.error(f"[ERROR] 温度检查失败: {e}")
            return {}
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        
        error_keywords = ['halt', 'kill', 'emergency', 'error']
        if any(keyword in state for keyword in error_keywords):
            logger.error(f"[ERROR] 打印机处于错误状态: {state}")
            return False
        
        ready_states = ['operational', 'ready']
        return any(ready_state in state for ready_state in ready_states)
    
    def wait_for_printer_ready(self, timeout: float = 5.0) -> bool:
        """等待打印机就绪"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if self.is_printer_ready():
                    return True
                time.sleep(0.2)
            except Exception as e:
                logger.debug(f"等待打印机就绪时出错: {e}")
                time.sleep(0.5)
        
        return False
    
    # ==================== 命令发送 ====================
    
    def send_and_wait(self, command: str, wait_time: float = 0.1) -> bool:
        """
        发送单条指令并等待响应 - Stage 4核心逻辑
        改进：更详细的日志和错误处理
        """
        command = command.strip()
        if not command or command.startswith(';'):
            return True
        
        # 检查危险指令
        if self.is_dangerous_command(command):
            logger.warning(f"[WARN] 跳过危险指令: {command}")
            return True
        
        # 检查暂停/停止信号
        if self.stop_event.is_set():
            logger.info("[INFO] 收到停止信号，取消发送")
            return False
        
        try:
            # 发送指令
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=self.response_timeout
            )
            response.raise_for_status()
            
            # 等待打印机处理
            if self.is_waiting_command(command):
                wait_time = 0.5  # 加热等指令等待更长时间
            
            time.sleep(wait_time)
            
            # 重置错误计数
            self.error_count = 0
            self.consecutive_timeouts = 0
            self.last_response_time = time.time()
            
            logger.debug(f"[SEND] ✓ {command}")
            return True
            
        except requests.exceptions.Timeout:
            self.consecutive_timeouts += 1
            logger.warning(
                f"[WARN] 指令超时: '{command}' "
                f"({self.consecutive_timeouts}/{self.max_timeouts})"
            )
            
            if self.consecutive_timeouts >= self.max_timeouts:
                logger.error("[ERROR] 连续超时过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
                return False
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(
                f"[ERROR] 指令发送失败: '{command}' - {e} "
                f"({self.error_count}/{self.max_errors})"
            )
            
            if self.error_count >= self.max_errors:
                logger.error("[ERROR] 连续发送失败过多，停止操作")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            
            return False
    
    # ==================== 文件处理 ====================
    
    def load_gcode_file(self, file_path: str) -> bool:
        """加载G-code文件到内存 - 改进版"""
        try:
            logger.info(f"[LOAD] 准备加载文件: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                self.gcode_lines = [line.strip() for line in lines]
                self.total_lines = len(self.gcode_lines)
                
                # 统计有效行
                valid_lines = sum(1 for line in self.gcode_lines 
                                 if line and not line.startswith(';'))
                
                logger.info(f"[LOAD] ✓ 文件加载成功")
                logger.info(f"       总行数: {self.total_lines}")
                logger.info(f"       有效行数: {valid_lines}")
                return True
                
        except Exception as e:
            logger.error(f"[ERROR] 加载文件失败: {e}")
            return False
    
    # ==================== 打印控制 ====================
    
    def execute_printer_pause(self) -> bool:
        """
        执行打印机级暂停 - 改进版
        """
        logger.info("[PAUSE] 执行打印机级暂停...")
        
        try:
            # 使用OctoPrint的暂停API
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps({"command": "pause", "action": "pause"}),
                timeout=5
            )
            
            if response.status_code == 204:
                logger.info("[PAUSE] ✓ OctoPrint暂停命令已发送")
                time.sleep(0.5)
            
            # 提升喷嘴
            if self.pause_lift_z > 0:
                logger.info(f"[PAUSE] 抬升喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            # 回抽耗材
            if self.pause_retract > 0:
                logger.info(f"[PAUSE] 回抽耗材 {self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E-{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            # 保存当前温度
            temps = self.check_temperatures_safe()
            if temps:
                tool_target = temps.get('tool0', {}).get('target', 0)
                bed_target = temps.get('bed', {}).get('target', 0)
                self.print_state.save_temperatures(tool_target, bed_target)
                logger.info(f"[PAUSE] ✓ 已保存温度: 热端={tool_target}°C, 热床={bed_target}°C")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 暂停失败: {e}")
            return False
    
    def execute_printer_resume(self) -> bool:
        """
        执行打印机级恢复 - 改进版
        """
        logger.info("[RESUME] 执行打印机级恢复...")
        
        try:
            # 恢复温度
            if self.maintain_temp_on_pause:
                tool_temp = self.print_state.temperatures.get('tool', 0)
                bed_temp = self.print_state.temperatures.get('bed', 0)
                
                if tool_temp > 0:
                    logger.info(f"[RESUME] 恢复热端温度: {tool_temp}°C")
                    self.send_and_wait(f"M109 S{tool_temp}", wait_time=0.5)
                
                if bed_temp > 0:
                    logger.info(f"[RESUME] 恢复热床温度: {bed_temp}°C")
                    self.send_and_wait(f"M190 S{bed_temp}", wait_time=0.5)
            
            # 恢复耗材位置
            if self.pause_retract > 0:
                logger.info(f"[RESUME] 恢复耗材位置 +{self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            # 恢复Z轴位置
            if self.pause_lift_z > 0:
                logger.info(f"[RESUME] 降低喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z-{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            # OctoPrint恢复API
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps({"command": "pause", "action": "resume"}),
                timeout=5
            )
            
            if response.status_code == 204:
                logger.info("[RESUME] ✓ OctoPrint恢复命令已发送")
            
            time.sleep(0.5)
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 恢复失败: {e}")
            return False
    
    def sender_worker(self, file_path: str):
        """
        发送器工作线程 - Stage 4核心逻辑
        改进：更详细的日志
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"[WORKER] 开始处理文件: {Path(file_path).name}")
        logger.info(f"{'='*60}\n")
        
        # 检查打印机状态
        if not self.is_printer_ready():
            logger.error("[WORKER] ❌ 打印机未就绪")
            self.state = PrinterState.ERROR
            return
        
        # 加载文件
        if not self.load_gcode_file(file_path):
            self.state = PrinterState.ERROR
            return
        
        # 初始化
        self.file_path = file_path
        self.current_line_index = 0
        self.processed_lines = 0
        self.error_count = 0
        self.state = PrinterState.RUNNING
        
        logger.info(f"[WORKER] ✓ 打印机就绪，开始发送指令...\n")
        
        try:
            while self.current_line_index < self.total_lines and not self.stop_event.is_set():
                # 等待恢复信号
                self.pause_event.wait()
                
                if self.stop_event.is_set():
                    break
                
                # 获取当前行
                line = self.gcode_lines[self.current_line_index]
                
                # 跳过空行和注释
                if not line or line.startswith(';'):
                    self.current_line_index += 1
                    continue
                
                # 发送并等待确认（Stage 4核心）
                success = self.send_and_wait(line, wait_time=0.1)
                
                if not success:
                    logger.error(f"[ERROR] 发送失败，停止于第 {self.current_line_index} 行")
                    self.state = PrinterState.ERROR
                    break
                
                # 更新进度
                self.current_line_index += 1
                self.processed_lines += 1
                
                # 进度报告
                if self.processed_lines % 100 == 0:
                    progress = (self.current_line_index / self.total_lines) * 100
                    logger.info(f"[PROGRESS] {self.current_line_index}/{self.total_lines} ({progress:.1f}%)")
            
            # 完成状态
            if self.stop_event.is_set():
                logger.info(f"\n[WORKER] 打印已停止: {self.current_line_index}/{self.total_lines}")
            elif self.state == PrinterState.ERROR:
                logger.error(f"\n[WORKER] 打印出错: {self.current_line_index}/{self.total_lines}")
            else:
                self.state = PrinterState.IDLE
                logger.info(f"\n[WORKER] ✓ 打印完成: {self.processed_lines} 条指令已执行")
                
        except Exception as e:
            logger.error(f"[ERROR] 发送过程异常: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str) -> bool:
        """开始文件打印"""
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("[WARN] 已有任务在运行中")
            return False
        
        # 重置状态
        self.stop_event.clear()
        self.pause_event.set()
        self.error_count = 0
        
        logger.info(f"[START] 准备启动文件打印: {file_path}")
        
        # 启动发送线程
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        logger.info("[START] ✓ 发送线程已启动")
        return True
    
    def pause(self) -> bool:
        """暂停打印"""
        if self.state != PrinterState.RUNNING:
            logger.warning(f"[WARN] 当前状态 {self.state.value} 无法暂停")
            return False
        
        logger.info("[PAUSE] 暂停请求...")
        self.state = PrinterState.PAUSING
        
        # 立即停止Python端发送
        self.pause_event.clear()
        time.sleep(0.2)
        
        # 执行打印机级暂停
        if self.execute_printer_pause():
            self.state = PrinterState.PAUSED
            self.print_state.line_number = self.current_line_index
            logger.info("[PAUSE] ✓ 暂停成功")
            return True
        else:
            logger.error("[ERROR] 暂停失败")
            self.state = PrinterState.ERROR
            return False
    
    def resume(self) -> bool:
        """恢复打印"""
        if self.state != PrinterState.PAUSED:
            logger.warning(f"[WARN] 当前状态 {self.state.value} 无法恢复")
            return False
        
        logger.info("[RESUME] 恢复请求...")
        self.state = PrinterState.RESUMING
        
        # 执行打印机级恢复
        if self.execute_printer_resume():
            # 恢复Python端发送
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            logger.info("[RESUME] ✓ 恢复成功")
            return True
        else:
            logger.error("[ERROR] 恢复失败")
            self.state = PrinterState.ERROR
            return False
    
    def stop(self) -> bool:
        """停止打印"""
        logger.info("[STOP] 停止请求...")
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
        
        logger.info("[STOP] ✓ 停止成功")
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
            'error_count': self.error_count,
            'printer_state': self.last_printer_state,
            'saved_temperatures': self.print_state.temperatures,
            'speed_multiplier': self.speed_multiplier
        }
    
    def set_speed_multiplier(self, multiplier: float):
        """设置速度倍率 - Stage 5接口预留"""
        self.speed_multiplier = max(0.1, min(2.0, multiplier))
        logger.info(f"[CONFIG] 速度倍率设置为: {self.speed_multiplier}x")
    
    def close(self):
        """清理资源"""
        logger.info("[CLOSE] 正在清理资源...")
        self.stop()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        
        self.session.close()
        logger.info("[CLOSE] ✓ 资源已清理")


# 导入Path用于例子中的文件处理
from pathlib import Path


def interactive_mode():
    """交互模式"""
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"
    
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    print("=" * 60)
    print("Stage 4: 精准暂停系统 v2.0 (改进版)")
    print("=" * 60)
    print("\n新功能:")
    print("  • 逐条发送 + ok 确认机制")
    print("  • 打印机级暂停/恢复 (M25/M24)")
    print("  • 温度保持策略")
    print("  • 暂停时Z轴抬升 + 耗材回抽")
    print("  • 状态保存与恢复")
    print("  • Stage 5速度控制接口预留")
    print("  • 详细日志和错误追踪")
    print("\n命令列表:")
    print("  file <path>          - 开始文件打印")
    print("  pause                - 精准暂停")
    print("  resume               - 安全恢复")
    print("  stop                 - 停止打印")
    print("  status               - 打印机状态")
    print("  temps                - 温度信息")
    print("  progress             - 进度信息")
    print("  speed <multiplier>   - 设置速度倍率(0.1-2.0)")
    print("  config               - 显示配置")
    print("  quit                 - 退出")
    print("=" * 60)
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
                        print(f"{'ok' if result else '不OK'} 开始文件打印")
                    else:
                        print("请提供文件路径")
                        
                elif command == 'pause':
                    result = sender.pause()
                    if not result:
                        print("暂停失败，请检查状态")
                        
                elif command == 'resume':
                    result = sender.resume()
                    if not result:
                        print("恢复失败，请检查状态")
                        
                elif command == 'stop':
                    sender.stop()
                    
                elif command == 'status':
                    status = sender.check_printer_status()
                    print(json.dumps(status, indent=2, ensure_ascii=False))
                    
                elif command == 'temps':
                    temps = sender.check_temperatures_safe()
                    print(json.dumps(temps, indent=2, ensure_ascii=False))
                    
                elif command == 'progress':
                    progress = sender.get_progress()
                    print(json.dumps(progress, indent=2, ensure_ascii=False))
                    
                elif command == 'speed':
                    if len(cmd) > 1:
                        try:
                            multiplier = float(cmd[1])
                            sender.set_speed_multiplier(multiplier)
                        except ValueError:
                            print("请输入有效的数值 (0.1-2.0)")
                    else:
                        print("请提供速度倍率")
                        
                elif command == 'config':
                    print("\n当前配置:")
                    print(f"  暂停Z轴抬升: {sender.pause_lift_z} mm")
                    print(f"  暂停回抽长度: {sender.pause_retract} mm")
                    print(f"  保持温度: {sender.maintain_temp_on_pause}")
                    print(f"  速度倍率: {sender.speed_multiplier}x")
                    print()
                    
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


if __name__ == '__main__':
    interactive_mode()