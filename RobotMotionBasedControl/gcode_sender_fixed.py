#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 4: Enhanced G-code Sender with Precise Pause System
FIXED VERSION: 移除床加热等待阻塞问题
改进：
1. 床加热等待不再阻塞主线程
2. 支持后台等待床加热
3. 与Stage 6机器人速度控制兼容
"""

import requests
import time
import threading
import json
import os
import re
from enum import Enum
from typing import List, Optional, Dict, Callable
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PrinterState(Enum):
    """打印机状态枚举"""
    IDLE = "idle"
    WAITING_BED = "waiting_bed"      # 等待床加热
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
    """Stage 4 增强型G-code发送器 - 修复版"""
    
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
        self.bed_heat_thread = None  # 单独的床加热线程
        
        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # ok响应等待
        self.last_response_time = time.time()
        self.response_timeout = 10.0
        
        # 错误监控
        self.error_count = 0
        self.max_errors = 5
        self.consecutive_timeouts = 0
        self.max_timeouts = 3
        
        # 温度保持配置
        self.maintain_temp_on_pause = True
        
        # 暂停恢复配置
        self.pause_lift_z = 5.0
        self.pause_retract = 5.0
        
        # 床加热配置 - FIXED: 移除会阻塞的配置
        self.target_bed_temp = 0
        self.bed_heating_tolerance = 5.0
        self.bed_heat_complete = False
        self.skip_bed_heat_wait = False  # 可选：跳过床加热等待
        
        # Stage 5 接口
        self.speed_multiplier = 1.0
        self.base_platform_speed = 100
        
        # 危险指令模式
        self.dangerous_patterns = [r'^M112$']
        
        # 需要等待的指令
        self.waiting_patterns = [r'^M109', r'^M190', r'^G28']
        
        self.last_printer_state = ""
        
        # 回调函数 - 用于与Stage 6集成
        self.on_bed_heat_complete: Optional[Callable] = None
        self.on_print_complete: Optional[Callable] = None
        
        logger.info("[INIT] ✓ GCodeSender 已初始化")
    
    # ==================== 工具方法 ====================
    
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
    
    def extract_bed_temperature_from_gcode(self) -> Optional[float]:
        """从G-code文件中提取目标床温度"""
        for line in self.gcode_lines[:100]:
            line = line.strip().upper()
            if 'M140' in line or 'M190' in line:
                match = re.search(r'S(\d+)', line)
                if match:
                    bed_temp = float(match.group(1))
                    logger.info(f"[FILE] 提取床温: {bed_temp}°C")
                    return bed_temp
        
        logger.warning("[FILE] G-code中未找到床温设置")
        return None
    
    # ==================== 打印机通信 ====================
    
    def check_printer_status(self) -> dict:
        """检查打印机状态"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printer', timeout=5)
            response.raise_for_status()
            status = response.json()
            
            state_text = status.get('state', {}).get('text', '').lower()
            
            if 'halt' in state_text or 'kill' in state_text:
                logger.error(f"[STATUS] 检测到紧急停止: {state_text}")
                self.state = PrinterState.HALTED
                self.stop_event.set()
            
            self.last_printer_state = state_text
            return status
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[STATUS] 获取状态失败: {e}")
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
            logger.error(f"[TEMP] 温度检查失败: {e}")
            return {}
    
    def is_printer_ready(self) -> bool:
        """检查打印机是否准备就绪"""
        status = self.check_printer_status()
        state = status.get('state', {}).get('text', '').lower()
        
        error_keywords = ['halt', 'kill', 'emergency', 'error']
        if any(keyword in state for keyword in error_keywords):
            logger.error(f"[READY] 打印机错误状态: {state}")
            return False
        
        ready_states = ['operational', 'ready']
        return any(ready_state in state for ready_state in ready_states)
    
    def send_and_wait(self, command: str, wait_time: float = 0.1) -> bool:
        """发送单条指令并等待响应"""
        command = command.strip()
        if not command or command.startswith(';'):
            return True
        
        if self.is_dangerous_command(command):
            logger.warning(f"[CMD] 跳过危险指令: {command}")
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
            self.last_response_time = time.time()
            
            logger.debug(f"[CMD] ✓ {command}")
            return True
            
        except requests.exceptions.Timeout:
            self.consecutive_timeouts += 1
            logger.warning(f"[CMD] 超时 '{command}' ({self.consecutive_timeouts}/{self.max_timeouts})")
            
            if self.consecutive_timeouts >= self.max_timeouts:
                logger.error("[CMD] 连续超时过多")
                self.state = PrinterState.ERROR
                self.stop_event.set()
                return False
            return True
            
        except requests.exceptions.RequestException as e:
            self.error_count += 1
            logger.error(f"[CMD] 发送失败 '{command}': {e}")
            
            if self.error_count >= self.max_errors:
                logger.error("[CMD] 连续失败过多")
                self.state = PrinterState.ERROR
                self.stop_event.set()
            return False
    
    # ==================== 床加热等待 - 非阻塞版本 ====================
    
    def _bed_heat_worker(self):
        """
        后台床加热等待线程 - 不阻塞主线程
        FIXED: 这是独立线程，不会阻塞sender_worker
        """
        if self.target_bed_temp <= 0:
            logger.info("[BED] 无需加热，直接开始")
            self.bed_heat_complete = True
            if self.on_bed_heat_complete:
                self.on_bed_heat_complete()
            return
        
        logger.info(f"[BED] 等待床加热至 {self.target_bed_temp}°C...")
        self.state = PrinterState.WAITING_BED
        
        start_time = time.time()
        last_log_time = start_time
        bed_stabilize_count = 0
        timeout = 600.0
        
        while time.time() - start_time < timeout and not self.stop_event.is_set():
            try:
                temps = self.check_temperatures_safe()
                bed_temp_data = temps.get('bed', {})
                current_temp = bed_temp_data.get('actual', 0)
                target_temp = bed_temp_data.get('target', self.target_bed_temp)
                
                # 定期日志输出
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    elapsed = int(current_time - start_time)
                    logger.info(f"[BED] {elapsed:3d}s | 温度: {current_temp:.1f}°C / {target_temp:.1f}°C")
                    last_log_time = current_time
                
                # 检查是否达到目标温度
                if current_temp >= (self.target_bed_temp - self.bed_heating_tolerance):
                    bed_stabilize_count += 1
                    if bed_stabilize_count >= 3:
                        logger.info(f"[BED] ✓ 床已加热到 {current_temp:.1f}°C")
                        self.bed_heat_complete = True
                        if self.on_bed_heat_complete:
                            self.on_bed_heat_complete()
                        return
                else:
                    bed_stabilize_count = 0
                
                time.sleep(2)
                
            except Exception as e:
                logger.warning(f"[BED] 温度检查失败: {e}")
                time.sleep(2)
        
        if self.stop_event.is_set():
            logger.info("[BED] 用户取消床加热等待")
        else:
            logger.error(f"[BED] 超时：床加热超过 {timeout}s 未完成")
        
        self.bed_heat_complete = False
    
    def start_bed_heat_wait(self):
        """启动后台床加热等待 - 非阻塞"""
        if self.bed_heat_thread and self.bed_heat_thread.is_alive():
            logger.warning("[BED] 床加热等待已在运行")
            return False
        
        self.bed_heat_thread = threading.Thread(
            target=self._bed_heat_worker,
            daemon=True
        )
        self.bed_heat_thread.start()
        logger.info("[BED] 后台床加热等待已启动")
        return True
    
    def is_bed_heat_complete(self) -> bool:
        """检查床加热是否完成"""
        return self.bed_heat_complete
    
    # ==================== 暂停/恢复 ====================
    
    def execute_printer_pause(self) -> bool:
        """执行打印机级暂停"""
        logger.info("[PAUSE] 执行暂停...")
        
        try:
            response = self.session.post(
                f'{self.octoprint_url}/api/job',
                data=json.dumps({"command": "pause", "action": "pause"}),
                timeout=5
            )
            
            if response.status_code == 204:
                logger.info("[PAUSE] ✓ OctoPrint暂停命令已发送")
                time.sleep(0.5)
            
            if self.pause_lift_z > 0:
                logger.info(f"[PAUSE] 抬升喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            if self.pause_retract > 0:
                logger.info(f"[PAUSE] 回抽耗材 {self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E-{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            temps = self.check_temperatures_safe()
            if temps:
                tool_target = temps.get('tool0', {}).get('target', 0)
                bed_target = temps.get('bed', {}).get('target', 0)
                self.print_state.save_temperatures(tool_target, bed_target)
                logger.info(f"[PAUSE] 已保存温度: 热端={tool_target}°C, 热床={bed_target}°C")
            
            return True
            
        except Exception as e:
            logger.error(f"[PAUSE] 暂停失败: {e}")
            return False
    
    def execute_printer_resume(self) -> bool:
        """执行打印机级恢复"""
        logger.info("[RESUME] 执行恢复...")
        
        try:
            if self.maintain_temp_on_pause:
                tool_temp = self.print_state.temperatures.get('tool', 0)
                bed_temp = self.print_state.temperatures.get('bed', 0)
                
                if tool_temp > 0:
                    logger.info(f"[RESUME] 恢复热端温度: {tool_temp}°C")
                    self.send_and_wait(f"M109 S{tool_temp}", wait_time=0.5)
                
                if bed_temp > 0:
                    logger.info(f"[RESUME] 恢复热床温度: {bed_temp}°C")
                    self.send_and_wait(f"M190 S{bed_temp}", wait_time=0.5)
            
            if self.pause_retract > 0:
                logger.info(f"[RESUME] 恢复耗材位置 +{self.pause_retract}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 E{self.pause_retract} F1800", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
            if self.pause_lift_z > 0:
                logger.info(f"[RESUME] 降低喷嘴 {self.pause_lift_z}mm")
                self.send_and_wait("G91", wait_time=0.05)
                self.send_and_wait(f"G1 Z-{self.pause_lift_z} F300", wait_time=0.2)
                self.send_and_wait("G90", wait_time=0.05)
            
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
            logger.error(f"[RESUME] 恢复失败: {e}")
            return False
    
    def pause(self) -> bool:
        """暂停打印"""
        if self.state not in [PrinterState.RUNNING, PrinterState.WAITING_BED]:
            logger.warning(f"[PAUSE] 当前状态 {self.state.value} 无法暂停")
            return False
        
        logger.info("[PAUSE] 暂停请求...")
        self.state = PrinterState.PAUSING
        
        self.pause_event.clear()
        time.sleep(0.2)
        
        if self.execute_printer_pause():
            self.state = PrinterState.PAUSED
            logger.info("[PAUSE] ✓ 暂停成功")
            self.print_state.line_number = self.current_line_index
            return True
        else:
            logger.error("[PAUSE] ✗ 暂停失败")
            self.state = PrinterState.ERROR
            return False
    
    def resume(self) -> bool:
        """恢复打印"""
        if self.state != PrinterState.PAUSED:
            logger.warning(f"[RESUME] 当前状态 {self.state.value} 无法恢复")
            return False
        
        logger.info("[RESUME] 恢复请求...")
        self.state = PrinterState.RESUMING
        
        if self.execute_printer_resume():
            self.pause_event.set()
            self.state = PrinterState.RUNNING
            logger.info("[RESUME] ✓ 恢复成功")
            return True
        else:
            logger.error("[RESUME] ✗ 恢复失败")
            self.state = PrinterState.ERROR
            return False
    
    # ==================== 文件操作 ====================
    
    def load_gcode_file(self, file_path: str) -> bool:
        """加载G-code文件到内存"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                self.gcode_lines = [line.strip() for line in file]
                self.total_lines = len(self.gcode_lines)
                logger.info(f"[FILE] ✓ 加载完成: {self.total_lines} 行")
                
                self.target_bed_temp = self.extract_bed_temperature_from_gcode() or 0
                
                return True
        except Exception as e:
            logger.error(f"[FILE] 加载失败: {e}")
            return False
    
    def sender_worker(self, file_path: str):
        """
        发送器工作线程 - FIXED版本
        关键改进：不再阻塞床加热等待
        """
        logger.info(f"[WORKER] 开始处理文件: {file_path}")
        
        if not self.is_printer_ready():
            logger.error("[WORKER] 打印机未就绪")
            self.state = PrinterState.ERROR
            return
        
        if not self.load_gcode_file(file_path):
            self.state = PrinterState.ERROR
            return
        
        self.file_path = file_path
        self.current_line_index = 0
        self.processed_lines = 0
        self.error_count = 0
        
        # FIXED: 启动后台床加热等待，不阻塞
        logger.info("[WORKER] 启动后台床加热等待...")
        self.start_bed_heat_wait()
        
        self.state = PrinterState.RUNNING
        
        try:
            while self.current_line_index < self.total_lines and not self.stop_event.is_set():
                self.pause_event.wait()
                
                if self.stop_event.is_set():
                    break
                
                line = self.gcode_lines[self.current_line_index]
                
                if not line or line.startswith(';'):
                    self.current_line_index += 1
                    continue
                
                success = self.send_and_wait(line, wait_time=0.1)
                
                if not success:
                    logger.error(f"[WORKER] 发送失败，停止于第 {self.current_line_index} 行")
                    self.state = PrinterState.ERROR
                    break
                
                self.current_line_index += 1
                self.processed_lines += 1
                
                if self.processed_lines % 100 == 0:
                    progress = (self.current_line_index / self.total_lines) * 100
                    logger.info(f"[PROGRESS] {self.current_line_index}/{self.total_lines} ({progress:.1f}%)")
            
            if self.stop_event.is_set():
                logger.info(f"[WORKER] 打印已停止")
            elif self.state == PrinterState.ERROR:
                logger.error(f"[WORKER] 打印出错")
            else:
                self.state = PrinterState.IDLE
                logger.info(f"[WORKER] ✓ 打印完成: {self.processed_lines} 条指令")
                if self.on_print_complete:
                    self.on_print_complete()
                
        except Exception as e:
            logger.error(f"[WORKER] 异常: {e}")
            self.state = PrinterState.ERROR
    
    def start_file_print(self, file_path: str) -> bool:
        """开始文件打印"""
        if self.sender_thread and self.sender_thread.is_alive():
            logger.warning("[PRINT] 已有任务在运行中")
            return False
        
        self.stop_event.clear()
        self.pause_event.set()
        self.error_count = 0
        self.bed_heat_complete = False
        
        self.sender_thread = threading.Thread(
            target=self.sender_worker,
            args=(file_path,),
            daemon=True
        )
        self.sender_thread.start()
        logger.info("[PRINT] ✓ 打印线程已启动")
        return True
    
    def stop(self):
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
        
        logger.info("[STOP] ✓ 已停止")
    
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
            'target_bed_temp': self.target_bed_temp,
            'bed_heat_complete': self.bed_heat_complete,
            'speed_multiplier': self.speed_multiplier
        }
    
    def set_speed_multiplier(self, multiplier: float):
        """设置速度倍率"""
        self.speed_multiplier = max(0.1, min(2.0, multiplier))
        logger.info(f"[CONFIG] 速度倍率: {self.speed_multiplier}x")
    
    def set_bed_temp_override(self, temp: float):
        """手动设置床温度"""
        self.target_bed_temp = max(0, temp)
        logger.info(f"[CONFIG] 目标床温: {self.target_bed_temp}°C")
    
    def close(self):
        """清理资源"""
        logger.info("[CLOSE] 正在清理资源...")
        self.stop()
        
        if self.sender_thread:
            self.sender_thread.join(timeout=10)
        
        if self.bed_heat_thread:
            self.bed_heat_thread.join(timeout=5)
        
        self.session.close()
        logger.info("[CLOSE] ✓ 已清理")