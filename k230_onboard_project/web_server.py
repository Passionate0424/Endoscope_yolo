"""
HTTP服务器模块
支持静态文件服务、API路由、MJPEG视频流
"""

import socket
import os
import json
import gc


class HTTPServer:
    """简单的HTTP服务器"""
    
    # 类变量：用于生成连接ID
    _connection_counter = 0
    
    def __init__(self, host='0.0.0.0', port=80):
        self.host = host
        self.port = port
        self.socket = None
        self.routes = {}
        self.running = False
        
    def route(self, path, method='GET'):
        """路由装饰器"""
        def decorator(func):
            key = f"{method}:{path}"
            self.routes[key] = func
            return func
        return decorator
        
    def start(self, custom_handler=None):
        """启动服务器"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 设置为非阻塞模式，然后再改回阻塞模式（刷新socket状态）
        self.socket.setblocking(False)
        self.socket.setblocking(True)
        
        try:
            self.socket.bind((self.host, self.port))
        except OSError as e:
            print(f"绑定端口失败: {e}")
            print(f"端口 {self.port} 可能已被占用")
            return
            
        # 增加监听队列长度，避免连接被拒绝
        # 从 10 增加到 20，支持更多并发连接
        self.socket.listen(20)
        self.running = True
        print(f"HTTP服务器启动: http://{self.host}:{self.port}")
        
        # 运行服务器主循环
        while self.running:
            try:
                # 设置accept超时，避免永久阻塞
                self.socket.settimeout(1.0)
                client_socket, addr = self.socket.accept()
                
                # 接受连接成功，启动处理线程
                import _thread
                if custom_handler:
                    _thread.start_new_thread(custom_handler, (client_socket,))
                else:
                    _thread.start_new_thread(self.handle_client, (client_socket, addr))
                    
            except OSError as e:
                # 静默处理常见的网络错误
                error_code = e.args[0] if e.args else 0
                
                if error_code == 110:  # ETIMEDOUT - 超时
                    continue
                elif error_code == 103:  # ECONNABORTED - 连接被客户端中止
                    continue
                elif error_code == 104:  # ECONNRESET - 连接被重置
                    continue
                elif error_code == 11:  # EAGAIN - 资源暂时不可用
                    import utime
                    utime.sleep_ms(10)
                    continue
                elif self.running:
                    print(f"Socket错误: {e}")
            except Exception as e:
                if self.running:
                    print(f"接受连接错误: {e}")
                # 发生异常后也让出CPU
                import utime
                utime.sleep_ms(10)
        
    def stop(self):
        """停止服务器"""
        self.running = False
        if self.socket:
            self.socket.close()
        print("HTTP服务器已停止")
        
    def handle_client(self, client_socket, addr):
        """处理客户端请求 - 支持Keep-Alive"""
        import gc  # 导入gc模块用于垃圾回收和内存监控
        
        request_count = 0
        max_requests = 50  # 单个连接最多处理50个请求
        request_start = None  # 初始化请求开始时间
        
        # 生成唯一的连接ID
        HTTPServer._connection_counter += 1
        conn_id = HTTPServer._connection_counter
        
        try:
            print(f"[连接#{conn_id}] 新连接: {addr}")
            client_socket.settimeout(0.5)  # 减少到0.5秒,加快响应
            
            # Keep-Alive 循环
            while request_count < max_requests:
                request_count += 1
                request_start = None  # 重置请求开始时间
                
                # 接收请求数据 - 分批接收直到收到完整的HTTP头
                request = b''
                max_size = 8192
                first_chunk = True  # 标记是否是第一个数据块
                
                while len(request) < max_size:
                    try:
                        # 对于第一个chunk,如果超时说明客户端没有新请求,可以安全退出
                        chunk = client_socket.recv(1024)
                        if not chunk:
                            # 客户端关闭连接
                            if request_count == 1:
                                print(f"[连接#{conn_id}] 客户端在第一次请求前就关闭了")
                            return
                        request += chunk
                        first_chunk = False  # 已收到数据
                        
                        # 检查是否收到完整的HTTP头（以\r\n\r\n结束）
                        if b'\r\n\r\n' in request:
                            break
                            
                    except OSError as e:
                        # 超时或其他错误
                        if e.args[0] in (110, 11):  # ETIMEDOUT or EAGAIN
                            if first_chunk and request_count > 1:
                                # 第一个chunk就超时,说明客户端没有新请求
                                # 正常结束Keep-Alive连接
                                return
                            elif not first_chunk:
                                # 已经收到部分数据但后续超时,这是异常情况
                                print(f"[连接#{conn_id}] 接收请求中途超时")
                                return
                            else:
                                # 第一个请求就超时
                                return
                        else:
                            print(f"[连接#{conn_id}] 接收数据错误: {e}")
                            return
                    except Exception as e:
                        print(f"[连接#{conn_id}] 接收数据错误: {e}")
                        return
                        
                if not request:
                    return
                
                # 解析请求 - MicroPython的decode不支持errors参数
                try:
                    request_str = request.decode('utf-8')
                except:
                    # 如果解码失败，尝试用latin-1
                    request_str = request.decode('latin-1')
                
                lines = request_str.split('\r\n')
                
                if not lines:
                    return
                    
                # 解析请求行
                request_line = lines[0].split(' ')
                if len(request_line) < 3:
                    return
                    
                method = request_line[0]
                path = request_line[1]
                
                # 解析请求头，检查Content-Length
                content_length = 0
                keep_alive = False
                connection_header = None
                for line in lines[1:]:
                    line_lower = line.lower()
                    if line_lower.startswith('content-length:'):
                        try:
                            content_length = int(line.split(':', 1)[1].strip())
                        except:
                            pass
                    elif line_lower.startswith('connection:'):
                        connection_header = line
                        if 'keep-alive' in line_lower:
                            keep_alive = True
                        elif 'close' in line_lower:
                            keep_alive = False
                
                # 如果有请求体，继续读取（POST/PUT等）
                if content_length > 0:
                    # 计算已经读取的请求体长度
                    header_end = request.find(b'\r\n\r\n')
                    if header_end != -1:
                        body_received = len(request) - (header_end + 4)
                        body_remaining = content_length - body_received
                        
                        # 继续读取剩余的请求体
                        while body_remaining > 0 and len(request) < max_size:
                            try:
                                chunk = client_socket.recv(min(1024, body_remaining))
                                if not chunk:
                                    break
                                request += chunk
                                body_remaining -= len(chunk)
                            except OSError as e:
                                print(f"[连接#{conn_id}] 读取请求体错误: {e}")
                                break
                
                # 打印请求信息（进一步减少日志输出）
                # 只在第一个请求或非status的API请求时打印
                if request_count == 1 or (('/api/' in path or path == '/') and '/status' not in path):
                    import utime
                    request_start = utime.ticks_ms()
                    print(f"[连接#{conn_id}] 请求#{request_count}: {method} {path}")
                else:
                    request_start = None
                
                # 解析查询参数
                query_params = {}
                if '?' in path:
                    path, query_string = path.split('?', 1)
                    for param in query_string.split('&'):
                        if '=' in param:
                            key, value = param.split('=', 1)
                            query_params[key] = value
                
                # 路由匹配
                route_key = f"{method}:{path}"
                response = None
                
                if route_key in self.routes:
                    # 调用路由处理函数
                    try:
                        response = self.routes[route_key](query_params)
                    except Exception as e:
                        print(f"[连接#{conn_id}] 路由处理错误: {e}")
                        response = self.build_response(500, "Internal Server Error")
                    
                    # 检查是否是流式响应标记
                    if isinstance(response, dict) and response.get('_stream'):
                        # 流式响应直接在当前线程处理（已经在独立线程中）
                        if hasattr(self, 'streamer'):
                            self.streamer.stream_handler(client_socket)
                        return  # 不关闭连接，由streamer处理
                        
                else:
                    # 尝试静态文件服务
                    response = self.serve_static_file(path, keep_alive)
                
                if response:
                    # 为API响应添加Keep-Alive头
                    if route_key in self.routes and keep_alive:
                        response = self._add_keepalive_header(response)
                    
                    try:
                        client_socket.sendall(response)
                        
                        # 打印请求处理时间
                        if request_start is not None:
                            import utime
                            elapsed = utime.ticks_diff(utime.ticks_ms(), request_start)
                            if elapsed > 1000:  # 超过1秒的请求打印警告
                                print(f"[连接#{conn_id}] ⚠️ 慢请求: {path} 耗时 {elapsed}ms")
                            
                    except OSError as e:
                        print(f"[连接#{conn_id}] 发送响应失败: {e}")
                        return
                else:
                    print(f"[连接#{conn_id}] 警告: 无响应数据 for {path}")
                    return
                
                # 如果客户端不支持Keep-Alive，退出循环
                if not keep_alive:
                    print(f"[连接#{conn_id}] 客户端请求关闭连接")
                    return
                    
        except Exception as e:
            print(f"[连接#{conn_id}] 处理请求错误: {e}")
            import sys
            sys.print_exception(e)
            error_response = self.build_response(500, "Internal Server Error")
            try:
                client_socket.sendall(error_response)
            except:
                pass
        finally:
            # 打印内存使用情况（每10个连接打印一次）
            if conn_id % 10 == 0:
                try:
                    print(f"[内存] 空闲内存: {gc.mem_free()} bytes")
                except:
                    pass
            
            print(f"[连接#{conn_id}] 关闭 (共处理 {request_count} 个请求)")
            try:
                client_socket.close()
            except:
                pass
            gc.collect()  # 强制垃圾回收
    
    def _add_keepalive_header(self, response):
        """为响应添加Keep-Alive头"""
        try:
            # 查找响应头结束位置
            header_end = response.find(b'\r\n\r\n')
            if header_end == -1:
                return response
            
            # 检查是否已有Connection头，替换为keep-alive
            header_part = response[:header_end]
            if b'Connection: close' in header_part or b'Connection: Close' in header_part:
                header_part = header_part.replace(b'Connection: close', b'Connection: keep-alive')
                header_part = header_part.replace(b'Connection: Close', b'Connection: keep-alive')
                return header_part + response[header_end:]
            else:
                # 添加Keep-Alive头
                header_str = header_part.decode('utf-8', 'ignore')
                header_str += '\r\nConnection: keep-alive\r\nKeep-Alive: timeout=5, max=50'
                return header_str.encode('utf-8') + response[header_end:]
        except:
            return response
            
    def serve_static_file(self, path, keep_alive=False):
        """提供静态文件服务"""
        # 默认首页
        if path == '/':
            path = '/index.html'
            
        # 安全检查
        if '..' in path:
            return self.build_response(403, "Forbidden")
            
        # 文件路径 - K230使用/data/static目录
        file_path = '/data/static' + path
        
        # 检查文件是否存在并读取
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                
            # 根据扩展名确定Content-Type
            content_type = self.get_content_type(path)
            
            # 构建响应头
            headers = f"HTTP/1.1 200 OK\r\n"
            headers += f"Content-Type: {content_type}\r\n"
            headers += f"Content-Length: {len(content)}\r\n"
            
            # 添加缓存控制头 - 让浏览器缓存静态资源
            # MicroPython的endswith不支持元组，需要逐个检查
            is_static_resource = (path.endswith('.css') or path.endswith('.js') or 
                                 path.endswith('.jpg') or path.endswith('.jpeg') or 
                                 path.endswith('.png') or path.endswith('.gif') or 
                                 path.endswith('.ico'))
            
            if is_static_resource:
                # 静态资源缓存1小时
                headers += "Cache-Control: public, max-age=3600\r\n"
            elif path.endswith('.html'):
                # HTML文件不缓存，确保能看到最新内容
                headers += "Cache-Control: no-cache\r\n"
            
            if keep_alive:
                headers += "Connection: keep-alive\r\n"
                headers += "Keep-Alive: timeout=5, max=50\r\n"
            else:
                headers += "Connection: close\r\n"
            
            headers += "\r\n"
            
            return headers.encode('utf-8') + content
            
        except OSError as e:
            return self.build_response(404, "Not Found")
            
    def get_content_type(self, path):
        """根据文件扩展名返回Content-Type"""
        if path.endswith('.html'):
            return 'text/html; charset=utf-8'
        elif path.endswith('.css'):
            return 'text/css; charset=utf-8'
        elif path.endswith('.js'):
            return 'application/javascript; charset=utf-8'
        elif path.endswith('.json'):
            return 'application/json; charset=utf-8'
        elif path.endswith('.jpg') or path.endswith('.jpeg'):
            return 'image/jpeg'
        elif path.endswith('.png'):
            return 'image/png'
        elif path.endswith('.gif'):
            return 'image/gif'
        else:
            return 'application/octet-stream'
            
    def build_response(self, status_code, message, content_type='text/plain', body=None):
        """构建HTTP响应"""
        status_messages = {
            200: 'OK',
            404: 'Not Found',
            403: 'Forbidden',
            500: 'Internal Server Error'
        }
        
        status_text = status_messages.get(status_code, 'Unknown')
        
        headers = f"HTTP/1.1 {status_code} {status_text}\r\n"
        headers += f"Content-Type: {content_type}\r\n"
        
        if body is None:
            body = message.encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
            
        headers += f"Content-Length: {len(body)}\r\n"
        headers += "Connection: close\r\n"
        headers += "\r\n"
        
        return headers.encode('utf-8') + body
        
    def json_response(self, data, status_code=200):
        """构建JSON响应"""
        json_str = json.dumps(data)
        return self.build_response(status_code, 'OK', 'application/json', json_str)
