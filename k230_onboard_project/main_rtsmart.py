"""
K230 内窥镜平台 - RT-Smart 版本
C 层 HTTP 服务器 + Python YOLO 检测
"""

import gc
import utime as time
from rtsmart_web_adapter import RTWebAdapter
from detection_manager import DetectionManager
from yolo_controller import YOLOController
from wifi_config import connect_wifi, WIFI_SSID, WIFI_PASSWORD


def start_http_server_with_wifi_awareness():
    """
    启动 HTTP 服务器，具有 WiFi 感知能力
    - HTTP 服务器已通过 C 层自动启动机制运行
    - 无需手动调用 start()
    """
    try:
        import rtsmart_web
        
        print("[RTWeb] 加载 rtsmart_web 模块成功")
        print("[RTWeb] ✅ HTTP 服务器已通过 C 层自动启动")
        
        return True
        
    except ImportError:
        print("[RTWeb] ❌ rtsmart_web 模块未找到")
        return False
    except Exception as e:
        print("[RTWeb] ⚠️ 检查模块时出错: " + str(e))
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
    # ⭐ 降低 JPEG 质量以提高编码速度和推送频率（MJPEG 流需要 30fps）
    # 质量 50 可以显著减小文件大小，加快编码速度
    web_adapter = RTWebAdapter(quality=50)
    
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
    # ⭐ 启动摄像头和检测
    yolo_controller.start_camera()
    yolo_controller.enable_detection()
    
    # ⭐ 关键修复：启动后立即同步状态到 C 层
    # 告诉 C 层"摄像头已启动"，确保网页刷新后能读取到正确状态
    # 等待一小段时间让YOLO线程初始化
    time.sleep(0.5)
    web_adapter.update_runtime(
        yolo_controller.camera_running,
        yolo_controller.detection_enabled,
        yolo_controller.confidence_threshold,
    )
    print("[RTWeb] ✅ 已同步初始状态到 C 层（摄像头: %s, 检测: %s）" % 
          ("运行" if yolo_controller.camera_running else "停止",
           "启用" if yolo_controller.detection_enabled else "禁用"))
    
    # 打印访问信息
    stats = web_adapter.get_stats()
    print("\n" + "=" * 60)
    print("✅ 系统启动成功！")
    print("=" * 60)
    print("🌐 Web 服务器: http://<板子IP>:" + str(stats.get('port', 8080)) + "/")
    print("📊 MJPEG 流: http://<板子IP>:" + str(stats.get('port', 8080)) + "/stream")
    print("🔍 YOLO 检测: ✅ 已启用")
    print("\n💡 使用提示:")
    print("- 在浏览器打开上述地址查看实时视频")
    print("- 按 Ctrl+C 停止程序")
    print("=" * 60 + "\n")
    
    # 保持运行
    try:
        last_print = time.time()
        # ⭐ 关键修复：初始化时先读取一次当前命令版本，避免处理旧的初始状态
        # 因为系统启动时摄像头已启动，但 C 层的 desired 可能还是 false（网页未点击）
        # 如果直接用 last_command_version=0，可能会误判并停止摄像头
        # 等待 HTTP 服务器完全启动（延迟 2 秒，给网络栈足够时间初始化）
        time.sleep(2.0)
        
        initial_control = None
        for retry in range(5):  # 重试 5 次，给足够的时间让 HTTP 服务器就绪
            initial_control = web_adapter.pull_control()
            if initial_control:
                break
            if retry < 4:  # 最后一次不等待
                time.sleep(0.5)
        
        if initial_control:
            last_command_version = initial_control.get('command_version', 0)
            print("[Control] 🔍 初始化时读取到命令版本: %d (当前摄像头状态: desired=%s, running=%s)" % 
                  (last_command_version, 
                   initial_control.get('camera_desired', None), 
                   initial_control.get('camera_running', None)))
        else:
            last_command_version = 0
            print("[Control] ⚠️ 初始化时无法读取命令版本，将从 0 开始")
            print("[Control] 💡 提示：如果网页端点击按钮后仍无响应，请检查 HTTP API 连接")
        
        # 控制循环：减少 HTTP API 调用频率，避免资源耗尽
        control_check_interval = 1.0  # 每 1 秒检查一次（而不是 0.5 秒）
        last_control_check = time.time()
        
        while True:
            time.sleep(0.5)
            
            # 只在间隔时间到达时检查控制状态（减少 HTTP API 调用，避免 socket 泄漏）
            current_time = time.time()
            if current_time - last_control_check >= control_check_interval:
                last_control_check = current_time
                control = web_adapter.pull_control()
            else:
                control = None  # 跳过本次检查，减少 HTTP API 调用
            
            if control:
                # ⭐ 调试：打印控制信息
                desired_cam = control.get('camera_desired')
                running_cam = control.get('camera_running')
                command_version = control.get('command_version', 0)
                
                # ⭐ 调试：打印完整的控制信息（仅当版本号变化或首次）
                if command_version != last_command_version:
                    print("[Control] 🔍 收到新的控制信息: %s" % str(control))
                
                # ⭐ 关键修复：只处理新的命令（通过 command_version 判断）
                if command_version > last_command_version:
                    print("[Control] 🔄 收到新命令 (版本: %d -> %d), desired_cam=%s, running_cam=%s" % 
                          (last_command_version, command_version, desired_cam, running_cam))
                    last_command_version = command_version
                    
                    if desired_cam is not None:
                        if desired_cam and not yolo_controller.camera_running:
                            print("[Control] ▶️ 收到启动摄像头命令")
                            yolo_controller.start_camera()
                            # ⭐ 关键修复：启动摄像头后，立即同步状态（即使线程还在初始化）
                            # 这样前端刷新后能立即看到"摄像头正在启动"的状态
                            web_adapter.update_runtime(
                                yolo_controller.camera_running,  # 此时为True（已设置）
                                yolo_controller.detection_enabled,
                                yolo_controller.confidence_threshold,
                            )
                            print("[Control] ✅ 已同步启动状态到C层 (camera_running=%s)" % yolo_controller.camera_running)
                        elif (not desired_cam) and yolo_controller.camera_running:
                            print("[Control] ⏹️ 收到停止摄像头命令")
                            yolo_controller.stop_camera()
                            # ⭐ 立即同步状态
                            web_adapter.update_runtime(
                                yolo_controller.camera_running,  # 此时为False（已设置）
                                yolo_controller.detection_enabled,
                                yolo_controller.confidence_threshold,
                            )
                            print("[Control] ✅ 已同步停止状态到C层 (camera_running=%s)" % yolo_controller.camera_running)
                elif command_version == last_command_version:
                    # ⭐ 关键修复：命令版本未变化时，不要自动停止摄像头
                    # 因为启动时摄像头已运行，但 C 层的 desired 可能是 false（网页未点击）
                    # 只有当用户真正点击了"开启/停止"（版本号增加）时，才处理命令
                    # 这里只记录日志，不执行操作，避免误停止已启动的摄像头
                    if desired_cam is not None:
                        if desired_cam != yolo_controller.camera_running:
                            print("[Control] ℹ️ 命令版本未变化 (%d)，状态不一致但不执行操作 (desired=%s, running=%s)" % 
                                  (command_version, desired_cam, yolo_controller.camera_running))
                            print("[Control] 💡 等待用户点击网页按钮（命令版本增加）后才会执行")
                    desired_det = control.get('detection_desired')
                    if desired_det is not None:
                        if desired_det and not yolo_controller.detection_enabled:
                            print("[Control] 收到启用检测命令")
                            yolo_controller.enable_detection()
                            # ⭐ 立即同步状态
                            web_adapter.update_runtime(
                                yolo_controller.camera_running,
                                yolo_controller.detection_enabled,
                                yolo_controller.confidence_threshold,
                            )
                        elif (not desired_det) and yolo_controller.detection_enabled:
                            print("[Control] 收到禁用检测命令")
                            yolo_controller.disable_detection()
                            # ⭐ 立即同步状态
                            web_adapter.update_runtime(
                                yolo_controller.camera_running,
                                yolo_controller.detection_enabled,
                                yolo_controller.confidence_threshold,
                            )

                    desired_conf = control.get('confidence_desired')
                    if desired_conf is not None:
                        if abs(desired_conf - yolo_controller.confidence_threshold) > 1e-3:
                            print("[Control] 收到置信度调整命令: " + str(desired_conf))
                            yolo_controller.set_confidence_threshold(desired_conf)
                            # ⭐ 立即同步状态
                            web_adapter.update_runtime(
                                yolo_controller.camera_running,
                                yolo_controller.detection_enabled,
                                yolo_controller.confidence_threshold,
                            )

            stats = yolo_controller.get_statistics()
            det_stats = detection_manager.get_statistics()

            # ⭐ 修复：只在状态变化或定期更新时同步状态（避免重复更新）
            # 减少日志输出，只在必要时更新
            
            # ⭐ 关键修复：始终更新统计数据（确保网页端能看到实时数据）
            # 即使FPS为0也要更新，这样前端才能知道系统状态
            total_frames = stats.get('total_frames', 0)
            total_detections = stats.get('total_detections', 0)
            fps = stats.get('fps', 0.0)
            
            # 确保FPS是有效的数值（避免NaN或None）
            if fps is None or fps != fps:  # 检查NaN
                fps = 0.0
            
            web_adapter.update_stats_remote(
                total_frames,
                total_detections,
                fps,
            )
            
            # 调试：每10秒打印一次状态（包括发送到C层的数据）
            if time.time() - last_print >= 10:
                det_count = det_stats.get('total_count', 0)
                print("[Stats] ⏱️ FPS: %.1f | 📊 总帧数: %d | 检测数: %d | 保存记录: %d | 摄像头: %s | 检测: %s" % 
                      (fps, total_frames, total_detections, det_count,
                       "运行" if yolo_controller.camera_running else "停止",
                       "启用" if yolo_controller.detection_enabled else "禁用"))
                print("[Stats] 📤 已发送到C层: FPS=%.2f, 总帧数=%d, 检测数=%d" % 
                      (fps, total_frames, total_detections))
                last_print = time.time()

            gc.collect()
    
    except KeyboardInterrupt:
        print("\n\n⏸️ 停止中...")
        yolo_controller.stop_camera()
        print("✅ 程序已停止")


if __name__ == "__main__":
    main()
