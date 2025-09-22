# Stage 1

# 1. 需求核心 

写一个 ROS 节点（node），语言是 Python。

这个节点的作用是：

一行行地发送 G-code 指令（比如 G28 回零、G1 X10 移动等）。

目标对象是运行在树莓派上的 OctoPrint（octopi.local），它连接着3D打印机。

最终效果：用ROS消息或逻辑控制3D打印机的运动/打印过程。

# 2. 关键技术点

要实现上面的目标，需要清楚几个环节：

(a) ROS节点结构 

ROS节点 = 程序的一个“进程”，负责某个功能。

用 Python 写时通常用 rospy。

你的节点大概会有：

订阅者（Subscriber）：接受上游节点传来的“要执行的G-code指令”。

发布者（Publisher）（可选）：把执行状态、反馈结果发出去。

主循环：一行行把G-code通过 OctoPrint 发送给打印机。

(b) 与OctoPrint通信

OctoPrint 提供了 REST API 和 WebSocket API。

你需要选择 REST API（比较简单，逐行发G-code）。

REST API 的要点：

认证：需要一个 API Key（在 OctoPrint 设置里生成）。

请求方式：一般用 POST 请求，比如：

POST http://octopi.local/api/printer/command

请求体（JSON）：{"command": "G28"}

每次请求就是一条 G-code 指令。

(c) ROS与OctoPrint的接口关系

你需要让ROS节点和OctoPrint的API对接，逻辑可以这样：

ROS节点从某个话题（topic）接收一行G-code（比如 /printer_commands）。

节点调用 OctoPrint 的 API，把这一行指令发过去。

OctoPrint 把指令转发给打印机 → 打印机执行动作。

节点可选择把结果发布到另一个话题（比如 /printer_status），方便其他节点订阅。

# 3. 需求的分层描述

可以这样拆解：

最低层（硬件/通信层）

树莓派运行 OctoPrint，USB 连着打印机。

你不直接写串口，而是通过 OctoPrint API。

中间层（接口层）

Python 用 requests 库（或者 websocket）与 OctoPrint REST API 通信。

每次发一行 G-code。

ROS层（逻辑层）

一个 Python ROS node。

输入：订阅 ROS 话题（或从文件/逻辑生成 G-code）。

输出：逐行调用 OctoPrint API 执行指令。

可选：把打印机状态再发布出来。

# 4. 你需要准备的东西

确认 OctoPrint 已经能在浏览器里访问（http://octopi.local）。

在 OctoPrint 中创建 API Key（设置 → API → Application Key 或 Global API Key）。

树莓派和你运行 ROS 的电脑要在同一个网络里。

ROS 环境：确保 rospy 可用。

# 5. 最终效果

当你在ROS里发消息（比如 rostopic pub /printer_commands "data: 'G28'"），

你的ROS节点就会把 G28 发给 octopi.local → 打印机执行回零动作。

逐行控制打印机的所有动作，而不需要手动在OctoPrint界面点按钮。

# Stage 2

# 1.任务背景

你已经在 Ubuntu 系统上的 ROS 环境 成功运行了一个 Python 脚本。该脚本可以在 3D 打印机处于空闲状态（没有正在打印文件） 时，通过 OctoPrint (OctoPi) 接口来控制打印机。接下来，你希望进一步扩展这个功能，使脚本能够自动读取并逐行处理 G-code 文件，并与前一个控制脚本协同工作，从而实现对打印机的更精细化管理。

# 2.任务目标

### 实现 G-code 文件逐行读取

编写一个新的 Python 文件，用于按顺序逐行读取指定的 G-code 文件内容。

每一行 G-code 指令将作为独立的命令进行处理，确保与打印机的通信顺序一致。

### 与现有控制逻辑配合

将新文件与之前的控制脚本结合使用。

在检测到打印机空闲时，脚本能够从 G-code 文件中逐行发送指令。

在检测到打印机正在执行任务时，脚本应暂停或等待，避免冲突。

### 通过 OctoPrint 接口发送指令

使用 OctoPrint 的 API，将读取到的每条 G-code 命令发送至打印机。

确保指令执行成功后，才继续发送下一条。

### 增加可控性与健壮性

在 G-code 文件读取和发送过程中，考虑错误处理机制（如：无效的 G-code 行、与打印机通信异常、网络连接问题等）。

提供简单的日志或提示信息，便于监控打印过程。