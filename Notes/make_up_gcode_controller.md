
duiyu脚本enhanced_xx，暂停/恢复/停止功能是通过 **调用类的方法** 来实现的：

```python
controller.pause_processing()
controller.resume_processing()
controller.stop_processing()
controller.emergency_stop()
```

但是它没有写成「可以直接在另一个 terminal 输入命令来控制」的形式。
所以直接 `python gcode_controller.py` 跑，它会一直在一个循环里执行 G-code，**你没法在另一个终端用命令行来控制它**。

---

### 方案 1：用 ROS 节点 + topic/service 控制

这是最常见的 ROS 做法。思路是：

1. 把 `GCodeController` 封装成一个 ROS 节点。
2. 订阅一个 topic（比如 `/printer_control`），或者提供 service。
3. 你在另一个终端可以用 `rostopic pub` 或 `rosservice call` 来发送 `pause/resume/stop/emergency_stop` 指令。

示例（简化版）：

```python
import rospy
from std_msgs.msg import String
from gcode_controller import GCodeController

controller = None

def control_callback(msg):
    global controller
    if msg.data == "pause":
        controller.pause_processing()
    elif msg.data == "resume":
        controller.resume_processing()
    elif msg.data == "stop":
        controller.stop_processing()
    elif msg.data == "emergency":
        controller.emergency_stop()

def main():
    global controller
    rospy.init_node("gcode_controller_node")
    
    OCTOPRINT_URL = "http://octopi.local"
    API_KEY = "xxx"
    GCODE_FILE = "/path/to/file.gcode"
    
    controller = GCodeController(OCTOPRINT_URL, API_KEY)
    rospy.Subscriber("/printer_control", String, control_callback)
    
    controller.process_gcode_file(GCODE_FILE)

if __name__ == "__main__":
    main()
```

这样你就能在另一个终端输入：

```bash
rostopic pub /printer_control std_msgs/String "pause"
rostopic pub /printer_control std_msgs/String "resume"
rostopic pub /printer_control std_msgs/String "stop"
rostopic pub /printer_control std_msgs/String "emergency"
```

就能远程控制打印机。

---

### 方案 2：用多进程/信号量

如果你不想动 ROS，可以用 Python 的 **signal** 或 **多进程**：

* 在主脚本里监听 `SIGUSR1`、`SIGUSR2` 信号（`kill -USR1 <pid>` 就能发信号）。
* 收到不同信号时调用 `pause_processing()` / `resume_processing()`。

示例：

```python
import signal
import sys

def handle_signal(signum, frame):
    if signum == signal.SIGUSR1:
        controller.pause_processing()
    elif signum == signal.SIGUSR2:
        controller.resume_processing()
    elif signum == signal.SIGINT:
        controller.stop_processing()

signal.signal(signal.SIGUSR1, handle_signal)
signal.signal(signal.SIGUSR2, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
```

然后你可以在另一个终端执行：

```bash
kill -USR1 <pid>   # 暂停
kill -USR2 <pid>   # 恢复
kill -INT <pid>    # 停止
```

