cmake_minimum_required(VERSION 3.0.2)
project(gcode_sender)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  message_generation
)

## 生成消息
add_message_files(
  FILES
  PrinterStatus.msg
  PrintProgress.msg
  TemperatureInfo.msg
)

## 生成服务
add_service_files(
  FILES
  StartPrint.srv
  PausePrint.srv
  ResumePrint.srv
  StopPrint.srv
  SetSpeed.srv
  GetStatus.srv
)

## 生成消息和服务
generate_messages(
  DEPENDENCIES
  std_msgs
)

catkin_package(
  CATKIN_DEPENDS 
    rospy 
    std_msgs 
    message_runtime
)

include_directories(
  ${catkin_INCLUDE_DIRS}
)

## 安装Python脚本
catkin_install_python(PROGRAMS
  scripts/gcode_sender_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

## 安装launch文件
install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)

## 安装配置文件
install(DIRECTORY config/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/config
)