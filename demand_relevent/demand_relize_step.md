*** 注意事项和安全提醒 ***

1.安全第一：在测试移动指令前，确保打印机已正确回零，并且移动范围在安全限制内。
2.API密钥安全：不要将API密钥提交到版本控制系统，考虑使用环境变量。
3.网络连接：确保ROS主机能够访问 octopi.local。
4.错误处理：节点包含了基本的错误处理，但在生产环境中可能需要更robust的错误恢复机制。
5.速度限制：默认移动速度设置较低，根据你的打印机调整合适的速度。

# 第一步：环境准备和依赖安装 

1.1 确认环境

确认ROS环境：
echo $ROS_DISTRO

确认Python环境：
python3 --version

1.2 安装必要的Python包
pip3 install requests octopi-client

# 第二步：获取OctoPrint API密钥
2.1 登录OctoPrint Web界面
在浏览器中访问：http://octopi.local

2.2 生成API密钥

登录后，点击右上角设置图标
找到 "API" 选项卡
生成新的API密钥并保存（类似：1234567890ABCDEF1234567890ABCDEF）

2.3 备注
*** Octopi_URL = "http://octopi.local/api/printer/command" ***
*** Global_API_key = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k" ***

# 第三步：创建ROS包结构
进入你的ROS工作空间
cd ~/catkin_ws/src  

创建新包
catkin_create_pkg gcode_controller rospy std_msgs geometry_msgs

创建必要目录
cd gcode_controller
mkdir scripts config launch

# 第四步：创建核心ROS节点
gcode_controller_node.py

# 第五步：创建启动文件
gcode_controller.launch

# 第六步：创建配置文件
config/printer_config.yaml

# 第七步：创建测试脚本
scripts/test_gcode_controller.py

# 第八步：设置文件权限和编译
进入包目录
cd ~/catkin_ws/src/gcode_controller

给脚本添加执行权限
chmod +x scripts/gcode_controller_node.py
chmod +x scripts/test_gcode_controller.py

编译ROS包
cd ~/catkin_ws
catkin_make

刷新环境
source devel/setup.bash

# 第九步：配置和启动
9.1 修改配置文件
编辑launch文件，替换API密钥
nano ~/catkin_ws/src/gcode_controller/launch/gcode_controller.launch
在launch文件中，将 YOUR_API_KEY_HERE 替换为你从OctoPrint获取的实际API密钥。

9.2 启动节点
启动G-code控制器
roslaunch gcode_controller gcode_controller.launch

# 第十步：测试和使用
10.1 基本测试
在新终端中运行测试脚本
rosrun gcode_controller test_gcode_controller.py basic

10.2 交互式测试
交互式模式
rosrun gcode_controller test_gcode_controller.py interactive

10.3 手动发送指令

发送单个G-code指令
rostopic pub /gcode_command std_msgs/String "data: 'G28'"

发送移动指令
rostopic pub /cmd_vel geometry_msgs/Twist "linear: {x: 10.0, y: 0.0, z: 0.0}"

10.4 监控状态
监控打印机状态
rostopic echo /printer_status
