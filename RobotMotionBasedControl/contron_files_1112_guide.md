# 三个文件的修改总结

## 📋 修改清单

### 1️⃣ `gcode_sender1112.py` 
**新增方法（第 335-354 行）：**
```python
def check_temperatures_safe(self) -> Dict[str, Dict[str, float]]:
    """
    安全地获取温度信息。
    返回格式：
    {
        'bed': {'actual': float, 'target': float},
        'tool0': {'actual': float, 'target': float}
    }
    """
    # 完整实现已添加
```

**功能：** 为 script.py 中的温度检查提供支持，避免运行时错误

**其他内容：** 完全保留（包括 OctoPrint 地址、API 密钥、所有现有方法）

---

### 2️⃣ `robot_speed_controller1112.py`
**状态：** ✅ 完全保留，无需修改

**原因：** 该模块已经功能完整，包含：
- ✓ 速度监控（支持 `/odom` 和 `/cmd_vel`）
- ✓ 自动暂停/恢复逻辑
- ✓ 防抖机制
- ✓ 日志记录
- ✓ 状态管理

---

### 3️⃣ `script1112.py`
**主要修改：**

| 修改项 | 原代码 | 修复后 |
|-------|--------|--------|
| 导入模块 | `from gcode_sender_251111 import ...` | `from gcode_sender1112 import ...` |
| 导入模块 | `from robot_speed_controller_251111 import ...` | `from robot_speed_controller1112 import ...` |
| 温度检查 | `sender.check_temperatures_safe()` 调用但未定义 | 现在在 gcode_sender1112.py 中定义了 |
| 状态判断 | `self.sender.state != PrinterState.IDLE` | 改为 `!= PrinterState.IDLE and != PrinterState.READY` |

**其他内容：** 完全保留（OctoPrint 地址、API 密钥、话题名称、参数配置）

---

## 🚀 快速开始

### 前置条件
```bash
# 1. 确保 ROS 已安装
source /opt/ros/melodic/setup.bash  # 或其他版本

# 2. 安装 Python 依赖
pip3 install requests rospy
```

### 文件放置
将三个文件放在同一目录：
```
your_project_directory/
├── gcode_sender1112.py
├── robot_speed_controller1112.py
└── script1112.py
```

### 运行方式 1：命令行参数（推荐）
```bash
python3 script1112.py \
    --url http://octopi.local \
    --api-key YOUR_API_KEY \
    --threshold 0.04 \
    --speed-source odom \
    --odom-topic /odom
```

**参数说明：**
- `--url`: OctoPrint 地址（默认：http://octopi.local）
- `--api-key`: OctoPrint API Key（必需）
- `--threshold`: 速度阈值，单位 m/s（默认：0.04）
- `--speed-source`: 速度数据源（odom 或 cmd_vel，默认：odom）
- `--odom-topic`: 里程计话题（默认：/odom）
- `--cmd-vel-topic`: 速度命令话题（默认：/cmd_vel）

### 运行方式 2：直接运行
```bash
python3 script1112.py
```
然后在交互式界面中使用命令

---

## 💻 交互式命令

启动后你会看到一个命令行界面：
```
>>>
```

### 主要命令

| 命令 | 语法 | 说明 |
|------|------|------|
| 打印 | `print /path/to/file.gcode` | 上传并开始打印，自动启用速度控制 |
| 状态 | `status` | 显示系统状态（速度、打印进度等） |
| 暂停 | `pause` | 手动暂停打印 |
| 恢复 | `resume` | 手动恢复打印 |
| 停止 | `stop` | 停止打印任务 |
| 阈值 | `threshold 0.05` | 修改速度阈值（单位 m/s） |
| 防抖 | `debounce 0.8` | 修改防抖时间（单位 s） |
| 日志 | `logs` | 显示当前日志文件位置 |
| 帮助 | `help` | 显示帮助信息 |
| 退出 | `quit` | 退出程序 |

---

## 📊 自动控制流程

