# 内窥镜检测Web平台

基于K230的实时息肉检测与监控系统

## 功能特性

- 🎥 **实时视频流**: MJPEG格式，支持浏览器直接访问
- 🤖 **YOLO检测**: 实时息肉检测，可调整置信度阈值
- 💾 **自动保存**: 检测到息肉自动保存图像和元数据
- 📊 **实时统计**: FPS、检测数量、处理帧数等
- 🎛️ **远程控制**: Web界面控制摄像头和检测开关
- 📱 **响应式设计**: 支持PC和移动设备访问

## 系统架构

```
内窥镜检测平台
├── web_main.py          # 主程序入口
├── web_server.py        # HTTP服务器
├── stream_handler.py    # MJPEG视频流
├── yolo_controller.py   # YOLO检测控制
├── detection_manager.py # 检测记录管理
├── config.json          # 配置文件
└── static/              # Web前端
    ├── index.html
    └── app.js
```

## 安装部署

### 1. 准备工作

确保K230已安装以下依赖：
- CanMV固件
- YOLO模型文件（model.kmodel）
- libs库（PipeLine, YOLO等）

### 2. 文件部署

将以下文件上传到K230的data分区（28GB空间）：

```
/data/
├── web_main.py
├── web_server.py
├── stream_handler.py
├── yolo_controller.py
├── detection_manager.py
├── wifi_config.py        # WiFi配置模块
├── config.json
├── model.kmodel
├── detections/           # 检测记录保存目录（自动创建）
└── static/               # Web前端文件目录
    ├── index.html
    └── app.js
```

### 3. 配置WiFi

编辑 `wifi_config.py` 文件，修改WiFi信息：

```python
# WiFi配置
WIFI_SSID = "你的WiFi名称"
WIFI_PASSWORD = "你的WiFi密码"
```

### 4. 启动服务

在K230上运行：

```python
python web_main.py
```

程序会自动：
1. 连接到WiFi网络
2. 显示IP地址
3. 启动HTTP服务器

或者通过CanMV IDE运行。

### 5. 访问平台

在浏览器中访问：

```
http://<K230的IP地址>:8080
```

## API文档

### 摄像头控制

**启动摄像头**
- URL: `/api/camera/start`
- Method: `POST`
- Response:
```json
{
    "success": true,
    "message": "摄像头已启动"
}
```

**停止摄像头**
- URL: `/api/camera/stop`
- Method: `POST`
- Response:
```json
{
    "success": true,
    "message": "摄像头已停止"
}
```

### 检测控制

**启用检测**
- URL: `/api/detection/enable`
- Method: `POST`
- Response:
```json
{
    "success": true,
    "message": "检测已启用"
}
```

**禁用检测**
- URL: `/api/detection/disable`
- Method: `POST`
- Response:
```json
{
    "success": true,
    "message": "检测已禁用"
}
```

**设置置信度阈值**
- URL: `/api/config/confidence`
- Method: `POST`
- Body:
```json
{
    "value": 0.65
}
```
- Response:
```json
{
    "success": true,
    "message": "置信度已设置为 0.65"
}
```

### 状态查询

**获取运行状态**
- URL: `/api/status`
- Method: `GET`
- Response:
```json
{
    "success": true,
    "data": {
        "camera_running": true,
        "detection_enabled": true,
        "yolo_stats": {
            "total_frames": 1234,
            "total_detections": 56,
            "fps": 15.2
        },
        "detection_stats": {
            "total_count": 56,
            "total_size": 12345678,
            "avg_confidence": 0.78
        }
    }
}
```

### 检测记录

**获取记录列表**
- URL: `/api/records?limit=20&offset=0`
- Method: `GET`
- Response:
```json
{
    "success": true,
    "data": [
        {
            "id": 1712345678900,
            "filename": "detection_1712345678900.jpg",
            "timestamp": 1712345678900,
            "time_str": "2024-04-06 12:34:56",
            "bbox": [100, 200, 150, 120],
            "confidence": 0.85,
            "size": 45678
        }
    ]
}
```

