from libs.PipeLine import PipeLine
from libs.YOLO import YOLOv5
from libs.Utils import *
import sys, gc
import ulab.numpy as np
import image
import time

# 由于 MicroPython 环境不一定包含完整的 os 模块，这里做兼容处理
try:
    import uos as os_module
except ImportError:
    import os as os_module

# 网络初始化（需要在导入socket之前）
try:
    import network
    NETWORK_AVAILABLE = True
    # 尝试导入以太网相关类（可能不存在）
    try:
        from network import ETH
        ETH_AVAILABLE = True
    except ImportError:
        try:
            from network_lan import ETH
            ETH_AVAILABLE = True
        except ImportError:
            ETH_AVAILABLE = False
except ImportError:
    NETWORK_AVAILABLE = False
    ETH_AVAILABLE = False
    print("Warning: Network module not available")

from http_server import HTTPServer

# 尝试导入RTSP服务器（可选）
try:
    from rtsp_server import RTSPServer
    RTSP_AVAILABLE = True
except ImportError:
    RTSP_AVAILABLE = False
    print("注意: rtsp_server 模块不可用，将使用HTTP/MJPEG方式")

# --------- 可按需修改的配置 ----------
KMODEL_PATH = "/data/model.kmodel"          # 你的 kmodel 路径
LABELS = ["polyp"]                          # 如果有多类别就扩展这个列表
MODEL_INPUT_SIZE = [640, 640]               # 与导出的 kmodel 保持一致
DISPLAY_MODE = None                         # hdmi/lcd/lt9611/st7701/hx8399, None=禁用显示
RGB888P_SIZE = [640, 360]                   # 相机输入尺寸
CONF_THRESHOLD = 0.35                       # 置信度阈值
NMS_THRESHOLD = 0.45                        # NMS 阈值
HTTP_PORT = 80                              # HTTP服务器端口
DETECTIONS_DIR = "/data/detections"         # 检测图像保存目录

# 性能优化配置
ENABLE_DISPLAY = False                      # 是否显示到LCD/HDMI（False可节省资源）
DETECTION_SKIP_FRAMES = 3                   # 每N帧检测一次（降低检测频率）
VIDEO_SKIP_FRAMES = 0                       # 每N帧更新一次视频流（0=每帧都获取，降低可减少频率）

# 视频流配置
USE_RTSP = True                             # 是否使用RTSP推流（推荐，比MJPEG效率高）
RTSP_PORT = 8554                            # RTSP端口
RTSP_STREAM_NAME = "endoscope"              # RTSP流名称
RTSP_VIDEO_TYPE = "h264"                    # 视频编码: "h264" 或 "h265"

# 网络配置
USE_WIFI = True                             # 是否使用WiFi（如果为False，则尝试以太网）
WIFI_SSID = "Passionate的Mate70Pro+"                  # WiFi名称（2.4G频段）
WIFI_PASSWORD = "20050424"          # WiFi密码

# 以太网配置（如果USE_WIFI=False）
USE_STATIC_IP = False                       # 是否使用静态IP
STATIC_IP = "192.168.1.100"                 # 静态IP地址（如果USE_STATIC_IP=True）
STATIC_MASK = "255.255.255.0"               # 子网掩码
STATIC_GW = "192.168.1.1"                   # 网关
# --------------------------------------

def ensure_dir(path):
    """确保目录存在"""
    try:
        # 尝试使用 uos 模块（MicroPython标准）
        try:
            import uos
            uos_module = uos
        except:
            uos_module = os_module
        
        # 检查目录是否存在
        try:
            uos_module.stat(path)
            # 目录存在，返回
            return
        except OSError:
            # 目录不存在，创建
            pass
        
        # 创建目录（支持多级目录）
        parts = path.strip('/').split('/')
        current_path = ''
        for part in parts:
            if not part:
                continue
            if current_path:
                current_path = current_path + '/' + part
            else:
                current_path = '/' + part if path.startswith('/') else part
            
            try:
                uos_module.stat(current_path)
            except OSError:
                try:
                    uos_module.mkdir(current_path)
                except Exception as e:
                    if 'exists' not in str(e).lower():
                        print(f"Create directory error: {e}")
    except Exception as e:
        print(f"Ensure directory error: {e}")

