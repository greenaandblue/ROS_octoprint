# G-code Sender ROS节点使用手册

## 目录
1. [安装配置](#安装配置)
2. [启动节点](#启动节点)
3. [ROS话题](#ros话题)
4. [ROS服务](#ros服务)
5. [使用示例](#使用示例)
6. [命令行工具](#命令行工具)
7. [故障排除](#故障排除)

---

## 安装配置

### 1. 创建ROS包结构
```bash
cd ~/catkin_ws/src

# 创建消息包
catkin_create_pkg gcode_sender_msgs std_msgs message_generation message_runtime

# 创建节点包
catkin_create_pkg gcode_sender rospy std_msgs std_srvs gcode_sender_msgs
```

### 2. 安装依赖
```bash
# 安装Python依赖
pip3 install requests

# 或使用apt安装
sudo apt-get install python3-requests
```

### 3. 文件放置
```
catkin_ws/src/
├── gcode_sender_msgs/          # 消息和服务包
│   ├── msg/
│   │   ├── PrinterStatus.msg
│   │   ├── Progress.msg
│   │   └── TemperatureInfo.msg
│   ├── srv/
│   │   ├── SendCommand.srv
│   │   └── StartPrint.srv
│   ├── CMakeLists.txt
│   └── package.xml
│
└── gcode_sender/               # 节点包
    ├── scripts/
    │   └── gcode_sender_node.py  (添加执行权限)
    ├── launch/
    │   └── gcode_sender.launch
    ├── config/
    │   └── gcode_sender.yaml
    ├── CMakeLists.txt
    └── package.xml
```

### 4. 添加执行权限
```bash
chmod +x ~/catkin_ws/src/gcode_sender/scripts/gcode_sender_node.py
```

### 5. 编译
```bash
cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

---

## 启动节点

### 方法1: 直接启动
```bash
rosrun gcode_sender gcode_sender_node.py \
  _octoprint_url:=http://192.168.1.100 \
  _api_key:=YOUR_API_KEY_HERE \
  _buffer_size:=20 \
  _publish_rate:=1.0
```

### 方法2: 使用Launch文件

**创建 `gcode_sender.launch`:**
```xml
<launch>
  <!-- G-code Sender Node -->
  <node name="gcode_sender" pkg="gcode_sender" type="gcode_sender_node.py" output="screen">
    <!-- OctoPrint配置 -->
    <param name="octoprint_url" value="http://192.168.1.100"/>
    <param name="api_key" value="YOUR_API_KEY_HERE"/>
    
    <!-- 缓冲区和发布频率 -->
    <param name="buffer_size" value="20"/>
    <param name="publish_rate" value="1.0"/>
  </node>
</launch>
```

启动:
```bash
roslaunch gcode_sender gcode_sender.launch
```

### 方法3: 使用参数文件

**创建 `gcode_sender.yaml`:**
```yaml
gcode_sender:
  octoprint_url: "http://192.168.1.100"
  api_key: "YOUR_API_KEY_HERE"
  buffer_size: 20
  publish_rate: 1.0
```

**修改Launch文件:**
```xml
<launch>
  <node name="gcode_sender" pkg="gcode_sender" type="gcode_sender_node.py" output="screen">
    <rosparam command="load" file="$(find gcode_sender)/config/gcode_sender.yaml"/>
  </node>
</launch>
```

---

## ROS话题

### 发布的话题 (Publishers)

#### 1. `/gcode_sender/printer_status`
- **类型**: `gcode_sender_msgs/PrinterStatus`
- **频率**: 1 Hz (可配置)
- **说明**: 打印机状态信息

**查看:**
```bash
rostopic echo /gcode_sender/printer_status
```

**输出示例:**
```
state: "running"
printer_state: "operational"
error_count: 0
safe_mode: True
```

#### 2. `/gcode_sender/progress`
- **类型**: `gcode_sender_msgs/Progress`
- **频率**: 1 Hz
- **说明**: 打印进度信息

**查看:**
```bash
rostopic echo /gcode_sender/progress
```

**输出示例:**
```
current_line: 1500
total_lines: 3000
processed_commands: 1450
progress_percent: 50.0
file_path: "/home/user/test.gcode"
buffer_size: 15
```

#### 3. `/gcode_sender/temperature`
- **类型**: `gcode_sender_msgs/TemperatureInfo`
- **频率**: 每2秒更新
- **说明**: 温度信息

**查看:**
```bash
rostopic echo /gcode_sender/temperature
```

**输出示例:**
```
tool_actual: 210.5
tool_target: 210.0
bed_actual: 60.2
bed_target: 60.0
```

#### 4. `/gcode_sender/state`
- **类型**: `std_msgs/String`
- **频率**: 1 Hz
- **说明**: 当前状态（简单字符串）

**查看:**
```bash
rostopic echo /gcode_sender/state
```

### 订阅的话题 (Subscribers)

#### `/gcode_sender/gcode_command`
- **类型**: `std_msgs/String`
- **说明**: 接收单条G-code命令

**发送命令:**
```bash
# 发送归零命令
rostopic pub /gcode_sender/gcode_command std_msgs/String "data: 'G28'"

# 设置热端温度
rostopic pub /gcode_sender/gcode_command std_msgs/String "data: 'M104 S200'"
```

---

## ROS服务

### 1. 开始打印 - `/gcode_sender/start_print`
- **类型**: `gcode_sender_msgs/StartPrint`
- **说明**: 开始打印G-code文件

**使用:**
```bash
rosservice call /gcode_sender/start_print "file_path: '/home/user/model.gcode'"
```

**响应:**
```
success: True
message: "开始打印文件: /home/user/model.gcode"
```

### 2. 暂停打印 - `/gcode_sender/pause`
- **类型**: `std_srvs/Trigger`
- **说明**: 暂停当前打印

**使用:**
```bash
rosservice call /gcode_sender/pause
```

**响应:**
```
success: True
message: "暂停成功"
```

### 3. 恢复打印 - `/gcode_sender/resume`
- **类型**: `std_srvs/Trigger`
- **说明**: 恢复暂停的打印

**使用:**
```bash
rosservice call /gcode_sender/resume
```

### 4. 停止打印 - `/gcode_sender/stop`
- **类型**: `std_srvs/Trigger`
- **说明**: 停止当前打印

**使用:**
```bash
rosservice call /gcode_sender/stop
```

### 5. 紧急复位 - `/gcode_sender/emergency_reset`
- **类型**: `std_srvs/Trigger`
- **说明**: 紧急复位打印机（处理HALT状态）

**使用:**
```bash
rosservice call /gcode_sender/emergency_reset
```

### 6. 发送命令 - `/gcode_sender/send_command`
- **类型**: `gcode_sender_msgs/SendCommand`
- **说明**: 发送单条G-code命令（带强制选项）

**使用:**
```bash
# 普通发送（会跳过危险命令）
rosservice call /gcode_sender/send_command "command: 'G28' 
force: false"

# 强制发送（不跳过危险命令，慎用！）
rosservice call /gcode_sender/send_command "command: 'M104 S0' 
force: true"
```

### 7. 系统诊断 - `/gcode_sender/diagnose`
- **类型**: `std_srvs/Trigger`
- **说明**: 获取系统诊断信息

**使用:**
```bash
rosservice call /gcode_sender/diagnose
```

**响应示例:**
```
success: True
message: |
  打印机状态: operational
  当前状态: running
  错误计数: 0/5
  进度: 1500/3000 (50.0%)
```

---

## 使用示例

### 示例1: 完整的打印流程

```bash
# 1. 启动节点
roslaunch gcode_sender gcode_sender.launch

# 2. 检查节点状态
rostopic echo /gcode_sender/state

# 3. 开始打印
rosservice call /gcode_sender/start_print "file_path: '/home/user/my_model.gcode'"

# 4. 监控进度（另一个终端）
rostopic echo /gcode_sender/progress

# 5. 监控温度（另一个终端）
rostopic echo /gcode_sender/temperature

# 6. 如需暂停
rosservice call /gcode_sender/pause

# 7. 恢复打印
rosservice call /gcode_sender/resume

# 8. 或者停止
rosservice call /gcode_sender/stop
```

### 示例2: 手动发送G-code命令

```bash
# 归零所有轴
rostopic pub -1 /gcode_sender/gcode_command std_msgs/String "data: 'G28'"

# 设置热端温度到200度
rostopic pub -1 /gcode_sender/gcode_command std_msgs/String "data: 'M104 S200'"

# 等待热端加热
rostopic pub -1 /gcode_sender/gcode_command std_msgs/String "data: 'M109 S200'"

# 移动到指定位置
rostopic pub -1 /gcode_sender/gcode_command std_msgs/String "data: 'G1 X100 Y100 Z10 F3000'"
```

### 示例3: Python脚本控制

```python
#!/usr/bin/env python3
import rospy
from gcode_sender_msgs.srv import StartPrint, StartPrintRequest
from std_srvs.srv import Trigger
from gcode_sender_msgs.msg import Progress

def progress_callback(msg):
    """进度回调"""
    rospy.loginfo(f"进度: {msg.progress_percent}% ({msg.current_line}/{msg.total_lines})")

def main():
    rospy.init_node('gcode_controller', anonymous=True)
    
    # 等待服务可用
    rospy.wait_for_service('/gcode_sender/start_print')
    rospy.wait_for_service('/gcode_sender/pause')
    
    # 创建服务代理
    start_print = rospy.ServiceProxy('/gcode_sender/start_print', StartPrint)
    pause_print = rospy.ServiceProxy('/gcode_sender/pause', Trigger)
    
    # 订阅进度
    rospy.Subscriber('/gcode_sender/progress', Progress, progress_callback)
    
    # 开始打印
    req = StartPrintRequest()
    req.file_path = '/home/user/test.gcode'
    
    try:
        resp = start_print(req)
        if resp.success:
            rospy.loginfo(f"打印已开始: {resp.message}")
        else:
            rospy.logerr(f"打印失败: {resp.message}")
    except rospy.ServiceException as e:
        rospy.logerr(f"服务调用失败: {e}")
    
    rospy.spin()

if __name__ == '__main__':
    main()
```

### 示例4: 使用rqt监控

```bash
# 启动rqt
rqt

# 在rqt中：
# 1. Plugins -> Topics -> Topic Monitor (监控所有话题)
# 2. Plugins -> Services -> Service Caller (调用服务)
# 3. Plugins -> Visualization -> Plot (绘制温度曲线)
```

---

## 命令行工具

### 快速查看所有相关话题和服务

```bash
# 查看所有gcode_sender相关的话题
rostopic list | grep gcode_sender

# 查看所有gcode_sender相关的服务
rosservice list | grep gcode_sender

# 查看节点信息
rosnode info /gcode_sender
```

### 实时监控脚本

创建 `monitor.sh`:
```bash
#!/bin/bash
# 实时监控打印状态

echo "=== G-code Sender 监控 ==="
echo ""

while true; do
    clear
    echo "=== 打印状态 ==="
    rostopic echo -n 1 /gcode_sender/state
    echo ""
    
    echo "=== 进度信息 ==="
    rostopic echo -n 1 /gcode_sender/progress
    echo ""
    
    echo "=== 温度信息 ==="
    rostopic echo -n 1 /gcode_sender/temperature
    echo ""
    
    sleep 2
done
```

使用:
```bash
chmod +x monitor.sh
./monitor.sh
```

---

## 故障排除

### 问题1: 节点无法启动
**症状**: `rosrun` 报错找不到节点

**解决:**
```bash
# 检查文件权限
ls -l ~/catkin_ws/src/gcode_sender/scripts/gcode_sender_node.py

# 添加执行权限
chmod +x ~/catkin_ws/src/gcode_sender/scripts/gcode_sender_node.py

# 重新source
source ~/catkin_ws/devel/setup.bash
```

### 问题2: 找不到消息类型
**症状**: `ImportError: cannot import name 'PrinterStatus'`

**解决:**
```bash
# 重新编译消息包
cd ~/catkin_ws
catkin_make --pkg gcode_sender_msgs
source devel/setup.bash

# 验证消息已生成
rosmsg show gcode_sender_msgs/PrinterStatus
```

### 问题3: 连接OctoPrint失败
**症状**: 日志显示 "获取打印机状态失败"

**解决:**
```bash
# 检查OctoPrint是否可访问
curl http://192.168.1.100/api/version

# 检查API Key是否正确
# 在OctoPrint网页: Settings -> API -> Copy API Key

# 更新Launch文件中的参数
```

### 问题4: 打印机进入HALT状态
**症状**: 节点报告 "检测到打印机紧急停止状态"

**解决:**
```bash
# 尝试紧急复位
rosservice call /gcode_sender/emergency_reset

# 如果失败，需要手动操作：
# 1. 断开USB连接
# 2. 重新连接USB
# 3. 在OctoPrint中重新连接打印机
# 4. 重启节点
```

### 问题5: 命令发送失败
**症状**: "批量发送失败" 或 "连续发送失败过多"

**解决:**
```bash
# 降低buffer_size参数
rosparam set /gcode_sender/buffer_size 10

# 检查打印机缓冲区
# 在OctoPrint终端查看是否有错误消息

# 运行诊断
rosservice call /gcode_sender/diagnose
```

### 调试技巧

**启用详细日志:**
```bash
# 设置日志级别为DEBUG
rosservice call /gcode_sender/set_logger_level "logger: 'rosout' 
level: 'debug'"

# 查看日志
rqt_console
```

**检查话题通信:**
```bash
# 检查话题发布频率
rostopic hz /gcode_sender/progress

# 检查话题带宽
rostopic bw /gcode_sender/progress

# 查看话题详细信息
rostopic info /gcode_sender/progress
```

---

## 高级用法

### 集成到更大的系统

**示例: 与机械臂协作**
```python
#!/usr/bin/env python3
import rospy
from gcode_sender_msgs.msg import Progress
from std_srvs.srv import Trigger

class PrintArmCoordinator:
    def __init__(self):
        self.print_done = False
        
        # 订阅打印进度
        rospy.Subscriber('/gcode_sender/progress', Progress, self.progress_cb)
        
        # 等待机械臂服务
        rospy.wait_for_service('/arm/move_to_position')
        self.arm_move = rospy.ServiceProxy('/arm/move_to_position', Trigger)
    
    def progress_cb(self, msg):
        # 当打印完成时，通知机械臂取件
        if msg.progress_percent >= 100.0 and not self.print_done:
            self.print_done = True
            rospy.loginfo("打印完成，通知机械臂取件")
            self.arm_move()
    
    def run(self):
        rospy.spin()

if __name__ == '__main__':
    rospy.init_node('print_arm_coordinator')
    coordinator = PrintArmCoordinator()
    coordinator.run()
```

### 创建自定义监控界面

使用 `rqt_gui` 创建自定义监控面板，显示实时状态、温度曲线和进度条。

---

## 参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `octoprint_url` | string | `http://192.168.1.100` | OctoPrint服务器地址 |
| `api_key` | string | `YOUR_API_KEY_HERE` | OctoPrint API密钥 |
| `buffer_size` | int | 20 | G-code缓冲区大小 |
| `publish_rate` | float | 1.0 | 状态发布频率(Hz) |

---

## 安全注意事项

⚠️ **重要安全提示**:

1. **危险命令防护**: 节点会自动过滤危险命令（如M112紧急停止）
2. **安全模式**: 默认启用，防止发送可能损坏打印机的命令
3. **温度监控**: 自动检测温度异常，防止热失控
4. **错误计数**: 连续错误达到阈值会自动停止
5. **紧急停止**: 检测到HALT状态会立即停止所有操作

**不要**使用 `force: true` 选项除非你完全知道后果！

---

## 更新日志

### v1.0.0
- 初始ROS节点版本
- 支持所有基本功能
- M112错误防护
- 实时状态监控