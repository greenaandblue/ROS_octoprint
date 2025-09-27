#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
告诉系统用 Python3 来运行这个脚本
指定源码文件编码为 UTF-8(防止中文注释报错）。
"""

import requests # 发送 HTTP 请求，用于与 OctoPrint API 通信
import json # 处理 JSON 数据（API 请求和响应）
import time # 延时、计时
import logging # rezhi
import os # lujing
from typing import List, Dict, Optional, Generator
from enum import Enum # 枚举类，用来定义打印机状态
import threading # 多线程（这里虽然导入了，但代码没用到）
from datetime import datetime # 时间记录（可以用于日志/时间戳）

# 这个文件要和脚本一起跑，应为没办法喝命令行交互，要通过脚本调动pause_processing()`、`resume_processing()等函数来实现暂停等功能


class PrinterState(Enum):
    """打印机状态枚举"""
    OPERATIONAL = "Operational"
    PRINTING = "Printing" 
    PAUSED = "Paused"
    ERROR = "Error"
    OFFLINE = "Offline"
    CANCELLING = "Cancelling"


class GCodeController:
    """G-code文件处理和OctoPrint控制器"""
    
    def __init__(self, octoprint_url: str, api_key: str, log_level: int = logging.INFO):
        """
        初始化控制器
        
        Args:
            octoprint_url: OctoPrint服务器URL (例如: http://192.168.1.100)
            api_key: OctoPrint API密钥
            log_level: 日志级别
        """
        self.base_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        
        # 设置日志
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('gcode_controller.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # 控制变量
        self._stop_requested = False
        self._pause_requested = False
        
    def validate_connection(self) -> bool:
        """验证与OctoPrint的连接"""
        try:
            response = requests.get(
                f"{self.base_url}/api/connection",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.logger.info(f"连接验证成功: {data}")
                return True
            else:
                self.logger.error(f"连接验证失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"连接验证异常: {e}")
            return False
    
    def get_printer_state(self) -> Optional[Dict]:
        """获取打印机当前状态"""
        try:
            response = requests.get(
                f"{self.base_url}/api/printer",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"获取打印机状态失败: HTTP {response.status_code}")
                return None
        except Exception as e:
            self.logger.error(f"获取打印机状态异常: {e}")
            return None
    
    def is_printer_idle(self) -> bool:
        """检查打印机是否空闲"""
        state_data = self.get_printer_state()
        if not state_data:
            return False
        
        # 检查打印机状态
        state = state_data.get('state', {})
        text = state.get('text', '')
        flags = state.get('flags', {})
        
        # 打印机空闲的条件：operational状态且没有在打印
        is_operational = flags.get('operational', False)
        is_printing = flags.get('printing', False)
        is_paused = flags.get('paused', False)
        is_error = flags.get('error', False)
        
        idle = is_operational and not is_printing and not is_paused and not is_error
        
        self.logger.debug(f"打印机状态检查: text='{text}', idle={idle}")
        return idle
    
    def wait_for_idle(self, check_interval: float = 2.0, timeout: float = 300.0) -> bool:
        """
        等待打印机变为空闲状态
        
        Args:
            check_interval: 检查间隔（秒）
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否成功等到空闲状态
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._stop_requested:
                self.logger.info("收到停止请求，退出等待")
                return False
                
            if self.is_printer_idle():
                self.logger.info("打印机已空闲")
                return True
            
            self.logger.debug("打印机忙碌中，继续等待...")
            time.sleep(check_interval)
        
        self.logger.warning(f"等待打印机空闲超时（{timeout}秒）")
        return False
    
    def send_gcode_command(self, gcode: str, wait_for_completion: bool = True) -> bool:
        """
        发送单条G-code命令
        
        Args:
            gcode: G-code命令
            wait_for_completion: 是否等待命令完成
            
        Returns:
            bool: 发送是否成功
        """
        try:
            # 清理G-code命令
            gcode = gcode.strip()
            if not gcode or gcode.startswith(';'):
                return True  # 跳过空行和注释
            
            # 发送命令
            payload = {"command": gcode}
            response = requests.post(
                f"{self.base_url}/api/printer/command",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 204:
                self.logger.debug(f"G-code命令发送成功: {gcode}")
                
                # 如果需要等待完成，检查打印机状态
                if wait_for_completion and gcode.upper().startswith(('G', 'M')):
                    time.sleep(0.1)  # 给命令一些执行时间
                    # 对于某些可能耗时的命令，等待更长时间
                    if any(cmd in gcode.upper() for cmd in ['G28', 'M109', 'M190', 'M106']):
                        time.sleep(1.0)
                
                return True
            else:
                self.logger.error(f"G-code命令发送失败: {gcode}, HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"发送G-code命令异常: {gcode}, 错误: {e}")
            return False
    
    def read_gcode_file(self, file_path: str) -> Generator[str, None, None]:
        """
        逐行读取G-code文件
        
        Args:
            file_path: G-code文件路径
            
        Yields:
            str: 每行G-code命令
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"G-code文件不存在: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                line_number = 0
                for line in f:
                    line_number += 1
                    line = line.strip()
                    
                    # 跳过空行
                    if not line:
                        continue
                    
                    # 记录处理进度
                    if line_number % 100 == 0:
                        self.logger.info(f"正在处理第 {line_number} 行")
                    
                    yield line
                    
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    line_number = 0
                    for line in f:
                        line_number += 1
                        line = line.strip()
                        if line:
                            yield line
            except Exception as e:
                self.logger.error(f"读取文件失败: {e}")
                raise
    
    def process_gcode_file(self, file_path: str, 
                          line_delay: float = 0.1,
                          check_idle_interval: int = 50) -> bool:
        """
        处理G-code文件, 逐行发送命令
        
        Args:
            file_path: G-code文件路径
            line_delay: 每行之间的延迟（秒）
            check_idle_interval: 每隔多少行检查一次打印机状态
            
        Returns:
            bool: 处理是否成功完成
        """
        if not self.validate_connection():
            self.logger.error("无法连接到OctoPrint,终止处理")
            return False
        
        # 等待打印机空闲
        if not self.wait_for_idle():
            self.logger.error("打印机未处于空闲状态,无法开始处理G-code文件")
            return False
        
        self.logger.info(f"开始处理G-code文件: {file_path}")
        
        try:
            line_count = 0
            success_count = 0
            error_count = 0
            
            for gcode_line in self.read_gcode_file(file_path):
                if self._stop_requested:
                    self.logger.info("收到停止请求,终止G-code处理")
                    break
                
                # 检查暂停请求
                while self._pause_requested and not self._stop_requested:
                    self.logger.info("处理已暂停，等待恢复...")
                    time.sleep(1.0)
                
                line_count += 1
                
                # 定期检查打印机状态
                if line_count % check_idle_interval == 0:
                    if not self.is_printer_idle():
                        self.logger.warning("检测到打印机非空闲状态，等待...")
                        if not self.wait_for_idle():
                            self.logger.error("打印机长时间未空闲，终止处理")
                            break
                
                # 发送G-code命令
                if self.send_gcode_command(gcode_line):
                    success_count += 1
                    self.logger.debug(f"第 {line_count} 行处理成功: {gcode_line}")
                else:
                    error_count += 1
                    self.logger.warning(f"第 {line_count} 行处理失败: {gcode_line}")
                
                # 行间延迟
                if line_delay > 0:
                    time.sleep(line_delay)
            
            # 处理完成统计
            self.logger.info(f"G-code文件处理完成:")
            self.logger.info(f"  总行数: {line_count}")
            self.logger.info(f"  成功: {success_count}")
            self.logger.info(f"  失败: {error_count}")
            
            return error_count == 0
            
        except Exception as e:
            self.logger.error(f"处理G-code文件时发生异常: {e}")
            return False
    
    def emergency_stop(self):
        """紧急停止"""
        self.logger.warning("执行紧急停止")
        self._stop_requested = True
        try:
            # 发送紧急停止命令
            self.send_gcode_command("M112")  # Emergency stop
        except:
            pass
    
    def pause_processing(self):
        """暂停处理"""
        self.logger.info("暂停G-code处理")
        self._pause_requested = True
    
    def resume_processing(self):
        """恢复处理"""
        self.logger.info("恢复G-code处理")
        self._pause_requested = False
    
    def stop_processing(self):
        """停止处理"""
        self.logger.info("停止G-code处理")
        self._stop_requested = True


def main():
    """主函数"""
    # 配置参数
    OCTOPRINT_URL = "http://octopi.local"  
    API_KEY = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"  # 修改为API密钥
    GCODE_FILE = "/path/to/your/gcode/file.gcode"  # 修改为G-code文件路径
    
    # 创建控制器
    controller = GCodeController(OCTOPRINT_URL, API_KEY)
    
    # 验证连接
    if not controller.validate_connection():
        print("无法连接到OctoPrint,请检查URL和API密钥")
        return
    
    try:
        # 处理G-code文件
        success = controller.process_gcode_file(
            GCODE_FILE,
            line_delay=0.1,  # 每行间隔0.1秒
            check_idle_interval=50  # 每50行检查一次状态
        )
        
        if success:
            print("G-code文件处理完成")
        else:
            print("G-code文件处理失败,请查看日志")
            
    except KeyboardInterrupt:
        print("\n收到中断信号,停止处理...")
        controller.emergency_stop()
    except Exception as e:
        print(f"处理过程中发生错误: {e}")
        controller.emergency_stop()


if __name__ == "__main__":
    main()