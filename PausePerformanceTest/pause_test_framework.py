#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G-code暂停性能测试框架
针对GCodeSender的精准暂停系统的性能测试
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
    """暂停性能测试框架"""
    
    def __init__(self, gcode_sender):
        """
        初始化测试框架
        
        Args:
            gcode_sender: GCodeSender实例
        """
        self.sender = gcode_sender
        self.test_results = []
        self.test_config = {
            'repeat_count': 3, # repeat times (optinaal change)
            'wait_after_pause': 1.0,  # 暂停后等待时间(秒)
            'timeout': 300.0,  # 单次测试超时(秒)
        }
    
    # ==================== 测试用例生成 ====================
    
    def generate_dimension1_testcases(self, 
                                     gcode_file: str, 
                                     pause_lines: List[int]) -> List[Dict]:
        """
        维度1：同一文件，在不同行数暂停
        测试行数对暂停性能的影响
        
        Args:
            gcode_file: G-code文件路径
            pause_lines: 要暂停的行数列表，如 [500, 1000, 2000, 3000]
        
        Returns:
            测试用例列表
        """
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
        """
        维度2：同一文件，在不同进度百分比暂停
        测试进度百分比对暂停性能的影响
        
        Args:
            gcode_file: G-code文件路径
            pause_percents: 百分比列表，如 [10, 20, 30, 50, 80]
        """
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
        """
        维度3：不同文件，在相同行数暂停
        测试不同文件特性对暂停性能的影响
        
        Args:
            gcode_files: G-code文件列表
            pause_line: 固定暂停行数
        """
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
        执行单个测试用例
        
        测试流程：
        1. 启动文件打印
        2. 等待到达指定行数
        3. 测量暂停耗时
        4. 等待一段时间
        5. 测量恢复耗时
        6. 等待文件完成
        
        Returns:
            {
                'testcase': 测试用例信息,
                'pause_times': [单位: 秒],
                'resume_times': [单位: 秒],
                'total_times': [暂停+恢复总时间],
                'stats': 统计数据
            }
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
                time.sleep(1)  # 确保打印开始
                
                # 2. 等待到达指定行数
                if not self._wait_until_line(testcase['pause_line'], 
                                             timeout=self.test_config['timeout']):
                    raise TimeoutError(f"未在规定时间内到达第{testcase['pause_line']}行")
                
                logger.debug(f"    已到达第{testcase['pause_line']}行")
                
                # 3. 测量暂停耗时
                start_pause = time.perf_counter()
                pause_success = self.sender.pause()
                pause_time = time.perf_counter() - start_pause
                
                if not pause_success:
                    raise RuntimeError("暂停失败")
                
                pause_times.append(pause_time)
                logger.debug(f"    暂停耗时: {pause_time:.4f}s")
                
                # 4. 暂停状态保持
                time.sleep(self.test_config['wait_after_pause'])
                
                # 5. 测量恢复耗时
                start_resume = time.perf_counter()
                resume_success = self.sender.resume()
                resume_time = time.perf_counter() - start_resume
                
                if not resume_success:
                    raise RuntimeError("恢复失败")
                
                resume_times.append(resume_time)
                total_times.append(pause_time + resume_time)
                logger.debug(f"    恢复耗时: {resume_time:.4f}s")
                
                # 6. 等待文件完成或继续执行（可选择只等待一段时间）
                # 为了节省测试时间，这里只等待10秒后停止
                self._wait_file_continue(timeout=10)
                self.sender.stop()
                
            except Exception as e:
                logger.error(f"    测试失败: {str(e)}")
                errors.append(str(e))
                self.sender.stop()  # 确保停止
                time.sleep(2)  # 等待打印机稳定
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
        logger.info(f"    暂停耗时: {result['stats']['pause_mean']:.4f}s "
                   f"(±{result['stats']['pause_stdev']:.4f}s)")
        logger.info(f"    恢复耗时: {result['stats']['resume_mean']:.4f}s "
                   f"(±{result['stats']['resume_stdev']:.4f}s)")
        
        return result
    
    def run_all_tests(self, testcases: List[Dict]) -> List[Dict]:
        """
        执行所有测试用例
        
        Args:
            testcases: 测试用例列表
        
        Returns:
            所有测试结果列表
        """
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
            
            # 测试间隔
            if idx < total:
                logger.info("等待3秒后开始下一个测试...")
                time.sleep(3)
        
        self.test_results = all_results
        logger.info(f"\n{'='*70}")
        logger.info(f"所有测试完成 - 成功: {len(all_results)}/{total}")
        logger.info(f"{'='*70}")
        
        return all_results
    
    # ==================== 数据分析与输出 ====================
    
    def generate_report(self, output_file: str = 'pause_test_report.json'): #可选修改：改成你想要的文件名file name report
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
        
        # 按维度分组
        dimensions = {}
        for result in self.test_results:
            dim = result['testcase']['dimension']
            if dim not in dimensions:
                dimensions[dim] = []
            dimensions[dim].append(result)
        
        # 输出各维度结果
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
                    logger.warning(f"  错误: {result['errors']}")
        
        logger.info("\n" + "="*70)
    
    def export_csv(self, output_file: str = 'pause_test_results.csv'):
        """导出CSV格式的详细数据"""
        import csv
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写表头
            writer.writerow([
                '维度', '文件', '描述', '暂停行数', '进度%', '总行数',
                '暂停耗时(ms)', '恢复耗时(ms)', '总耗时(ms)', '错误'
            ])
            
            # 写数据
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
        """计算G-code文件的有效行数（过滤注释和空行）"""
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
        
        Args:
            target_line: 目标行数
            timeout: 超时时间(秒)
        
        Returns:
            是否成功到达目标行
        """
        start_time = time.time()
        last_line = 0
        
        while time.time() - start_time < timeout:
            progress = self.sender.get_progress()
            current_line = progress.get('current_line', 0)
            
            if current_line >= target_line:
                logger.debug(f"已到达第{current_line}行")
                return True
            
            # 进度日志
            if current_line != last_line and current_line % 100 == 0:
                logger.debug(f"进度: {current_line}/{progress.get('total_lines', '?')} 行")
                last_line = current_line
            
            time.sleep(0.5)
        
        logger.error(f"超时: 未能在{timeout}秒内到达第{target_line}行")
        return False
    
    def _wait_file_continue(self, timeout: float = 10):
        """等待文件继续执行一段时间"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            progress = self.sender.get_progress()
            if progress.get('state') != 'running':
                break
            time.sleep(0.5)
    
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


