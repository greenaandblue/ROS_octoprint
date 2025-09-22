# config.py - 配置文件
"""
OctoPrint G-code控制器配置文件
"""

import os

# OctoPrint 设置
OCTOPRINT_CONFIG = {
    'url': 'http://octopi.local/api/printer/command',
    'api_key': 'kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k',  # 从OctoPrint设置中获取API密钥
    'timeout': 30  # API请求超时时间（秒）
}

# G-code 处理设置
GCODE_CONFIG = {
    'line_delay': 0.1,  # 每行G-code之间的延迟（秒）
    'check_idle_interval': 50,  # 每隔多少行检查打印机状态
    'wait_idle_timeout': 300,  # 等待打印机空闲的超时时间（秒）
    'check_interval': 2.0  # 状态检查间隔（秒）
}

# 日志设置
LOG_CONFIG = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
    'file': 'gcode_controller.log',
    'max_size': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5
}

# 支持的G-code文件扩展名
SUPPORTED_EXTENSIONS = ['.gcode', '.g', '.nc', '.cnc']


# example_usage.py - 使用示例
"""
G-code控制器使用示例
演示如何使用控制器处理不同场景
"""

import sys
import os
import threading
import time
from gcode_controller import GCodeController, PrinterState
from config import OCTOPRINT_CONFIG, GCODE_CONFIG, LOG_CONFIG

def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 创建控制器实例
    controller = GCodeController(
        OCTOPRINT_CONFIG['url'], 
        OCTOPRINT_CONFIG['api_key']
    )
    
    # 验证连接
    if not controller.validate_connection():
        print("错误: 无法连接到OctoPrint")
        return False
    
    # 检查打印机状态
    print("检查打印机状态...")
    state = controller.get_printer_state()
    if state:
        print(f"打印机状态: {state['state']['text']}")
    
    # 处理G-code文件
    gcode_file = "example.gcode"  # 替换为你的文件路径
    if os.path.exists(gcode_file):
        print(f"开始处理G-code文件: {gcode_file}")
        success = controller.process_gcode_file(gcode_file)
        print(f"处理结果: {'成功' if success else '失败'}")
    else:
        print(f"G-code文件不存在: {gcode_file}")
    
    return True

def example_with_monitoring():
    """带监控的使用示例"""
    print("=== 带监控的使用示例 ===")
    
    controller = GCodeController(
        OCTOPRINT_CONFIG['url'], 
        OCTOPRINT_CONFIG['api_key']
    )
    
    def monitor_printer_status():
        """监控打印机状态的后台线程"""
        while not stop_monitoring:
            state = controller.get_printer_state()
            if state:
                print(f"[监控] 打印机状态: {state['state']['text']}")
            time.sleep(10)  # 每10秒检查一次
    
    # 启动监控线程
    stop_monitoring = False
    monitor_thread = threading.Thread(target=monitor_printer_status, daemon=True)
    monitor_thread.start()
    
    try:
        # 处理G-code文件
        gcode_file = "example.gcode"
        if os.path.exists(gcode_file):
            controller.process_gcode_file(gcode_file)
    except KeyboardInterrupt:
        print("\n用户中断，停止处理...")
        controller.emergency_stop()
    finally:
        stop_monitoring = True
    
    return True

def example_send_single_commands():
    """发送单个命令示例"""
    print("=== 发送单个G-code命令示例 ===")
    
    controller = GCodeController(
        OCTOPRINT_CONFIG['url'], 
        OCTOPRINT_CONFIG['api_key']
    )
    
    if not controller.validate_connection():
        print("连接失败")
        return False
    
    # 等待打印机空闲
    if not controller.wait_for_idle():
        print("打印机未空闲")
        return False
    
    # 发送一些测试命令
    test_commands = [
        "M105",  # 获取温度
        "G28 X Y",  # 归零X和Y轴
        "G1 X10 Y10 F1000",  # 移动到指定位置
        "M114",  # 获取当前位置
    ]
    
    for cmd in test_commands:
        print(f"发送命令: {cmd}")
        success = controller.send_gcode_command(cmd)
        print(f"结果: {'成功' if success else '失败'}")
        time.sleep(1)
    
    return True

