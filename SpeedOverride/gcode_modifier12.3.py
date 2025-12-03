#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GCode Modifier - 独立的代码修改模块
功能：
  • 实时修改 F 值（速度覆写）
  • 支持百分比缩放和固定值两种模式
  • 模态状态管理
  • 边界情况处理
  • 与 GCodeSender 解耦
"""

import re
import logging
from enum import Enum
from typing import Optional

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
    """G-code 修改器 - 速度覆写功能"""
    
    def __init__(self):
        """初始化修改器"""
        self.override_enabled = False
        self.override_mode = OverrideMode.DISABLED
        self.speed_factor = 1.0
        self.fixed_speed_value = 1500
        self.last_known_f_value = 3000.0
        self.min_speed_threshold = 60
        self.max_speed_threshold = 10000
        self.movement_commands = {'G0', 'G1', 'G2', 'G3'}
        self.stats = {
            'total_lines_processed': 0,
            'lines_modified': 0,
            'lines_with_f_detected': 0,
            'lines_without_f_injected': 0,
        }
        logger.info("✓ GCodeModifier 已初始化")
    
    def _extract_command_type(self, gcode_line: str) -> Optional[str]:
        """提取 G-code 命令类型"""
        line = gcode_line.strip()
        if not line or line.startswith(';'):
            return None
        match = re.match(r'([GM]\d+)', line.upper())
        return match.group(1) if match else None
    
    def _is_movement_command(self, command_type: Optional[str]) -> bool:
        """判断是否为移动指令"""
        return command_type in self.movement_commands if command_type else False
    
    def _extract_f_value(self, gcode_line: str) -> Optional[float]:
        """从 G-code 行中提取 F 值"""
        match = re.search(r'[Ff](\d+(?:\.\d+)?)', gcode_line)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    
    def _replace_f_value(self, gcode_line: str, new_f_value: float) -> str:
        """替换 G-code 行中的 F 值"""
        return re.sub(
            r'[Ff]\d+(?:\.\d+)?',
            f'F{int(new_f_value)}',
            gcode_line
        )
    
    def _append_f_value(self, gcode_line: str, f_value: float) -> str:
        """为 G-code 行追加 F 值"""
        return f"{gcode_line} F{int(f_value)}"
    
    def _clamp_speed(self, speed: float) -> float:
        """限制速度在有效范围内"""
        clamped = max(self.min_speed_threshold, min(speed, self.max_speed_threshold))
        if clamped != speed:
            logger.debug(f"速度被限制: {speed} → {clamped}")
        return clamped
    
    def _calculate_new_f_value(self, original_f: float) -> float:
        """根据覆写模式计算新的 F 值"""
        if self.override_mode == OverrideMode.PERCENTAGE:
            new_f = original_f * self.speed_factor
        elif self.override_mode == OverrideMode.FIXED_VALUE:
            new_f = float(self.fixed_speed_value)
        else:
            new_f = original_f
        return self._clamp_speed(new_f)
    
    def enable_override(self, mode: OverrideMode, value: float) -> bool:
        """启用速度覆写"""
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
        """禁用速度覆写"""
        self.override_enabled = False
        self.override_mode = OverrideMode.DISABLED
        logger.info("✓ 禁用速度覆写")
        return True
    
    def process_line(self, gcode_line: str) -> str:
        """处理单行 G-code，修改 F 值"""
        self.stats['total_lines_processed'] += 1
        
        if not self.override_enabled:
            return gcode_line
        
        command_type = self._extract_command_type(gcode_line)
        if not self._is_movement_command(command_type):
            return gcode_line
        
        original_f = self._extract_f_value(gcode_line)
        
        if original_f is not None:
            self.stats['lines_with_f_detected'] += 1
            self.last_known_f_value = original_f
            new_f = self._calculate_new_f_value(original_f)
            modified_line = self._replace_f_value(gcode_line, new_f)
            self.stats['lines_modified'] += 1
            logger.debug(f"修改 F 值: {original_f} → {new_f}")
            return modified_line
        else:
            new_f = self._calculate_new_f_value(self.last_known_f_value)
            modified_line = self._append_f_value(gcode_line, new_f)
            self.stats['lines_without_f_injected'] += 1
            self.stats['lines_modified'] += 1
            logger.debug(f"注入 F 值: {new_f}")
            return modified_line
    
    def reset_state(self):
        """重置修改器状态"""
        self.last_known_f_value = 3000.0
        self.stats = {
            'total_lines_processed': 0,
            'lines_modified': 0,
            'lines_with_f_detected': 0,
            'lines_without_f_injected': 0,
        }
        logger.info("✓ 修改器状态已重置")
    
    def get_status(self) -> dict:
        """获取修改器状态"""
        return {
            'override_enabled': self.override_enabled,
            'override_mode': self.override_mode.value if self.override_mode else None,
            'speed_factor': self.speed_factor if self.override_mode == OverrideMode.PERCENTAGE else None,
            'fixed_speed_value': self.fixed_speed_value if self.override_mode == OverrideMode.FIXED_VALUE else None,
            'statistics': self.stats,
        }


if __name__ == "__main__":
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
        "G1 X20 Y20",
        "M104 S200 F999",
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
        "G0 Z10",
    ]
    for line in test_lines:
        result = modifier.process_line(line)
        print(f"  {line:35} → {result}")
    print()
    
    print("=" * 70)
    print("所有测试完成！")
    print("=" * 70)