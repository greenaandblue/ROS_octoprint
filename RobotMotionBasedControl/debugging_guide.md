# Stage 6: 机器人速度打印控制系统 - 诊断与设置指南

## 常见问题与解决方案

### 问题 1: 打印机没有根据机器人速度暂停/恢复

**原因分析：**
- ✗ 原版本：床加热等待**阻塞**了主发送线程，使得打印无法进行
- ✗ ROS 话题未正确订阅
- ✗ 速度信息未被正确接收

**解决方案：**

```bash
# 1. 检查 ROS 话题是否发布
rostopic list | grep -E "(odom|cmd_vel)"

# 应该看到类似：
# /odom
# /cmd_vel
# /tf

# 2. 检查话题数据
rostopic echo /odom
# 应该看到连续的数据流

# 3. 检查发送的速度值
rostopic echo /cmd_vel
```

### 问题 2: "未收到速度信息"错误

**原因：**
- ROS 话题名称不匹配
- ROS 节点未启动
- 话题订阅超时

**解决方案：**

```python
# 使用正确的话题名称启动系统
python stage6_integrated_script_fixed.py \
  --url http://octopi.local \
  --api-key YOUR_KEY \
  --speed-source odom \
  --odom-topic /odom \
  --cmd-vel-topic /cmd_vel \
  --threshold 0.04
```

### 问题 3: 速度阈值不生效

**症状：**
- 机器人移动了，但打印机没有暂停
- 或者打印机一直在暂停

**诊断步骤：**

```bash
# 1. 启动系统后，在命令行输入：
status

# 检查输出中的：
# - current_robot_speed: 应该显示实时速度
# - speed_threshold: 应该是你设置的值（默认0.04）
# - messages_received: 应该大于0，表示收到了ROS消息

# 2. 如果 current_robot_speed 总是0，说明没收到速度信息
# 3. 如果 messages_received 为0，说明话题订阅失败
```

**常见速度阈值设置：**
```
0.01 m/s  → 极低速移动才能打印 (最安全)
0.04 m/s  → 推荐值，低速巡航时打印
0.1  m/s  → 较高速移动时打印
0.2  m/s  → 高速移动时打印
```

## 正确的使用流程

### 第一次设置

```bash
# 1. 确保 ROS 已启动
source devel/setup.bash

# 2. 启动你的机器人节点（例如 turtlebot）
roslaunch turtlebot3_gazebo turtlebot3_world.launch  # 模拟器
# 或真机：
roslaunch turtlebot3_bringup turtlebot3_robot.launch

# 3. 在另一个终端启动 Stage 6
source /opt/ros/noetic/setup.bash
cd /path/to/stage6
python stage6_integrated_script_fixed.py \
  --url http://octopi.local \
  --api-key YOUR_API_KEY \
  --threshold 0.04
```

### 第二步：启动打印

```
>>> print /path/to/model.gcode
✓ 打印线程已启动
✓ 床加热完成
✓ 打印和速度控制已启动
```

### 第三步：控制机器人

```bash
# 在另一个终端移动机器人
# 使用 turtlebot3_teleop 或 move_base

# 当机器人速度 > 0.04 m/s 时：
# → 打印机自动暂停 ✓

# 当机器人速度 ≤ 0.04 m/s 时：
# → 打印机自动恢复 ✓
```

### 在 Stage 6 命令行中查看效果

```
>>> status
系统状态:
  bed_heat_complete: True
  current_file: /path/to/model.gcode
  log_file: ./logs/robot_printer_control_20240101_120000.csv
  pause_count: 5          ← 暂停了5次
  printer_paused: False   ← 当前在运行
  printer_progress: 35.5%
  printer_state: running
  robot_speed: 0.0234 m/s ← 当前速度
  resume_count: 4         ← 恢复了4次
  speed_monitor_alive: True
  speed_threshold: 0.0400 m/s
  timestamp: 2024-01-01T12:00:00.123456
```

## 🔧 关键改进点

### 改进 1: 床加热不再阻塞 

**问题代码（原版）：**
```python
# 这会阻塞主线程！
while 床未加热:
    等待2秒
    检查温度
# 完成后才开始打印
```

**修复代码（新版）：**
```python
#  后台线程，不阻塞主线程
def _bed_heat_worker(self):  # 独立线程
    while 床未加热:
        等待2秒
        检查温度
    标记 bed_heat_complete = True

# 主线程可以继续运行，同时启动速度控制
```

### 改进 2: 更好的ROS话题处理 

**新增特性：**
- ✅ 自动重连
- ✅ 消息计数器，验证是否收到数据
- ✅ 超时检测（3秒无数据则警告）
- ✅ 支持自定义话题名称

```python
# 查看消息计数
>>> status
messages_received: 1523  # 已收到1523条消息
```

### 改进 3: 更智能的防抖 

**原版本：**
```python
# 简单的时间防抖，可能误判
if 时间差 > 0.5s:
    切换状态
```

**新版本：**
```python
# 连续低速确认后才恢复
stable_counter = 0
while 速度 ≤ 阈值:
    stable_counter += 1
    if stable_counter >= 3:  # 连续3个周期低速
        恢复打印

# 这样可以避免速度波动造成的误暂停
```

## 日志分析

生成的 CSV 日志包含：
```
timestamp,robot_speed_ms,action,printer_state,response_time_ms,notes
2024-01-01T12:00:00,0.0500,PAUSE,pausing,150,高速运动: 0.0500m/s
2024-01-01T12:00:05,0.0250,RESUME,resuming,120,低速运动: 0.0250m/s
```

查看日志：
```bash
# 最后的日志文件
tail -f logs/robot_printer_control_*.csv

# 统计暂停/恢复次数
grep -c "PAUSE" logs/robot_printer_control_*.csv
grep -c "RESUME" logs/robot_printer_control_*.csv
```

## 测试检查清单

- [ ] ROS 节点正在运行
- [ ] `/odom` 或 `/cmd_vel` 话题有数据流
- [ ] OctoPrint 可以访问
- [ ] 打印机已就绪（connected）
- [ ] G-code 文件存在
- [ ] 速度阈值设置合理（默认0.04 m/s）
- [ ] 日志文件正确生成
- [ ] 机器人移动时速度值在变化
- [ ] 打印机根据速度暂停/恢复

## 性能优化

### 减少虚假暂停

```bash
# 增加防抖时间（默认0.5s）
>>> debounce 1.0

# 或增加连续确认次数（在代码中修改）
if stable_counter >= 5:  # 改为需要连续5个周期
    恢复打印
```

### 加快响应速度

```bash
# 监控周期在 _control_loop 中
time.sleep(0.1)  # 改为更短的周期（不要低于0.05s）
```

### 检查响应延迟

```bash
status
# 查看 response_time 字段，应该 < 200ms
```

## 获取支持

如果问题仍未解决：

1. 收集诊断信息：
```bash
# 列出所有 ROS 话题
rostopic list

# 查看话题类型
rostopic type /odom

# 检查系统日志
grep -r "ERROR\|WARN" logs/
```

2. 查看详细日志：
```python
# 在代码中增加日志级别
logging.basicConfig(level=logging.DEBUG)
```

3. 检查网络连接：
```bash
ping octopi.local
curl -H "X-Api-Key: YOUR_KEY" http://octopi.local/api/printer
```