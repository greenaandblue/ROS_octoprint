#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OctoPrint 暂停延迟测试执行脚本 - 改进版
用途：获取函数关系 T_pause = f(S_gcode)
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List
import json

try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("警告：matplotlib 未安装，无法生成图表")
    print("安装方式：pip install matplotlib numpy")

from Integrated_Pause_Testing_Suite import OctoPrintPhysicalPauseTester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestRunner:
    """测试运行器"""
    
    def __init__(self, octoprint_url: str, api_key: str):
        self.tester = OctoPrintPhysicalPauseTester(octoprint_url, api_key)
        logger.info(f"[INIT] ✓ 测试器已初始化")
        logger.info(f"[INIT] URL: {octoprint_url}")
    
    def find_gcode_files(self, directory: str) -> List[str]:
        """查找目录中的 G-code 文件"""
        if not os.path.isdir(directory):
            logger.error(f"[FILE] ✗ 目录不存在: {directory}")
            return []
        
        gcode_files = []
        for ext in ['*.gcode', '*.g', '*.gco', '*.nc']:
            gcode_files.extend(Path(directory).glob(ext))
        
        files_list = sorted([str(f) for f in gcode_files])
        logger.info(f"[FILE] ✓ 在 {directory} 中找到 {len(files_list)} 个 G-code 文件")
        return files_list
    
    def run_scenario_different_sizes(self,
                                    gcode_files: List[str],
                                    repeat_count: int = 3,
                                    wait_before_pause: float = 5.0):
        """
        场景 1：不同文件大小的暂停延迟
        目标：得到 T_pause = f(S_gcode)
        """
        logger.info("\n" + "="*70)
        logger.info("[SCENARIO 1] 不同文件大小的暂停延迟测试")
        logger.info("="*70)
        logger.info(f"[SCENARIO] 文件数: {len(gcode_files)}")
        logger.info(f"[SCENARIO] 每个文件重复: {repeat_count} 次")
        logger.info(f"[SCENARIO] 暂停前等待: {wait_before_pause:.1f} 秒")
        
        # 按文件大小排序
        gcode_files_sorted = sorted(gcode_files, 
                                    key=lambda f: os.path.getsize(f))
        
        logger.info(f"\n[SCENARIO] 测试文件列表：")
        for i, f in enumerate(gcode_files_sorted, 1):
            size_mb = os.path.getsize(f) / (1024 * 1024)
            logger.info(f"  {i}. {Path(f).name} ({size_mb:.2f} MB)")
        
        self.tester.run_batch_tests(
            gcode_files_sorted,
            wait_before_pause=wait_before_pause,
            repeat_count=repeat_count
        )
    
    def run_scenario_single_file_repeat(self,
                                       gcode_file: str,
                                       repeat_count: int = 10,
                                       wait_before_pause: float = 5.0):
        """
        场景 2：单个文件重复测试
        目标：检查同一文件多次测试的稳定性
        """
        logger.info("\n" + "="*70)
        logger.info("[SCENARIO 2] 单文件重复测试")
        logger.info("="*70)
        logger.info(f"[SCENARIO] 文件: {Path(gcode_file).name}")
        logger.info(f"[SCENARIO] 重复次数: {repeat_count}")
        logger.info(f"[SCENARIO] 暂停前等待: {wait_before_pause:.1f} 秒")
        
        import time
        for i in range(repeat_count):
            logger.info(f"\n[REPEAT {i+1}/{repeat_count}]")
            result = self.tester.run_single_pause_test(
                gcode_file,
                wait_before_pause=wait_before_pause
            )
            if result:
                self.tester.test_results.append(result)
            
            if i < repeat_count - 1:
                logger.info("等待 15 秒后进行下一个测试...")
                time.sleep(15)
    
    def generate_analysis(self, output_dir: str = '.'):
        """生成分析报告"""
        if not self.tester.test_results:
            logger.warning("[ANALYSIS] 没有测试结果可用于分析")
            return
        
        results = self.tester.test_results
        
        # 提取数据
        sizes_mb = [r['file_size_mb'] for r in results]
        latencies_s = [r['pause_latency_s'] for r in results]
        latencies_ms = [t * 1000 for t in latencies_s]
        gcode_lines = [r['gcode_lines'] for r in results]
        
        # 生成文本报告
        logger.info("\n" + "="*70)
        logger.info("[ANALYSIS] 分析结果")
        logger.info("="*70)
        
        logger.info(f"\n【原始数据】")
        logger.info(f"  总测试数: {len(results)}")
        logger.info(f"  文件大小范围: {min(sizes_mb):.2f} - {max(sizes_mb):.2f} MB")
        logger.info(f"  G-code行数范围: {min(gcode_lines)} - {max(gcode_lines)} 行")
        logger.info(f"  暂停延迟范围: {min(latencies_ms):.2f} - {max(latencies_ms):.2f} ms")
        
        logger.info(f"\n【统计指标】")
        import statistics
        logger.info(f"  平均延迟: {statistics.mean(latencies_ms):.2f} ms")
        logger.info(f"  中位数延迟: {statistics.median(latencies_ms):.2f} ms")
        if len(latencies_ms) > 1:
            logger.info(f"  标准差: {statistics.stdev(latencies_ms):.2f} ms")
        
        # 如果有numpy，计算相关性
        if HAS_MATPLOTLIB:
            import numpy as np
            if len(set(sizes_mb)) > 1:
                corr_size = np.corrcoef(sizes_mb, latencies_ms)[0, 1]
                logger.info(f"  文件大小 vs 延迟相关性: {corr_size:.4f}")
            
            if len(set(gcode_lines)) > 1:
                corr_lines = np.corrcoef(gcode_lines, latencies_ms)[0, 1]
                logger.info(f"  G-code行数 vs 延迟相关性: {corr_lines:.4f}")
                
                # 计算拟合函数
                if len(gcode_lines) > 2:
                    z = np.polyfit(gcode_lines, latencies_ms, 1)
                    logger.info(f"\n【函数拟合】")
                    logger.info(f"  T_pause = {z[0]:.6f} * S_gcode + {z[1]:.2f}")
                    logger.info(f"  其中 S_gcode 为 G-code 行数")
                    logger.info(f"       T_pause 为暂停延迟 (ms)")
        
        logger.info(f"\n【详细结果】")
        logger.info(f"{'序号':<6} {'文件':<25} {'大小(MB)':<10} {'行数':<8} {'延迟(ms)':<12} {'原因'}")
        logger.info("-" * 80)
        
        for i, result in enumerate(sorted(results, key=lambda x: x['pause_latency_s']), 1):
            logger.info(
                f"{i:<6} {result['file_name']:<25} "
                f"{result['file_size_mb']:<10.2f} "
                f"{result['gcode_lines']:<8} "
                f"{result['pause_latency_s']*1000:<12.2f} "
                f"{result['stop_reason']}"
            )
        
        logger.info(f"\n{'='*70}\n")
        
        # 生成图表
        if HAS_MATPLOTLIB:
            self._generate_plots(sizes_mb, latencies_ms, gcode_lines, output_dir)
    
    def _generate_plots(self, sizes_mb, latencies_ms, gcode_lines, output_dir):
        """生成可视化图表"""
        os.makedirs(output_dir, exist_ok=True)
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('OctoPrint 暂停延迟分析 - T_pause = f(S_gcode)', 
                    fontsize=16, fontweight='bold')
        
        # 图1：延迟 vs 文件大小
        ax = axes[0, 0]
        ax.scatter(sizes_mb, latencies_ms, s=100, alpha=0.6, color='blue')
        if len(set(sizes_mb)) > 1:
            z = np.polyfit(sizes_mb, latencies_ms, 1)
            p = np.poly1d(z)
            x_line = np.linspace(min(sizes_mb), max(sizes_mb), 100)
            ax.plot(x_line, p(x_line), "r--", alpha=0.8, 
                   label=f'T_pause = {z[0]:.2f}*S + {z[1]:.2f}')
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
            x_line = np.linspace(min(gcode_lines), max(gcode_lines), 100)
            ax.plot(x_line, p(x_line), "r--", alpha=0.8,
                   label=f'T_pause = {z[0]:.6f}*N + {z[1]:.2f}')
            ax.legend()
        ax.set_xlabel('G-code 行数')
        ax.set_ylabel('暂停延迟 (ms)')
        ax.set_title('暂停延迟 vs G-code 行数【关键图表】')
        ax.grid(True, alpha=0.3)
        
        # 图3：延迟分布直方图
        ax = axes[1, 0]
        ax.hist(latencies_ms, bins=max(3, len(latencies_ms)//2), 
               alpha=0.7, color='purple', edgecolor='black')
        mean_val = np.mean(latencies_ms)
        median_val = np.median(latencies_ms)
        ax.axvline(mean_val, color='red', linestyle='--', linewidth=2, 
                  label=f'均值: {mean_val:.2f}ms')
        ax.axvline(median_val, color='orange', linestyle='--', linewidth=2, 
                  label=f'中位数: {median_val:.2f}ms')
        ax.set_xlabel('暂停延迟 (ms)')
        ax.set_ylabel('频数')
        ax.set_title('暂停延迟分布')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # 图4：时间序列
        ax = axes[1, 1]
        ax.plot(range(len(latencies_ms)), latencies_ms, marker='o', 
               linestyle='-', color='teal', linewidth=2, markersize=6)
        ax.set_xlabel('测试序号')
        ax.set_ylabel('暂停延迟 (ms)')
        ax.set_title('暂停延迟时间序列')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        output_file = os.path.join(output_dir, 'pause_analysis.png')
        plt.savefig(output_file, dpi=150)
        logger.info(f"[PLOT] ✓ 分析图表已保存: {output_file}")
        plt.close()


def main():
    # 配置
    CONFIG = {
        'url': 'http://octopi.local',                    # ← 改这里
        'api_key': 'YOUR_API_KEY_HERE',                  # ← 改这里
        'scenario': '1',                                  # 1=不同大小, 2=单文件重复, both=全部
        'gcode_dir': './gcode',                          # G-code文件目录
        'gcode_file': None,                              # 场景2：指定单个文件
        'repeat': 2,                                      # 重复次数
        'wait_before_pause': 5.0,                        # 暂停前等待(秒)
        'output_dir': './test_results',                  # 输出目录
        'tolerance': 0.05,                               # 位置容限(mm)
        'stable_count': 5,                               # 连续稳定次数
    }
    
    parser = argparse.ArgumentParser(
        description='OctoPrint 暂停延迟测试 - 求解 T_pause = f(S_gcode)'
    )
    
    parser.add_argument('--url', default=CONFIG['url'], 
                       help='OctoPrint URL')
    parser.add_argument('--api-key', default=CONFIG['api_key'], 
                       help='OctoPrint API Key')
    parser.add_argument('--scenario', choices=['1', '2', 'both'], 
                       default=CONFIG['scenario'],
                       help='1=不同文件大小, 2=单文件重复, both=全部')
    parser.add_argument('--gcode-dir', default=CONFIG['gcode_dir'],
                       help='G-code 文件目录')
    parser.add_argument('--gcode-file', default=CONFIG['gcode_file'],
                       help='指定单个 G-code 文件')
    parser.add_argument('--repeat', type=int, default=CONFIG['repeat'],
                       help='重复次数')
    parser.add_argument('--wait-before-pause', type=float, 
                       default=CONFIG['wait_before_pause'],
                       help='暂停前等待时间(秒)')
    parser.add_argument('--output-dir', default=CONFIG['output_dir'],
                       help='输出目录')
    parser.add_argument('--tolerance', type=float, default=CONFIG['tolerance'],
                       help='位置容限(mm)')
    parser.add_argument('--stable-count', type=int, default=CONFIG['stable_count'],
                       help='连续稳定次数')
    
    args = parser.parse_args()
    
    # 初始化
    runner = TestRunner(args.url, args.api_key)
    runner.tester.test_config['position_tolerance'] = args.tolerance
    runner.tester.test_config['stable_count'] = args.stable_count
    
    logger.info("="*70)
    logger.info("OctoPrint 暂停延迟测试框架 v2.0")
    logger.info("目标：求解 T_pause = f(S_gcode) 的函数关系")
    logger.info("="*70)
    logger.info(f"[CONFIG] URL: {args.url}")
    logger.info(f"[CONFIG] 位置容限: {args.tolerance} mm")
    logger.info(f"[CONFIG] 稳定次数: {args.stable_count}")
    
    try:
        # 场景 1：不同文件大小
        if args.scenario in ['1', 'both']:
            gcode_files = runner.find_gcode_files(args.gcode_dir)
            if not gcode_files:
                logger.error(f"[ERROR] ✗ 未找到 G-code 文件在: {args.gcode_dir}")
                sys.exit(1)
            
            runner.run_scenario_different_sizes(
                gcode_files,
                repeat_count=args.repeat,
                wait_before_pause=args.wait_before_pause
            )
        
        # 场景 2：单文件重复
        if args.scenario in ['2', 'both']:
            if not args.gcode_file:
                logger.error("[ERROR] ✗ 场景 2 需要 --gcode-file 参数")
                sys.exit(1)
            
            if not os.path.exists(args.gcode_file):
                logger.error(f"[ERROR] ✗ 文件不存在: {args.gcode_file}")
                sys.exit(1)
            
            runner.run_scenario_single_file_repeat(
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
        
        # 生成分析
        runner.generate_analysis(args.output_dir)
        
        logger.info("[SUCCESS] ✓ 所有测试完成！")
        logger.info(f"[SUCCESS] 结果保存在: {args.output_dir}")
        
    except KeyboardInterrupt:
        logger.info("\n[INTERRUPT] ✗ 用户中断测试")
        sys.exit(0)
    except Exception as e:
        logger.error(f"[FATAL] ✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()