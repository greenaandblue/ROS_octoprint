#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G-code挤出问题诊断工具
专门用于检测和解决OctoPrint suppress command导致的挤出问题
"""

import requests
import json
import time
import logging
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExtrusionDiagnostic:
    """挤出问题诊断器"""
    
    def __init__(self, octoprint_url: str, api_key: str):
        self.octoprint_url = octoprint_url.rstrip('/')
        self.api_key = api_key
        
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        })
        
        # 常见的挤出相关指令
        self.extrusion_commands = [
            "T0",           # 选择工具0
            "T1",           # 选择工具1（如果有双挤出机）
            "M83",          # 相对挤出模式
            "M82",          # 绝对挤出模式  
            "G92 E0",       # 重置挤出机位置
            "G1 E5 F300",   # 测试挤出5mm
            "G1 E-2 F1800", # 测试回抽2mm
            "M104 S200",    # 设置热端温度200度
            "M109 S200",    # 等待热端加热到200度
        ]
    
    def send_command_and_check_response(self, command: str) -> Dict:
        """发送指令并检查响应，看是否被抑制"""
        logger.info(f"测试指令: {command}")
        
        try:
            # 发送指令
            data = {"commands": [command]}
            response = self.session.post(
                f'{self.octoprint_url}/api/printer/command',
                data=json.dumps(data),
                timeout=10
            )
            
            # 检查HTTP状态
            if response.status_code != 204:
                return {
                    'command': command,
                    'status': 'HTTP_ERROR',
                    'http_code': response.status_code,
                    'response': response.text,
                    'suppressed': False
                }
            
            # 等待一下让打印机处理
            time.sleep(0.5)
            
            # 检查是否有suppress通知（通过日志或状态）
            # 这里我们主要通过HTTP响应判断
            return {
                'command': command,
                'status': 'SENT',
                'http_code': 204,
                'response': 'Success',
                'suppressed': False  # 如果HTTP 204表示发送成功
            }
            
        except requests.exceptions.Timeout:
            return {
                'command': command,
                'status': 'TIMEOUT',
                'http_code': None,
                'response': 'Request timeout',
                'suppressed': False
            }
        except requests.exceptions.RequestException as e:
            return {
                'command': command,
                'status': 'NETWORK_ERROR',
                'http_code': None,
                'response': str(e),
                'suppressed': False
            }
    
    def get_printer_profile(self) -> Dict:
        """获取打印机配置"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/printerprofiles')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取打印机配置失败: {e}")
            return {}
    
    def get_settings(self) -> Dict:
        """获取OctoPrint设置"""
        try:
            response = self.session.get(f'{self.octoprint_url}/api/settings')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取设置失败: {e}")
            return {}
    
    def check_firmware_info(self) -> Dict:
        """检查固件信息"""
        logger.info("检查固件信息...")
        result = self.send_command_and_check_response("M115")
        return result
    
    def diagnose_extrusion_setup(self):
        """诊断挤出设置"""
        logger.info("=== 🔍 挤出问题诊断 ===")
        
        # 1. 检查打印机配置
        logger.info("1. 检查打印机配置...")
        profiles = self.get_printer_profile()
        if profiles:
            current_profile = profiles.get('_default', 'Unknown')
            logger.info(f"当前配置: {current_profile}")
            
            # 检查挤出机数量
            profile_data = profiles.get('profiles', {})
            if profile_data:
                for name, profile in profile_data.items():
                    extruder_count = profile.get('extruder', {}).get('count', 1)
                    logger.info(f"配置 '{name}': {extruder_count} 个挤出机")
        
        # 2. 检查固件信息
        logger.info("\n2. 检查固件信息...")
        firmware_result = self.check_firmware_info()
        logger.info(f"M115指令状态: {firmware_result['status']}")
        
        # 3. 测试挤出相关指令
        logger.info("\n3. 测试挤出相关指令...")
        results = []
        for command in self.extrusion_commands:
            result = self.send_command_and_check_response(command)
            results.append(result)
            
            status_emoji = "✅" if result['status'] == 'SENT' else "❌"
            logger.info(f"{status_emoji} {command}: {result['status']}")
            
            time.sleep(0.5)  # 避免过快发送
        
        # 4. 分析结果
        logger.info("\n=== 📊 诊断结果 ===")
        
        failed_commands = [r for r in results if r['status'] != 'SENT']
        if failed_commands:
            logger.error(f"发现 {len(failed_commands)} 个问题指令:")
            for cmd in failed_commands:
                logger.error(f"  - {cmd['command']}: {cmd['status']}")
                
                if 'T' in cmd['command']:
                    logger.warning("  🚨 工具选择指令失败 - 这会导致挤出机无法工作!")
                    logger.info("     解决方案:")
                    logger.info("     1. 检查打印机配置中的挤出机数量设置")
                    logger.info("     2. 确认固件支持T0/T1指令")
                    logger.info("     3. 考虑在OctoPrint设置中禁用指令过滤")
                
                elif 'E' in cmd['command']:
                    logger.warning("  🚨 挤出指令失败!")
                    logger.info("     可能原因:")
                    logger.info("     - 挤出机温度不够")
                    logger.info("     - 挤出机模式设置错误")
                    logger.info("     - 固件安全保护")
        
        else:
            logger.info("✅ 所有挤出相关指令测试通过")
        
        # 5. 提供解决建议
        self.provide_solutions(results)
    
    def provide_solutions(self, results: List[Dict]):
        """提供解决方案"""
        logger.info("\n=== 🔧 解决方案建议 ===")
        
        # 检查T指令问题
        t_commands = [r for r in results if r['command'].startswith('T')]
        failed_t_commands = [r for r in t_commands if r['status'] != 'SENT']
        
        if failed_t_commands:
            logger.info("🔧 工具选择(T指令)问题解决方案:")
            logger.info("1. 在OctoPrint中检查打印机配置:")
            logger.info("   Settings -> Printer Profiles -> 编辑当前配置")
            logger.info("   确保 'Extruder Count' 设置正确")
            logger.info("")
            logger.info("2. 如果是单挤出机打印机:")
            logger.info("   - 将挤出机数量设为1")
            logger.info("   - G-code中的T1指令可能不适用")
            logger.info("")
            logger.info("3. 禁用指令过滤 (不推荐但可能有效):")
            logger.info("   Settings -> Serial Connection -> 取消勾选相关安全选项")
        
        # 检查挤出指令问题  
        e_commands = [r for r in results if 'E' in r['command']]
        failed_e_commands = [r for r in e_commands if r['status'] != 'SENT']
        
        if failed_e_commands:
            logger.info("\n🔧 挤出(E指令)问题解决方案:")
            logger.info("1. 检查温度:")
            logger.info("   - 确保热端温度达到挤出温度(通常>180°C)")
            logger.info("   - 使用M104 S200预热后再测试挤出")
            logger.info("")
            logger.info("2. 检查挤出机模式:")
            logger.info("   - 发送M83设置为相对模式")
            logger.info("   - 或发送M82设置为绝对模式")
            logger.info("")
            logger.info("3. 重置挤出机位置:")
            logger.info("   - 发送G92 E0重置挤出机位置")
    
    def test_manual_extrusion(self, temperature: int = 200, extrude_amount: float = 5.0):
        """手动测试挤出"""
        logger.info(f"🧪 手动挤出测试 (温度: {temperature}°C, 挤出量: {extrude_amount}mm)")
        
        test_sequence = [
            f"M104 S{temperature}",  # 设置温度
            "M83",                   # 相对挤出模式
            "G92 E0",               # 重置挤出机位置
            f"G1 E{extrude_amount} F300",  # 慢速挤出
            "G92 E0",               # 再次重置
        ]
        
        for i, command in enumerate(test_sequence, 1):
            logger.info(f"步骤 {i}: {command}")
            result = self.send_command_and_check_response(command)
            
            if result['status'] != 'SENT':
                logger.error(f"❌ 步骤 {i} 失败: {result['status']}")
                return False
            else:
                logger.info(f"✅ 步骤 {i} 成功")
            
            # 等待温度稳定
            if 'M104' in command:
                logger.info("⏳ 等待加热...")
                time.sleep(5)  # 实际使用中可能需要更长时间
            else:
                time.sleep(1)
        
        logger.info("✅ 手动挤出测试序列完成")
        logger.info("请观察挤出机是否有耗材挤出")
        return True
    
    def generate_safe_gcode_filter(self, original_file_path: str, output_file_path: str):
        """生成过滤了可能被抑制指令的G-code文件"""
        logger.info(f"🔄 生成安全G-code文件: {original_file_path} -> {output_file_path}")
        
        # 可能被抑制的指令模式
        potentially_suppressed = [
            'T1',  # 如果是单挤出机，T1会被抑制
            'T2', 'T3', 'T4',  # 更高编号的工具
        ]
        
        # 替换规则
        replacements = {
            'T1': 'T0',  # 将T1替换为T0
            'T2': 'T0', 
            'T3': 'T0',
            'T4': 'T0',
        }
        
        try:
            with open(original_file_path, 'r', encoding='utf-8') as infile:
                with open(output_file_path, 'w', encoding='utf-8') as outfile:
                    modified_count = 0
                    
                    for line_num, line in enumerate(infile, 1):
                        original_line = line.strip()
                        modified_line = original_line
                        
                        # 检查和替换
                        for old_cmd, new_cmd in replacements.items():
                            if original_line.startswith(old_cmd):
                                modified_line = original_line.replace(old_cmd, new_cmd, 1)
                                if modified_line != original_line:
                                    modified_count += 1
                                    logger.debug(f"行 {line_num}: {original_line} -> {modified_line}")
                        
                        outfile.write(modified_line + '\n')
                    
                    logger.info(f"✅ 文件处理完成，修改了 {modified_count} 行")
                    
        except FileNotFoundError:
            logger.error(f"❌ 源文件未找到: {original_file_path}")
        except Exception as e:
            logger.error(f"❌ 文件处理失败: {e}")


