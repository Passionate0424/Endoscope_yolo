# 内窥镜息肉检测平台 - K230部署说明

## 📋 功能概述

这是一个基于庐山派K230开发板的内窥镜息肉检测平台，提供以下功能：

- ✅ **视频流控制**：通过Web界面启动/停止内窥镜视频流
- ✅ **YOLO检测控制**：动态启用/禁用AI息肉检测
- ✅ **实时视频预览**：在Web浏览器中实时查看内窥镜画面
- ✅ **自动图像记录**：检测到息肉时自动保存图像
- ✅ **检测记录查看**：Web界面显示历史检测记录

## 🏗️ 系统架构

```
K230设备
├── HTTP服务器 (端口80)
│   ├── Web界面 (HTML/JS)
│   ├── REST API
│   └── MJPEG视频流
├── 视频采集模块 (PipeLine)
├── YOLO检测模块 (YOLOv5)
└── 图像存储模块
```

## 📁 文件结构

```
k230_onboard_project/
├── main.py           # 主程序（集成HTTP服务器和YOLO检测）
├── http_server.py    # HTTP服务器模块
└── README.md         # 本文件
```

## 🚀 使用步骤

### 1. 准备模型文件

确保以下文件已部署到K230设备：

- `/data/model.kmodel` - YOLOv5模型文件（已转换为kmodel格式）
- `main.py` 和 `http_server.py` - 程序文件

### 2. 运行程序

在K230设备上运行：

```bash
python main.py
```

程序启动后会显示：

```
=== 内窥镜息肉检测平台启动 ===
HTTP服务器: http://192.168.x.x:80
检测图像保存目录: /data/detections
等待Web界面连接...
```

### 3. 访问Web界面

在同一局域网内的设备（PC、手机、平板）上打开浏览器，访问：

```
http://[K230设备IP地址]
```

例如：`http://192.168.1.100`

## 🎮 Web界面功能

### 控制面板

- **启动视频**：开始采集内窥镜视频流
- **停止视频**：停止视频采集
- **启用检测**：开启YOLO息肉检测（需要先启动视频）
- **禁用检测**：关闭息肉检测

### 状态显示

- 视频状态：显示视频流是否运行中
- 检测状态：显示AI检测是否启用
- 检测次数：累计检测到息肉的次数

### 检测记录

- 实时显示检测历史
- 显示检测时间和置信度
- 点击查看详细信息（未来可扩展）

## 📡 API接口

### GET /api/status

获取系统状态

**响应示例：**
```json
{
  "video_enabled": true,
  "detection_enabled": true,
  "detection_count": 5,
  "timestamp": 1704067200.0
}
```

### POST /api/video/start

启动视频流

**响应示例：**
```json
{
  "status": "ok",
  "message": "Video started"
}
```

### POST /api/video/stop

停止视频流

### POST /api/detection/enable

启用YOLO检测

### POST /api/detection/disable

禁用YOLO检测

### GET /api/video/stream

获取MJPEG视频流（用于Web页面显示）

### GET /api/detections

获取检测记录列表

**响应示例：**
```json
[
  {
    "id": 1,
    "timestamp": 1704067200.0,
    "results": [
      {
        "x1": 100,
        "y1": 100,
        "x2": 200,
        "y2": 200,
        "confidence": 0.85,
        "class_id": 0,
        "class_name": "polyp"
      }
    ]
  }
]
```

## ⚙️ 配置参数

在 `main.py` 中可以修改以下配置：

```python
KMODEL_PATH = "/data/model.kmodel"    # 模型文件路径
LABELS = ["polyp"]                     # 类别标签
MODEL_INPUT_SIZE = [640, 640]         # 模型输入尺寸
DISPLAY_MODE = "lcd"                  # 显示模式: lcd/hdmi/lt9611/st7701/hx8399
RGB888P_SIZE = [640, 360]             # 相机输入尺寸
CONF_THRESHOLD = 0.35                 # 置信度阈值
NMS_THRESHOLD = 0.45                  # NMS阈值
HTTP_PORT = 80                        # HTTP服务器端口
DETECTIONS_DIR = "/data/detections"   # 检测图像保存目录
```

