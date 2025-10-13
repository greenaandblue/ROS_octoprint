# ROS消息和服务定义文件

## 目录结构
```
gcode_sender_msgs/
├── msg/
│   ├── PrinterStatus.msg
│   ├── Progress.msg
│   └── TemperatureInfo.msg
├── srv/
│   ├── SendCommand.srv
│   └── StartPrint.srv
├── CMakeLists.txt
└── package.xml
```

## 消息定义

### msg/PrinterStatus.msg
```
string state                # 当前状态: idle, running, paused, stopped, error, halted
string printer_state        # 打印机状态文本
int32 error_count          # 错误计数
bool safe_mode             # 安全模式是否启用
```

### msg/Progress.msg
```
int32 current_line         # 当前行号
int32 total_lines          # 总行数
int32 processed_commands   # 已处理的命令数
float32 progress_percent   # 进度百分比
string file_path           # 文件路径
int32 buffer_size          # 缓冲区大小
```

### msg/TemperatureInfo.msg
```
float32 tool_actual        # 热端实际温度
float32 tool_target        # 热端目标温度
float32 bed_actual         # 热床实际温度
float32 bed_target         # 热床目标温度
```

## 服务定义

### srv/SendCommand.srv
```
string command             # 要发送的G-code命令
bool force                 # 是否强制发送（跳过危险检查）
---
bool success              # 是否成功
string message            # 返回消息
```

### srv/StartPrint.srv
```
string file_path          # G-code文件路径
---
bool success             # 是否成功
string message           # 返回消息
```

## CMakeLists.txt
```cmake
cmake_minimum_required(VERSION 3.0.2)
project(gcode_sender_msgs)

find_package(catkin REQUIRED COMPONENTS
  message_generation
  std_msgs
)

add_message_files(
  FILES
  PrinterStatus.msg
  Progress.msg
  TemperatureInfo.msg
)

add_service_files(
  FILES
  SendCommand.srv
  StartPrint.srv
)

generate_messages(
  DEPENDENCIES
  std_msgs
)

catkin_package(
  CATKIN_DEPENDS message_runtime std_msgs
)
```

## package.xml
```xml
<?xml version="1.0"?>
<package format="2">
  <name>gcode_sender_msgs</name>
  <version>1.0.0</version>
  <description>Messages and services for G-code sender node</description>
  
  <maintainer email="your_email@example.com">Your Name</maintainer>
  <license>MIT</license>

  <buildtool_depend>catkin</buildtool_depend>
  
  <build_depend>message_generation</build_depend>
  <build_depend>std_msgs</build_depend>
  
  <exec_depend>message_runtime</exec_depend>
  <exec_depend>std_msgs</exec_depend>
</package>
```