**删除记录**
- URL: `/api/records/{id}`
- Method: `DELETE`
- Response:
```json
{
    "success": true,
    "message": "记录已删除"
}
```

**清空所有记录**
- URL: `/api/records/clear`
- Method: `POST`
- Response:
```json
{
    "success": true,
    "message": "所有记录已清空"
}
```

### 视频流

**MJPEG视频流**
- URL: `/stream`
- Method: `GET`
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- 说明: 返回MJPEG格式的视频流，可直接在`<img>`标签中使用

## 配置说明

编辑`config.json`文件：

```json
{
    "server": {
        "host": "0.0.0.0",    // 服务器地址
        "port": 8080           // 服务器端口
    },
    "camera": {
        "width": 1920,         // 摄像头宽度
        "height": 1080,        // 摄像头高度
        "fps": 30              // 摄像头帧率
    },
    "yolo": {
        "model_path": "/data/model.kmodel",    // 模型路径（使用/data分区）
        "confidence_threshold": 0.5,            // 置信度阈值
        "iou_threshold": 0.45                   // IOU阈值
    },
    "stream": {
        "jpeg_quality": 75,    // JPEG质量（1-95）
        "max_fps": 15          // 视频流最大帧率
    },
    "detection": {
        "save_dir": "/data/detections",  // 保存目录（/data有28GB空间）
        "max_records": 100,              // 最大记录数
        "auto_save": true                // 自动保存
    }
}
```

## 使用说明

### 基本流程

1. **启动平台**: 运行`web_main.py`
2. **打开Web界面**: 浏览器访问平台地址
3. **启动摄像头**: 点击"启动摄像头"按钮
4. **启用检测**: 点击"启用检测"按钮
5. **查看实时视频**: 视频流自动显示
6. **查看检测结果**: 检测到息肉后自动保存并显示在记录列表

### 高级功能

- **调整置信度**: 拖动滑块调整检测灵敏度
- **下载检测图像**: 点击记录的"下载"按钮
- **删除记录**: 点击"删除"按钮移除单条记录
- **批量清空**: 点击"清空所有"按钮删除全部记录

## 故障排除

### 无法访问Web界面
- 检查K230的WiFi是否连接成功
- 确认K230显示的IP地址
- 确保电脑和K230在同一WiFi网络
- 验证IP地址和端口（默认8080）
- 检查防火墙设置

### 视频流不显示
- 确认摄像头已启动
- 检查浏览器是否支持MJPEG
- 查看控制台错误信息

### 检测不工作
- 验证模型文件路径
- 检查模型文件完整性
- 确认检测已启用

### 保存失败
- 检查/data分区空间（应有28GB可用）
- 验证保存目录权限
- 查看系统日志

## 性能优化

- **降低视频流帧率**: 修改`max_fps`参数
- **降低JPEG质量**: 修改`jpeg_quality`参数
- **限制检测记录数**: 修改`max_records`参数
- **关闭屏幕显示**: 注释`pl.show_image()`代码

## 开发扩展

### 添加新API

在`web_main.py`的`register_routes()`方法中添加：

```python
@self.server.route('/api/custom')
def custom_api(params):
    # 自定义逻辑
    return self.server.json_response({
        'success': True,
        'data': 'custom data'
    })
```

### 修改前端

编辑`static/index.html`和`static/app.js`文件。

## 技术支持

- 项目地址: [GitHub Repository]
- 问题反馈: [Issues]
- 文档: [Wiki]

## 许可证

MIT License

## 更新日志

### v1.0.0 (2024-04-06)
- ✅ 实现HTTP服务器
- ✅ 实现MJPEG视频流
- ✅ 实现YOLO检测控制
- ✅ 实现检测记录管理
- ✅ 实现Web前端界面
- ✅ 完整API文档

## 致谢

感谢K230团队提供优秀的AI平台和完善的API文档。