def example_error_handling():
    """错误处理示例"""
    print("=== 错误处理示例 ===")
    
    # 故意使用错误的配置来演示错误处理
    controller = GCodeController("http://invalid-url", "invalid-key")
    
    # 这会失败，但程序不会崩溃
    print("测试无效连接...")
    if not controller.validate_connection():
        print("连接验证失败（预期行为）")
    
    # 测试不存在的文件
    print("测试不存在的文件...")
    try:
        list(controller.read_gcode_file("nonexistent.gcode"))
    except FileNotFoundError as e:
        print(f"文件不存在错误（预期行为）: {e}")
    
    return True

def create_sample_gcode():
    """创建示例G-code文件"""
    sample_gcode = """
; 示例G-code文件
; 这是一个简单的测试文件
G21 ; 设置单位为毫米
G90 ; 绝对定位模式
M82 ; 绝对挤出模式
M104 S200 ; 设置喷嘴温度
M109 S200 ; 等待喷嘴温度
G28 ; 归零所有轴
G1 Z15.0 F9000 ; 抬升Z轴
G92 E0 ; 重置挤出机
G1 F1000 ; 设置进给速度
G1 X10 Y10 ; 移动到起始位置
G1 X20 Y20 ; 绘制对角线
G1 X10 Y20 ; 绘制另一条线
G1 X10 Y10 ; 回到起点
M104 S0 ; 关闭喷嘴加热
M140 S0 ; 关闭热床加热
G28 X0 ; 归零X轴
M84 ; 关闭电机
"""
    
    with open("example.gcode", "w") as f:
        f.write(sample_gcode.strip())
    
    print("已创建示例G-code文件: example.gcode")

def interactive_mode():
    """交互模式"""
    print("=== 交互模式 ===")
    print("可用命令:")
    print("  connect - 测试连接")
    print("  status - 检查打印机状态") 
    print("  send <gcode> - 发送G-code命令")
    print("  process <file> - 处理G-code文件")
    print("  quit - 退出")
    
    controller = GCodeController(
        OCTOPRINT_CONFIG['url'], 
        OCTOPRINT_CONFIG['api_key']
    )
    
    while True:
        try:
            cmd = input("\n> ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] == "quit":
                break
            elif cmd[0] == "connect":
                result = controller.validate_connection()
                print(f"连接结果: {'成功' if result else '失败'}")
            elif cmd[0] == "status":
                state = controller.get_printer_state()
                if state:
                    print(f"打印机状态: {state['state']['text']}")
                else:
                    print("无法获取状态")
            elif cmd[0] == "send" and len(cmd) > 1:
                gcode = " ".join(cmd[1:])
                result = controller.send_gcode_command(gcode)
                print(f"发送结果: {'成功' if result else '失败'}")
            elif cmd[0] == "process" and len(cmd) > 1:
                file_path = cmd[1]
                if os.path.exists(file_path):
                    result = controller.process_gcode_file(file_path)
                    print(f"处理结果: {'成功' if result else '失败'}")
                else:
                    print(f"文件不存在: {file_path}")
            else:
                print("未知命令")
                
        except KeyboardInterrupt:
            print("\n退出交互模式")
            break
        except Exception as e:
            print(f"错误: {e}")

def main():
    """主函数"""
    print("OctoPrint G-code控制器示例")
    print("请确保已在config.py中配置正确的OctoPrint URL和API密钥")
    print()
    
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        print("选择运行模式:")
        print("1. 基本使用")
        print("2. 带监控")
        print("3. 发送单个命令")
        print("4. 错误处理测试")
        print("5. 创建示例G-code文件")
        print("6. 交互模式")
        
        try:
            choice = input("请选择 (1-6): ").strip()
            mode = {
                '1': 'basic',
                '2': 'monitor', 
                '3': 'single',
                '4': 'error',
                '5': 'create',
                '6': 'interactive'
            }.get(choice, 'basic')
        except KeyboardInterrupt:
            print("\n退出")
            return
    
    # 执行相应的示例
    if mode == 'basic':
        example_basic_usage()
    elif mode == 'monitor':
        example_with_monitoring()
    elif mode == 'single':
        example_send_single_commands()
    elif mode == 'error':
        example_error_handling()
    elif mode == 'create':
        create_sample_gcode()
    elif mode == 'interactive':
        interactive_mode()
    else:
        print(f"未知模式: {mode}")

if __name__ == "__main__":
    main()