def save_detection_image(frame, results, detections_dir):
    """保存检测到息肉的图像"""
    try:
        ensure_dir(detections_dir)
        
        # 生成文件名：时间戳_置信度
        timestamp = int(time.time() * 1000)
        max_conf = 0
        if results and len(results) > 0:
            # 获取最高置信度
            for r in results:
                if hasattr(r, 'confidence') and r.confidence > max_conf:
                    max_conf = r.confidence
                elif isinstance(r, dict) and 'confidence' in r:
                    max_conf = max(max_conf, r['confidence'])
        
        filename = f"{detections_dir}/polyp_{timestamp}_{int(max_conf*100)}.jpg"
        
        # 保存图像（可能需要根据实际图像格式调整）
        try:
            # 尝试直接保存
            frame.save(filename)
            print(f"Saved detection image: {filename}")
            return filename
        except Exception as e:
            print(f"Save image error (method 1): {e}")
            # 如果直接保存失败，尝试转换为JPEG
            try:
                frame_jpeg = frame.to_jpeg(quality=90)
                with open(filename, 'wb') as f:
                    f.write(frame_jpeg)
                print(f"Saved detection image (JPEG): {filename}")
                return filename
            except Exception as e2:
                print(f"Save image error (method 2): {e2}")
                return None
    except Exception as e:
        print(f"Save detection image error: {e}")
        return None

# 全局网络对象（用于保持网络连接）
network_obj = None

def init_network_wifi():
    """初始化WiFi连接（STA模式）"""
    global network_obj
    
    if not NETWORK_AVAILABLE:
        return False
        
    try:
        print("Initializing WiFi (STA mode)...")
        
        # 创建STA模式的WiFi对象
        sta = network.WLAN(network.STA_IF)
        
        # 激活WiFi
        if not sta.active():
            sta.active(True)
            print("WiFi activated")
        
        # 检查是否已连接
        if sta.isconnected():
            ip_info = sta.ifconfig()
            print(f"Already connected to WiFi!")
            print(f"IP: {ip_info[0]}")
            network_obj = sta
            return True
        
        # 连接到WiFi
        print(f"Connecting to WiFi: {WIFI_SSID}...")
        sta.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # 等待连接（最多20秒）
        max_wait = 20
        wait_count = 0
        
        while wait_count < max_wait:
            if sta.isconnected():
                ip_info = sta.ifconfig()
                print(f"WiFi connected successfully!")
                print(f"IP address: {ip_info[0]}")
                print(f"Subnet mask: {ip_info[1]}")
                print(f"Gateway: {ip_info[2]}")
                print(f"DNS server: {ip_info[3]}")
                network_obj = sta
                return True
            
            time.sleep(1)
            wait_count += 1
            if wait_count % 5 == 0:
                print(f"Waiting for WiFi connection... ({wait_count}/{max_wait})")
        
        print("WiFi connection timeout!")
        return False
        
    except Exception as e:
        print(f"WiFi initialization error: {e}")
        return False