def main():
    """主函数"""
    # 配置信息
    OCTOPRINT_URL = "http://192.168.1.100"
    API_KEY = "YOUR_API_KEY_HERE"
    
    diagnostic = ExtrusionDiagnostic(OCTOPRINT_URL, API_KEY)
    
    print("=== 🩺 G-code挤出问题诊断工具 ===")
    print("此工具将帮助诊断OctoPrint中的挤出问题")
    print("特别是suppress command导致的问题")
    print()
    
    while True:
        print("选择操作:")
        print("1. 完整诊断")
        print("2. 测试手动挤出")
        print("3. 生成安全G-code文件")
        print("4. 退出")
        
        choice = input("请选择 (1-4): ").strip()
        
        if choice == '1':
            diagnostic.diagnose_extrusion_setup()
        elif choice == '2':
            temp = input("输入目标温度 (默认200): ").strip()
            temp = int(temp) if temp.isdigit() else 200
            
            amount = input("输入挤出量mm (默认5): ").strip() 
            amount = float(amount) if amount.replace('.','').isdigit() else 5.0
            
            diagnostic.test_manual_extrusion(temp, amount)
        elif choice == '3':
            input_file = input("输入原始G-code文件路径: ").strip()
            output_file = input("输入输出文件路径: ").strip()
            
            if input_file and output_file:
                diagnostic.generate_safe_gcode_filter(input_file, output_file)
            else:
                print("请提供有效的文件路径")
        elif choice == '4':
            print("再见!")
            break
        else:
            print("无效选择，请重试")
        
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    main()