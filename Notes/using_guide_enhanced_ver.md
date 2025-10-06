# 状态管理
pythonclass PrinterState(Enum):
    IDLE = "idle"
    RUNNING = "running" 
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
# 线程控制

主线程：处理用户输入和状态控制
工作线程：处理文件读取和G-code发送
使用 threading.Event 实现暂停/恢复

# 使用方法
## 1. 配置
修改脚本中的配置信息：
pythonOCTOPRINT_URL = "http://192.168.1.100"  # 你的OctoPrint地址
API_KEY = "YOUR_API_KEY_HERE"  # 你的API密钥
## 2. 运行交互模式
python gcode_sender_enhanced.py
python3 src/octoprint_ros/scripts/enhanced_gcode_sender.py
## 3. 可用命令

single G28 - 发送单条指令
file /path/to/file.gcode - 开始打印文件
file src/octoprint_ros/gcode/example.gcode
pause - 暂停发送
resume - 恢复发送
stop - 停止发送
progress - 查看进度
status - 查看打印机状态

## 4. 编程接口
pythonsender = GCodeSender("http://192.168.1.100", "YOUR_API_KEY")

下面说的是函数，不能当作交互行的指令用：
### 发送单条指令
sender.send_single_command("G28")

### 开始文件打印
sender.start_file_print("/path/to/file.gcode")

### 控制操作
sender.pause()
sender.resume()
sender.stop()

### 获取进度
progress = sender.get_progress()