def init_network_ethernet():
    """初始化以太网连接"""
    global network_obj
    
    if not NETWORK_AVAILABLE or not ETH_AVAILABLE:
        return False
        
    try:
        print("Initializing Ethernet...")
        
        # 尝试初始化以太网接口（多种方式兼容）
        eth = None
        
        # 方式1: 带参数的初始化（适用于特定硬件配置）
        try:
            eth = ETH(0, phy_type=ETH.PHY_LAN8720, ref_clk_mode=ETH.REF_CLK_GPIO0, phy_addr=0, ref_clk=23)
            print("Ethernet initialized with parameters")
        except Exception as e1:
            # 方式2: 无参数初始化
            try:
                eth = ETH()
                print("Ethernet initialized without parameters")
            except Exception as e2:
                # 方式3: 尝试从network_lan导入
                try:
                    from network_lan import ETH as ETH_LAN
                    eth = ETH_LAN()
                    print("Ethernet initialized from network_lan")
                except Exception as e3:
                    print(f"Failed to create ETH object:")
                    print(f"  Method 1 error: {e1}")
                    print(f"  Method 2 error: {e2}")
                    print(f"  Method 3 error: {e3}")
                    return False
        
        if eth is None:
            return False
        
        # 配置网络
        if USE_STATIC_IP:
            # 使用静态IP
            print(f"Configuring static IP: {STATIC_IP}")
            try:
                eth.set_ifconfig((STATIC_IP, STATIC_MASK, STATIC_GW, "8.8.8.8"))
            except:
                # 某些版本可能需要不同的参数格式
                try:
                    eth.ifconfig((STATIC_IP, STATIC_MASK, STATIC_GW, "8.8.8.8"))
                except Exception as e:
                    print(f"Failed to set static IP: {e}")
        else:
            # 使用DHCP自动获取IP
            print("Configuring DHCP...")
            try:
                eth.set_ifconfig("dhcp")
            except:
                try:
                    eth.ifconfig("dhcp")
                except Exception as e:
                    print(f"Failed to set DHCP: {e}")
        
        # 启动网络接口
        eth.active(True)
        print("Ethernet interface activated")
        
        # 等待网络连接
        print("Waiting for Ethernet connection...")
        max_wait = 20  # 最多等待20秒
        wait_count = 0
        
        while wait_count < max_wait:
            try:
                ifconfig = eth.ifconfig()
                ip = ifconfig[0] if isinstance(ifconfig, (list, tuple)) else ifconfig
                if ip and ip != '0.0.0.0' and ip != '':
                    print(f"Ethernet connected! IP: {ip}")
                    if isinstance(ifconfig, (list, tuple)) and len(ifconfig) > 1:
                        print(f"Network config: {ifconfig}")
                    network_obj = eth
                    return True
            except Exception as e:
                print(f"Error checking network status: {e}")
                
            time.sleep(1)
            wait_count += 1
            if wait_count % 5 == 0:
                print(f"Waiting... ({wait_count}/{max_wait})")
        
        print("Ethernet initialization timeout!")
        print("Note: Check cable connection.")
        return False
        
    except Exception as e:
        print(f"Ethernet initialization error: {e}")
        return False

def init_network():
    """初始化网络接口（WiFi优先或以太网）"""
    if not NETWORK_AVAILABLE:
        print("Network module not available, skipping network init")
        return False
    
    # 根据配置选择网络类型
    if USE_WIFI:
        # 优先尝试WiFi
        if init_network_wifi():
            return True
        # WiFi失败，尝试以太网作为备选
        print("WiFi failed, trying Ethernet as fallback...")
        return init_network_ethernet()
    else:
        # 优先尝试以太网
        if init_network_ethernet():
            return True
        # 以太网失败，尝试WiFi作为备选
        print("Ethernet failed, trying WiFi as fallback...")
        return init_network_wifi()

def format_detection_results(results):
    """格式化检测结果为可序列化的格式"""
    formatted = []
    if results:
        for r in results:
            if hasattr(r, '__dict__'):
                # 对象类型，提取属性
                item = {
                    'x1': getattr(r, 'x1', 0),
                    'y1': getattr(r, 'y1', 0),
                    'x2': getattr(r, 'x2', 0),
                    'y2': getattr(r, 'y2', 0),
                    'confidence': getattr(r, 'confidence', 0),
                    'class_id': getattr(r, 'class_id', 0),
                    'class_name': getattr(r, 'class_name', 'polyp')
                }
                formatted.append(item)
            elif isinstance(r, dict):
                # 字典类型，直接使用
                formatted.append(r)
            elif isinstance(r, (list, tuple)) and len(r) >= 6:
                # 元组或列表格式: (x1, y1, x2, y2, conf, class_id)
                formatted.append({
                    'x1': r[0],
                    'y1': r[1],
                    'x2': r[2],
                    'y2': r[3],
                    'confidence': r[4] if len(r) > 4 else 0,
                    'class_id': r[5] if len(r) > 5 else 0,
                    'class_name': 'polyp'
                })
    return formatted

