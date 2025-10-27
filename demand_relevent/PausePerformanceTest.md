
## 主要特点

### 1. **精确集成你的API**
- 使用 `sender.start_file_print()` 启动打印
- 使用 `sender.pause()` 和 `sender.resume()` 测量耗时
- 使用 `sender.get_progress()` 获取当前行数
- 使用 `sender.get_progress()` 检查打印状态

### 2. **三个测试维度**
```python
# 维度1: 同一文件 + 不同行数
pause_lines=[500, 1000, 2000, 3000]

# 维度2: 同一文件 + 不同进度百分比
pause_percents=[10, 20, 30, 50, 80]

# 维度3: 不同文件 + 相同行数
files=['file1.gcode', 'file2.gcode', 'file3.gcode']
pause_line=2000
```

### 3. **精确性能测量**
- 使用 `time.perf_counter()` 高精度计时
- 单位：**毫秒(ms)** 便于观察
- 计算：平均值、标准差、最小值、最大值

### 4. **完整的输出**
- **JSON报告** - 机器可读，用于进一步分析
- **CSV导出** - 可在Excel中打开分析
- **控制台摘要** - 实时查看结果

## 使用步骤

### 第一步：准备测试文件
```bash
# 你需要3-5个不同大小的G-code文件：
# - 小文件：500-1000行
# - 中文件：2000-5000行
# - 大文件：10000+行
```

### 第二步：配置并运行
```python
from gcode_sender import GCodeSender  # 你的模块
from pause_test_framework import PausePerformanceTest

# 初始化
sender = GCodeSender("http://octopi.local", "your_api_key")
tester = PausePerformanceTest(sender)

# 配置
tester.test_config['repeat_count'] = 3  # 每个用例重复3次
tester.test_config['wait_after_pause'] = 1.0  # 暂停后等待1秒

# 生成测试用例
testcases = []
testcases += tester.generate_dimension1_testcases('test.gcode', [2000, 3000])
testcases += tester.generate_dimension2_testcases('test.gcode', [20, 30, 50])
testcases += tester.generate_dimension3_testcases(['file1.gcode', 'file2.gcode'], 2000)

# 执行
tester.run_all_tests(testcases)

# 生成报告
tester.generate_report()
tester.export_csv()
tester.print_summary()
```

### 第三步：分析结果
报告会显示：
- 暂停耗时趋势（是否与行数/文件大小相关）
- 恢复耗时是否稳定
- 不同阶段的性能差异

## 注意事项

 **重要**：
1. **打印机要就绪** - 确保OctoPrint连接正常
2. **充足的测试时间** - 每个测试需要几分钟
3. **避免中断** - 测试期间不要手动操作打印机
4. **温度管理** - 如果需要测试加热过程，调整 `wait_after_pause`

