# Stage 6: 机器人速度 + 打印机集成控制系统 - 部署指南

## 1. 文件结构

```
project_root/
├── gcode_sender.py              # Stage 4 原始打印机控制脚本
├── robot_speed_controller.py    # Stage 6 新增：速度监控和控制模块
├── stage6_integrated_main.py    # Stage 6 新增：集成主脚本
├── logs/                        # 日志输出目录（自动创建）
└── test_files/                  # 测试用的G-code文件
```

## 2. 环境要求

### 2.1 Python 依赖
```bash
pip install requests rospy geometry-msgs nav-msgs
```

### 2.2 ROS 环境
必须在有效的 ROS 环境中运行：
```bash
source /opt/ros/humble/setup.bash  # 或您的 ROS 版本
# 或
source /opt/ros/noetic/setup.bash
```

## 3. 快速开始

### 3.1 基本启动
```bash
# 在 ROS 工作空间中
cd /path/to/your/project
python3 stage6_integrated_main.py
```

### 3.2 交互命令

#### 启动打印
```
>>> print /path/to/your/file.gcode
✓ 打印和速度控制已启动
```

#### 查看状态
```
>>> status
系统状态:
  timestamp: 2025-01-15T10:30:45.123456
  printer_state: running
  printer_progress: 45.2%
  robot_speed: 0.234 m/s
  printer_paused: False
  speed_threshold: 0.4
  current_file: /path/to/file.gcode
  log_file: ./logs/robot_printer_control_20250115_103045.csv
```

#### 调整参数
```
>>> threshold 0.5          # 将速度阈值改为 0.5 m/s
>>> debounce 1.0          # 将防抖时间改为 1.0 s
```

## 4. 工作流程

### 4.1 系统初始化流程
```
1. 加载 gcode_sender.py → GCodeSender 实例
2. 初始化 ROS 节点
3. 创建 PrinterSpeedController 实例
4. 订阅机器人速度话题（/odom 或 /cmd_vel）
```

### 4.2 打印 + 速度控制流程
```
启动 print 命令
    ↓
加载 G-code 文件到内存
    ↓
启动打印线程（逐条发送 G-code 指令）
    ↓
启动速度监控线程（200ms 周期检查一次机器人速度）
    ↓
┌─────────────────────────────────────────┐
│ 速度监控循环                              │
├─────────────────────────────────────────┤
│ current_speed = 获取机器人速度              │
│                                         │
│ if current_speed > 0.4 m/s:             │
│    └─ 暂停打印（执行 pause()）            │
│    └─ 记录事件到 CSV 日志                  │
│    └─ 等待防抖时间（0.5s）                │
│                                         │
│ elif current_speed ≤ 0.4 m/s:           │
│    └─ 恢复打印（执行 resume()）            │
│    └─ 记录事件到 CSV 日志                  │
│    └─ 等待防抖时间（0.5s）                │
│                                         │
│ sleep(0.2s) → 下一个周期                 │
└─────────────────────────────────────────┘
```

## 5. 数据记录

### 5.1 CSV 日志文件格式
```
timestamp,robot_speed_ms,action,printer_state,response_time_ms,notes
2025-01-15T10:30:45.234567,0.350,RUNNING,running,0.00,
2025-01-15T10:30:47.456789,0.520,PAUSE,pausing,150.00,高速运动触发: 0.520 m/s
2025-01-15T10:30:48.123456,0.520,PAUSED,paused,0.00,
2025-01-15T10:31:05.789012,0.250,RESUME,resuming,200.00,低速运动触发: 0.250 m/s
2025-01-15T10:31:06.345678,0.250,RUNNING,running,0.00,
```

### 5.2 日志分析
```python
import pandas as pd

# 读取日志
df = pd.read_csv('./logs/robot_printer_control_*.csv')

# 分析暂停响应延迟
pause_events = df[df['action'] == 'PAUSE']
avg_pause_response = pause_events['response_time_ms'].mean()
print(f"平均暂停响应延迟: {avg_pause_response:.1f}ms")

# 分析恢复响应延迟
resume_events = df[df['action'] == 'RESUME']
avg_resume_response = resume_events['response_time_ms'].mean()
print(f"平均恢复响应延迟: {avg_resume_response:.1f}ms")

# 统计暂停/恢复次数
print(f"暂停次数: {len(pause_events)}")
print(f"恢复次数: {len(resume_events)}")
```

## 6. 配置参数说明

