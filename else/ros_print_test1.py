#!/usr/bin/env python3
"""
简单的3D打印机控制脚本
直接连接OctoPrint API控制打印机
在Ubuntu本地运行,无需ROS环境
"""

import requests
import json
import time
import sys
from typing import List, Dict, Any, Optional

class SimplePrinterController:
    def __init__(self, host="octopi.local", port=80, api_key=""):
        """
        初始化打印机控制器
        
        Args:
            host: OctoPrint服务器地址
            port: 端口号
            api_key: OctoPrint API密钥
        """
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key
        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        print(f"初始化打印机控制器 - 连接到: {self.base_url}")
        
        # 测试连接
        if not self.test_connection():
            print("连接失败!请检查:")
            print("1. OctoPrint是否运行在 http://octopi.local")
            print("2. API密钥是否正确")
            print("3. 网络连接是否正常")
            sys.exit(1)
        else:
            print("成功连接到OctoPrint!")
    
    def test_connection(self) -> bool:
        """测试连接"""
        try:
            response = requests.get(f"{self.base_url}/api/version", headers=self.headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"连接测试失败: {e}")
            return False
    
    def get_printer_status(self) -> Optional[Dict]:
        """获取打印机状态"""
        try:
            response = requests.get(f"{self.base_url}/api/printer", headers=self.headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"获取状态失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            print(f"获取状态异常: {e}")
            return None
    
    def send_gcode(self, command: str) -> bool:
        """发送G-code命令"""
        try:
            payload = {"command": command}
            response = requests.post(
                f"{self.base_url}/api/printer/command",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            success = response.status_code == 204
            if success:
                print(f"G-code发送成功: {command}")
            else:
                print(f"G-code发送失败: {command} (状态码: {response.status_code})")
            return success
        except Exception as e:
            print(f"发送G-code异常: {e}")
            return False
    
    def send_multiple_gcode(self, commands: List[str], delay: float = 0.5) -> bool:
        """发送多条G-code命令"""
        print(f"准备发送 {len(commands)} 条G-code命令...")
        success_count = 0
        
        for i, command in enumerate(commands, 1):
            print(f"[{i}/{len(commands)}] 发送: {command}")
            if self.send_gcode(command):
                success_count += 1
            
            if delay > 0 and i < len(commands):
                time.sleep(delay)
        
        print(f"完成! 成功: {success_count}/{len(commands)}")
        return success_count == len(commands)
    
    def home_printer(self) -> bool:
        """归零打印机"""
        print("执行归零操作...")
        return self.send_gcode("G28")
    
    def move_to(self, x=None, y=None, z=None, feedrate=1500) -> bool:
        """移动到指定位置"""
        command = f"G1 F{feedrate}"
        moves = []
        
        if x is not None:
            command += f" X{x}"
            moves.append(f"X={x}")
        if y is not None:
            command += f" Y{y}"
            moves.append(f"Y={y}")
        if z is not None:
            command += f" Z{z}"
            moves.append(f"Z={z}")
        
        if moves:
            print(f"移动到: {', '.join(moves)}")
            return self.send_gcode(command)
        return False
    
    def set_hotend_temp(self, temperature: int) -> bool:
        """设置热端温度"""
        print(f"设置热端温度: {temperature}°C")
        return self.send_gcode(f"M104 S{temperature}")
    
    def set_bed_temp(self, temperature: int) -> bool:
        """设置热床温度"""
        print(f"设置热床温度: {temperature}°C")
        return self.send_gcode(f"M140 S{temperature}")
    
    def wait_for_temp(self, hotend_temp=None, bed_temp=None) -> bool:
        """等待温度达到目标"""
        commands = []
        if hotend_temp:
            commands.append(f"M109 S{hotend_temp}")  # 等待热端温度
        if bed_temp:
            commands.append(f"M190 S{bed_temp}")     # 等待热床温度
        
        if commands:
            print("等待温度达到目标...")
            return self.send_multiple_gcode(commands)
        return True
    
    def display_message(self, message: str) -> bool:
        """在打印机屏幕显示消息"""
        print(f"显示消息: {message}")
        return self.send_gcode(f"M117 {message}")
    
    def emergency_stop(self) -> bool:
        """紧急停止"""
        print("执行紧急停止!")
        return self.send_gcode("M112")
    
    def print_status(self):
        """打印当前状态"""
        print("\n" + "="*50)
        print("打印机状态信息")
        print("="*50)
        
        status = self.get_printer_status()
        if status:
            # 基本状态
            state = status.get('state', {})
            print(f"状态: {state.get('text', 'Unknown')}")
            print(f"操作: {state.get('flags', {})}")
            
            # 温度信息
            temps = status.get('temperature', {})
            if 'tool0' in temps:
                tool_temp = temps['tool0']
                print(f"热端温度: {tool_temp.get('actual', 0):.1f}°C / {tool_temp.get('target', 0):.1f}°C")
            
            if 'bed' in temps:
                bed_temp = temps['bed']
                print(f"热床温度: {bed_temp.get('actual', 0):.1f}°C / {bed_temp.get('target', 0):.1f}°C")
        else:
            print("无法获取状态信息")
        print("="*50)

def main():
    """主程序"""
    print("3D打印机控制程序启动")
    print("请确保OctoPrint正在运行并且打印机已连接")
    
    # 配置信息 - 请修改为你的实际配置
    API_KEY = input("请输入OctoPrint API密钥: ").strip()
    if not API_KEY:
        print("API密钥不能为空!")
        return
    
    HOST = input("输入OctoPrint地址 (默认: octopi.local): ").strip() or "octopi.local"
    
    # 创建控制器
    controller = SimplePrinterController(host=HOST, api_key=API_KEY)
    
    # 显示当前状态
    controller.print_status()
    
    while True:
        print("\n" + "="*40)
        print("3D打印机控制菜单")
        print("="*40)
        print("1. 查看状态")
        print("2. 归零打印机")
        print("3. 移动打印机")
        print("4. 设置温度")
        print("5. 发送G-code命令")
        print("6. 预热(PLA)")
        print("7. 冷却")
        print("8. 显示消息")
        print("9. 紧急停止")
        print("0. 退出")
        print("="*40)
        
        choice = input("请选择操作 (0-9): ").strip()
        
        try:
            if choice == '1':
                controller.print_status()
                
            elif choice == '2':
                controller.home_printer()
                
            elif choice == '3':
                print("输入移动坐标 (留空保持当前位置):")
                x_str = input("X坐标: ").strip()
                y_str = input("Y坐标: ").strip()
                z_str = input("Z坐标: ").strip()
                
                x = float(x_str) if x_str else None
                y = float(y_str) if y_str else None
                z = float(z_str) if z_str else None
                
                controller.move_to(x=x, y=y, z=z)
                
            elif choice == '4':
                temp_type = input("设置温度类型 (1-热端, 2-热床): ").strip()
                temp = int(input("目标温度 (°C): ").strip())
                
                if temp_type == '1':
                    controller.set_hotend_temp(temp)
                elif temp_type == '2':
                    controller.set_bed_temp(temp)
                else:
                    print("无效选择")
                    
            elif choice == '5':
                gcode = input("输入G-code命令: ").strip()
                if gcode:
                    controller.send_gcode(gcode)
                else:
                    print("命令不能为空")
                    
            elif choice == '6':
                print("开始预热 PLA...")
                controller.display_message("Preheating for PLA")
                controller.set_hotend_temp(200)
                controller.set_bed_temp(60)
                
            elif choice == '7':
                print("开始冷却...")
                controller.display_message("Cooling down")
                controller.set_hotend_temp(0)
                controller.set_bed_temp(0)
                
            elif choice == '8':
                message = input("输入要显示的消息: ").strip()
                if message:
                    controller.display_message(message)
                else:
                    print("消息不能为空")
                    
            elif choice == '9':
                confirm = input("确认执行紧急停止? (y/N): ").strip().lower()
                if confirm == 'y':
                    controller.emergency_stop()
                else:
                    print("已取消")
                    
            elif choice == '0':
                print("程序退出")
                break
                
            else:
                print("无效选择，请重试")
                
        except ValueError as e:
            print(f"输入错误: {e}")
        except KeyboardInterrupt:
            print("\n程序被用户中断")
            break
        except Exception as e:
            print(f"程序异常: {e}")

if __name__ == "__main__":
    main()