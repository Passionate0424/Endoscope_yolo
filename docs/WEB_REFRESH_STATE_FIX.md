# 网页刷新状态恢复和Stream挂起问题修复

## 问题描述

用户报告了三个主要问题：

1. **网页刷新后状态恢复初始状态**：即使刷新前摄像头处于开启状态，刷新后也会显示为停止
2. **Stream挂起**：摄像头开启后stream请求会挂起（Pending状态），看不到推送的图片
3. **Status数据不更新**：网页端的FPS、处理帧数等统计数据没有更新

## 根本原因分析

### 1. 网页刷新状态恢复问题
- **原因**：`app.js` 在 `init()` 时没有从服务器获取当前状态
- **影响**：每次刷新页面，前端状态都重置为初始值（`cameraRunning = false`）
- **位置**：`k230_onboard_project/static/app.js`

### 2. Stream挂起问题
- **原因**：
  - MJPEG流处理函数 `http_handle_mjpeg_stream` 没有超时机制
  - 如果 `frame_buffer` 没有有效帧，会一直等待
  - Python层可能没有及时推送帧到C层
- **影响**：浏览器请求 `/stream` 后会一直挂起，看不到视频
- **位置**：`rtsmart_userapp/src/http_handler.c`

### 3. Status数据不更新问题
- **原因**：
  - Python层状态同步频率可能太低
  - 网页端轮询间隔太长
  - 数据解析可能有问题（布尔值vs字符串）
- **影响**：FPS、处理帧数等统计数据不更新
- **位置**：`k230_onboard_project/main_rtsmart.py`, `k230_onboard_project/static/app.js`

## 修复方案

### 1. 网页端状态恢复修复 (`k230_onboard_project/static/app.js`)

#### 1.1 添加 `loadInitialState()` 方法
- 在 `init()` 时调用，从 `/api/status` 获取当前状态
- 恢复摄像头状态、检测状态、置信度阈值
- 恢复视频流显示
- 更新统计数据

```javascript
async loadInitialState() {
    const result = await this.apiCall('/api/status');
    if (result.success && result.data) {
        // 恢复摄像头状态
        const cameraRunning = data.camera && (
            data.camera.running === true || 
            data.camera.running === 'true' || 
            data.camera.running === 1
        );
        if (cameraRunning) {
            this.updateVideoStream();
        }
        // ... 其他状态恢复
    }
}
```

#### 1.2 改进 `updateStats()` 方法
- 正确处理布尔值和字符串格式的状态值
- 同步摄像头和检测状态，防止状态不同步
- 添加错误处理和日志
- 降低轮询间隔从5秒到2秒

#### 1.3 改进 `updateVideoStream()` 方法
- 添加更好的错误处理和重试机制
- 防止无限重连
- 添加超时保护

### 2. C层MJPEG流超时修复 (`rtsmart_userapp/src/http_handler.c`)

#### 2.1 添加超时机制
- 首次连接等待最多5秒
- 已有帧后，如果超过3秒没有新帧，关闭流
- 添加详细的日志输出

```c
int http_handle_mjpeg_stream(int client_fd)
{
    rt_uint32_t stream_start_ms = http_get_tick_ms();
    rt_uint32_t last_frame_time_ms = 0;
    
    while (1) {
        rt_uint32_t now = http_get_tick_ms();
        
        // 首次连接，等待最多5秒
        if (frame_count == 0 && (now - stream_start_ms > 5000)) {
            rt_kprintf("[MJPEG] Timeout: No frames received in 5s\n");
            break;
        }
        
        // 已有帧后，如果超过3秒没有新帧，关闭流
        if (last_frame_time_ms > 0 && (now - last_frame_time_ms) > 3000) {
            rt_kprintf("[MJPEG] Timeout: No new frames for 3s\n");
            break;
        }
        
        // ... 获取和发送帧
    }
}
```

### 3. Python层状态同步修复 (`k230_onboard_project/main_rtsmart.py`)

#### 3.1 提高状态同步频率
- 主循环sleep时间从1秒降低到0.5秒
- 每次循环都更新状态到C层
- 收到控制命令后立即同步状态

```python
while True:
    time.sleep(0.5)  # 降低到0.5秒，提高响应速度
    
    # 处理控制命令
    control = web_adapter.pull_control()
    if control:
        # 处理命令后立即同步状态
        web_adapter.update_runtime(...)
    
    # 始终同步状态到C层
    web_adapter.update_runtime(
        yolo_controller.camera_running,
        yolo_controller.detection_enabled,
        yolo_controller.confidence_threshold,
    )
    
    # 始终更新统计数据
    web_adapter.update_stats_remote(
        total_frames,
        total_detections,
        fps,
    )
```

#### 3.2 启动时立即同步状态
- 启动摄像头后等待0.5秒让YOLO线程初始化
- 立即同步状态到C层，确保网页刷新后能读取到正确状态

## 修改的文件列表

1. **k230_onboard_project/static/app.js**
   - 添加 `loadInitialState()` 方法
   - 改进 `updateStats()` 方法
   - 改进 `updateVideoStream()` 方法
   - 降低轮询间隔到2秒
   - 添加更好的错误处理和日志