```
启动 script1112.py
    ↓
初始化 GCodeSender (连接 OctoPrint)
    ↓
初始化 RobotSpeedMonitor (订阅 ROS 话题)
    ↓
用户执行 "print /path/to/file.gcode"
    ↓
上传文件到 OctoPrint
    ↓
等待床温加热完成（可选）
    ↓
启动 PrinterSpeedController 控制线程
    ↓
【持续监控】
  - 读取机器人当前速度
  - 与阈值 (0.04 m/s) 比较
  
  ├─ 速度 > 0.04 m/s → 自动暂停打印 ⏸
  │   └─ 记录日志
  │
  └─ 速度 ≤ 0.04 m/s 持续 3 个周期 → 自动恢复打印 ▶
      └─ 记录日志
    ↓
打印完成或用户停止
    ↓
清理资源，退出
```

---

## 🔧 关键参数配置

### 速度阈值 (threshold)
| 值 | 推荐场景 | 说明 |
|----|---------|------|
| 0.02 m/s | 精细打印、高精度 | 更容易触发暂停，更保守 |
| 0.04 m/s | 默认（推荐） | 平衡敏感性和误触发 |
| 0.1 m/s | 快速打印、室内环境 | 只在明显运动时暂停 |
| 0.2 m/s | 大型机器人 | 仅在高速运动时暂停 |

### 防抖时间 (debounce_time)
| 值 | 效果 |
|----|------|
| 0.2 s | 快速响应，可能有轻微抖动 |
| 0.5 s | 默认，平衡响应和稳定性 |
| 1.0 s | 较稳定，响应较慢 |

---

## 📝 日志文件

自动生成的日志文件位置：
```
./logs/robot_printer_control_YYYYMMDD_HHMMSS.csv
```

**CSV 格式：**
```
timestamp,robot_speed_ms,action,printer_state,response_time_ms,notes
2025-01-12T10:30:45.123456,0.0527,PAUSE,PAUSED,245,高速运动: 0.0527m/s
2025-01-12T10:30:50.456789,0.0125,RESUME,PRINTING,189,低速运动: 0.0125m/s
```

---

## ✅ 完整工作流示例

```bash
# 1. 启动系统
python3 script1112.py \
    --url http://octopi.local \
    --api-key abcdef123456 \
    --threshold 0.04

# 2. 在交互界面中输入
>>> print /home/user/models/benchy.gcode

# 3. 系统自动：
#    - 上传文件到 OctoPrint
#    - 等待床加热
#    - 启动打印
#    - 启动速度控制

# 4. 查看状态
>>> status

# 5. 如需调整参数
>>> threshold 0.05
>>> debounce 0.8

# 6. 查看日志
>>> logs

# 7. 退出
>>> quit
```

---

## 🐛 故障排查

### 问题 1: "无法导入 GCodeSender"
**原因：** 文件名不匹配或文件不在同一目录
**解决：** 确保三个文件都在同一目录，文件名完全正确

### 问题 2: "速度信息未准备好"
**原因：** ROS 话题未正确发布或连接
**解决：**
```bash
# 检查话题是否存在
rostopic list | grep odom
rostopic echo /odom
```

### 问题 3: "暂停/恢复失败"
**原因：** OctoPrint 连接或 API Key 错误
**解决：**
1. 检查 OctoPrint 是否在线
2. 验证 API Key 是否正确
3. 查看日志中的错误信息

### 问题 4: 频繁暂停/恢复
**原因：** 速度阈值设置不当，或防抖时间过短
**解决：** 增加阈值或防抖时间
```
>>> threshold 0.05
>>> debounce 0.8
```

---

## 📌 重要提示

⚠️ **保留的配置（不做修改）：**
- OctoPrint 网址 (`http://octopi.local`)
- OctoPrint API Key
- ROS 话题名称 (`/odom`, `/cmd_vel`)
- 所有 G-code 固件命令（M601, M602 等）

✅ **已修复的问题：**
- ✓ 缺失的 `check_temperatures_safe()` 方法
- ✓ 导入文件名不匹配
- ✓ 运行时错误

🎯 **自动控制逻辑已完整实现：**
- ✓ 速度监控
- ✓ 自动暂停/恢复
- ✓ 防抖机制
- ✓ 日志记录
- ✓ 状态管理

---

## 🎉 现在你可以：

1. ✅ 自动监控机器人速度
2. ✅ 在高速运动时自动暂停打印
3. ✅ 在低速运动时自动恢复打印
4. ✅ 实时调整速度阈值
5. ✅ 查看完整的控制日志
6. ✅ 手动控制打印机

**祝你使用愉快！** 🚀