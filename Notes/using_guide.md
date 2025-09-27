# OctoPrint G-code控制器 - 安装配置指南

## 系统要求

- Ubuntu系统（已配置ROS环境）
- Python 3.6+
- 网络连接到OctoPrint服务器
- OctoPrint已正常运行且可访问

## 安装步骤

### 1. 创建项目目录

```bash
mkdir ~/gcode_controller
cd ~/gcode_controller
```

### 2. 安装Python依赖

```bash
# 安装必要的Python包
pip3 install requests

# 如果需要更详细的日志功能
pip3 install colorlog
```

### 3. 下载项目文件

将以下文件保存到项目目录：
- `gcode_controller.py` - 主控制器
- `config.py` - 配置文件
- `example_usage.py` - 使用示例

### 4. 配置OctoPrint连接

#### 4.1 获取API密钥

1. 打开OctoPrint web界面（通常是 `http://你的打印机IP地址`）
2. 登录管理员账户
3. 点击 **设置** (Settings) → **API**
4. 在"Application Keys"部分，点击 **Generate** 生成新的API密钥
5. 复制生成的API密钥

#### 4.2 修改配置文件

编辑 `config.py` 文件：

```python
# 修改这些配置项
OCTOPRINT_CONFIG = {
    'url': 'http://192.168.1.100',  # 改为你的OctoPrint IP地址
    'api_key': 'YOUR_ACTUAL_API_KEY',  # 粘贴刚才复制的API密钥
    'timeout': 30
}
```

### 5. 测试连接

```bash
# 运行连接测试
python3 example_usage.py

# 选择选项 1 进行基本测试
```

## 使用方法

### 基本用法

```python
from gcode_controller import GCodeController

# 创建控制器
controller = GCodeController(
    "http://192.168.1.100",  # OctoPrint URL
    "YOUR_API_KEY"           # API密钥
)

# 处理G-code文件
controller.process_gcode_file("/path/to/your/file.gcode")
```

### 命令行使用

```bash
# 创建示例G-code文件
python3 example_usage.py create

# 基本使用模式
python3 example_usage.py basic

# 交互模式
python3 example_usage.py interactive
```

### 在ROS环境中集成

如果要在ROS节点中使用：

```python
#!/usr/bin/env python3

import rospy
from gcode_controller import GCodeController
from std_msgs.msg import String

class GCodeROSNode:
    def __init__(self):
        rospy.init_node('gcode_controller_node')
        
        # 获取ROS参数
        octoprint_url = rospy.get_param('~octoprint_url', 'http://192.168