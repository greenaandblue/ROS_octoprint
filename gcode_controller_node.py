#!/usr/bin/env python3

import rospy  # type: ignore
import requests
import json
import time
from std_msgs.msg import String  # type: ignore
from geometry_msgs.msg import Twist  # type: ignore
import threading
from queue import Queue
from typing import Dict, Any, Optional, Union

class GCodeController:
    def __init__(self) -> None:
        rospy.init_node('gcode_controller', anonymous=True)
        
        # 从参数服务器获取配置
        self.octoprint_host: str = rospy.get_param('~octoprint_host', 'octopi.local')
        self.octoprint_port: int = rospy.get_param('~octoprint_port', 80)
        self.api_key: str = rospy.get_param('~api_key', '')
        
        if not self.api_key:
            rospy.logerr("API key is required! Set it via parameter ~api_key")
            return
        
        # API端点
        self.base_url: str = f"http://{self.octoprint_host}:{self.octoprint_port}/api"
        self.headers: Dict[str, str] = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        
        # G-code指令队列
        self.gcode_queue: Queue[str] = Queue()
        self.is_processing: bool = False
        
        # ROS订阅者
        self.gcode_sub = rospy.Subscriber('/gcode_command', String, self.gcode_callback)
        self.twist_sub = rospy.Subscriber('/cmd_vel', Twist, self.twist_callback)
        
        # ROS发布者
        self.status_pub = rospy.Publisher('/printer_status', String, queue_size=10)
        
        # 启动G-code处理线程
        self.processing_thread: threading.Thread = threading.Thread(target=self.process_gcode_queue)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        # 状态监控定时器
        self.status_timer = rospy.Timer(rospy.Duration(2.0), self.publish_status)
        
        rospy.loginfo("G-code Controller initialized")
        rospy.loginfo(f"Connected to OctoPrint at {self.octoprint_host}:{self.octoprint_port}")
        
        self.test_connection()

    def test_connection(self) -> bool:
        """测试与OctoPrint的连接"""
        try:
            response = requests.get(f"{self.base_url}/version", headers=self.headers, timeout=5)
            if response.status_code == 200:
                version_info: Dict[str, Any] = response.json()
                rospy.loginfo(f"Connected to OctoPrint version: {version_info.get('server', 'Unknown')}")
                return True
            else:
                rospy.logerr(f"Failed to connect to OctoPrint. Status: {response.status_code}")
                return False
        except Exception as e:
            rospy.logerr(f"Connection test failed: {str(e)}")
            return False

    def gcode_callback(self, msg: String) -> None:
        """处理G-code指令消息"""
        gcode: str = msg.data.strip()
        if gcode:
            rospy.loginfo(f"Received G-code: {gcode}")
            self.gcode_queue.put(gcode)

    def twist_callback(self, msg: Twist) -> None:
        """将Twist消息转换为G-code移动指令"""
        # 将Twist消息转换为相对移动的G-code
        # 这里假设linear.x, linear.y, linear.z对应XYZ轴移动
        # angular.z可以对应挤出机
        
        # 检查是否有足够的移动量
        has_linear_movement: bool = (
            abs(msg.linear.x) > 0.01 or 
            abs(msg.linear.y) > 0.01 or 
            abs(msg.linear.z) > 0.01
        )
        
        if has_linear_movement or abs(msg.angular.z) > 0.01:
            # 构建G1移动指令
            gcode_parts: list[str] = ["G91", "G1"]  # G91设置相对定位，G1线性移动
            
            if abs(msg.linear.x) > 0.01:
                gcode_parts.append(f"X{msg.linear.x:.2f}")
            if abs(msg.linear.y) > 0.01:
                gcode_parts.append(f"Y{msg.linear.y:.2f}")
            if abs(msg.linear.z) > 0.01:
                gcode_parts.append(f"Z{msg.linear.z:.2f}")
            if abs(msg.angular.z) > 0.01:
                gcode_parts.append(f"E{msg.angular.z:.2f}")
            
            gcode_parts.append("F1500")  # 设置移动速度
            
            gcode_command: str = " ".join(gcode_parts)
            rospy.loginfo(f"Twist to G-code: {gcode_command}")
            self.gcode_queue.put(gcode_command)

    def send_gcode(self, gcode: str) -> bool:
        """发送单条G-code指令到OctoPrint"""
        try:
            data: Dict[str, list[str]] = {
                "commands": [gcode]
            }
            
            response = requests.post(
                f"{self.base_url}/printer/command",
                headers=self.headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 204:
                rospy.loginfo(f"Successfully sent: {gcode}")
                return True
            else:
                rospy.logerr(f"Failed to send G-code. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            rospy.logerr(f"Error sending G-code '{gcode}': {str(e)}")
            return False

    def process_gcode_queue(self) -> None:
        """处理G-code队列的后台线程"""
        while not rospy.is_shutdown():
            try:
                if not self.gcode_queue.empty():
                    gcode: str = self.gcode_queue.get(timeout=1)
                    self.send_gcode(gcode)
                    # 添加小延迟避免过快发送指令
                    time.sleep(0.1)
                else:
                    time.sleep(0.1)
            except Exception as e:
                rospy.logerr(f"Error in gcode processing thread: {str(e)}")
                time.sleep(1)

    def get_printer_status(self) -> Dict[str, Any]:
        """获取打印机状态"""
        try:
            response = requests.get(f"{self.base_url}/printer", headers=self.headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return {"state": {"text": "Unknown"}}
        except Exception as e:
            rospy.logwarn(f"Failed to get printer status: {str(e)}")
            return {"state": {"text": "Connection Error"}}

    def publish_status(self, event: Any) -> None:
        """定期发布打印机状态"""
        status: Dict[str, Any] = self.get_printer_status()
        status_msg = String()
        status_msg.data = json.dumps(status)
        self.status_pub.publish(status_msg)

    def shutdown(self) -> None:
        """节点关闭时的清理工作"""
        rospy.loginfo("Shutting down G-code Controller...")
        # 发送停止指令
        self.send_gcode("M104 S0")  # 关闭热端
        self.send_gcode("M140 S0")  # 关闭热床
        self.send_gcode("M84")      # 关闭步进电机

def main() -> None:
    try:
        controller = GCodeController()
        rospy.on_shutdown(controller.shutdown)
        rospy.spin()
    except rospy.ROSInterruptException:  # type: ignore
        rospy.loginfo("G-code Controller interrupted")
    except Exception as e:
        rospy.logerr(f"G-code Controller failed: {str(e)}")

if __name__ == '__main__':
    main()