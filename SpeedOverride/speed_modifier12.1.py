#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCode Modifier - 实时速度覆写功能
Gcode Real-time Feed Rate Override Module

功能：
  • 在发送前动态修改 F 参数
  • 支持百分比缩放和固定值两种模式
  • 模态状态管理（维护上一次已知的 F 值）
  • 无损修改（仅在内存中修改，不改动原始文件）
  • 边界情况处理（极低速度保护、非移动指令判别）
"""

import re
import logging
from enum import Enum
from typing import Optional, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OverrideMode(Enum):
    """速度覆写模式"""
    DISABLED = "disabled"          # 禁用
    PERCENTAGE = "percentage"      # 百分比缩放
    FIXED_VALUE = "fixed_value"    # 固定值


class GCodeModifier:
    """GCode 实时修改器 - 速度覆写"""
    
    def __init__(self):
        """初始化修改器"""
        
        # 覆写状态
        self.override_enabled = False
        self.override_mode = OverrideMode.DISABLED
        
        # 覆写参数
        self.speed_factor = 1.0           # 百分比缩放因子（0.1 - 2.0）
        self.fixed_speed_value = 1500     # 固定速度值
        
        # 模态状态 - 维护打印机的模态状态
        self.last_known_f_value = 3000.0  # 最后已知的 F 值（默认）
        self.min_speed_threshold = 60     # 最小速度阈值（防止极低速）
        self.max_speed_threshold = 10000  # 最大速度阈值
        
        # 移动指令集合
        self.movement_commands = {'G0', 'G1', 'G2', 'G3'}
        
        # 统计信息
        self.stats = {
            'total_lines_processed': 0,
            'lines_modified': 0,
            'lines_with_f_detected': 0,
            'lines_without_f_injected': 0,
        }
        
        logger.info("GCodeModifier 初始化完成")
    
    def _extract_command_type(self, gcode_line: str) -> Optional[str]:
        """
        提取 G-code 命令类型（G0, G1, M104等）
        
        Args:
            gcode_line: 原始 G-code 行
            
        Returns:
            命令类型字符串（大写），如 'G1', 'M104'，如果无效则返回 None
        """
        # 移除注释和前后空白
        line = gcode_line.strip()
        if not line or line.startswith(';'):
            return None
        
        # 提取命令（G/M 后跟数字）
        match = re.match(r'([GM]\d+)', line.upper())
        if match:
            return match.group(1)
        return None
    
    def _is_movement_command(self, command_type: Optional[str]) -> bool:
        """
        判断是否为移动指令
        
        Args:
            command_type: 命令类型
            
        Returns:
            True 如果是移动指令
        """
        if not command_type:
            return False
        return command_type in self.movement_commands
    
    def _extract_f_value(self, gcode_line: str) -> Optional[float]:
        """
        从 G-code 行中提取 F 值
        
        Args:
            gcode_line: G-code 行
            
        Returns:
            提取的 F 值（浮点数），如果不存在则返回 None
        """
        # 正则匹配 F 参数（大小写不敏感）
        # 匹配 F 后跟数字（可选小数点）
        match = re.search(r'[Ff](\d+(?:\.\d+)?)', gcode_line)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    
    def _replace_f_value(self, gcode_line: str, new_f_value: float) -> str:
        """
        替换 G-code 行中的 F 值
        
        Args:
            gcode_line: 原始 G-code 行
            new_f_value: 新的 F 值
            
        Returns:
            修改后的 G-code 行
        """
        # 使用正则替换 F 值
        modified_line = re.sub(
            r'[Ff]\d+(?:\.\d+)?',
            f'F{int(new_f_value)}',
            gcode_line
        )
        return modified_line
    
    def _append_f_value(self, gcode_line: str, f_value: float) -> str:
        """
        为 G-code 行追加 F 值（当行中无 F 时）
        
        Args:
            gcode_line: 原始 G-code 行
            f_value: 要追加的 F 值
            
        Returns:
            追加 F 值后的 G-code 行
        """
        # 在行末添加 F 值
        return f"{gcode_line} F{int(f_value)}"
    
    def _clamp_speed(self, speed: float) -> float:
        """
        限制速度在有效范围内
        
        Args:
            speed: 原始速度值
            
        Returns:
            限制后的速度值
        """
        clamped = max(self.min_speed_threshold, min(speed, self.max_speed_threshold))
        if clamped != speed:
            logger.debug(f"速度被限制: {speed} → {clamped}")
        return clamped
    
    def _calculate_new_f_value(self, original_f: float) -> float:
        """
        根据覆写模式计算新的 F 值
        
        Args:
            original_f: 原始 F 值
            
        Returns:
            计算后的新 F 值
        """
        if self.override_mode == OverrideMode.PERCENTAGE:
            new_f = original_f * self.speed_factor
        elif self.override_mode == OverrideMode.FIXED_VALUE:
            new_f = float(self.fixed_speed_value)
        else:
            new_f = original_f
        
        return self._clamp_speed(new_f)
    
    def enable_override(self, mode: OverrideMode, value: float) -> bool:
        """
        启用速度覆写
        
        Args:
            mode: 覆写模式 (PERCENTAGE 或 FIXED_VALUE)
            value: 
                - 如果 mode 是 PERCENTAGE: 缩放因子 (0.1 - 2.0)
                - 如果 mode 是 FIXED_VALUE: 固定速度值 (60 - 10000)
                
        Returns:
            True 如果成功，False 如果参数无效
        """
        # 参数验证
        if mode == OverrideMode.PERCENTAGE:
            if not (0.1 <= value <= 2.0):
                logger.error(f"百分比缩放因子必须在 0.1 - 2.0 之间，收到: {value}")
                return False
            self.speed_factor = value
            logger.info(f"✓ 启用百分比缩放模式: {value * 100}%")
            
        elif mode == OverrideMode.FIXED_VALUE:
            if not (60 <= value <= 10000):
                logger.error(f"固定速度值必须在 60 - 10000 之间，收到: {value}")
                return False
            self.fixed_speed_value = int(value)
            logger.info(f"✓ 启用固定值模式: F{self.fixed_speed_value}")
            
        else:
            logger.error(f"未知的覆写模式: {mode}")
            return False
        
        self.override_enabled = True
        self.override_mode = mode
        return True
    
    def disable_override(self) -> bool:
        """
        禁用速度覆写
        
        Returns:
            True 如果成功
        """
        self.override_enabled = False
        self.override_mode = OverrideMode.DISABLED
        logger.info("✓ 禁用速度覆写")
        return True
    
    def process_line(self, gcode_line: str) -> str:
        """
        处理单行 G-code，根据覆写模式修改 F 值
        
        核心方法 - 在发送前调用此函数
        
        Args:
            gcode_line: 原始 G-code 行
            
        Returns:
            处理后的 G-code 行（如果启用覆写则可能被修改）
        """
        # 更新统计
        self.stats['total_lines_processed'] += 1
        
        # 如果覆写已禁用，直接返回原行
        if not self.override_enabled:
            return gcode_line
        
        # 提取命令类型
        command_type = self._extract_command_type(gcode_line)
        
        # 只处理移动指令
        if not self._is_movement_command(command_type):
            return gcode_line
        
        # 尝试提取原始 F 值
        original_f = self._extract_f_value(gcode_line)
        
        if original_f is not None:
            # 场景1：行中已有 F 值 → 替换
            self.stats['lines_with_f_detected'] += 1
            self.last_known_f_value = original_f  # 保存为上次已知值
            
            new_f = self._calculate_new_f_value(original_f)
            modified_line = self._replace_f_value(gcode_line, new_f)
            
            self.stats['lines_modified'] += 1
            logger.debug(f"修改 F 值: {original_f} → {new_f} | {gcode_line} → {modified_line}")
            
            return modified_line
        
        else:
            # 场景2：行中无 F 值 → 注入上次已知的 F 值（应用覆写）
            # 这保证了打印机模态的正确性
            new_f = self._calculate_new_f_value(self.last_known_f_value)
            modified_line = self._append_f_value(gcode_line, new_f)
            
            self.stats['lines_without_f_injected'] += 1
            self.stats['lines_modified'] += 1
            logger.debug(f"注入 F 值: {new_f} | {gcode_line} → {modified_line}")
            
            return modified_line
    
    def process_batch(self, gcode_lines: list) -> list:
        """
        批量处理 G-code 行
        
        Args:
            gcode_lines: G-code 行列表
            
        Returns:
            处理后的 G-code 行列表
        """
        processed_lines = []
        for line in gcode_lines:
            processed_lines.append(self.process_line(line))
        
        logger.info(f"批量处理完成: {len(processed_lines)} 行")
        self._log_statistics()
        return processed_lines
    
    def reset_state(self):
        """
        重置修改器状态
        通常在开始新的打印任务时调用
        """
        self.last_known_f_value = 3000.0
        self.stats = {
            'total_lines_processed': 0,
            'lines_modified': 0,
            'lines_with_f_detected': 0,
            'lines_without_f_injected': 0,
        }
        logger.info("修改器状态已重置")
    
    def set_min_speed_threshold(self, threshold: float):
        """
        设置最小速度阈值
        
        Args:
            threshold: 最小速度值（F值）
        """
        if 1 <= threshold <= 1000:
            self.min_speed_threshold = threshold
            logger.info(f"最小速度阈值设置为: {threshold}")
        else:
            logger.error(f"无效的最小速度阈值: {threshold}")
    
    def set_max_speed_threshold(self, threshold: float):
        """
        设置最大速度阈值
        
        Args:
            threshold: 最大速度值（F值）
        """
        if 100 <= threshold <= 20000:
            self.max_speed_threshold = threshold
            logger.info(f"最大速度阈值设置为: {threshold}")
        else:
            logger.error(f"无效的最大速度阈值: {threshold}")
    
    def get_status(self) -> dict:
        """
        获取修改器状态和统计信息
        
        Returns:
            状态字典
        """
        return {
            'override_enabled': self.override_enabled,
            'override_mode': self.override_mode.value if self.override_mode else None,
            'speed_factor': self.speed_factor if self.override_mode == OverrideMode.PERCENTAGE else None,
            'fixed_speed_value': self.fixed_speed_value if self.override_mode == OverrideMode.FIXED_VALUE else None,
            'last_known_f_value': self.last_known_f_value,
            'min_speed_threshold': self.min_speed_threshold,
            'max_speed_threshold': self.max_speed_threshold,
            'statistics': self.stats,
        }
    
    def _log_statistics(self):
        """输出统计信息"""
        logger.info("=" * 60)
        logger.info("GCode 修改统计:")
        logger.info(f"  总处理行数: {self.stats['total_lines_processed']}")
        logger.info(f"  已修改行数: {self.stats['lines_modified']}")
        logger.info(f"  检测到 F 值的行: {self.stats['lines_with_f_detected']}")
        logger.info(f"  注入 F 值的行: {self.stats['lines_without_f_injected']}")
        logger.info("=" * 60)


# ============================================================================
# 集成示例：展示如何与 gcode_sender.py 集成
# ============================================================================

class IntegratedGCodeSender:
    """
    集成示例：GCodeSender + GCodeModifier
    
    使用方式：
    1. 在 gcode_sender.py 的 GCodeSender 类中实例化 GCodeModifier
    2. 在 send_and_wait() 前调用 modifier.process_line()
    """
    
    @staticmethod
    def example_integration():
        """
        集成示例代码
        在 gcode_sender.py 中修改 send_and_wait 方法：
        
        ```python
        # 在 GCodeSender.__init__ 中添加：
        self.modifier = GCodeModifier()
        
        # 在 send_and_wait 方法中修改：
        def send_and_wait(self, command: str, wait_time: float = 0.1) -> bool:
            command = command.strip()
            if not command or command.startswith(';'):
                return True
            
            # ✓ 新增：使用 modifier 处理 F 值
            command = self.modifier.process_line(command)
            
            # 其余代码保持不变...
            try:
                data = {"commands": [command]}
                response = self.session.post(...)
                # ...
        ```
        
        # 在暂停时禁用覆写：
        def pause(self):
            # ... 暂停逻辑 ...
            self.modifier.disable_override()
            # ...
        
        # 在恢复时启用覆写：
        def resume(self):
            # ... 恢复逻辑 ...
            if self.modifier.override_enabled:
                self.modifier.enable_override(...)
            # ...
        """
        pass


if __name__ == "__main__":
    # 单元测试示例
    print("=" * 70)
    print("GCode Modifier 单元测试")
    print("=" * 70)
    print()
    
    modifier = GCodeModifier()
    
    # 测试1：百分比缩放
    print("【测试1】百分比缩放 (50% 速度)")
    modifier.enable_override(OverrideMode.PERCENTAGE, 0.5)
    test_lines = [
        "G1 X10 Y10 F3000",
        "G1 X20 Y20",  # 没有 F，应注入
        "M104 S200 F999",  # 非移动指令，不应修改
    ]
    for line in test_lines:
        result = modifier.process_line(line)
        print(f"  {line:30} → {result}")
    print()
    
    # 测试2：固定值模式
    print("【测试2】固定值模式 (F=1200)")
    modifier.reset_state()
    modifier.disable_override()
    modifier.enable_override(OverrideMode.FIXED_VALUE, 1200)
    test_lines = [
        "G1 X100 Y100 F5000",
        "G2 X50 Y50 I25 J25 F4000",
        "G0 Z10",  # 没有 F
    ]
    for line in test_lines:
        result = modifier.process_line(line)
        print(f"  {line:35} → {result}")
    print()
    
    # 测试3：极限值保护
    print("【测试3】极限值保护 (最小60, 最大10000)")
    modifier.reset_state()
    modifier.disable_override()
    modifier.enable_override(OverrideMode.PERCENTAGE, 0.1)
    test_lines = [
        "G1 X10 Y10 F100",    # 100 * 0.1 = 10 → 限制为60
        "G1 X20 Y20 F50000",  # 50000 * 0.1 = 5000 → 正常
    ]
    for line in test_lines:
        result = modifier.process_line(line)
        print(f"  {line:30} → {result}")
    print()
    
    # 测试4：状态输出
    print("【测试4】修改器状态")
    status = modifier.get_status()
    print(f"  启用状态: {status['override_enabled']}")
    print(f"  覆写模式: {status['override_mode']}")
    print(f"  统计信息: {status['statistics']}")
    print()
    
    print("=" * 70)
    print("所有测试完成！")
    print("=" * 70)