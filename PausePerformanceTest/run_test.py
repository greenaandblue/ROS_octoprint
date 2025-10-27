#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G-code暂停性能测试 - 主运行脚本
根据需要修改下面标记为 ❌ 的部分
"""

import sys
import os
import time
import logging

# ❌ 改这里：确保导入路径正确
# 如果你的gcode_sender.py在同一目录，这样就可以
from gcode_sender import GCodeSender
from pause_test_framework import PausePerformanceTest

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主测试函数"""
    
    # 改这里：填入OctoPrint信息
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"
    
    logger.info("="*70)
    logger.info("G-code暂停性能测试框架")
    logger.info("="*70)
    
    # 初始化发送器
    try:
        logger.info(f"\n连接到 {OCTOPRINT_URL}...")
        sender = GCodeSender(OCTOPRINT_URL, API_KEY)
        
        # 检查连接
        status = sender.check_printer_status()
        if not status:
            logger.error("无法连接到打印机，请检查配置")
            return
        
        logger.info("✓ 打印机连接成功")
        
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        return
    
    # 创建测试框架
    tester = PausePerformanceTest(sender)
    
    # 可选改这里：调整测试参数
    tester.test_config['repeat_count'] = 3              # 每个测试重复3次
    tester.test_config['wait_after_pause'] = 1.0        # 暂停后等待1秒
    tester.test_config['timeout'] = 300.0               # 单次测试超时300秒
    
    logger.info(f"\n测试配置:")
    logger.info(f"  重复次数: {tester.test_config['repeat_count']}")
    logger.info(f"  暂停后等待: {tester.test_config['wait_after_pause']}s")
    logger.info(f"  超时时间: {tester.test_config['timeout']}s")
    
    # 准备测试用例
    testcases = []
    
    # ❌ 改这里：改成你的实际文件路径
    
    # 维度1：同一文件，不同行数暂停
    logger.info("\n准备维度1测试用例 (同一文件，不同行数)...")
    testcases += tester.generate_dimension1_testcases(
        'test_files/medium_test.gcode',  # ❌ 改成你的文件
        pause_lines=[500, 1000, 2000, 3000]  # ❌ 可选：改成你想测试的行数
    )
    
    # 维度2：同一文件，不同进度百分比暂停
    logger.info("准备维度2测试用例 (同一文件，不同进度)...")
    testcases += tester.generate_dimension2_testcases(
        'test_files/medium_test.gcode',  # ❌ 改成你的文件
        pause_percents=[20, 30, 50, 70]  # ❌ 可选：改成你想测试的百分比
    )
    
    # 维度3：不同文件，相同行数暂停
    logger.info("准备维度3测试用例 (不同文件，相同行数)...")
    testcases += tester.generate_dimension3_testcases(
        [
            'test_files/small_test.gcode',    # ❌ 改成你的文件
            'test_files/medium_test.gcode',   # ❌ 改成你的文件
            'test_files/large_test.gcode'     # ❌ 改成你的文件
        ],
        pause_line=2000  # ❌ 可选：改成你想测试的行数
    )
    
    logger.info(f"\n总共准备了 {len(testcases)} 个测试用例")
    logger.info("请确保打印机处于空闲状态，然后按Enter开始测试...")
    input()
    
    # 执行测试
    try:
        tester.run_all_tests(testcases)
        
        # ❌ 可选改这里：改成你想要的输出文件名
        logger.info("\n生成测试报告...")
        tester.generate_report('pause_test_report.json')
        tester.export_csv('pause_test_results.csv')
        tester.print_summary()
        
        logger.info("\n✓ 测试完全完成！")
        logger.info(f"  JSON报告: pause_test_report.json")
        logger.info(f"  CSV数据: pause_test_results.csv")
        
    except KeyboardInterrupt:
        logger.warning("\n测试被中断")
        tester.sender.stop()
        
    except Exception as e:
        logger.error(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        tester.sender.stop()
        
    finally:
        logger.info("\n清理资源...")
        sender.close()
        logger.info("程序已退出")


if __name__ == '__main__':
    main()