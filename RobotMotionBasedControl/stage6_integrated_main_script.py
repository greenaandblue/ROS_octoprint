#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 6: 集成主脚本
将打印机控制与机器人速度监控整合在一起
"""

import sys
import os

# 确保能导入 gcode_sender 模块
# sys.path.insert(0, '/path/to/gcode_sender/directory')

try:
    # 尝试导入 ROS 相关模块
    import rospy # type: ignore
    ROS_AVAILABLE = True
except ImportError:
    print("警告: 未找到 ROS，某些功能不可用")
    ROS_AVAILABLE = False

import time
import logging
from datetime import datetime

# 导入模块（假设 gcode_sender.py 在同一目录）
try:
    from gcode_sender import GCodeSender, PrinterState
except ImportError:
    print("错误: 找不到 gcode_sender 模块")
    print("请确保 gcode_sender.py 在同一目录下")
    sys.exit(1)

# 只在 ROS 可用时导入控制模块
if ROS_AVAILABLE:
    try:
        from robot_speed_controller import PrinterSpeedController
    except ImportError:
        print("错误: 找不到 robot_speed_controller 模块")
        print("请确保 robot_speed_controller.py 在同一目录下")
        sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Stage6IntegratedSystem:
    """Stage 6 集成系统 - 打印机 + 机器人速度控制"""
    
    def __init__(self, octoprint_url, api_key, speed_source='odom'):
        """初始化集成系统"""
        
        if not ROS_AVAILABLE:
            print("错误: 需要 ROS 环境才能运行 Stage 6")
            sys.exit(1)
        
        rospy.init_node('stage6_printer_controller', anonymous=True)
        
        self.octoprint_url = octoprint_url
        self.api_key = api_key
        self.speed_source = speed_source
        
        # 初始化打印机控制器
        logger.info("初始化打印机控制器...")
        self.sender = GCodeSender(octoprint_url, api_key)
        
        # 初始化速度控制器
        logger.info("初始化速度控制器...")
        self.controller = PrinterSpeedController(
            self.sender,
            speed_source=speed_source
        )
        
        self.current_file = None
        logger.info("系统初始化完成")
    
    def start_printing_with_speed_control(self, file_path):
        """启动文件打印并启用速度控制"""
        
        logger.info(f"启动打印: {file_path}")
        
        # 初始化日志
        self.controller.init_logging()
        
        # 启动打印
        if not self.sender.start_file_print(file_path):
            logger.error("无法启动打印")
            return False
        
        self.current_file = file_path
        time.sleep(1)  # 等待打印开始
        
        # 启动速度控制
        if not self.controller.start_control():
            logger.error("无法启动速度控制")
            return False
        
        logger.info("✓ 打印和速度控制已启动")
        return True
    
    def stop(self):
        """停止所有操作"""
        logger.info("正在停止所有操作...")
        
        if self.controller.control_enabled:
            self.controller.stop_control()
        
        if self.sender.state != PrinterState.IDLE:
            self.sender.stop()
        
        logger.info("✓ 已停止")
    
    def get_system_status(self):
        """获取系统状态"""
        controller_status = self.controller.get_status()
        sender_progress = self.sender.get_progress()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'printer_state': sender_progress['state'],
            'printer_progress': f"{sender_progress['progress_percent']:.1f}%",
            'robot_speed': f"{controller_status['current_robot_speed']:.3f} m/s",
            'printer_paused': controller_status['printer_paused'],
            'speed_threshold': controller_status['speed_threshold'],
            'current_file': self.current_file,
            'log_file': self.controller.log_file,
        }
    
    def interactive_shell(self):
        """交互式命令行"""
        
        print("\n" + "="*70)
        print("Stage 6: 机器人速度 + 打印机集成控制系统")
        print("="*70)
        print("\n系统配置:")
        print(f"  OctoPrint: {self.octoprint_url}")
        print(f"  速度源: {self.speed_source}")
        print("\n命令列表:")
        print("  print <file>         - 启动文件打印 (自动启用速度控制)")
        print("  status               - 显示系统状态")
        print("  pause                - 手动暂停打印")
        print("  resume               - 手动恢复打印")
        print("  stop                 - 停止打印")
        print("  threshold <value>    - 设置速度阈值 (m/s)")
        print("  debounce <time>      - 设置防抖时间 (s)")
        print("  logs                 - 显示日志文件位置")
        print("  help                 - 显示帮助信息")
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
                        logger.info("正在退出...")
                        break
                    
                    elif command == 'print':
                        if len(cmd) > 1:
                            file_path = cmd[1]
                            if os.path.exists(file_path):
                                self.start_printing_with_speed_control(file_path)
                            else:
                                print(f"文件不存在: {file_path}")
                        else:
                            print("请提供文件路径")
                    
                    elif command == 'status':
                        status = self.get_system_status()
                        print("\n系统状态:")
                        for key, value in status.items():
                            print(f"  {key}: {value}")
                        print()
                    
                    elif command == 'pause':
                        if self.sender.pause():
                            print("✓ 已暂停")
                        else:
                            print("✗ 暂停失败")
                    
                    elif command == 'resume':
                        if self.sender.resume():
                            print("✓ 已恢复")
                        else:
                            print("✗ 恢复失败")
                    
                    elif command == 'stop':
                        self.stop()
                        print("✓ 已停止")
                    
                    elif command == 'threshold':
                        if self.controller and len(cmd) > 1:
                            try:
                                threshold = float(cmd[1])
                                self.controller.set_speed_threshold(threshold)
                                print(f"✓ 速度阈值已设置为 {threshold} m/s")
                            except ValueError:
                                print("请输入有效的数值")
                        else:
                            print("请提供速度阈值")
                    
                    elif command == 'debounce':
                        if self.controller and len(cmd) > 1:
                            try:
                                debounce = float(cmd[1])
                                self.controller.set_debounce_time(debounce)
                                print(f"✓ 防抖时间已设置为 {debounce} s")
                            except ValueError:
                                print("请输入有效的数值")
                        else:
                            print("请提供防抖时间")
                    
                    elif command == 'logs':
                        if self.controller.log_file:
                            print(f"日志文件: {self.controller.log_file}")
                        else:
                            print("日志未初始化")
                    
                    elif command == 'help':
                        print("\n帮助信息:")
                        print("  print <file> - 打开文件并开始打印，同时启用速度监控")
                        print("  status - 显示当前打印进度、机器人速度、打印机状态")
                        print("  threshold - 调整速度触发阈值（默认0.4 m/s）")
                        print("  debounce - 调整防抖时间以避免频繁切换（默认0.5 s）")
                        print()
                    
                    else:
                        print(f"未知命令: {command}")
                        
                except KeyboardInterrupt:
                    print("\n正在退出...")
                    break
                except Exception as e:
                    print(f"错误: {e}")
                    logger.exception("命令执行异常")
        
        finally:
            self.stop()
            logger.info("程序已退出")


def main():
    """主函数"""
    
    # 配置参数
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"
    
    # 速度源选项: 'odom' (里程计) 或 'cmd_vel' (速度命令)
    SPEED_SOURCE = 'odom'
    
    # 创建集成系统
    system = Stage6IntegratedSystem(
        octoprint_url=OCTOPRINT_URL,
        api_key=API_KEY,
        speed_source=SPEED_SOURCE
    )
    
    # 启动交互式命令行
    system.interactive_shell()


if __name__ == '__main__':
    if not ROS_AVAILABLE:
        print("错误: Stage 6 需要在 ROS 环境中运行")
        print("请确保已安装 ROS 并已执行: source /opt/ros/*/setup.bash")
        sys.exit(1)
    
    try:
        main()
    except Exception as e:
        logger.error(f"致命错误: {e}")
        sys.exit(1)