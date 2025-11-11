#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成版：OctoPrint 暂停延迟测试框架 + G-code 发送器
核心改进：
1. 正确的属性类型声明
2. 详细的操作反馈日志
3. 床加热等待与G-code执行解耦
4. 完整的数据采集流程
"""

import requests
import time
import json
import csv
import os
import statistics
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional, List
from pathlib import Path
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StopReason(Enum):
    """停止原因"""
    POSITION_STABLE = "位置稳定"
    TIMEOUT = "超时"
    ERROR = "错误"


class OctoPrintPhysicalPauseTester:
    """
    OctoPrint 物理暂停测试框架 - 改进版
    核心思想：通过打印头坐标变化判断"完全停下"
    """
    
    def __init__(self, octoprint_url: str, api_key: str):
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        self.headers = {'X-Api-Key': api_key}
        self.test_results = []
        self.test_config = {
            'position_tolerance': 0.05,      # 位置容限 (mm)
            'stable_count': 5,               # 连续稳定次数
            'check_interval': 0.2,           # 检查间隔 (秒)
            'max_wait_time': 30.0,           # 最长等待时间 (秒)
            'pre_pause_stabilize': 2.0,      # pause前让打印机稳定的时间
            'bed_heat_timeout': 600.0,       # 床加热最长等待时间 (秒)
            'bed_heat_tolerance': 5.0,       # 床加热温度容差 (°C)
        }
        
        # 改进：明确的属性声明，避免类型错误
        self._is_waiting_bed_heat: bool = False
        self._bed_heat_complete: bool = False
    
    # ==================== 核心通信 ====================
    
    def get_printer_state(self) -> Dict:
        """获取打印机完整状态"""
        try:
            resp = requests.get(
                f"{self.octoprint_url}/api/printer",
                headers=self.headers,
                timeout=5
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[API] 获取打印机状态失败: {e}")
            return {}
    
    def get_position(self) -> Optional[Dict]:
        """获取打印头当前位置"""
        state = self.get_printer_state()
        try:
            return state.get('position', {})
        except:
            return None
    
    def get_progress(self) -> Dict:
        """获取打印进度"""
        try:
            resp = requests.get(
                f"{self.octoprint_url}/api/job",
                headers=self.headers,
                timeout=5
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[API] 获取打印进度失败: {e}")
            return {}
    
    def send_pause_command(self) -> bool:
        """发送暂停命令"""
        try:
            resp = requests.post(
                f"{self.octoprint_url}/api/job",
                headers=self.headers,
                json={"command": "pause", "action": "pause"},
                timeout=5
            )
            resp.raise_for_status()
            logger.info("[PAUSE] ✓ 暂停命令已发送")
            return True
        except Exception as e:
            logger.error(f"[PAUSE] ✗ 发送暂停命令失败: {e}")
            return False
    
    def send_resume_command(self) -> bool:
        """发送恢复命令"""
        try:
            resp = requests.post(
                f"{self.octoprint_url}/api/job",
                headers=self.headers,
                json={"command": "pause", "action": "resume"},
                timeout=5
            )
            resp.raise_for_status()
            logger.info("[RESUME] ✓ 恢复命令已发送")
            return True
        except Exception as e:
            logger.error(f"[RESUME] ✗ 发送恢复命令失败: {e}")
            return False
    
    def is_printing(self) -> bool:
        """检查是否正在打印"""
        progress = self.get_progress()
        state = progress.get('state')
        return state in ['Printing', 'Paused']
    
    def is_paused(self) -> bool:
        """检查是否已暂停"""
        progress = self.get_progress()
        state = progress.get('state')
        return state == 'Paused'
    
    # ==================== 床加热监测 ====================
    
    def _wait_for_bed_heating_complete(self) -> bool:
        """
        等待热床加热完成
        改进：增强反馈和状态判断
        """
        start_time = time.time()
        bed_stabilize_count = 0
        timeout = self.test_config['bed_heat_timeout']
        tolerance = self.test_config['bed_heat_tolerance']
        
        logger.info("[BED] 开始监测热床温度...")
        self._is_waiting_bed_heat = True
        self._bed_heat_complete = False
        
        last_log_time = start_time
        
        while time.time() - start_time < timeout:
            try:
                state = self.get_printer_state()
                temp_data = state.get('temperature', {})
                bed = temp_data.get('bed', {})
                current_bed_temp = bed.get('actual', 0)
                target_bed_temp = bed.get('target', 0)
                
                progress = self.get_progress()
                print_state = progress.get('state', 'Unknown')
                
                # 定期输出（每5秒一次）
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    elapsed = int(current_time - start_time)
                    logger.info(
                        f"[BED] {elapsed:3d}s | 温度: {current_bed_temp:6.1f}°C / {target_bed_temp:6.1f}°C | "
                        f"状态: {print_state}"
                    )
                    last_log_time = current_time
                
                # 判断逻辑
                if target_bed_temp == 0:
                    logger.info("[BED] ✓ 热床无需加热，直接开始")
                    self._is_waiting_bed_heat = False
                    self._bed_heat_complete = True
                    return True
                
                if current_bed_temp >= (target_bed_temp - tolerance):
                    bed_stabilize_count += 1
                    if bed_stabilize_count == 1:
                        logger.info(f"[BED] 热床温度达到 ({current_bed_temp:.1f}°C ≈ {target_bed_temp:.1f}°C)")
                    logger.debug(f"[BED] 稳定计数: [{bed_stabilize_count}/3]")
                    
                    if bed_stabilize_count >= 3:
                        logger.info("[BED] ✓ 热床加热完成，准备开始测试")
                        self._is_waiting_bed_heat = False
                        self._bed_heat_complete = True
                        time.sleep(1)
                        return True
                else:
                    bed_stabilize_count = 0
                
                time.sleep(2)
                
            except Exception as e:
                logger.warning(f"[BED] 获取温度信息失败: {e}")
                time.sleep(2)
        
        logger.error(f"[BED] ✗ 超时：热床加热超过 {timeout}s 未完成")
        self._is_waiting_bed_heat = False
        self._bed_heat_complete = False
        return False
    
    # ==================== 位置监测 ====================
    
    def _calculate_position_change(self, pos1: Dict, pos2: Dict) -> float:
        """计算两个位置之间的变化量（不计e轴）"""
        if not pos1 or not pos2:
            return float('inf')
        
        dx = abs(pos1.get('x', 0) - pos2.get('x', 0))
        dy = abs(pos1.get('y', 0) - pos2.get('y', 0))
        dz = abs(pos1.get('z', 0) - pos2.get('z', 0))
        
        distance = (dx**2 + dy**2 + dz**2) ** 0.5
        return distance
    
    def wait_until_physically_stopped(self,
                                     position_tolerance: Optional[float] = None,
                                     stable_count: Optional[int] = None,
                                     check_interval: Optional[float] = None,
                                     max_wait_time: Optional[float] = None
                                     ) -> Tuple[StopReason, float, List[Dict]]:
        """
        等待打印机物理上完全停下
        改进：详细的实时监测日志
        """
        pos_tol = position_tolerance or self.test_config['position_tolerance']
        stab_cnt = stable_count or self.test_config['stable_count']
        chk_int = check_interval or self.test_config['check_interval']
        max_time = max_wait_time or self.test_config['max_wait_time']
        
        start_time = time.time()
        prev_pos = None
        stable_counter = 0
        position_history = []
        
        logger.info(f"[MONITOR] 开始监测打印头位置")
        logger.info(f"[MONITOR] 容限: {pos_tol:.3f}mm | 稳定次数: {stab_cnt} | 检查间隔: {chk_int:.1f}s")
        
        while time.time() - start_time < max_time:
            pos = self.get_position()
            
            if not pos or all(v is None for v in pos.values()):
                logger.debug("[MONITOR] 无法获取位置，继续等待...")
                time.sleep(chk_int)
                continue
            
            position_history.append(pos.copy())
            elapsed = time.time() - start_time
            
            if prev_pos is not None:
                pos_change = self._calculate_position_change(pos, prev_pos)
                
                if pos_change < pos_tol:
                    stable_counter += 1
                    status = "✓"
                else:
                    stable_counter = 0
                    status = "✗"
                
                logger.debug(
                    f"[{elapsed:6.2f}s] X={pos['x']:7.2f} Y={pos['y']:7.2f} "
                    f"Z={pos['z']:6.2f} E={pos['e']:6.2f} | "
                    f"Δ={pos_change:.4f}mm {status} [{stable_counter}/{stab_cnt}]"
                )
            else:
                logger.debug(
                    f"[{elapsed:6.2f}s] X={pos['x']:7.2f} Y={pos['y']:7.2f} "
                    f"Z={pos['z']:6.2f} E={pos['e']:6.2f} [基准]"
                )
            
            prev_pos = pos
            
            if stable_counter >= stab_cnt:
                elapsed = time.time() - start_time
                logger.info(f"[SUCCESS] ✓ 打印机已完全停止 | 耗时: {elapsed:.3f}s")
                return StopReason.POSITION_STABLE, elapsed, position_history
            
            time.sleep(chk_int)
        
        elapsed = time.time() - start_time
        logger.warning(f"[TIMEOUT] ✗ 超时（{max_time}s）未检测到完全停止")
        return StopReason.TIMEOUT, elapsed, position_history
    
    # ==================== 单次测试 ====================
    
    def run_single_pause_test(self,
                             gcode_file: str,
                             wait_before_pause: float = 5.0) -> Optional[Dict]:
        """
        运行单次暂停延迟测试
        改进：增强反馈和错误处理
        """
        try:
            # 1. 检查文件
            if not os.path.exists(gcode_file):
                logger.error(f"[FILE] ✗ 文件不存在: {gcode_file}")
                return None
            
            file_size_mb = os.path.getsize(gcode_file) / (1024 * 1024)
            gcode_lines = self._count_gcode_lines(gcode_file)
            
            logger.info(f"\n{'='*70}")
            logger.info(f"[TEST] {Path(gcode_file).name}")
            logger.info(f"[FILE] ✓ 大小: {file_size_mb:.2f}MB | 行数: {gcode_lines}")
            logger.info(f"{'='*70}")
            
            # 2. 启动打印
            logger.info("[START] 启动文件打印...")
            if not self._start_print(gcode_file):
                logger.error("[START] ✗ 启动打印失败")
                return None
            
            logger.info("[START] ✓ 文件已加载并开始打印")
            time.sleep(1)
            
            # 3. 等待床加热
            logger.info(f"[HEAT] 等待床加热完成...")
            if not self._wait_for_bed_heating_complete():
                logger.error("[HEAT] ✗ 床加热等待失败")
                self._stop_print()
                return None
            
            # 4. 等待打印机进入稳定打印状态
            logger.info(f"[WAIT] 等待 {wait_before_pause:.1f}s 让打印机进入稳定状态...")
            for remaining in range(int(wait_before_pause), 0, -1):
                logger.debug(f"[WAIT] 倒计时: {remaining}s")
                time.sleep(1)
            logger.info(f"[WAIT] ✓ 已等待 {wait_before_pause:.1f}s，准备发送暂停命令")
            
            # 5. 发送暂停命令并计时
            logger.info("[PAUSE] 发送暂停命令...")
            t_pause_start = time.perf_counter()
            if not self.send_pause_command():
                logger.error("[PAUSE] ✗ 暂停命令发送失败")
                self._stop_print()
                return None
            
            # 6. 等待打印机物理停下
            logger.info("[MONITOR] 等待打印机物理停下...")
            stop_reason, pause_latency, pos_history = self.wait_until_physically_stopped()
            
            # 7. 数据整理
            result = {
                'timestamp': datetime.now().isoformat(),
                'file': gcode_file,
                'file_name': Path(gcode_file).name,
                'file_size_mb': round(file_size_mb, 3),
                'gcode_lines': gcode_lines,
                'pause_latency_s': round(pause_latency, 4),
                'stop_reason': stop_reason.value,
                'position_samples': len(pos_history),
                'first_position': pos_history[0] if pos_history else None,
                'last_position': pos_history[-1] if pos_history else None,
                'position_history': pos_history,
            }
            
            logger.info(f"[RESULT] ✓ 暂停延迟: {pause_latency:.3f}s | "
                       f"位置样本: {len(pos_history)} | "
                       f"原因: {stop_reason.value}")
            
            # 8. 恢复打印或停止
            logger.info("[ACTION] 恢复打印3秒后停止...")
            self.send_resume_command()
            time.sleep(3)
            self._stop_print()
            logger.info("[ACTION] ✓ 测试完成")
            time.sleep(2)
            
            return result
            
        except Exception as e:
            logger.error(f"[TEST] ✗ 测试失败: {e}")
            self._stop_print()
            return None
    
    # ==================== 批量测试 ====================
    
    def run_batch_tests(self,
                       gcode_files: List[str],
                       wait_before_pause: float = 5.0,
                       repeat_count: int = 3) -> List[Dict]:
        """批量运行暂停延迟测试"""
        all_results = []
        total_tests = len(gcode_files) * repeat_count
        current_test = 0
        
        logger.info(f"\n{'='*70}")
        logger.info(f"[BATCH] 批量测试启动")
        logger.info(f"[BATCH] 文件数: {len(gcode_files)} | 重复次数: {repeat_count} | 总测试数: {total_tests}")
        logger.info(f"{'='*70}\n")
        
        for file_idx, gcode_file in enumerate(gcode_files, 1):
            logger.info(f"\n[FILE {file_idx}/{len(gcode_files)}] {Path(gcode_file).name}")
            
            for repeat_idx in range(1, repeat_count + 1):
                current_test += 1
                logger.info(f"[REPEAT {repeat_idx}/{repeat_count}]")
                
                result = self.run_single_pause_test(gcode_file, wait_before_pause)
                if result:
                    all_results.append(result)
                
                if current_test < total_tests:
                    logger.info("等待15秒后进行下一个测试...")
                    time.sleep(15)
        
        self.test_results = all_results
        logger.info(f"\n{'='*70}")
        logger.info(f"[COMPLETE] ✓ 批量测试完成 | 成功: {len(all_results)}/{total_tests}")
        logger.info(f"{'='*70}\n")
        
        return all_results
    
    # ==================== 数据分析与导出 ====================
    
    def save_results_csv(self, output_file: str = 'pause_test_results.csv'):
        """保存测试结果到 CSV"""
        if not self.test_results:
            logger.warning("[EXPORT] 没有测试结果要保存")
            return
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'timestamp', 'file_name', 'file_size_mb', 'gcode_lines',
                    'pause_latency_s', 'position_samples', 'stop_reason'
                ])
                writer.writeheader()
                
                for result in self.test_results:
                    writer.writerow({
                        'timestamp': result['timestamp'],
                        'file_name': result['file_name'],
                        'file_size_mb': result['file_size_mb'],
                        'gcode_lines': result['gcode_lines'],
                        'pause_latency_s': result['pause_latency_s'],
                        'position_samples': result['position_samples'],
                        'stop_reason': result['stop_reason'],
                    })
            
            logger.info(f"[EXPORT] ✓ CSV 已保存: {output_file}")
        except Exception as e:
            logger.error(f"[EXPORT] ✗ 保存 CSV 失败: {e}")
    
    def save_results_json(self, output_file: str = 'pause_test_results.json'):
        """保存测试结果到 JSON"""
        if not self.test_results:
            logger.warning("[EXPORT] 没有测试结果要保存")
            return
        
        try:
            json_results = []
            for result in self.test_results:
                json_results.append({
                    'timestamp': result['timestamp'],
                    'file_name': result['file_name'],
                    'file_size_mb': result['file_size_mb'],
                    'gcode_lines': result['gcode_lines'],
                    'pause_latency_s': result['pause_latency_s'],
                    'position_samples': result['position_samples'],
                    'stop_reason': result['stop_reason'],
                    'first_position': result['first_position'],
                    'last_position': result['last_position'],
                })
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[EXPORT] ✓ JSON 已保存: {output_file}")
        except Exception as e:
            logger.error(f"[EXPORT] ✗ 保存 JSON 失败: {e}")
    
    def print_summary(self):
        """打印测试总结"""
        if not self.test_results:
            logger.info("[SUMMARY] 没有测试结果")
            return
        
        logger.info(f"\n{'='*70}")
        logger.info("[SUMMARY] 测试总结")
        logger.info(f"{'='*70}")
        
        latencies = [r['pause_latency_s'] for r in self.test_results]
        sizes = [r['file_size_mb'] for r in self.test_results]
        lines = [r['gcode_lines'] for r in self.test_results]
        
        logger.info(f"\n【统计数据】")
        logger.info(f"  测试数: {len(self.test_results)}")
        logger.info(f"  文件大小: {min(sizes):.2f} ~ {max(sizes):.2f} MB")
        logger.info(f"  G-code行数: {min(lines)} ~ {max(lines)} 行")
        logger.info(f"  暂停延迟: {min(latencies):.3f} ~ {max(latencies):.3f} s")
        logger.info(f"  平均延迟: {statistics.mean(latencies):.3f} s")
        if len(latencies) > 1:
            logger.info(f"  标准差:   {statistics.stdev(latencies):.3f} s")
            logger.info(f"  中位数:   {statistics.median(latencies):.3f} s")
        
        logger.info(f"\n【详细结果】")
        logger.info(f"{'文件':<30} {'大小':<10} {'行数':<8} {'延迟(s)':<10} {'原因'}")
        logger.info("-" * 70)
        
        for result in sorted(self.test_results, key=lambda x: x['file_size_mb']):
            logger.info(
                f"{result['file_name']:<30} "
                f"{result['file_size_mb']:<10.2f} "
                f"{result['gcode_lines']:<8} "
                f"{result['pause_latency_s']:<10.3f} "
                f"{result['stop_reason']}"
            )
        
        logger.info(f"\n{'='*70}\n")
    
    # ==================== 辅助方法 ====================
    
    def _count_gcode_lines(self, file_path: str) -> int:
        """计算 G-code 文件的有效行数"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                count = sum(1 for line in f 
                           if line.strip() and not line.strip().startswith((';', '(')))
                return count
        except Exception as e:
            logger.error(f"[FILE] ✗ 读取文件失败: {file_path} - {e}")
            return 0
    
    def _start_print(self, gcode_file: str) -> bool:
        """启动文件打印"""
        try:
            logger.info(f"[FILE] 上传文件到OctoPrint...")
            resp = requests.post(
                f"{self.octoprint_url}/api/files/local",
                headers={'X-Api-Key': self.api_key},
                files={'file': open(gcode_file, 'rb')},
                timeout=30
            )
            resp.raise_for_status()
            logger.info(f"[FILE] ✓ 文件上传成功")
            
            time.sleep(2)
            
            logger.info(f"[FILE] 启动打印...")
            file_name = Path(gcode_file).name
            resp = requests.post(
                f"{self.octoprint_url}/api/files/local/{file_name}",
                headers=self.headers,
                json={"command": "select", "print": True},
                timeout=10
            )
            resp.raise_for_status()
            
            return True
            
        except Exception as e:
            logger.error(f"[FILE] ✗ 启动打印失败: {e}")
            return False
    
    def _stop_print(self) -> bool:
        """停止打印"""
        try:
            resp = requests.post(
                f"{self.octoprint_url}/api/job",
                headers=self.headers,
                json={"command": "cancel"},
                timeout=5
            )
            resp.raise_for_status()
            logger.info("[STOP] ✓ 打印已停止")
            return True
        except Exception as e:
            logger.error(f"[STOP] ✗ 停止打印失败: {e}")
            return False
        