## 💾 图像存储

检测到息肉时，图像会保存在 `/data/detections/` 目录下，文件名格式：

```
polyp_[时间戳]_[置信度百分比].jpg
```

例如：`polyp_1704067200123_85.jpg`

## ⚠️ 注意事项

1. **网络连接**：
   - **WiFi模式（推荐）**：默认使用WiFi连接
     - 修改 `WIFI_SSID` 和 `WIFI_PASSWORD` 为你的WiFi信息
     - 确保WiFi是2.4G频段（不支持5G）
     - 如果路由器是双频合一，请先分离2.4G信号
   - **以太网模式**：设置 `USE_WIFI = False` 使用有线网络
     - 确保K230设备已连接网线
     - 默认使用DHCP自动获取IP
     - 如需使用静态IP，修改 `USE_STATIC_IP = True` 并配置IP地址
   - 程序会自动尝试连接，WiFi和以太网可以相互作为备选

2. **端口占用**：确保80端口未被占用（可在代码中修改HTTP_PORT）

3. **存储空间**：检测图像会占用存储空间，定期清理旧文件

4. **性能优化**：
   - 视频未启用时，主循环会休眠以节省资源
   - 每100帧自动进行垃圾回收
   - MJPEG视频流会自动去重相同帧

5. **网络初始化**：
   - 程序启动时会自动初始化网络接口
   - 如果网络初始化失败，检查网线连接
   - 程序会尝试多种网络初始化方式以兼容不同硬件配置

## 🔧 故障排除

### 问题1：OSError: no available NIC 或网络初始化失败

**原因**：网络接口未初始化或连接失败

**解决**：
1. **WiFi模式**：
   - 检查 `WIFI_SSID` 和 `WIFI_PASSWORD` 是否正确
   - 确保WiFi是2.4G频段（不支持5G频段）
   - 检查路由器是否正常工作
   - 如果路由器是双频合一，请分离2.4G信号
   
2. **以太网模式**：
   - 确保K230设备已连接网线
   - 检查网线连接是否正常
   - 检查路由器DHCP是否开启
   
3. **通用排查**：
   - 查看控制台输出的详细错误信息
   - 程序会自动尝试WiFi和以太网作为备选
   - 参考[庐山派WiFi文档](https://wiki.lckfb.com/zh-hans/lushan-pi-k230/network/wifi.html)
   - 参考[CanMV网络例程](https://www.kendryte.com/k230_canmv/zh/main/zh/example/network/index.html)

### 问题2：HTTP服务器启动失败

**原因**：端口被占用或网络未初始化

**解决**：
- 确保网络初始化成功（查看控制台输出）
- 修改 `HTTP_PORT` 为其他端口（如8080）
- 检查是否有其他程序占用端口

### 问题3：视频流无法显示

**原因**：图像格式转换问题或网络连接问题

**解决**：
- 检查K230的图像API是否支持 `to_jpeg()` 方法
- 检查网络连接
- 查看控制台错误信息

### 问题4：检测图像保存失败

**原因**：目录权限或存储空间不足

**解决**：
- 确保 `/data/detections` 目录有写入权限
- 检查存储空间
- 确认图像保存方法是否适配当前环境

## 📚 参考资料

- [庐山派K230使用手册](https://wiki.lckfb.com/zh-hans/lushan-pi-k230/)
- [YOLO模块API文档](https://wiki.lckfb.com/zh-hans/lushan-pi-k230/api/aidemo/yolo_module_api.html)

## 🔄 版本历史

- **v1.0** (2024-01-XX)
  - 初始版本
  - 支持视频流控制和YOLO检测控制
  - 实现息肉自动记录和Web界面显示

