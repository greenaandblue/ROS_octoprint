#!/usr/bin/env python3
"""
G-code Sender节点测试脚本
"""

import rospy # type: ignore
import sys
from gcode_sender.srv import ( # type: ignore
    StartPrint, PausePrint, ResumePrint, 
    StopPrint, SetSpeed, GetStatus
)
from gcode_sender.msg import PrintProgress, TemperatureInfo # type: ignore

class GCodeSenderTester:
    def __init__(self):
        rospy.init_node('gcode_sender_tester', anonymous=True)
        
        # 等待服务可用
        rospy.loginfo("等待服务启动...")
        rospy.wait_for_service('/gcode_sender/start_print')
        
        # 创建服务代理
        self.start_print = rospy.ServiceProxy('/gcode_sender/start_print', StartPrint)
        self.pause_print = rospy.ServiceProxy('/gcode_sender/pause_print', PausePrint)
        self.resume_print = rospy.ServiceProxy('/gcode_sender/resume_print', ResumePrint)
        self.stop_print = rospy.ServiceProxy('/gcode_sender/stop_print', StopPrint)
        self.set_speed = rospy.ServiceProxy('/gcode_sender/set_speed', SetSpeed)
        self.get_status = rospy.ServiceProxy('/gcode_sender/get_status', GetStatus)
        
        # 订阅话题
        rospy.Subscriber('/gcode_sender/print_progress', PrintProgress, self.progress_callback)
        rospy.Subscriber('/gcode_sender/temperatures', TemperatureInfo, self.temp_callback)
        
        rospy.loginfo("测试器已就绪")
    
    def progress_callback(self, msg):
        rospy.loginfo(f"进度: {msg.progress_percent:.1f}% ({msg.current_line}/{msg.total_lines})")
    
    def temp_callback(self, msg):
        rospy.logdebug(f"温度: 热端={msg.tool_actual:.1f}°C, 热床={msg.bed_actual:.1f}°C")
    
    def test_start_print(self, file_path):
        """测试开始打印"""
        rospy.loginfo(f"测试: 开始打印 {file_path}")
        try:
            resp = self.start_print(file_path)
            rospy.loginfo(f"结果: {resp.success} - {resp.message}")
            return resp.success
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False
    
    def test_pause_print(self):
        """测试暂停打印"""
        rospy.loginfo("测试: 暂停打印")
        try:
            resp = self.pause_print()
            rospy.loginfo(f"结果: {resp.success} - {resp.message}")
            return resp.success
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False
    
    def test_resume_print(self):
        """测试恢复打印"""
        rospy.loginfo("测试: 恢复打印")
        try:
            resp = self.resume_print()
            rospy.loginfo(f"结果: {resp.success} - {resp.message}")
            return resp.success
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False
    
    def test_stop_print(self):
        """测试停止打印"""
        rospy.loginfo("测试: 停止打印")
        try:
            resp = self.stop_print()
            rospy.loginfo(f"结果: {resp.success} - {resp.message}")
            return resp.success
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False
    
    def test_set_speed(self, multiplier):
        """测试设置速度"""
        rospy.loginfo(f"测试: 设置速度倍率为 {multiplier}x")
        try:
            resp = self.set_speed(multiplier)
            rospy.loginfo(f"结果: {resp.success} - 实际倍率: {resp.actual_multiplier}x")
            return resp.success
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False
    
    def test_get_status(self):
        """测试获取状态"""
        rospy.loginfo("测试: 获取状态")
        try:
            resp = self.get_status()
            rospy.loginfo(f"状态: {resp.state}")
            rospy.loginfo(f"进度: {resp.current_line}/{resp.total_lines} ({resp.progress_percent:.1f}%)")
            rospy.loginfo(f"文件: {resp.file_path}")
            return True
        except rospy.ServiceException as e:
            rospy.logerr(f"服务调用失败: {e}")
            return False

def main():
    tester = GCodeSenderTester()
    
    if len(sys.argv) < 2:
        rospy.loginfo("用法: rosrun gcode_sender test_gcode_sender.py <gcode_file_path>")
        return
    
    file_path = sys.argv[1]
    
    # 运行测试序列
    rospy.loginfo("=" * 60)
    rospy.loginfo("开始测试序列")
    rospy.loginfo("=" * 60)
    
    # 1. 获取初始状态
    tester.test_get_status()
    rospy.sleep(1)
    
    # 2. 开始打印
    if tester.test_start_print(file_path):
        rospy.sleep(5)  # 等待5秒
        
        # 3. 获取打印状态
        tester.test_get_status()
        rospy.sleep(2)
        
        # 4. 暂停打印
        if tester.test_pause_print():
            rospy.sleep(3)
            
            # 5. 获取暂停状态
            tester.test_get_status()
            rospy.sleep(2)
            
            # 6. 设置速度
            tester.test_set_speed(1.5)
            rospy.sleep(1)
            
            # 7. 恢复打印
            if tester.test_resume_print():
                rospy.sleep(5)
                
                # 8. 停止打印
                tester.test_stop_print()
    
    rospy.loginfo("=" * 60)
    rospy.loginfo("测试完成")
    rospy.loginfo("=" * 60)

if __name__ == '__main__':
    try:
        main()
    except rospy.ROSInterruptException:
        pass