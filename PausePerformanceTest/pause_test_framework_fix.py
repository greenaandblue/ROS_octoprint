#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G-code暂停性能测试框架 - 改进版
修复：
1. 使用与gcode_sender.py相同的pause/resume逻辑
2. 避免OctoPrint缓冲问题（大文件vs小文件问题）
3. 解决T指令错误
"""

import time
import json
import os
import statistics
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PausePerformanceTest:
    """暂停性能测试框架 - 改进版"""
    
    def __init__(self, gcode_sender):
        """
        初始化测试框架
        
        Args:
            gcode_sender: GCodeSender实例
        """
        self.sender = gcode_sender
        self.test_results = []
        self.test_config = {
            'repeat_count': 3,
            'wait_after_pause': 1.0,  # 暂停后等待时间(秒)
            'timeout': 300.0,  # 单次测试超时(秒)
            'check_interval': 0.5,  # 检查进度间隔(秒) - 重要：不要太频繁
            'stability_wait': 2.0,  # 确保打印机稳定的等待时间
        }
    
    # ==================== 测试用例生成 ====================
    
    def generate_dimension1_testcases(self, 
                                     gcode_file: str, 
                                     pause_lines: List[int]) -> List[Dict]:
        """维度1：同一文件，在不同行数暂停"""
        total_lines = self._count_gcode_lines(gcode_file)
        if total_lines == 0:
            logger.error(f"文件为空: {gcode_file}")
            return []
        
        testcases = []
        for line_num in pause_lines:
            if line_num < total_lines:
                percent = (line_num / total_lines) * 100
                testcases.append({
                    'dimension': 'line_number',
                    'file': gcode_file,
                    'pause_line': line_num,
                    'pause_percent': percent,
                    'total_lines': total_lines,
                    'description': f"在第{line_num}行暂停({percent:.1f}%)"
                })
            else:
                logger.warning(f"暂停行数{line_num}超过总行数{total_lines}，已跳过")
        
        return testcases
    
    def generate_dimension2_testcases(self, 
                                     gcode_file: str, 
                                     pause_percents: List[float]) -> List[Dict]:
        """维度2：同一文件，在不同进度百分比暂停"""
        total_lines = self._count_gcode_lines(gcode_file)
        if total_lines == 0:
            return []
        
        testcases = []
        for percent in pause_percents:
            if 0 < percent < 100:
                line_num = int((percent / 100) * total_lines)
                testcases.append({
                    'dimension': 'percentage',
                    'file': gcode_file,
                    'pause_line': line_num,
                    'pause_percent': percent,
                    'total_lines': total_lines,
                    'description': f"在{percent:.0f}%进度暂停(第{line_num}行)"
                })
        
        return testcases
    
    def generate_dimension3_testcases(self, 
                                     gcode_files: List[str], 
                                     pause_line: int) -> List[Dict]:
        """维度3：不同文件，在相同行数暂停"""
        testcases = []
        
        for gcode_file in gcode_files:
            total_lines = self._count_gcode_lines(gcode_file)
            if total_lines == 0:
                logger.warning(f"文件为空，已跳过: {gcode_file}")
                continue
            
            if pause_line < total_lines:
                percent = (pause_line / total_lines) * 100
                testcases.append({
                    'dimension': 'different_file',
                    'file': gcode_file,
                    'pause_line': pause_line,
                    'pause_percent': percent,
                    'total_lines': total_lines,
                    'description': f"{Path(gcode_file).name} - 第{pause_line}行({percent:.1f}%)"
                })
            else:
                logger.warning(f"文件{gcode_file}总行数{total_lines}少于{pause_line}，已跳过")
        
        return testcases
    
    # ==================== 核心测试执行 ====================
    
    def run_single_test(self, testcase: Dict, repeat_count: int = 3) -> Optional[Dict]:
        """
        执行单个测试用例 - 改进版
        
        关键改进：
        1. 等待打印机完全稳定后再暂停
        2. 确保pause指令被完全处理
        3. 检查打印机状态而不仅仅依赖行数
        4. 避免OctoPrint的缓冲问题
        """
        logger.info(f"\n执行测试: {testcase['description']}")
        logger.info(f"文件: {testcase['file']}")
        
        pause_times = []
        resume_times = []
        total_times = []
        errors = []
        
        for attempt in range(repeat_count):
            try:
                logger.info(f"  [重复 {attempt + 1}/{repeat_count}]")
                
                # 1. 启动文件打印
                success = self.sender.start_file_print(testcase['file'])
                if not success:
                    raise RuntimeError("无法启动文件打印")
                
                logger.debug(f"    文件打印已启动")
                
                # 2. 等待打印机稳定运行
                # 这很重要：小文件可能还在处理初始化代码，大文件也可能需要时间建立缓冲
                time.sleep(self.test_config['stability_wait'])
                
                # 3. 等待到达指定行数
                if not self._wait_until_line(testcase['pause_line'], 
                                             timeout=self.test_config['timeout']):
                    raise TimeoutError(f"未在规定时间内到达第{testcase['pause_line']}行")
                
                logger.debug(f"    已到达第{testcase['pause_line']}行")
                
                # 4. 再次等待打印机稳定，确保缓冲已清空
                # 这是解决"pause后还会运动"的关键：给打印机时间处理缓冲区
                time.sleep(0.5)
                
                # 5. 核心：测量pause耗时
                # 使用与gcode_sender.py相同的pause逻辑
                start_pause = time.perf_counter()
                pause_success = self.sender.pause()
                pause_time = time.perf_counter() - start_pause
                
                if not pause_success:
                    raise RuntimeError(f"暂停失败，状态: {self.sender.state.value}")
                
                pause_times.append(pause_time)
                logger.debug(f"    暂停耗时: {pause_time:.4f}s")
                
                # 6. 验证打印机确实已暂停
                # 这很重要：小文件暂停后如果还在运动，说明缓冲还有命令
                if not self._verify_paused(timeout=5.0):
                    logger.warning(f"    警告：暂停后打印机仍在运动")
                    errors.append("暂停后打印机仍在运动（可能是缓冲问题）")
                
                # 7. 暂停状态保持
                time.sleep(self.test_config['wait_after_pause'])
                
                # 8. 核心：测量resume耗时
                start_resume = time.perf_counter()
                resume_success = self.sender.resume()
                resume_time = time.perf_counter() - start_resume
                
                if not resume_success:
                    raise RuntimeError(f"恢复失败，状态: {self.sender.state.value}")
                
                resume_times.append(resume_time)
                total_times.append(pause_time + resume_time)
                logger.debug(f"    恢复耗时: {resume_time:.4f}s")
                
                # 9. 让打印继续一段时间以验证恢复正常
                time.sleep(2)
                
                # 10. 停止打印机
                self.sender.stop()
                
                # 11. 等待打印机完全停止
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"    测试失败: {str(e)}")
                errors.append(str(e))
                self.sender.stop()
                time.sleep(2)
                continue
        
        # 计算统计数据
        if not pause_times:
            logger.error("该测试用例所有重复都失败了")
            return None
        
        result = {
            'testcase': testcase,
            'pause_times': pause_times,
            'resume_times': resume_times,
            'total_times': total_times,
            'errors': errors,
            'stats': self._calculate_stats(pause_times, resume_times, total_times)
        }
        
        logger.info(f"  ✓ 测试完成")
        logger.info(f"    暂停耗时: {result['stats']['pause_mean']*1000:.2f}ms "
                   f"(±{result['stats']['pause_stdev']*1000:.2f}ms)")
        logger.info(f"    恢复耗时: {result['stats']['resume_mean']*1000:.2f}ms "
                   f"(±{result['stats']['resume_stdev']*1000:.2f}ms)")
        
        return result
    
    def run_all_tests(self, testcases: List[Dict]) -> List[Dict]:
        """执行所有测试用例"""
        all_results = []
        total = len(testcases)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"开始测试 - 共 {total} 个测试用例")
        logger.info(f"每个用例重复 {self.test_config['repeat_count']} 次")
        logger.info(f"{'='*70}")
        
        for idx, testcase in enumerate(testcases, 1):
            logger.info(f"\n[{idx}/{total}] {testcase['dimension']}")
            
            result = self.run_single_test(testcase, self.test_config['repeat_count'])
            if result:
                all_results.append(result)
            
            # 测试间隔 - 让打印机充分冷却和稳定
            if idx < total:
                logger.info("等待5秒后开始下一个测试...")
                time.sleep(5)
        
        self.test_results = all_results
        logger.info(f"\n{'='*70}")
        logger.info(f"所有测试完成 - 成功: {len(all_results)}/{total}")
        logger.info(f"{'='*70}")
        
        return all_results
    
    # ==================== 数据分析与输出 ====================
    
    def generate_report(self, output_file: str = 'pause_test_report.json'):
        """生成JSON格式的测试报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'test_config': self.test_config,
            'total_tests': len(self.test_results),
            'results': []
        }
        
        for result in self.test_results:
            report['results'].append({
                'description': result['testcase']['description'],
                'dimension': result['testcase']['dimension'],
                'file': result['testcase']['file'],
                'pause_line': result['testcase']['pause_line'],
                'pause_percent': round(result['testcase']['pause_percent'], 2),
                'total_lines': result['testcase']['total_lines'],
                'pause_times_ms': [round(t * 1000, 2) for t in result['pause_times']],
                'resume_times_ms': [round(t * 1000, 2) for t in result['resume_times']],
                'total_times_ms': [round(t * 1000, 2) for t in result['total_times']],
                'errors': result['errors'],
                'stats': {
                    'pause_mean_ms': round(result['stats']['pause_mean'] * 1000, 2),
                    'pause_stdev_ms': round(result['stats']['pause_stdev'] * 1000, 2),
                    'pause_min_ms': round(result['stats']['pause_min'] * 1000, 2),
                    'pause_max_ms': round(result['stats']['pause_max'] * 1000, 2),
                    'resume_mean_ms': round(result['stats']['resume_mean'] * 1000, 2),
                    'resume_stdev_ms': round(result['stats']['resume_stdev'] * 1000, 2),
                    'resume_min_ms': round(result['stats']['resume_min'] * 1000, 2),
                    'resume_max_ms': round(result['stats']['resume_max'] * 1000, 2),
                    'total_mean_ms': round(result['stats']['total_mean'] * 1000, 2),
                    'total_stdev_ms': round(result['stats']['total_stdev'] * 1000, 2),
                }
            })
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n✓ 报告已保存: {output_file}")
        return report
    
    def print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "="*70)
        logger.info("测试摘要")
        logger.info("="*70)
        
        dimensions = {}
        for result in self.test_results:
            dim = result['testcase']['dimension']
            if dim not in dimensions:
                dimensions[dim] = []
            dimensions[dim].append(result)
        
        for dim_name, results in dimensions.items():
            logger.info(f"\n【维度: {dim_name}】")
            logger.info("-" * 70)
            
            for result in results:
                tc = result['testcase']
                st = result['stats']
                
                logger.info(f"\n  {tc['description']}")
                logger.info(f"  文件: {tc['file']}")
                logger.info(f"  暂停点: 第{tc['pause_line']}行 ({tc['pause_percent']:.1f}%)")
                logger.info(f"  样本数: {len(result['pause_times'])}")
                logger.info(f"  暂停耗时: {st['pause_mean']*1000:.2f} ± {st['pause_stdev']*1000:.2f} ms "
                           f"[{st['pause_min']*1000:.2f}, {st['pause_max']*1000:.2f}]")
                logger.info(f"  恢复耗时: {st['resume_mean']*1000:.2f} ± {st['resume_stdev']*1000:.2f} ms "
                           f"[{st['resume_min']*1000:.2f}, {st['resume_max']*1000:.2f}]")
                logger.info(f"  总耗时:   {st['total_mean']*1000:.2f} ± {st['total_stdev']*1000:.2f} ms")
                
                if result['errors']:
                    logger.warning(f"  警告: {result['errors']}")
        
        logger.info("\n" + "="*70)
    
    def export_csv(self, output_file: str = 'pause_test_results.csv'):
        """导出CSV格式的详细数据"""
        import csv
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            writer.writerow([
                '维度', '文件', '描述', '暂停行数', '进度%', '总行数',
                '暂停耗时(ms)', '恢复耗时(ms)', '总耗时(ms)', '错误'
            ])
            
            for result in self.test_results:
                tc = result['testcase']
                for p_time, r_time, t_time in zip(
                    result['pause_times'], 
                    result['resume_times'],
                    result['total_times']
                ):
                    writer.writerow([
                        tc['dimension'],
                        os.path.basename(tc['file']),
                        tc['description'],
                        tc['pause_line'],
                        f"{tc['pause_percent']:.1f}",
                        tc['total_lines'],
                        f"{p_time*1000:.2f}",
                        f"{r_time*1000:.2f}",
                        f"{t_time*1000:.2f}",
                        ""
                    ])
        
        logger.info(f"\n✓ CSV已保存: {output_file}")
    
    # ==================== 辅助方法 ====================
    
    def _count_gcode_lines(self, file_path: str) -> int:
        """计算G-code文件的有效行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                count = sum(1 for line in f 
                           if line.strip() and not line.strip().startswith(';'))
                return count
        except Exception as e:
            logger.error(f"读取文件失败: {file_path} - {e}")
            return 0
    
    def _wait_until_line(self, target_line: int, timeout: float = 120) -> bool:
        """
        等待打印执行到指定行数
        改进：使用较长的检查间隔避免影响打印机
        """
        start_time = time.time()
        last_line = 0
        
        while time.time() - start_time < timeout:
            progress = self.sender.get_progress()
            current_line = progress.get('current_line', 0)
            
            if current_line >= target_line:
                logger.debug(f"已到达第{current_line}行")
                return True
            
            if current_line != last_line and current_line % 100 == 0:
                logger.debug(f"进度: {current_line}/{progress.get('total_lines', '?')} 行")
                last_line = current_line
            
            # 重要：检查间隔不要太短，避免频繁查询打印机状态
            time.sleep(self.test_config['check_interval'])
        
        logger.error(f"超时: 未能在{timeout}秒内到达第{target_line}行")
        return False
    
    def _verify_paused(self, timeout: float = 5.0) -> bool:
        """
        验证打印机确实已暂停
        这可以检测缓冲问题
        """
        start_time = time.time()
        last_line = None
        stable_count = 0
        
        while time.time() - start_time < timeout:
            progress = self.sender.get_progress()
            current_line = progress.get('current_line')
            state = progress.get('state')
            
            # 检查状态是否真的是暂停
            if state == 'paused':
                # 检查行数是否不再改变
                if current_line == last_line:
                    stable_count += 1
                    if stable_count >= 3:  # 连续3次检查行数未变
                        logger.debug("✓ 打印机已稳定暂停")
                        return True
                else:
                    stable_count = 0
                    last_line = current_line
                    logger.debug(f"暂停中但仍在处理: {current_line}行")
            
            time.sleep(0.3)
        
        return False
    
    def _calculate_stats(self, pause_times, resume_times, total_times):
        """计算统计数据"""
        return {
            'pause_mean': statistics.mean(pause_times),
            'pause_stdev': statistics.stdev(pause_times) if len(pause_times) > 1 else 0,
            'pause_min': min(pause_times),
            'pause_max': max(pause_times),
            'resume_mean': statistics.mean(resume_times),
            'resume_stdev': statistics.stdev(resume_times) if len(resume_times) > 1 else 0,
            'resume_min': min(resume_times),
            'resume_max': max(resume_times),
            'total_mean': statistics.mean(total_times),
            'total_stdev': statistics.stdev(total_times) if len(total_times) > 1 else 0,
        }