2. **rtsmart_userapp/src/http_handler.c**
   - 在 `http_handle_mjpeg_stream()` 中添加超时机制
   - 添加详细的日志输出
   - 改进错误处理

3. **k230_onboard_project/main_rtsmart.py**
   - 提高状态同步频率（0.5秒）
   - 启动时立即同步状态
   - 收到控制命令后立即同步状态
   - 每次循环都更新状态和统计数据

## 测试建议

1. **测试网页刷新状态恢复**：
   - 启动系统，在网页端点击"启动摄像头"
   - 刷新网页，应该能看到摄像头仍在运行
   - 检查视频流是否正常显示

2. **测试Stream挂起**：
   - 启动摄像头
   - 打开浏览器开发者工具，查看Network标签
   - `/stream` 请求不应该一直挂起
   - 如果5秒内没有帧，应该关闭连接

3. **测试Status更新**：
   - 启动摄像头后，观察FPS、处理帧数等统计数据
   - 应该每2秒更新一次
   - 数据应该与实际运行情况一致

## 注意事项

1. **C层需要重新编译**：修改了 `http_handler.c`，需要重新编译固件
2. **Python层无需重新编译**：修改的是Python文件，直接替换即可
3. **网页端需要刷新缓存**：修改了 `app.js`，浏览器可能需要强制刷新（Ctrl+F5）

## 架构说明

修复涉及三个层次：

1. **C层（RT-Smart）**：HTTP服务器、MJPEG流处理、状态管理
2. **Python层（MicroPython）**：YOLO检测、帧推送、状态同步
3. **网页端（JavaScript）**：UI控制、状态显示、数据更新

数据流向：
- **控制流**：网页 → C层 → Python层
- **状态流**：Python层 → C层 → 网页
- **视频流**：Python层 → C层frame_buffer → 网页MJPEG流
- **统计流**：Python层 → C层 → 网页

## 后续优化建议

1. 考虑使用WebSocket替代轮询，提高实时性
2. 添加连接心跳机制，检测客户端是否在线
3. 优化frame_buffer大小和推送频率
4. 添加更详细的错误日志和调试信息

---

## 2025-11-22 更新：进一步修复状态同步问题

### 新发现的问题

1. **页面刷新后状态重置**：
   - 点击启动摄像头后，刷新页面，状态会重置
   - 原因是状态同步时机不对，或者前端状态恢复逻辑有问题

2. **FPS等状态信息不更新**：
   - 统计数据虽然更新了，但前端显示不正确
   - 可能是数据解析问题，或者值为0时不显示

### 修复内容

#### 1. 前端状态恢复优化 (`k230_onboard_project/static/app.js`)

- **修复 `loadInitialState()`**：
  - 使用 `actual` 状态（`running`/`enabled`）而不是 `desired` 状态
  - 确保即使值为0也正确显示统计数据
  - 改进布尔值判断逻辑，支持多种格式（true/false/1/0/'true'/'false'）

- **修复 `updateStats()`**：
  - 确保FPS等统计数据即使为0也显示
  - 改进数据解析，处理 `undefined` 和 `null` 值
  - 使用 `actual` 状态同步摄像头和检测状态

- **修复 `startCamera()`**：
  - 不立即设置本地状态，而是等待服务器状态同步
  - 添加定期检查机制，直到状态同步成功
  - 提供更好的用户反馈

#### 2. Python层状态同步优化 (`k230_onboard_project/main_rtsmart.py`)

- **启动摄像头后立即同步状态**：
  - 在 `start_camera()` 调用后立即同步状态到C层
  - 即使YOLO线程还在初始化，也先同步"启动中"状态
  - 确保前端刷新后能立即看到状态变化

- **优化状态同步逻辑**：
  - 每次循环都同步状态，确保一致性
  - 处理控制命令后立即同步状态
  - 添加调试日志

#### 3. FPS计算优化 (`k230_onboard_project/yolo_controller.py`)

- **使用滑动窗口计算FPS**：
  - 每5秒重置一次FPS计算，避免初始化时间影响
  - 保持FPS计算的准确性
  - 确保统计数据正确传递

### 修改的文件

1. **k230_onboard_project/static/app.js**
   - 修复 `loadInitialState()` 状态恢复逻辑
   - 修复 `updateStats()` 数据解析和显示
   - 修复 `startCamera()` 状态同步机制

2. **k230_onboard_project/main_rtsmart.py**
   - 优化启动摄像头后的状态同步
   - 改进控制命令处理后的状态同步
   - 添加调试日志

3. **k230_onboard_project/yolo_controller.py**
   - 优化FPS计算，使用滑动窗口
   - 确保统计数据正确更新

### 测试验证

修复后应该验证：

1. **状态持久化**：
   - 启动摄像头后刷新页面，状态应该保持
   - 停止摄像头后刷新页面，状态应该保持

2. **统计数据更新**：
   - FPS应该实时更新（即使为0也显示）
   - 处理帧数和检测数应该正确显示
   - 数据应该每2秒更新一次

3. **状态同步**：
   - 点击启动/停止按钮后，状态应该立即更新
   - 刷新页面后，状态应该与服务器一致

