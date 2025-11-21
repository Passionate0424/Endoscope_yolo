"""
K230 内窥镜平台 - RT-Smart 版本
C 层 HTTP 服务器 + Python YOLO 检测
"""

import gc
import time
from rtsmart_web_adapter import RTWebAdapter
from detection_manager import DetectionManager
from yolo_controller import YOLOController
from wifi_config import connect_wifi, WIFI_SSID, WIFI_PASSWORD


def start_http_server_with_wifi_awareness():
    """
    启动 HTTP 服务器，具有 WiFi 感知能力
    - 使用新的 rtsmart_web 模块中的自动监控线程
    - 无需手动 http_start 命令
    """
    try:
        import rtsmart_web
        
        print("[RTWeb] 加载 rtsmart_web 模块成功")
        
        # 调用 start() 触发 WiFi 监控线程
        print("[RTWeb] 🌐 启动 WiFi 感知自启动系统...")
        rtsmart_web.start()
        
        print("[RTWeb] 📡 WiFi 监控线程已启动，等待网络就绪...")
        print("[RTWeb] ⏳ 最多等待 60 秒 (可在日志中跟踪进度)")
        
        return True
        
    except ImportError:
        print("[RTWeb] ❌ rtsmart_web 模块未找到")
        return False
    except Exception as e:
        print(f"[RTWeb] ❌ 启动异常: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🎯 K230 内窥镜 YOLO 检测系统 - 启动")
    print("=" * 60 + "\n")
    
    # 0. 使用新的 WiFi 感知自启动
    print("[0/4] 启动 HTTP 服务器 (WiFi 感知自启动)...")
    http_started = start_http_server_with_wifi_awareness()
    
    if not http_started:
        print("⚠️ WiFi 感知启动失败，尝试备用方案...")
        try:
            import auto_http_server
            auto_http_server.start_http_server()
        except:
            print("⚠️ 备用启动也失败")
            print("💡 请在大核串口手动执行: http_start")
    
    # 1. 连接 Wi-Fi
    print("\n[1/4] 连接 Wi-Fi...")
    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("❌ Wi-Fi 连接失败")
        return
    
    # 2. 初始化 RT-Smart Web 适配器
    print("\n[2/4] 初始化 RT-Smart Web 适配器...")
    web_adapter = RTWebAdapter(quality=75)
    
    print("[RTWeb] ✅ Web 适配器初始化完成")
    
    # 3. 初始化 YOLO 检测
    print("\n[3/4] 初始化 YOLO 检测...")
    yolo_controller = YOLOController()
    detection_manager = DetectionManager()
    
    # 设置回调
    detection_manager.set_web_adapter(web_adapter)
    yolo_controller.set_frame_callback(web_adapter.update_frame)
    yolo_controller.set_detection_callback(detection_manager.add_detection)
    
    # 4. 启动系统
    print("\n[4/4] 启动系统...")
    yolo_controller.start_camera()
    yolo_controller.enable_detection()
    
    # 打印访问信息
    stats = web_adapter.get_stats()
    print("\n" + "=" * 60)
    print("✅ 系统启动成功！")
    print("=" * 60)
    print(f"🌐 Web 服务器: http://<板子IP>:{stats.get('port', 8080)}/")
    print(f"📊 MJPEG 流: http://<板子IP>:{stats.get('port', 8080)}/stream")
    print("🔍 YOLO 检测: ✅ 已启用")
    print("\n💡 使用提示:")
    print("- 在浏览器打开上述地址查看实时视频")
    print("- 按 Ctrl+C 停止程序")
    print("=" * 60 + "\n")
    
    # 保持运行
    try:
        last_print = time.time()
        while True:
            time.sleep(1)

            control = web_adapter.pull_control()
            if control:
                desired_cam = control.get('camera_desired')
                if desired_cam is not None:
                    if desired_cam and not yolo_controller.camera_running:
                        yolo_controller.start_camera()
                    elif (not desired_cam) and yolo_controller.camera_running:
                        yolo_controller.stop_camera()

                desired_det = control.get('detection_desired')
                if desired_det is not None:
                    if desired_det and not yolo_controller.detection_enabled:
                        yolo_controller.enable_detection()
                    elif (not desired_det) and yolo_controller.detection_enabled:
                        yolo_controller.disable_detection()

                desired_conf = control.get('confidence_desired')
                if desired_conf is not None:
                    if abs(desired_conf - yolo_controller.confidence_threshold) > 1e-3:
                        yolo_controller.set_confidence_threshold(desired_conf)

            stats = yolo_controller.get_statistics()
            det_stats = detection_manager.get_statistics()

            web_adapter.update_runtime(
                yolo_controller.camera_running,
                yolo_controller.detection_enabled,
                yolo_controller.confidence_threshold,
            )
            web_adapter.update_stats_remote(
                stats.get('total_frames', 0),
                stats.get('total_detections', 0),
                stats.get('fps', 0.0),
            )

            if time.time() - last_print >= 10:
                fps = stats.get('fps', 0.0)
                total_detections = det_stats.get('total_count', 0)
                print("[Stats] ⏱️ FPS: %.1f | 📊 检测数: %d" % (fps, total_detections))
                last_print = time.time()

            gc.collect()
    
    except KeyboardInterrupt:
        print("\n\n⏸️ 停止中...")
        yolo_controller.stop_camera()
        print("✅ 程序已停止")


if __name__ == "__main__":
    main()
