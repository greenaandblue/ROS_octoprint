#!/usr/bin/env python3
# 这个文件要和配置文件一起跑，不能像另外两个那样单独跑，从from也能看出来

# 这个是和gcode_controller一起用的，因为gcode_conytroller里面的暂停、启动等是不能和命令行交互的
# 只能通过脚本调动 pause_processing()`、`resume_processing()等

import sys
import os
from gcode_controller import GCodeController
from gcode_controller_node.config import OCTOPRINT_CONFIG

def main():
    if len(sys.argv) < 2:
        print("使用方法: python3 run_gcode.py <gcode文件路径>")
        print("示例: python3 run_gcode.py /home/user/test.gcode")
        return
    
    gcode_file = sys.argv[1]
    
    # 检查文件是否存在
    if not os.path.exists(gcode_file):
        print(f"错误: 文件不存在 - {gcode_file}")
        return
    
    # 创建控制器
    controller = GCodeController(
        OCTOPRINT_CONFIG['url'],
        OCTOPRINT_CONFIG['api_key']
    )
    
    # 验证连接
    if not controller.validate_connection():
        print("错误: 无法连接到OctoPrint,请检查配置")
        return
    
    print(f"开始处理G-code文件: {gcode_file}")
    success = controller.process_gcode_file(gcode_file)
    
    if success:
        print("G-code文件处理完成")
    else:
        print("处理失败，请查看日志文件")

if __name__ == "__main__":
    main()