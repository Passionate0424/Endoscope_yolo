"""
轻量级HTTP服务器模块
用于K230 CanMV环境，提供Web API和MJPEG视频流
"""
import socket
import gc
import json
import time

# HTTP响应状态码
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405

class HTTPServer:
    def __init__(self, port=80):
        self.port = port
        self.socket = None
        self.running = False
        
        # 共享状态（由主程序控制）
        self.video_enabled = False
        self.detection_enabled = False
        self.last_frame = None
        self.detection_results = []
        self.detection_count = 0
        
    def start(self):
        """启动HTTP服务器"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(5)
            try:
                self.socket.setblocking(False)
            except AttributeError:
                pass
            self.running = True
            print(f"HTTP Server started on port {self.port}")
        except Exception as e:
            print(f"Failed to start HTTP server: {e}")
            self.running = False
            
    def stop(self):
        """停止HTTP服务器"""
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
            print("HTTP Server stopped")
            
    def update_frame(self, frame):
        """更新当前帧（由主循环调用）"""
        self.last_frame = frame
        
    def add_detection(self, frame, results):
        """添加检测记录（检测到息肉时调用）"""
        self.detection_count += 1
        timestamp = time.time()
        self.detection_results.append({
            'id': self.detection_count,
            'timestamp': timestamp,
            'results': results
        })
        # 保持最近50条记录
        if len(self.detection_results) > 50:
            self.detection_results.pop(0)
            
    def parse_request(self, data):
        """解析HTTP请求"""
        try:
            lines = data.decode('utf-8').split('\r\n')
            if not lines:
                return None, None
                
            # 解析请求行
            request_line = lines[0]
            parts = request_line.split(' ')
            if len(parts) < 2:
                return None, None
                
            method = parts[0]
            path = parts[1]
            
            # 解析查询参数
            if '?' in path:
                path, query = path.split('?', 1)
            else:
                query = ''
                
            return method, path
        except Exception as e:
            print(f"Parse request error: {e}")
            return None, None
            
    def send_response(self, client, status_code, content_type, body):
        """发送HTTP响应"""
        status_text = "OK" if status_code == HTTP_OK else "Not Found"
        
        # 计算body长度
        if isinstance(body, bytes):
            body_len = len(body)
        else:
            body_len = len(body.encode('utf-8'))
        
        response = f"HTTP/1.1 {status_code} {status_text}\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += f"Content-Length: {body_len}\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"
        response += "Connection: close\r\n"
        response += "\r\n"
        
        try:
            # 发送响应头
            response_bytes = response.encode('utf-8')
            sent = client.send(response_bytes)
            if sent < len(response_bytes):
                # 可能需要多次发送
                client.send(response_bytes[sent:])
            
            # 发送body
            if isinstance(body, bytes):
                total_sent = 0
                while total_sent < len(body):
                    sent = client.send(body[total_sent:])
                    if sent == 0:
                        break
                    total_sent += sent
            else:
                body_bytes = body.encode('utf-8')
                total_sent = 0
                while total_sent < len(body_bytes):
                    sent = client.send(body_bytes[total_sent:])
                    if sent == 0:
                        break
                    total_sent += sent
            
            print(f"Response sent: {status_code}, size: {body_len}")  # 调试信息
        except Exception as e:
            print(f"Send response error: {e}")
            
    def send_mjpeg_frame(self, client, frame_data):
        """发送MJPEG帧"""
        try:
            boundary = "----WebcamFrame"
            header = f"--{boundary}\r\n"
            header += "Content-Type: image/jpeg\r\n"
            
            # 确保frame_data是bytes类型
            if isinstance(frame_data, str):
                frame_data = frame_data.encode('utf-8')
            elif not isinstance(frame_data, bytes):
                # 尝试转换
                try:
                    frame_data = bytes(frame_data)
                except:
                    return
            
            if len(frame_data) == 0:
                return  # 空数据不发送
            
            header += f"Content-Length: {len(frame_data)}\r\n"
            header += "\r\n"
            
            # 发送帧头
            header_bytes = header.encode('utf-8')
            total_sent = 0
            while total_sent < len(header_bytes):
                try:
                    sent = client.send(header_bytes[total_sent:])
                    if sent == 0:
                        raise OSError("Connection broken")
                    total_sent += sent
                except (OSError, socket.error) as e:
                    raise
            
            # 发送帧数据
            total_sent = 0
            while total_sent < len(frame_data):
                try:
                    sent = client.send(frame_data[total_sent:])
                    if sent == 0:
                        raise OSError("Connection broken")
                    total_sent += sent
                except (OSError, socket.error) as e:
                    raise
            
            # 发送分隔符
            try:
                client.send("\r\n".encode('utf-8'))
            except:
                pass
                
        except (OSError, socket.error) as e:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            print(f"Send MJPEG frame error: {e}")
            
    def handle_api_status(self, client):
        """处理状态查询API"""
        status = {
            'video_enabled': self.video_enabled,
            'detection_enabled': self.detection_enabled,
            'detection_count': self.detection_count,
            'timestamp': time.time()
        }
        body = json.dumps(status)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_api_video_start(self, client):
        """处理启动视频API"""
        self.video_enabled = True
        response = {'status': 'ok', 'message': 'Video started'}
        body = json.dumps(response)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_api_video_stop(self, client):
        """处理停止视频API"""
        self.video_enabled = False
        response = {'status': 'ok', 'message': 'Video stopped'}
        body = json.dumps(response)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_api_detection_enable(self, client):
        """处理启用检测API"""
        self.detection_enabled = True
        response = {'status': 'ok', 'message': 'Detection enabled'}
        body = json.dumps(response)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_api_detection_disable(self, client):
        """处理禁用检测API"""
        self.detection_enabled = False
        response = {'status': 'ok', 'message': 'Detection disabled'}
        body = json.dumps(response)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_api_detections(self, client):
        """处理获取检测记录API"""
        body = json.dumps(self.detection_results)
        self.send_response(client, HTTP_OK, "application/json", body)
        
    def handle_mjpeg_stream(self, client):
        """处理MJPEG视频流（非阻塞方式）"""
        # 发送多部分响应头
        boundary = "----WebcamFrame"
        header = "HTTP/1.1 200 OK\r\n"
        header += "Content-Type: multipart/x-mixed-replace;boundary=" + boundary + "\r\n"
        header += "Connection: keep-alive\r\n"
        header += "\r\n"
        
        try:
            # 设置client为非阻塞（如果支持）
            try:
                client.setblocking(False)
            except:
                pass
            
            # 发送响应头
            try:
                client.send(header.encode('utf-8'))
                print("MJPEG stream header sent")
            except Exception as e:
                print(f"Failed to send MJPEG header: {e}")
                return
            
            frame_count = 0
            last_frame_time = 0
            max_wait_no_frame = 50  # 最多等待50次（约5秒）没有帧
            no_frame_count = 0
            
            # 限制循环次数，避免长时间阻塞
            max_frames = 10000  # 最大帧数限制
            frame_interval = 0.1  # 约10fps (1/10秒) - 降低帧率节省资源
            
            while self.running and self.video_enabled and frame_count < max_frames:
                try:
                    # 检查连接是否还活跃（简化检查）
                    # 在MicroPython中可能不支持MSG_PEEK，直接发送测试
                    # 如果连接断开会在send时抛出异常
                    
                    current_time = time.time()
                    
                    # 检查是否有新帧
                    if self.last_frame is not None:
                        # 检查帧是否更新（避免重复发送相同帧）
                        if current_time - last_frame_time >= frame_interval:
                            try:
                                # 将图像转换为JPEG字节
                                frame_jpeg = None
                                conversion_method = None
                                
                                arr = self.last_frame
                                
                                # 根据日志，ndarray是CHW格式 (3, 360, 640)，需要转换为HWC格式 (360, 640, 3)
                                # 方法1: 转置CHW到HWC，然后创建Image对象
                                try:
                                    import image
                                    import ulab.numpy as np
                                    
                                    # 检查形状：如果是(CHW)格式 (C, H, W)，转置为(HWC)格式 (H, W, C)
                                    if len(arr.shape) == 3 and arr.shape[0] == 3:
                                        # CHW -> HWC: (3, 360, 640) -> (360, 640, 3)
                                        # 使用transpose: (0,1,2) -> (1,2,0)
                                        hwc_arr = np.transpose(arr, (1, 2, 0))
                                        # 确保数据类型正确（如果需要）
                                        if hasattr(hwc_arr, 'astype'):
                                            try:
                                                hwc_arr = hwc_arr.astype(np.uint8)
                                            except:
                                                pass
                                        
                                        # 创建Image对象（CanMV可能需要size参数）
                                        try:
                                            img = image.Image(size=(hwc_arr.shape[1], hwc_arr.shape[0]), copy_to_fb=False)
                                            # 将数据复制到图像对象
                                            img.set_pixels(hwc_arr)
                                            if hasattr(img, 'to_jpeg'):
                                                frame_jpeg = img.to_jpeg(quality=60)
                                                conversion_method = "CHW_to_HWC_set_pixels_to_jpeg"
                                        except Exception as e_img:
                                            # 如果set_pixels失败，尝试直接传递ndarray
                                            try:
                                                img = image.Image(hwc_arr, copy_to_fb=False)
                                                if hasattr(img, 'to_jpeg'):
                                                    frame_jpeg = img.to_jpeg(quality=60)
                                                    conversion_method = "CHW_to_HWC_Image_to_jpeg"
                                            except:
                                                # 尝试compress方法
                                                try:
                                                    img = image.Image(hwc_arr, copy_to_fb=False)
                                                    if hasattr(img, 'compress'):
                                                        frame_jpeg = img.compress(quality=60)
                                                        conversion_method = "CHW_to_HWC_Image_compress"
                                                except:
                                                    pass
                                except Exception as e1:
                                    if frame_count == 0:
                                        print(f"CHW to HWC conversion failed: {e1}")
                                
                                # 方法2: 尝试直接使用原始数组（如果已经是HWC格式）
                                if frame_jpeg is None:
                                    try:
                                        import image
                                        # 检查是否是HWC格式 (H, W, C)
                                        if len(arr.shape) == 3 and arr.shape[2] == 3:
                                            try:
                                                img = image.Image(size=(arr.shape[1], arr.shape[0]), copy_to_fb=False)
                                                img.set_pixels(arr)
                                                if hasattr(img, 'to_jpeg'):
                                                    frame_jpeg = img.to_jpeg(quality=60)
                                                    conversion_method = "HWC_set_pixels_to_jpeg"
                                            except:
                                                try:
                                                    img = image.Image(arr, copy_to_fb=False)
                                                    if hasattr(img, 'to_jpeg'):
                                                        frame_jpeg = img.to_jpeg(quality=60)
                                                        conversion_method = "HWC_Image_to_jpeg"
                                                except:
                                                    pass
                                    except Exception as e2:
                                        if frame_count == 0:
                                            print(f"Direct HWC conversion failed: {e2}")
                                
                                # 打印ndarray的详细信息用于调试（在转换失败时，仅在前几次打印详细内容）
                                if frame_jpeg is None:
                                    arr = self.last_frame
                                    # 只在第一次或前几次失败时打印详细信息，避免输出过多
                                    print_debug_details = (frame_count == 0 and no_frame_count < 3)
                                    if print_debug_details:
                                        print(f"=== Image Conversion Debug Info (frame_count={frame_count}, no_frame_count={no_frame_count}) ===")
                                    print(f"Frame type: {type(arr)}")
                                    print(f"NDArray shape: {arr.shape if hasattr(arr, 'shape') else 'N/A'}")
                                    print(f"NDArray dtype: {arr.dtype if hasattr(arr, 'dtype') else 'N/A'}")
                                    print(f"NDArray size: {arr.size if hasattr(arr, 'size') else 'N/A'}")
                                    if hasattr(arr, '__class__'):
                                        print(f"NDArray class: {arr.__class__}")
                                    if hasattr(arr, '__class__') and hasattr(arr.__class__, '__name__'):
                                        print(f"NDArray class name: {arr.__class__.__name__}")
                                    
                                    # 打印对象的所有方法
                                    print(f"Available methods on frame object:")
                                    try:
                                        methods = [m for m in dir(arr) if not m.startswith('_')]
                                        for i, method in enumerate(methods[:20]):  # 只显示前20个方法
                                            print(f"  {method}")
                                        if len(methods) > 20:
                                            print(f"  ... and {len(methods) - 20} more methods")
                                    except Exception as e:
                                        print(f"  Could not list methods: {e}")
                                    
                                    # 尝试找到image模块并检查其功能
                                    try:
                                        import image
                                        print(f"image module found: {hasattr(image, 'Image')}")
                                        if hasattr(image, 'Image'):
                                            print(f"image.Image class: {image.Image}")
                                            # 尝试创建一个测试Image对象以查看其方法
                                            try:
                                                test_img_methods = [m for m in dir(image.Image) if not m.startswith('_')]
                                                print(f"image.Image available methods: {', '.join(test_img_methods[:10])}")
                                            except:
                                                pass
                                    except Exception as e:
                                        print(f"image module check failed: {e}")
                                    
                                    # 检查ulab.numpy模块
                                    try:
                                        import ulab.numpy as np
                                        print(f"ulab.numpy available: {hasattr(np, 'transpose')}, {hasattr(np, 'uint8')}")
                                    except Exception as e:
                                        print(f"ulab.numpy check failed: {e}")
                                    
                                    print("=" * 60)
                                
                                # 如果成功获取JPEG数据，发送帧
                                if frame_jpeg is not None and isinstance(frame_jpeg, bytes) and len(frame_jpeg) > 0:
                                    try:
                                        self.send_mjpeg_frame(client, frame_jpeg)
                                        last_frame_time = current_time
                                        frame_count += 1
                                        no_frame_count = 0
                                        
                                        # 第一次成功时打印方法
                                        if frame_count == 1:
                                            print(f"MJPEG: First frame sent using {conversion_method}, size: {len(frame_jpeg)} bytes")
                                        
                                        # 每100帧输出一次日志
                                        if frame_count % 100 == 0:
                                            print(f"MJPEG: Sent {frame_count} frames")
                                            gc.collect()
                                    except Exception as e:
                                        print(f"Send frame error: {e}")
                                        break
                                else:
                                    no_frame_count += 1
                                    if frame_count == 0 and no_frame_count == 1:
                                        print(f"MJPEG: Image conversion failed after all attempts.")
                                        print(f"  Frame type: {type(self.last_frame)}")
                                        print(f"  Frame value: {self.last_frame}")
                                        print(f"  frame_jpeg value: {frame_jpeg}")
                                        print(f"  frame_jpeg type: {type(frame_jpeg)}")
                                        if frame_jpeg is not None:
                                            print(f"  frame_jpeg length: {len(frame_jpeg)}")
                                        print(f"  Has to_jpeg: {hasattr(self.last_frame, 'to_jpeg')}")
                                        print(f"  Has compress: {hasattr(self.last_frame, 'compress')}")
                                        print(f"  Has save_to: {hasattr(self.last_frame, 'save_to')}")
                                    if no_frame_count > max_wait_no_frame:
                                        print("MJPEG: No valid frame data, stopping stream")
                                        break
                                    time.sleep(0.05)
                                    
                            except Exception as e:
                                print(f"MJPEG frame processing error: {e}")
                                no_frame_count += 1
                                if no_frame_count > max_wait_no_frame:
                                    break
                                time.sleep(0.05)
                        else:
                            # 帧间隔不够，短暂休眠
                            time.sleep(0.01)
                    else:
                        # 没有帧，等待
                        no_frame_count += 1
                        if no_frame_count > max_wait_no_frame:
                            print("MJPEG: No frame available, stopping stream")
                            # 发送一个占位符帧或错误信息
                            break
                        time.sleep(0.1)
                        
                except Exception as e:
                    print(f"MJPEG stream loop error: {e}")
                    break
                    
        except Exception as e:
            print(f"MJPEG stream connection error: {e}")
        finally:
            try:
                print(f"MJPEG stream ended, total frames: {frame_count}")
                client.close()
            except:
                pass
                
    def serve_html(self, client):
        """提供HTML页面"""
        html = self.get_html_page()
        self.send_response(client, HTTP_OK, "text/html", html)
        
    def get_html_page(self):
        """生成HTML页面"""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>内窥镜息肉检测平台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .header p {
            opacity: 0.9;
        }
        .content {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 20px;
            padding: 20px;
        }
        .video-section {
            background: #f5f5f5;
            border-radius: 10px;
            padding: 20px;
        }
        .video-container {
            position: relative;
            background: #000;
            border-radius: 10px;
            overflow: hidden;
            aspect-ratio: 16/9;
        }
        #videoStream {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .controls {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .control-group {
            margin-bottom: 25px;
        }
        .control-group h3 {
            margin-bottom: 15px;
            color: #333;
            font-size: 1.2em;
        }
        .btn {
            width: 100%;
            padding: 12px 20px;
            margin-bottom: 10px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 600;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .btn-success {
            background: #28a745;
            color: white;
        }
        .btn-success:hover {
            background: #218838;
            transform: translateY(-2px);
        }
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        .btn-danger:hover {
            background: #c82333;
            transform: translateY(-2px);
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .status {
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            background: #f8f9fa;
        }
        .status-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.95em;
        }
        .status-label {
            color: #666;
        }
        .status-value {
            font-weight: 600;
            color: #333;
        }
        .status-value.active {
            color: #28a745;
        }
        .status-value.inactive {
            color: #dc3545;
        }
        .detections {
            margin-top: 20px;
        }
        .detection-item {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .detection-item:hover {
            background: #ffe69c;
            transform: translateX(5px);
        }
        .detection-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
        }
        .detection-time {
            color: #666;
            font-size: 0.9em;
        }
        .detection-confidence {
            background: #28a745;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
        }
        @media (max-width: 768px) {
            .content {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 内窥镜息肉检测平台</h1>
            <p>实时视频流与AI检测系统</p>
        </div>
        <div class="content">
            <div class="video-section">
                <div class="video-container">
                    <img id="videoStream" src="/api/video/stream" alt="视频流">
                </div>
            </div>
            <div class="controls">
                <div class="control-group">
                    <h3>📹 视频控制</h3>
                    <button class="btn btn-success" id="btnStartVideo">启动视频</button>
                    <button class="btn btn-danger" id="btnStopVideo" disabled>停止视频</button>
                </div>
                <div class="control-group">
                    <h3>🤖 YOLO检测</h3>
                    <button class="btn btn-primary" id="btnEnableDetection" disabled>启用检测</button>
                    <button class="btn btn-danger" id="btnDisableDetection" disabled>禁用检测</button>
                </div>
                <div class="status">
                    <div class="status-item">
                        <span class="status-label">视频状态:</span>
                        <span class="status-value" id="videoStatus">已停止</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">检测状态:</span>
                        <span class="status-value" id="detectionStatus">已禁用</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">检测次数:</span>
                        <span class="status-value" id="detectionCount">0</span>
                    </div>
                </div>
                <div class="detections" id="detectionsList">
                    <h3>🔔 检测记录</h3>
                    <div id="detectionsContent">
                        <p style="color: #666; text-align: center; padding: 20px;">暂无检测记录</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        let videoEnabled = false;
        let detectionEnabled = false;
        let statusCheckInterval = null;
        
        // API调用函数
        async function apiCall(path, method = 'GET') {
            try {
                const response = await fetch(path, { method });
                return await response.json();
            } catch (error) {
                console.error('API error:', error);
                return null;
            }
        }
        
        // 更新状态
        async function updateStatus() {
            const status = await apiCall('/api/status');
            if (status) {
                videoEnabled = status.video_enabled;
                detectionEnabled = status.detection_enabled;
                
                document.getElementById('videoStatus').textContent = videoEnabled ? '运行中' : '已停止';
                document.getElementById('videoStatus').className = 'status-value ' + (videoEnabled ? 'active' : 'inactive');
                
                document.getElementById('detectionStatus').textContent = detectionEnabled ? '已启用' : '已禁用';
                document.getElementById('detectionStatus').className = 'status-value ' + (detectionEnabled ? 'active' : 'inactive');
                
                document.getElementById('detectionCount').textContent = status.detection_count;
                
                // 更新按钮状态
                document.getElementById('btnStartVideo').disabled = videoEnabled;
                document.getElementById('btnStopVideo').disabled = !videoEnabled;
                document.getElementById('btnEnableDetection').disabled = !videoEnabled || detectionEnabled;
                document.getElementById('btnDisableDetection').disabled = !videoEnabled || !detectionEnabled;
                
                // 更新视频流
                if (videoEnabled) {
                    const img = document.getElementById('videoStream');
                    img.src = '/api/video/stream?t=' + Date.now();
                }
            }
        }
        
        // 加载检测记录
        async function loadDetections() {
            const detections = await apiCall('/api/detections');
            const container = document.getElementById('detectionsContent');
            
            if (!detections || detections.length === 0) {
                container.innerHTML = '<p style="color: #666; text-align: center; padding: 20px;">暂无检测记录</p>';
                return;
            }
            
            container.innerHTML = detections.reverse().slice(0, 10).map(det => {
                const date = new Date(det.timestamp * 1000);
                const timeStr = date.toLocaleString('zh-CN');
                const maxConf = Math.max(...det.results.map(r => r.confidence || 0));
                return `
                    <div class="detection-item">
                        <div class="detection-header">
                            <span class="detection-time">${timeStr}</span>
                            <span class="detection-confidence">${(maxConf * 100).toFixed(1)}%</span>
                        </div>
                        <div>检测到 ${det.results.length} 个息肉</div>
                    </div>
                `;
            }).join('');
        }
        
        // 事件监听
        document.getElementById('btnStartVideo').addEventListener('click', async () => {
            await apiCall('/api/video/start', 'POST');
            updateStatus();
        });
        
        document.getElementById('btnStopVideo').addEventListener('click', async () => {
            await apiCall('/api/video/stop', 'POST');
            updateStatus();
        });
        
        document.getElementById('btnEnableDetection').addEventListener('click', async () => {
            await apiCall('/api/detection/enable', 'POST');
            updateStatus();
        });
        
        document.getElementById('btnDisableDetection').addEventListener('click', async () => {
            await apiCall('/api/detection/disable', 'POST');
            updateStatus();
        });
        
        // 初始化
        updateStatus();
        loadDetections();
        statusCheckInterval = setInterval(() => {
            updateStatus();
            loadDetections();
        }, 2000);
    </script>
</body>
</html>"""
        return html
        
    def process_request(self, client):
        """处理HTTP请求"""
        try:
            # 设置client socket为非阻塞（如果有此方法）
            try:
                client.setblocking(False)
            except:
                pass
            
            # 接收请求数据（可能需要多次接收）
            data = b''
            max_attempts = 10
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    chunk = client.recv(1024)
                    if not chunk:
                        if data:
                            break  # 数据接收完成
                        else:
                            return  # 没有数据
                    data += chunk
                    # 检查是否接收完HTTP请求头（以\r\n\r\n结束）
                    if b'\r\n\r\n' in data:
                        break
                    attempt += 1
                    time.sleep(0.01)  # 短暂延迟等待更多数据
                except OSError as e:
                    err = e.args[0] if len(e.args) > 0 else None
                    if err in (11, 110):  # EAGAIN/EWOULDBLOCK
                        if data:
                            break  # 有部分数据，继续处理
                        time.sleep(0.01)
                        attempt += 1
                    else:
                        raise
                except Exception as e:
                    print(f"Receive error: {e}")
                    return
            
            if not data:
                return
                
            method, path = self.parse_request(data)
            if not method or not path:
                print(f"Parse failed, method={method}, path={path}")
                return
            
            print(f"Request: {method} {path}")  # 调试信息
                
            # 路由处理
            if path == '/' or path == '/index.html':
                self.serve_html(client)
            elif path == '/api/status':
                self.handle_api_status(client)
            elif path == '/api/video/start' and method == 'POST':
                self.handle_api_video_start(client)
            elif path == '/api/video/stop' and method == 'POST':
                self.handle_api_video_stop(client)
            elif path == '/api/video/stream':
                self.handle_mjpeg_stream(client)
                return  # MJPEG流会保持连接，不在这里关闭
            elif path == '/api/detection/enable' and method == 'POST':
                self.handle_api_detection_enable(client)
            elif path == '/api/detection/disable' and method == 'POST':
                self.handle_api_detection_disable(client)
            elif path == '/api/detections':
                self.handle_api_detections(client)
            else:
                self.send_response(client, HTTP_NOT_FOUND, "text/plain", "Not Found")
                
        except Exception as e:
            print(f"Process request error: {e}")
            try:
                # 发送错误响应
                error_msg = f"HTTP/1.1 500 Internal Server Error\r\n\r\nError: {e}\r\n"
                client.send(error_msg.encode('utf-8'))
            except:
                pass
        finally:
            try:
                client.close()
            except:
                pass
                
    def loop(self):
        """服务器主循环（需要在主线程中调用）"""
        if not self.running or not self.socket:
            return
            
        try:
            client, addr = self.socket.accept()
            print(f"Client connected from: {addr}")  # 调试信息
            self.process_request(client)
        except OSError as e:
            # 非阻塞模式下没有连接会抛出 EAGAIN，直接忽略
            err = e.args[0] if len(e.args) > 0 else None
            if err in (11, 110, 2):  # EAGAIN/EWOULDBLOCK/ENOENT
                # 正常情况，没有新连接
                pass
            else:
                print(f"Socket accept error: {e}, errno: {err}")
            gc.collect()
        except Exception as e:
            print(f"Server loop error: {e}")
            gc.collect()

