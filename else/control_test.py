import requests
import time

Octopi_URL = "http://octopi.local/api/printer/command"
Global_API_key = "kZhM3w7vBAME6vEzF2iEIh1BLTa-8TnJSXSBa50uy1k"

headers = {"Content-Type": "application/json",
           "X-API-Key": Global_API_key}

def send_gcode(cmd):
    response = requests.post(
        Octopi_URL,
        headers = headers,
        json = {"command":cmd}
    )
    if response.status_code == 204:
        print(f"已发送：{cmd}")
    else:
        print(f"error:{response.status_code}, {response.text}")

if __name__=="__main__":
    send_gcode("M17")   # 上电电机
    send_gcode("G28")   # 回零
    time.sleep(5)       # wait for 5s

    send_gcode("G1 X50 Y50 F30000")     # move to (50,50,0)
    time.sleep(2)

    send_gcode("G1 Z10 F1200")            # move up to Z10
    time.sleep(2)

    send_gcode("M18")                   # 关闭电机
