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
        
    def update_frame(self, image):
        """更新当前帧（由YOLO线程调用）"""
        current_time = time.time()
        
        # 帧率限制
        if current_time - self.last_frame_time < self.frame_interval:
            return
        
        self.current_frame = image
        self.last_frame_time = current_time
        
        # 减少日志输出频率,从每30帧改为每100帧
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 100 == 0:
            print(f"[Stream] 已更新 {self._frame_count} 帧")
        
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
            
            last_sent_time = 0
            frame_sent_count = 0
            wait_count = 0
            
            while True:
                # 等待新帧
                if self.current_frame is None:
                    wait_count += 1
                    # 减少等待日志输出,从每20次改为每100次
                    if wait_count % 100 == 0:
                        print(f"[Stream] 等待帧数据... ({wait_count * 0.05:.1f}s)")
                    time.sleep(0.05)
                    continue
                    
                current_time = time.time()
                
                # 帧率控制
                if current_time - last_sent_time < self.frame_interval:
                    time.sleep(0.01)
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
        """压缩图像为JPEG"""
        try:
            # K230 image 模块的 compressed 方法
            if hasattr(image, 'compressed'):
                # compressed() 返回压缩后的数据
                compressed_data = image.compressed(quality=self.quality)
                # 直接返回 bytes
                return bytes(compressed_data)
            else:
                print(f"图像对象不支持压缩: {type(image)}")
                return None
                
        except Exception as e:
            print(f"压缩图像失败: {e}")
            import sys
            sys.print_exception(e)
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
