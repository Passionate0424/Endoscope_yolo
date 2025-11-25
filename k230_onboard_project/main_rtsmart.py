"""
精简版主程序：仅完成 Wi-Fi + HTTP + 推流（不跑检测、不做控制轮询），
用于排查运行时 Instruction Page Fault。退出时确保摄像头停止并同步状态。
"""

import gc
import utime as time

from rtsmart_web_adapter import RTWebAdapter
from wifi_config import WIFI_PASSWORD, WIFI_SSID, connect_wifi
from yolo_controller import YOLOController


def start_http_server():
    """启动 C 层 HTTP 服务器"""
    try:
        import rtsmart_web

        rtsmart_web.start_server()
        print("[RTWeb] HTTP 服务器已启动")
        return True
    except Exception as e:
        print("[RTWeb] 启动 HTTP 服务器失败: %s" % e)
        return False


def main():
    print("=" * 50)
    print("K230 精简推流模式（无检测/无控制）")
    print("=" * 50)

    # 1. 连接 Wi-Fi
    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("Wi-Fi 连接失败，退出")
        return

    # 2. 启动 HTTP 服务器
    if not start_http_server():
        print("HTTP 服务器启动失败，退出")
        return

    # 3. 初始化 Web 适配器与 YOLO
    # 减少 control poll 请求频率，避免设备中频繁的 HTTP 连接超时
    # Prefer the C binding for reading controls to avoid HTTP timeouts in constrained environments
    # 限制推帧速度：例如 min_push_interval_ms=100 -> 最多 10fps
    web_adapter = RTWebAdapter(quality=50, control_poll_interval_ms=5000, use_http_api_for_control=False, min_push_interval_ms=100)
    yolo = YOLOController()
    yolo.set_frame_callback(web_adapter.update_frame)

    # # 4. 启动摄像头（不启用检测）
    # yolo.start_camera()
    # time.sleep(0.5)
    # web_adapter.update_runtime(
    #     yolo.camera_running,
    #     yolo.detection_enabled,
    #     yolo.confidence_threshold,
    # )

    stats = web_adapter.get_stats()
    port = stats.get("port", 8080)
    print("访问：http://<板子IP>:%d/  或  http://<板子IP>:%d/stream" % (port, port))
    print("按 Ctrl+C 停止\n")

    last_print = time.time()
    try:
        while True:
            time.sleep(0.5)
            # 更新统计数据
            s = yolo.get_statistics()
            fps = s.get("fps") or 0.0
            if fps != fps:  # NaN
                fps = 0.0
            web_adapter.update_stats_remote(
                s.get("total_frames", 0),
                s.get("total_detections", 0),
                fps,
            )

            if time.time() - last_print >= 10:
                print(
                    "[Stats] FPS: %.1f | 总帧: %d | 检测: %d | 摄像头: %s"
                    % (
                        fps,
                        s.get("total_frames", 0),
                        s.get("total_detections", 0),
                        "运行" if yolo.camera_running else "停止",
                    )
                )
                last_print = time.time()

            gc.collect()
    except KeyboardInterrupt:
        print("\n停止中...")
    finally:
        yolo.stop_camera()
        web_adapter.update_runtime(
            yolo.camera_running,
            yolo.detection_enabled,
            yolo.confidence_threshold,
        )
        print("程序已退出")


if __name__ == "__main__":
    main()
