"""
MJPEG视频流模块
提供实时MJPEG视频流服务
"""

import utime as time
import gc


class MJPEGStreamer:
    """MJPEG视频流处理器"""
    
    def __init__(self, quality=75, max_fps=15):
        self.quality = quality
        self.max_fps = max_fps
        self.frame_interval = 1.0 / max_fps
        self.current_frame = None
        self.last_frame_time = 0
        self.active_clients = 0
        self.ready_check = None  # 可选：外部提供的就绪检查回调
        
    def update_frame(self, image):
        """更新当前帧（由YOLO线程调用）"""
        current_time = time.time()
        
        # 帧率限制
        if current_time - self.last_frame_time < self.frame_interval:
            return
        
        # 第一次收到帧时打印详细信息
        if self.current_frame is None:
            print(f"[Stream] ✅ 收到第一帧! 类型: {type(image)}")
            if hasattr(image, 'width') and hasattr(image, 'height'):
                print(f"[Stream] 图像尺寸: {image.width()}x{image.height()}")
        
        self.current_frame = image
        self.last_frame_time = current_time
        
        # 减少日志输出频率,从每30帧改为每100帧
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 100 == 0:
            print(f"[Stream] 已更新 {self._frame_count} 帧")
    
    def set_ready_checker(self, checker):
        """由外部注入的YOLO就绪检测函数"""
        if callable(checker):
            self.ready_check = checker
            print("[Stream] ✅ 已绑定YOLO就绪检测回调")
        else:
            self.ready_check = None
            print("[Stream] ⚠️ 提供的就绪检测函数不可调用，已忽略")
        
    def stream_handler(self, client_socket):
        """处理MJPEG流请求"""
        try:
            print("[Stream] 开始处理流请求")
            
            # 发送MJPEG响应头
            headers = "HTTP/1.1 200 OK\r\n"
            headers += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
            headers += "Connection: close\r\n"
            headers += "\r\n"
            client_socket.sendall(headers.encode('utf-8'))
            
            print("[Stream] HTTP头已发送")
            
            self.active_clients += 1
            print(f"[Stream] 视频流客户端已连接，当前活跃: {self.active_clients}")
            
            # 优化：优先使用外部提供的就绪检查回调 (ready_check)
            # 如果存在 callable ready_check(), 则等待该回调返回 True（带超时）。
            # 否则回退到原来的短时分段等待（2s），以兼容旧逻辑。
            if self.ready_check and callable(self.ready_check):
                print("[Stream] 等待YOLO初始化完成（由ready_check控制，最长15s）...")
                max_wait = 15.0
                waited = 0.0
                # 以 100ms 为步长检查 ready_check，期间让出CPU
                while not self.ready_check() and waited < max_wait:
                    time.sleep(0.1)
                    waited += 0.1
                    # 每0.5s打印一次进度
                    if int(waited * 10) % 5 == 0:
                        print(f"[Stream] 已等待 {waited:.1f}s...")

                if self.ready_check():
                    print("[Stream] ✅ YOLO已就绪，开始等待帧数据")
                else:
                    print("[Stream] ⚠️ YOLO在超时时间内未就绪，继续进入等待帧流程（可能会超时）")
            else:
                # 兼容旧逻辑：分段等待2秒
                print("[Stream] ⏳ 未绑定ready_check，回退为固定2秒等待...")
                for i in range(20):  # 20 * 100ms = 2秒
                    time.sleep(0.1)  # 每100ms让出一次CPU
                    if (i + 1) % 5 == 0:  # 每500ms打印一次
                        print(f"[Stream] 已等待 {(i + 1) * 0.1:.1f}s...")
                print("[Stream] ✅ 等待完成，开始等待帧数据")
            
            last_sent_time = 0
            frame_sent_count = 0
            wait_count = 0
            
            while True:
                # 等待新帧
                if self.current_frame is None:
                    wait_count += 1
                    # 每秒打印一次等待日志（20次 * 50ms = 1秒）
                    if wait_count % 20 == 0:
                        print(f"[Stream] 等待帧数据... ({wait_count * 0.05:.1f}s)")
                    
                    # 超时检查 - 15秒后断开连接（给初始化更多时间）
                    if wait_count > 300:  # 300 * 50ms = 15秒
                        print("[Stream] ❌ 等待帧超时（15秒），断开连接")
                        break
                    
                    # 🔧 增加sleep时间，减少CPU竞争
                    time.sleep(0.05)  # 50ms等待 - 给YOLO线程更多CPU时间
                    continue
                    
                current_time = time.time()
                
                # 帧率控制
                if current_time - last_sent_time < self.frame_interval:
                    time.sleep(0.01)  # 10ms等待
                    continue
                
                try:
                    # 压缩为JPEG
                    jpeg_data = self.compress_frame(self.current_frame)
                    
                    if jpeg_data:
                        # 发送MJPEG帧
                        frame_header = b"--frame\r\n"
                        frame_header += b"Content-Type: image/jpeg\r\n"
                        frame_header += f"Content-Length: {len(jpeg_data)}\r\n".encode('utf-8')
                        frame_header += b"\r\n"
                        
                        client_socket.sendall(frame_header)
                        client_socket.sendall(jpeg_data)
                        client_socket.sendall(b"\r\n")
                        
                        last_sent_time = current_time
                        frame_sent_count += 1
                        
                        # 大幅减少日志输出,从每10帧改为每50帧
                        if frame_sent_count % 50 == 0:
                            print(f"[Stream] 已发送 {frame_sent_count} 帧")
                        
                except Exception as e:
                    print(f"发送帧失败: {e}")
                    break
                    
                gc.collect()
                
        except Exception as e:
            print(f"视频流错误: {e}")
        finally:
            self.active_clients -= 1
            print(f"视频流客户端断开，当前活跃: {self.active_clients}")
            try:
                client_socket.close()
            except:
                pass
                
    def compress_frame(self, image):
        """压缩图像为JPEG - 支持K230图像对象和ndarray"""
        try:
            # 方法1: 检查是否有 to_jpeg 方法 (K230 Image对象的标准方法)
            if hasattr(image, 'to_jpeg'):
                # to_jpeg()返回一个新的JPEG格式Image对象
                jpeg_img = image.to_jpeg(quality=self.quality)
                # compressed()方法返回压缩后的字节数据
                if hasattr(jpeg_img, 'compressed'):
                    return bytes(jpeg_img.compressed())
                else:
                    return bytes(jpeg_img)
            
            # 方法2: 检查是否有 compressed 方法 (旧版API)
            elif hasattr(image, 'compressed'):
                compressed_data = image.compressed(quality=self.quality)
                return bytes(compressed_data)
            
            else:
                # 只在第一次打印错误,避免刷屏
                if not hasattr(self, '_compress_error_printed'):
                    print(f"[Stream] ❌ 图像对象不支持压缩: {type(image)}")
                    print(f"[Stream] 可用方法: {dir(image)[:10]}...")  # 打印前10个方法
                    self._compress_error_printed = True
                return None
                
        except Exception as e:
            if not hasattr(self, '_compress_exception_printed'):
                print(f"[Stream] 压缩图像失败: {e}")
                import sys
                sys.print_exception(e)
                self._compress_exception_printed = True
            return None
            
    def set_quality(self, quality):
        """设置JPEG质量"""
        if 10 <= quality <= 95:
            self.quality = quality
            return True
        return False
        
    def set_fps(self, fps):
        """设置最大帧率"""
        if 1 <= fps <= 30:
            self.max_fps = fps
            self.frame_interval = 1.0 / fps
            return True
        return False