def main():
    # 初始化网络（必须在socket使用之前）
    if not init_network():
        print("Warning: Network initialization failed. Servers may not work.")
        print("Continuing without network...")
    
    # 初始化管道（如果禁用显示，使用None）
    actual_display_mode = DISPLAY_MODE if ENABLE_DISPLAY else None
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=actual_display_mode)
    pl.create()
    if actual_display_mode:
        display_size = pl.get_display_size()
    else:
        display_size = RGB888P_SIZE
        print("Display disabled to save resources")

    # 初始化YOLO模型
    yolo = YOLOv5(
        task_type="detect",
        mode="video",
        kmodel_path=KMODEL_PATH,
        labels=LABELS,
        rgb888p_size=RGB888P_SIZE,
        model_input_size=MODEL_INPUT_SIZE,
        display_size=display_size,
        conf_thresh=CONF_THRESHOLD,
        nms_thresh=NMS_THRESHOLD,
        debug_mode=0
    )
    yolo.config_preprocess()

    # 初始化HTTP服务器
    http_server = HTTPServer(port=HTTP_PORT)
    http_server.start()
    
    # 初始化RTSP服务器（如果启用）
    rtsp_server = None
    if USE_RTSP and RTSP_AVAILABLE:
        print(f"尝试启动RTSP服务器...")
        try:
            rtsp_server = RTSPServer(
                port=RTSP_PORT,
                stream_name=RTSP_STREAM_NAME,
                video_type=RTSP_VIDEO_TYPE
            )
            if rtsp_server.start(
                width=RGB888P_SIZE[0],
                height=RGB888P_SIZE[1],
                fps=30,
                bitrate=2000000
            ):
                print(f"✓ RTSP服务器启动成功")
            else:
                print(f"✗ RTSP服务器启动失败，将仅使用HTTP/MJPEG")
                rtsp_server = None
        except Exception as e:
            print(f"RTSP服务器初始化失败: {e}")
            rtsp_server = None
    elif USE_RTSP and not RTSP_AVAILABLE:
        print("注意: RTSP功能未启用（rtsp_server模块不可用）")
    
    # 获取IP地址显示
    ip = "Unknown"
    global network_obj
    if network_obj is not None:
        try:
            ifconfig = network_obj.ifconfig()
            ip = ifconfig[0] if isinstance(ifconfig, (list, tuple)) else ifconfig
            if not ip or ip == '0.0.0.0':
                ip = "Unknown"
        except:
            ip = "Unknown"

    # 确保检测目录存在
    ensure_dir(DETECTIONS_DIR)

    # 上一帧检测结果（用于判断是否检测到息肉）
    last_detection_count = 0
    
    # 帧计数器（用于跳过帧）
    frame_counter = 0
    detection_frame_counter = 0
    
    print("=== 内窥镜息肉检测平台启动 ===")
    print(f"Display: {'Enabled' if ENABLE_DISPLAY else 'Disabled (resource saving mode)'}")
    print(f"Detection skip: Every {DETECTION_SKIP_FRAMES} frames")
    print(f"Video skip: Every {VIDEO_SKIP_FRAMES} frames")
    
    # 显示HTTP服务器信息
    if http_server.running and http_server.socket:
        try:
            server_ip = http_server.socket.getsockname()[0]
            if server_ip == '0.0.0.0':
                server_ip = ip
            print(f"HTTP服务器: http://{server_ip}:{HTTP_PORT}")
        except:
            print(f"HTTP服务器: http://{ip}:{HTTP_PORT}")
    else:
        print(f"HTTP服务器启动失败")
    
    # 显示RTSP服务器信息
    if rtsp_server and rtsp_server.running:
        print(f"RTSP视频流: rtsp://{ip}:{RTSP_PORT}/{RTSP_STREAM_NAME}")
        print(f"  编码格式: {RTSP_VIDEO_TYPE.upper()}")
        print(f"  使用VLC播放: vlc rtsp://{ip}:{RTSP_PORT}/{RTSP_STREAM_NAME}")
    
    print(f"检测图像保存目录: {DETECTIONS_DIR}")
    print("等待连接...")

    try:
        while True:
            # 处理HTTP请求（非阻塞，必须每次循环都调用）
            http_server.loop()
            
            # 检查是否需要采集视频
            if http_server.video_enabled:
                frame_counter += 1
                
                # 获取视频帧（降低获取频率，但每次都更新HTTP服务器）
                # 注意：获取帧可能很耗时，所以降低频率
                should_get_frame = (frame_counter % (VIDEO_SKIP_FRAMES + 1) == 0 or frame_counter == 1)
                
                if should_get_frame:
                    try:
                        # 获取视频帧
                        frame = pl.get_frame()
                        
                        # 更新HTTP服务器的当前帧（用于MJPEG视频流）
                        if frame is not None:
                            http_server.update_frame(frame)
                            
                            # 注意: RTSP推流不需要手动推送帧
                            # K230的RTSP服务器会自动从编码器获取数据并推流
                            
                            if frame_counter == 1 or frame_counter % 30 == 0:  # 第一帧和每30帧打印
                                print(f"Frame {frame_counter}: type={type(frame)}")
                                if hasattr(frame, 'shape'):
                                    print(f"  shape={frame.shape}, dtype={getattr(frame, 'dtype', 'N/A')}")
                                elif hasattr(frame, 'size'):
                                    print(f"  size={frame.size()}")
                                elif hasattr(frame, 'width') and hasattr(frame, 'height'):
                                    print(f"  dims={frame.width()}x{frame.height()}")
                        
                        # 是否进行YOLO检测（降低检测频率）
                        results = None
                        if http_server.detection_enabled:
                            detection_frame_counter += 1
                            
                            # 每N帧检测一次
                            if detection_frame_counter % (DETECTION_SKIP_FRAMES + 1) == 0:
                                results = yolo.run(frame)
                                
                                # 格式化检测结果
                                formatted_results = format_detection_results(results)
                                
                                # 检查是否检测到息肉（新增检测）
                                if formatted_results and len(formatted_results) > 0:
                                    current_count = len(formatted_results)
                                    
                                    # 如果检测到新的息肉，保存图像
                                    if current_count > last_detection_count or current_count > 0:
                                        # 保存检测图像（异步处理，避免阻塞）
                                        try:
                                            # 只保存一次，避免重复
                                            if last_detection_count == 0:
                                                saved_frame = frame.copy() if hasattr(frame, 'copy') else frame
                                                
                                                saved_path = save_detection_image(
                                                    saved_frame, 
                                                    formatted_results, 
                                                    DETECTIONS_DIR
                                                )
                                                
                                                if saved_path:
                                                    http_server.add_detection(saved_frame, formatted_results)
                                                    
                                        except Exception as e:
                                            print(f"Save detection error: {e}")
                                            
                                    last_detection_count = current_count
                                    
                                    # 在显示图像上绘制检测结果（如果启用显示）
                                    if ENABLE_DISPLAY:
                                        try:
                                            yolo.draw_result(results, pl.osd_img)
                                        except:
                                            pass
                                else:
                                    last_detection_count = 0
                        
                        # 显示图像（如果启用显示，降低频率）
                        if ENABLE_DISPLAY and frame_counter % 2 == 0:
                            try:
                                pl.show_image()
                            except:
                                pass
                                
                    except Exception as e:
                        print(f"Frame processing error: {e}")
                        time.sleep(0.05)  # 出错时短暂休眠
                else:
                    # 跳过帧时，短暂休眠节省CPU
                    time.sleep(0.01)
                    
                # 定期垃圾回收
                if frame_counter % 30 == 0:
                    gc.collect()
                    
            else:
                # 视频未启用，休眠一段时间以节省资源（但仍需处理HTTP请求）
                time.sleep(0.05)  # 减少休眠时间，确保HTTP响应及时
                gc.collect()
                
            gc.collect()
            
    except KeyboardInterrupt:
        print("\n收到停止信号，正在关闭...")
    except Exception as e:
        print(f"Main loop error: {e}")
        # 不打印 traceback（MicroPython 可能不支持）
        pass
    finally:
        print("清理资源...")
        http_server.stop()
        
        # 停止RTSP服务器
        if rtsp_server:
            rtsp_server.stop()
        
        yolo.deinit()
        pl.destroy()
        print("程序已退出")

if __name__ == "__main__":
    main()