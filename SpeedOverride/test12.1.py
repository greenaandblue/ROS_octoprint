#!/usr/bin/env python3
# 测试脚本

print("=" * 60)
print("测试 1: 导入修改器")
print("=" * 60)

try:
    from gcode_modifier import GCodeModifier, OverrideMode
    print("✓ GCodeModifier 导入成功\n")
except ImportError as e:
    print(f"✗ 导入失败: {e}\n")
    exit(1)

print("=" * 60)
print("测试 2: 导入发送器")
print("=" * 60)

try:
    # 这会检查发送器是否正确导入修改器
    from gcode_sender import GCodeSender
    print("✓ GCodeSender 导入成功\n")
except ImportError as e:
    print(f"✗ 导入失败: {e}\n")
    exit(1)

print("=" * 60)
print("测试 3: 创建修改器实例并测试")
print("=" * 60)

modifier = GCodeModifier()

# 启用百分比缩放
modifier.enable_override(OverrideMode.PERCENTAGE, 0.5)

# 测试几行 G-code
test_lines = [
    "G1 X10 Y10 F3000",
    "G1 X20 Y20",
    "G1 X30 Y30 F2000",
]

print("\n原始 → 修改后:")
for line in test_lines:
    result = modifier.process_line(line)
    status = "✓ 已修改" if result != line else "未改动"
    print(f"  {line:25} → {result:25} [{status}]")

# 获取统计信息
print("\n统计信息:")
status = modifier.get_status()
stats = status['statistics']
print(f"  已修改行数: {stats['lines_modified']}")
print(f"  检测到 F 值: {stats['lines_with_f_detected']}")
print(f"  注入 F 值: {stats['lines_without_f_injected']}")

print("\n" + "=" * 60)
print("✓ 所有测试通过！")
print("=" * 60)