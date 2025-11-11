#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OctoPrint 暂停延迟测试执行脚本 - 修复版 v2.0
改进：
1. 更详细的进度反馈
2. 调试模式支持
3. 参数验证
4. 结果分析
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List
import matplotlib.pyplot as plt
import numpy as np

from pause_latency_test_framwork import OctoPrintPhysicalPauseTester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestRunner:
    """测试运行器"""
    
    def __init__(self, octoprint_url: str, api_key: str):
        self.tester = OctoPrintPhysicalPauseTester(octoprint_url, api_key)
        logger.info(f"✓ 已连接到 OctoPrint: {octoprint_url}")
    
    def find_gcode_files(self, directory: str) -> List[str]:
        """查找目录中的 G-code 文件"""
        gcode_files = []
        for ext in ['*.gcode', '*.g', '*.gco', '*.nc']:
            gcode_files.extend(Path(directory).glob(ext))
        
        return sorted([str(f) for f in gcode_files])
    
    def run_test_scenario_1_different_sizes(self,
                                           gcode_files: List[str],
                                           repeat_count: int = 3,
                                           wait_before_pause: float = 10.0):
        """
        场景 1：测试不同文件大小的暂停延迟
        目标：得到 pause_latency = f(file_size)
        """
        logger.info("\n" + "="*70)
        logger.info("[SCENARIO 1] 不同文件大小的暂停延迟测试")
        logger.info("="*70)
        logger.info(f"文件数: {len(gcode_files)}")
        logger.info(f"每个文件重复: {repeat_count} 次")
        logger.info(f"暂停前等待: {wait_before_pause:.1f} 秒")
        logger.info("="*70)
        
        # 按文件大小排序
        gcode_files_sorted = sorted(gcode_files, 
                                    key=lambda f: os.path.getsize(f))
        
        logger.info(f"\n待测文件列表 (按大小升序):")
        for i, f in enumerate(gcode_files_sorted, 1):
            size_mb = os.path.getsize(f) / (1024*1024)
            logger.info(f"  {i}. {Path(f).name} ({size_mb:.2f} MB)")
        
        logger.info("\n开始批量测试...")
        self.tester.run_batch_tests(
            gcode_files_sorted,
            wait_before_pause=wait_before_pause,
            repeat_count=repeat_count
        )
    
    def run_test_scenario_2_single_file_repeat(self,
                                              gcode_file: str,
                                              repeat_count: int = 10,
                                              wait_before_pause: float = 10.0):
        """
        场景 2：单个文件重复测试
        目标：检查同一文件多次测试的稳定性和重复性
        """
        logger.info("\n" + "="*70)
        logger.info("[SCENARIO 2] 单文件重复测试 - 稳定性检验")
        logger.info("="*70)
        logger.info(f"文件: {Path(gcode_file).name}")
        logger.info(f"重复次数: {repeat_count}")
        logger.info(f"暂停前等待: {wait_before_pause:.1f} 秒")
        logger.info("="*70)
        
        for i in range(repeat_count):
            logger.info(f"\n[{i+1}/{repeat_count}] 执行测试...")
            result = self.tester.run_single_pause_test(
                gcode_file,
                wait_before_pause=wait_before_pause
            )
            if result:
                self.tester.test_results.append(result)
            
            if i < repeat_count - 1:
                logger.info("等待 10 秒后进行下一个测试...")
                import time
                time.sleep(10)
    
    def run_debug_single_file(self, gcode_file: str, wait_before_pause: float = 15.0):
        """
        调试模式：单文件详细测试
        目标：详细观察一次完整的测试过程
        """
        logger.info("\n" + "="*70)
        logger.info("[DEBUG] 调试模式 - 单文件详细测试")
        logger.info("="*70)
        logger.info(f"文件: {Path(gcode_file).name}")
        logger.info(f"暂停前等待: {wait_before_pause:.1f} 秒")
        logger.info("="*70 + "\n")
        
        result = self.tester.run_single_pause_test(
            gcode_file,
            wait_before_pause=wait_before_pause
        )
        
        if result:
            logger.info("\n" + "="*70)
            logger.info("[DEBUG] 测试结果详情")
            logger.info("="*70)
            logger.info(f"文件: {result['file_name']}")
            logger.info(f"文件大小: {result['file_size_mb']:.2f} MB")
            logger.info(f"G-code行数: {result['gcode_lines']}")
            logger.info(f"暂停延迟: {result['pause_latency_s']:.4f} 秒")
            logger.info(f"位置样本数: {result['position_samples']}")
            logger.info(f"停止原因: {result['stop_reason']}")
            
            if result['first_position']:
                pos = result['first_position']
                logger.info(f"初始位置: X={pos['x']:.2f}, Y={pos['y']:.2f}, Z={pos['z']:.2f}")
            if result['last_position']:
                pos = result['last_position']
                logger.info(f"最终位置: X={pos['x']:.2f}, Y={pos['y']:.2f}, Z={pos['z']:.2f}")
            
            logger.info("="*70 + "\n")
            self.tester.test_results.append(result)
    
    def generate_analysis_plots(self, output_dir: str = '.'):
        """生成分析图表"""
        if not self.tester.test_results:
            logger.warning("没有测试结果可用于绘图")
            return
        
        results = self.tester.test_results
        
        # 提取数据
        sizes_mb = [r['file_size_mb'] for r in results]
        latencies_ms = [r['pause_latency_s'] * 1000 for r in results]
        gcode_lines = [r['gcode_lines'] for r in results]
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('OctoPrint 暂停延迟分析', fontsize=16, fontweight='bold')
        
        # 图1：延迟 vs 文件大小
        ax = axes[0, 0]
        ax.scatter(sizes_mb, latencies_ms, s=100, alpha=0.6, color='blue')
        if len(set(sizes_mb)) > 1:
            z = np.polyfit(sizes_mb, latencies_ms, 1)
            p = np.poly1d(z)
            ax.plot(sizes_mb, p(sizes_mb), "r--", alpha=0.8, label=f'拟合: y={z[0]:.2f}x+{z[1]:.2f}')
            ax.legend()
        ax.set_xlabel('文件大小 (MB)')
        ax.set_ylabel('暂停延迟 (ms)')
        ax.set_title('暂停延迟 vs 文件大小')
        ax.grid(True, alpha=0.3)
        
        # 图2：延迟 vs 代码行数
        ax = axes[0, 1]
        ax.scatter(gcode_lines, latencies_ms, s=100, alpha=0.6, color='green')
        if len(set(gcode_lines)) > 1:
            z = np.polyfit(gcode_lines, latencies_ms, 1)
            p = np.poly1d(z)
            ax.plot(gcode_lines, p(gcode_lines), "r--", alpha=0.8, label=f'拟合: y={z[0]:.4f}x+{z[1]:.2f}')
            ax.legend()
        ax.set_xlabel('G-code 行数')
        ax.set_ylabel('暂停延迟 (ms)')
        ax.set_title('暂停延迟 vs G-code 行数')
        ax.grid(True, alpha=0.3)
        
        # 图3：延迟分布
        ax = axes[1, 0]
        ax.hist(latencies_ms, bins=10, alpha=0.7, color='purple', edgecolor='black')
        ax.axvline(np.mean(latencies_ms), color='red', linestyle='--', linewidth=2, label=f'均值: {np.mean(latencies_ms):.2f}ms')
        ax.axvline(np.median(latencies_ms), color='orange', linestyle='--', linewidth=2, label=f'中位数: {np.median(latencies_ms):.2f}ms')
        ax.set_xlabel('暂停延迟 (ms)')
        ax.set_ylabel('频数')
        ax.set_title('暂停延迟分布')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # 图4：时间序列
        ax = axes[1, 1]
        ax.plot(range(len(latencies_ms)), latencies_ms, marker='o', linestyle='-', color='teal', linewidth=2)
        ax.set_xlabel('测试序号')
        ax.set_ylabel('暂停延迟 (ms)')
        ax.set_title('暂停延迟时间序列')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        output_file = os.path.join(output_dir, 'pause_analysis.png')
        plt.savefig(output_file, dpi=150)
        logger.info(f"✓ 分析图表已保存: {output_file}")
        
        # 打印统计
        logger.info("\n" + "="*70)
        logger.info("[ANALYSIS] 统计分析")
        logger.info("="*70)
        logger.info(f"总测试数: {len(results)}")
        logger.info(f"平均延迟: {np.mean(latencies_ms):.2f} ms")
        logger.info(f"中位数延迟: {np.median(latencies_ms):.2f} ms")
        logger.info(f"标准差: {np.std(latencies_ms):.2f} ms")
        logger.info(f"最小延迟: {np.min(latencies_ms):.2f} ms")
        logger.info(f"最大延迟: {np.max(latencies_ms):.2f} ms")
        logger.info(f"延迟范围: {np.max(latencies_ms) - np.min(latencies_ms):.2f} ms")
        
        # 计算相关性
        if len(set(sizes_mb)) > 1:
            corr_size = np.corrcoef(sizes_mb, latencies_ms)[0, 1]
            logger.info(f"文件大小与延迟相关性: {corr_size:.3f}")
        
        if len(set(gcode_lines)) > 1:
            corr_lines = np.corrcoef(gcode_lines, latencies_ms)[0, 1]
            logger.info(f"G-code行数与延迟相关性: {corr_lines:.3f}")
        
        logger.info("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='OctoPrint 暂停延迟测试执行脚本 - 修复版',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 调试模式（推荐先用这个）
  python run_test_script.py --scenario debug --gcode-file test.gcode --wait-before-pause 15
  
  # 场景1：不同文件大小（3个文件，每个重复2次）
  python run_test_script.py --scenario 1 --gcode-dir ./gcode --repeat 2 --wait-before-pause 15
  
  # 场景2：单文件重复（同一文件10次）
  python run_test_script.py --scenario 2 --gcode-file test.gcode --repeat 10 --wait-before-pause 15
  
  # 场景both：全部测试
  python run_test_script.py --scenario both --gcode-dir ./gcode --gcode-file test.gcode --repeat 3
        """
    )
    
    CONFIG = {
        'url': 'http://octopi.local',
        'api_key': 'YOUR_API_KEY_HERE',
        'scenario': '1',
        'gcode_dir': './gcode',
        'gcode_file': None,
        'repeat': 3,
        'wait_before_pause': 60,  # 改为15秒（足够热床加热）
        'output_dir': './test_results',
        'tolerance': 0.05,
        'stable_count': 5,
    }
    
    parser.add_argument('--url', default=CONFIG['url'], 
                       help=f'OctoPrint URL (默认: {CONFIG["url"]})')
    parser.add_argument('--api-key', default=CONFIG['api_key'], 
                       help='OctoPrint API Key')
    parser.add_argument('--scenario', choices=['1', '2', 'debug', 'both'], 
                       default=CONFIG['scenario'],
                       help='测试场景: 1=不同文件大小, 2=单文件重复, debug=调试模式, both=全部')
    parser.add_argument('--gcode-dir', default=CONFIG['gcode_dir'],
                       help=f'G-code 文件目录 (默认: {CONFIG["gcode_dir"]})')
    parser.add_argument('--gcode-file', default=CONFIG['gcode_file'],
                       help='指定单个 G-code 文件（场景2和debug使用）')
    parser.add_argument('--repeat', type=int, default=CONFIG['repeat'],
                       help=f'重复次数 (默认: {CONFIG["repeat"]})')
    parser.add_argument('--wait-before-pause', type=float, default=CONFIG['wait_before_pause'],
                       help=f'暂停前等待时间秒数 (默认: {CONFIG["wait_before_pause"]}秒)')
    parser.add_argument('--output-dir', default=CONFIG['output_dir'],
                       help=f'输出目录 (默认: {CONFIG["output_dir"]})')
    parser.add_argument('--tolerance', type=float, default=CONFIG['tolerance'],
                       help=f'位置容限(mm) (默认: {CONFIG["tolerance"]})')
    parser.add_argument('--stable-count', type=int, default=CONFIG['stable_count'],
                       help=f'连续稳定次数 (默认: {CONFIG["stable_count"]})')
    
    args = parser.parse_args()
    
    # 初始化测试运行器
    runner = TestRunner(args.url, args.api_key)
    
    # 应用自定义参数
    runner.tester.test_config['position_tolerance'] = args.tolerance
    runner.tester.test_config['stable_count'] = args.stable_count
    
    logger.info("="*70)
    logger.info("OctoPrint 暂停延迟测试框架 - 修复版 v2.0")
    logger.info("="*70)
    logger.info(f"URL: {args.url}")
    logger.info(f"位置容限: {args.tolerance} mm")
    logger.info(f"稳定次数: {args.stable_count}")
    logger.info(f"暂停前等待: {args.wait_before_pause} 秒")
    logger.info("="*70 + "\n")
    
    try:
        # 调试模式
        if args.scenario == 'debug':
            if not args.gcode_file:
                logger.error("❌ 调试模式需要 --gcode-file 参数")
                sys.exit(1)
            
            if not os.path.exists(args.gcode_file):
                logger.error(f"❌ 文件不存在: {args.gcode_file}")
                sys.exit(1)
            
            runner.run_debug_single_file(
                args.gcode_file,
                wait_before_pause=args.wait_before_pause
            )
        
        # 场景 1：不同文件大小
        elif args.scenario in ['1', 'both']:
            gcode_files = runner.find_gcode_files(args.gcode_dir)
            if not gcode_files:
                logger.error(f"❌ 未找到 G-code 文件在: {args.gcode_dir}")
                sys.exit(1)
            
            runner.run_test_scenario_1_different_sizes(
                gcode_files,
                repeat_count=args.repeat,
                wait_before_pause=args.wait_before_pause
            )
        
        # 场景 2：单文件重复
        if args.scenario in ['2', 'both']:
            if not args.gcode_file:
                logger.error("❌ 场景 2/both 需要 --gcode-file 参数")
                sys.exit(1)
            
            if not os.path.exists(args.gcode_file):
                logger.error(f"❌ 文件不存在: {args.gcode_file}")
                sys.exit(1)
            
            runner.run_test_scenario_2_single_file_repeat(
                args.gcode_file,
                repeat_count=args.repeat,
                wait_before_pause=args.wait_before_pause
            )
        
        # 保存结果
        os.makedirs(args.output_dir, exist_ok=True)
        runner.tester.print_summary()
        runner.tester.save_results_csv(
            os.path.join(args.output_dir, 'pause_test_results.csv')
        )
        runner.tester.save_results_json(
            os.path.join(args.output_dir, 'pause_test_results.json')
        )
        runner.generate_analysis_plots(args.output_dir)
        
        logger.info("✓✓✓ 所有测试完成！")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  用户中断测试")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()