### 6.1 核心参数
| 参数 | 默认值 | 说明 |
|------|-------|------|
| `speed_threshold` | 0.4 m/s | 速度阈值 - 超过此值触发暂停 |
| `debounce_time` | 0.5 s | 防抖时间 - 避免频繁切换状态 |
| `speed_source` | 'odom' | 速度源 - 'odom'(里程计) 或 'cmd_vel'(速度命令) |
| `monitor_period` | 0.2 s | 监控周期 - 每 200ms 检查一次速度 |

### 6.2 打印机参数（继承自 Stage 4）
| 参数 | 默认值 | 说明 |
|------|-------|------|
| `pause_lift_z` | 5.0 mm | 暂停时 Z 轴抬升高度 |
| `pause_retract` | 5.0 mm | 暂停时耗材回抽长度 |
| `maintain_temp_on_pause` | True | 暂停时是否保持加热温度 |

## 7. 故障排除

### 问题 1: 无法连接到 OctoPrint
```
错误: 获取打印机状态失败: Connection refused
```
**解决方案:**
- 检查 OctoPrint 服务是否运行: `curl http://octopi.local/api/version`
- 验证 API_KEY 是否正确
- 检查网络连接

### 问题 2: 无法订阅速度话题
```
警告: 未收到速度信息，停止控制
```
**解决方案:**
- 检查机器人是否在发布速度信息: `rostopic list`
- 验证话题名称是否正确 (`/odom` 或 `/cmd_vel`)
- 确保机器人驱动节点正在运行

### 问题 3: 频繁暂停/恢复
**原因:** 速度信号波动或阈值设置不当
**解决方案:**
- 增加防抖时间: `debounce 1.0`
- 调整速度阈值: `threshold 0.5`
- 检查机器人速度发布频率

### 问题 4: 暂停/恢复响应缓慢
**原因:** OctoPrint 响应延迟或网络问题
**解决方案:**
- 检查 OctoPrint 系统负载
- 减少 G-code 文件的指令数量
- 使用有线网络而非 WiFi

## 8. 性能优化建议

### 8.1 监控周期优化
- 当前设置: 200ms (5Hz)
- 对于快速移动的机器人，可以减少到 100ms (10Hz)
- 对于缓慢移动的机器人，可以增加到 500ms (2Hz)

### 8.2 防抖时间优化
- 当前设置: 0.5s
- 如果触发太频繁，增加到 1.0s 或更长
- 平衡响应速度和稳定性

### 8.3 速度阈值微调
- 根据您的机器人和打印机实际情况调整
- 建议先从 0.4 m/s 开始，逐步微调

## 9. 测试用例

### 用例 1: 静止打印（基线测试）
```bash
>>> print /path/to/test.gcode
# 机器人保持静止
# 期望: 打印持续进行，无暂停事件
```

### 用例 2: 低速运动（<0.4 m/s）
```bash
# 让机器人以 0.2 m/s 速度运动
# 期望: 打印继续，无暂停事件
```

### 用例 3: 高速运动（>0.4 m/s）
```bash
# 让机器人以 0.6 m/s 速度运动
# 期望: 打印立即暂停，记录暂停事件
```

### 用例 4: 速度切换
```bash
# 让机器人交替切换速度 0.2 m/s ↔ 0.6 m/s
# 期望: 打印自动切换暂停/恢复状态
# 验证: 检查 CSV 日志中的事件顺序和时间戳
```

## 10. 后续改进（Stage 7）

### 10.1 整合为 ROS Node
- 将 Stage 6 包装为正式的 ROS Node
- 添加 ROS Parameter Server 支持
- 实现 ROS Service 和 Topic 接口

### 10.2 与导航栈集成
- 订阅全局规划器信息预判高速区段
- 自动调整速度阈值
- 实现智能暂停策略

### 10.3 数据可视化
- 实时展示机器人速度和打印状态
- 生成性能统计图表
- 集成 RViz 和 Gazebo 模拟

## 11. 常用命令速查表

| 任务 | 命令 |
|------|------|
| 启动打印 | `print /path/to/file.gcode` |
| 查看状态 | `status` |
| 手动暂停 | `pause` |
| 手动恢复 | `resume` |
| 停止打印 | `stop` |
| 调整阈值为 0.5 m/s | `threshold 0.5` |
| 调整防抖为 1.0 s | `debounce 1.0` |
| 查看日志位置 | `logs` |
| 显示帮助 | `help` |
| 退出程序 | `quit` |

---

**版本:** Stage 6 v1.0  
**最后更新:** 2025-01-15  
**维护者:** 项目开发团队