# ==================== 使用示例 ====================
# 我放进了run_test里面
'''

if __name__ == '__main__':
    from your_module import GCodeSender
    
    # 初始化发送器
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "your_api_key_here"
    sender = GCodeSender(OCTOPRINT_URL, API_KEY)
    
    # 创建测试框架
    tester = PausePerformanceTest(sender)
    
    # 配置测试参数
    tester.test_config['repeat_count'] = 3  # 每个测试重复3次
    tester.test_config['wait_after_pause'] = 1.0  # 暂停后等待1秒
    
    # 示例：准备三个维度的测试
    testcases = []
    
    # 维度1：同一文件，不同行数暂停
    testcases += tester.generate_dimension1_testcases(
        'test_file.gcode', # remember to change the file path!!!
        pause_lines=[500, 1000, 2000, 3000]
    )
    
    # 维度2：同一文件，不同百分比暂停
    testcases += tester.generate_dimension2_testcases(
        'test_file.gcode', ####
        pause_percents=[10, 20, 30, 50, 80]
    )
    
    # 维度3：不同文件，相同行数暂停
    testcases += tester.generate_dimension3_testcases(
        ['file1.gcode', 'file2.gcode', 'file3.gcode'], ####
        pause_line=2000
    )
    
    # 执行测试
    try:
        tester.run_all_tests(testcases)
        
        # 生成报告
        tester.generate_report('pause_test_report.json')
        tester.export_csv('pause_test_results.csv')
        tester.print_summary()
        
    finally:
        sender.close()
'''