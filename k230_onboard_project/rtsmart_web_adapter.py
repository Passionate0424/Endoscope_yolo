"""
RT-Smart Web 服务器 Python 适配层
C 层 HTTP 服务器 + Python YOLO 检测
"""

import utime as time
import gc
import socket
import json

# 尝试导入 C 模块
try:
    import rtsmart_web
    HAS_C_SERVER = True
    print("[RTWeb] ✅ C 层 HTTP 服务器已加载")
except ImportError:
    HAS_C_SERVER = False
    print("[RTWeb] ⚠️ C 层服务器未找到，请检查固件编译")


class RTWebAdapter:
    """
    适配器：将 Python YOLO 检测结果推送到 C 层 HTTP 服务器
    """
    
    def __init__(self, quality=75, http_api_host="127.0.0.1", http_api_port=8080):
        self.quality = quality
        self.use_c_server = HAS_C_SERVER
        self._frame_count = 0
        self._push_success_count = 0
        self._push_fail_count = 0
        self._last_push_time = 0
        self._first_push_time = 0
        
        # ⭐ HTTP API 配置（用于读取状态）
        # 
        # 架构说明：
        # RT-Smart 中，内核层的 web_state（HTTP 服务器使用）和用户层的 web_state
        # （MicroPython 绑定使用）是两份独立的数据结构，不共享内存。
        # 
        # 当前使用 HTTP API 同步方案：
        # - 通过 HTTP API (/api/status) 读取内核层的 web_state
        # - 确保 Python 层和前端读取的是同一份数据
        # - 简单可靠，不需要修改内核代码
        # 
        # 如果需要更高性能，可以实现共享内存方案（需要修改内核代码）
        # 详见：docs/WEB_STATE_SHARING.md
        self.http_api_host = http_api_host
        self.http_api_port = http_api_port
        self._use_http_api_for_control = True  # 使用 HTTP API 读取控制信息
        
        # 尝试获取本地 IP 地址（如果 http_api_host 是默认值）
        if self.http_api_host == "127.0.0.1":
            try:
                import network
                wlan = network.WLAN(network.STA_IF)
                if wlan.isconnected():
                    ifconfig = wlan.ifconfig()
                    self.http_api_host = ifconfig[0]  # 使用实际 IP 地址
                    print("[RTWeb] 📍 检测到本地 IP: %s" % self.http_api_host)
            except:
                pass  # 使用默认的 127.0.0.1
        
        if not self.use_c_server:
            print("[RTWeb] ❌ C 服务器不可用，系统无法工作")
            raise RuntimeError("RT-Smart web server module not found")
        
        # HTTP 服务器已通过 C 层自动启动机制运行，无需手动启动
        print("[RTWeb] ✅ C 层 HTTP 服务器已就绪")
        print("[RTWeb] 调试模式：将详细记录前 20 帧的推送情况")
        print("[RTWeb] ⚠️ 使用 HTTP API 读取控制信息 (http://%s:%d/api/status)" % (self.http_api_host, self.http_api_port))
    
    def update_frame(self, image):
        """
        由 YOLO 检测线程调用，推送帧到 C 层
        
        Args:
            image: CanMV image 对象
        """
        if not self.use_c_server:
            return
        
        self._frame_count += 1
        current_time = time.time()
        is_debug_frame = (self._frame_count <= 20)
        
        try:
            # 编码为 JPEG
            if is_debug_frame:
                print("[RTWeb] [帧#%d] 开始编码 JPEG..." % self._frame_count)
            
            jpeg_bytes = image.compress(quality=self.quality)
            
            if jpeg_bytes is None or len(jpeg_bytes) == 0:
                if is_debug_frame or self._frame_count % 100 == 0:
                    print("[RTWeb] [帧#%d] ⚠️ JPEG 编码失败或为空" % self._frame_count)
                self._push_fail_count += 1
                return
            
            if is_debug_frame:
                print("[RTWeb] [帧#%d] JPEG 编码成功，大小: %d 字节" % (self._frame_count, len(jpeg_bytes)))
            
            # 推送到 C 层 frame_buffer
            try:
                rtsmart_web.push_frame(jpeg_bytes)
                self._push_success_count += 1
                
                if self._first_push_time == 0:
                    self._first_push_time = current_time
                
                # 计算推送频率
                interval = 0
                if self._last_push_time > 0:
                    interval = current_time - self._last_push_time
                    fps = 1.0 / interval if interval > 0 else 0
                else:
                    fps = 0
                self._last_push_time = current_time
                
                # 详细日志（前20帧或每100帧）
                if is_debug_frame:
                    print("[RTWeb] [帧#%d] ✅ push_frame 成功 (大小: %d 字节, 间隔: %.3fs, 推送FPS: %.1f)" % 
                          (self._frame_count, len(jpeg_bytes), interval, fps))
                    # 警告：如果推送频率太低，MJPEG 流会挂起
                    if fps < 5 and self._frame_count > 5:
                        print("[RTWeb] ⚠️ 警告：推送频率太低 (%.1f fps)，MJPEG 流可能需要 10+ fps" % fps)
                elif self._frame_count % 100 == 0:
                    success_rate = (self._push_success_count / self._frame_count * 100) if self._frame_count > 0 else 0
                    avg_fps = 1.0 / interval if interval > 0 else 0
                    print("[RTWeb] [帧#%d] ✅ 已推送 %d 帧 (成功: %d, 失败: %d, 成功率: %.1f%%, 平均FPS: %.1f)" % 
                          (self._frame_count, self._push_success_count, self._push_success_count, 
                           self._push_fail_count, success_rate, avg_fps))
                
                if self._frame_count % 100 == 0:
                    gc.collect()  # 定期 GC
                    
            except OSError as e:
                # push_frame 失败会抛出 OSError
                self._push_fail_count += 1
                if is_debug_frame or self._frame_count % 100 == 0:
                    print("[RTWeb] [帧#%d] ❌ push_frame 失败: %s" % (self._frame_count, str(e)))
                    import sys
                    sys.print_exception(e)
            
        except Exception as e:
            self._push_fail_count += 1
            if is_debug_frame or self._frame_count % 100 == 0:
                print("[RTWeb] [帧#%d] ❌ 推送帧异常: %s" % (self._frame_count, str(e)))
                import sys
                sys.print_exception(e)
    
    def is_ready(self):
        """检查 C 服务器是否就绪"""
        if not self.use_c_server:
            return False
        return rtsmart_web.is_ready()
    
    def get_stats(self):
        """获取服务器统计信息"""
        if not self.use_c_server:
            return {}
        return rtsmart_web.get_stats()

    def pull_control(self):
        if not self.use_c_server:
            return None
        
        # ⭐ 关键说明：
        # RT-Smart 中，内核层的 web_state 和用户层的 web_state 是两份独立的数据结构
        # 内核层的 web_state（HTTP 服务器使用）和用户层的 web_state（MicroPython 绑定使用）
        # 它们不共享内存，所以需要通过 IPC 机制同步
        #
        # 方案1：通过 HTTP API 读取（当前实现）- 简单可靠，与前端同步
        # 方案2：实现共享内存/设备节点（需要修改内核，复杂度高）
        #
        # 当前使用方案1：通过 HTTP API 读取内核层的 web_state
        if self._use_http_api_for_control:
            try:
                # 通过 HTTP API 读取状态（从内核层的 web_state）
                status_data = self._http_get_status()
                if status_data and status_data.get('success') and status_data.get('data'):
                    data = status_data['data']
                    # 转换为与 rtsmart_web.get_control() 相同的格式
                    control = {
                        'camera_desired': data.get('camera', {}).get('desired', False),
                        'camera_running': data.get('camera', {}).get('running', False),
                        'detection_desired': data.get('detection', {}).get('desired', False),
                        'detection_enabled': data.get('detection', {}).get('enabled', False),
                        'confidence_desired': data.get('confidence', {}).get('desired', 0.5),
                        'confidence_actual': data.get('confidence', {}).get('actual', 0.5),
                        'command_version': data.get('command_version', 0),
                    }
                    return control
                return None
            except Exception as e:
                # HTTP API 失败，回退到 C 绑定（虽然可能读取不到正确的版本号，因为读取的是用户层的 web_state）
                # 这里只记录错误，不打印详细信息（避免刷屏）
                try:
                    return rtsmart_web.get_control()
                except:
                    return None
        else:
            # 使用 C 绑定（不推荐，因为读取的是用户层的 web_state，与内核层的 web_state 不同步）
            # 用户层的 web_state.command_version 始终是初始值，不会反映内核层的变化
            try:
                control = rtsmart_web.get_control()
                if control is None:
                    print("[RTWeb] ⚠️ get_control() 返回 None")
                elif 'command_version' not in control:
                    print("[RTWeb] ⚠️ 控制信息中缺少 command_version 字段: %s" % str(control))
                return control
            except Exception as e:
                print("[RTWeb] ⚠️ 获取控制信息失败:", e)
                import sys
                sys.print_exception(e)
                return None
    
    def _http_get_status(self):
        """通过 HTTP API 获取状态"""
        # 尝试地址：实际 IP 和 localhost
        hosts_to_try = [self.http_api_host, "127.0.0.1"]
        
        for host in hosts_to_try:
            sock = None
            try:
                # 创建 socket 连接
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.3)  # 0.3 秒连接超时（快速失败）
                
                try:
                    sock.connect((host, self.http_api_port))
                except (socket.timeout, OSError):
                    # 连接失败，关闭 socket 并尝试下一个地址
                    try:
                        sock.close()
                    except:
                        pass
                    sock = None
                    continue
                
                # 连接成功，发送 HTTP GET 请求
                try:
                    request = "GET /api/status HTTP/1.1\r\n"
                    request += "Host: %s:%d\r\n" % (host, self.http_api_port)
                    request += "Connection: close\r\n"
                    request += "\r\n"
                    
                    sock.send(request.encode('utf-8'))
                    
                    # 接收响应（设置超时）
                    sock.settimeout(0.5)  # 0.5 秒接收超时
                    response = b""
                    try:
                        while True:
                            chunk = sock.recv(2048)  # 减小缓冲区大小
                            if not chunk:
                                break
                            response += chunk
                            # 限制响应大小，避免内存溢出
                            if len(response) > 8192:
                                break
                    except socket.timeout:
                        pass  # 超时也算收到部分数据
                    
                    # 关闭 socket
                    try:
                        sock.close()
                    except:
                        pass
                    sock = None
                    
                    # 解析响应
                    if response:
                        response_str = response.decode('utf-8', errors='ignore')
                        # 查找 JSON 部分（在 \r\n\r\n 之后）
                        json_start = response_str.find('\r\n\r\n')
                        if json_start >= 0:
                            json_str = response_str[json_start + 4:]
                            try:
                                result = json.loads(json_str)
                                # 成功读取，更新使用的 host
                                if host != self.http_api_host:
                                    self.http_api_host = host
                                return result
                            except:
                                pass
                except Exception:
                    # 发送或接收失败，关闭 socket
                    try:
                        if sock:
                            sock.close()
                    except:
                        pass
                    sock = None
                    continue
            except Exception:
                # 任何其他异常，确保关闭 socket
                try:
                    if sock:
                        sock.close()
                except:
                    pass
                sock = None
                continue
        
        # 所有地址都失败，返回 None（不打印错误，避免刷屏）
        return None

    def update_runtime(self, camera_running, detection_enabled, confidence):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.set_runtime(camera_running, detection_enabled, confidence)
            print("[RTWeb] ✅ 已更新运行状态: camera=%s, detection=%s, confidence=%.2f" % 
                  (camera_running, detection_enabled, confidence))
        except Exception as e:
            print("[RTWeb] ⚠️ 更新运行状态失败:", e)
            import sys
            sys.print_exception(e)

    def update_stats_remote(self, total_frames, total_detections, fps):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.set_stats(total_frames, total_detections, fps)
            # 调试：每100次更新打印一次（避免日志过多）
            if self._frame_count > 0 and self._frame_count % 100 == 0:
                print("[RTWeb] 📊 统计数据已更新: FPS=%.2f, 总帧数=%d, 检测数=%d" % 
                      (fps, total_frames, total_detections))
        except Exception as e:
            print("[RTWeb] ⚠️ 更新统计失败:", e)
            import sys
            sys.print_exception(e)

    def notify_record_saved(self, record):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.add_record(record['filename'], record['time_str'], record['confidence'])
        except Exception as e:
            print("[RTWeb] ⚠️ 同步检测记录失败:", e)

    def notify_record_deleted(self, record_id):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.delete_record(record_id)
        except Exception as e:
            print("[RTWeb] ⚠️ 删除检测记录失败:", e)

    def notify_records_cleared(self):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.clear_records()
        except Exception as e:
            print("[RTWeb] ⚠️ 清空检测记录失败:", e)


# 兼容旧代码的别名
MJPEGStreamerAdapter = RTWebAdapter


def print_info():
    """打印系统信息"""
    print("=" * 50)
    print("RT-Smart Web 服务器架构")
    print("=" * 50)
    status = "✅ 可用" if HAS_C_SERVER else "❌ 不可用"
    print("C 层 HTTP 服务器: " + status)
    
    if HAS_C_SERVER:
        stats = rtsmart_web.get_stats()
        print("服务器端口: %d" % stats.get('port', 8080))
        ready_status = "🟢 运行中" if stats.get('ready', False) else "🔴 未就绪"
        print("服务器状态: " + ready_status)
    
    print("\n架构说明:")
    print("- C 层: RT-Smart pthread + lwIP socket (HTTP + MJPEG)")
    print("- Python 层: CanMV + YOLO 检测")
    print("- 通信: MicroPython C 模块 (rtsmart_web)")
    print("\n启动方式:")
    print("1. RT-Smart 串口: http_start")
    print("2. Python 层: import rtsmart_web_adapter")
    print("=" * 50)
