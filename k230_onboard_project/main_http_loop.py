"""
单循环版 HTTP + YOLO 推流示例：
- 不再创建额外线程，所有逻辑在主线程顺序执行
- 周期性同步 HTTP 控制命令与运行/统计状态
"""

import gc
import utime as time

from libs.PipeLine import PipeLine
from libs.YOLO import YOLOv5

from rtsmart_web_adapter import RTWebAdapter
from wifi_config import WIFI_PASSWORD, WIFI_SSID, connect_wifi

# 可按需调整的基础配置
RGB888P_SIZE = [640, 360]
MODEL_INPUT_SIZE = [640, 640]
LABELS = ["polyp"]
DISPLAY_MODE = "lcd"
CONF_THRESHOLD = 0.5
NMS_THRESHOLD = 0.45
FRAME_PUSH_INTERVAL_MS = 100  # 控制 update_stats_remote 周期


def main():
    print("=" * 60)
    print("HTTP + YOLO 单线程推流模式（无 MicroPython _thread）")
    print("=" * 60)

    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("[Wi-Fi] 连接失败，退出")
        return

    # 启动 C 端 HTTP 服务器
    import rtsmart_web

    rtsmart_web.start_server()
    print("[HTTP] 服务器已启动")

    web = RTWebAdapter(quality=50)

    # 初始化视频 Pipeline 与 YOLO
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=DISPLAY_MODE)
    pl.create()
    display_size = pl.get_display_size()

    yolo = YOLOv5(
        task_type="detect",
        mode="video",
        kmodel_path="/data/model.kmodel",
        labels=LABELS,
        rgb888p_size=RGB888P_SIZE,
        model_input_size=MODEL_INPUT_SIZE,
        display_size=display_size,
        conf_thresh=CONF_THRESHOLD,
        nms_thresh=NMS_THRESHOLD,
        debug_mode=0,
    )
    yolo.config_preprocess()

    detection_enabled = False
    stream_enabled = True
    total_frames = 0
    total_detections = 0
    last_stats_ts = time.ticks_ms()
    last_frames = 0

    def report_runtime():
        web.update_runtime(stream_enabled, detection_enabled, yolo.conf_thresh)

    report_runtime()
    print("[提示] 浏览器访问 http://<板子IP>:8080/")

    try:
        while True:
            frame = pl.get_frame()
            total_frames += 1

            results = None
            if detection_enabled:
                results = yolo.run(frame)
                total_detections += len(results) if results else 0
                yolo.draw_result(results, pl.osd_img)

            pl.show_image()

            if stream_enabled:
                try:
                    web.update_frame(pl.osd_img)
                except Exception as err:
                    print("[HTTP] 推帧失败：", err)

            now = time.ticks_ms()
            if time.ticks_diff(now, last_stats_ts) >= FRAME_PUSH_INTERVAL_MS:
                elapsed = max(time.ticks_diff(now, last_stats_ts) / 1000, 0.001)
                fps = (total_frames - last_frames) / elapsed
                web.update_stats_remote(total_frames, total_detections, fps)
                last_stats_ts = now
                last_frames = total_frames

            # 处理来自网页的控制命令
            ctrl = web.pull_control()
            if ctrl:
                desired_stream = bool(ctrl.get("camera_desired"))
                desired_det = bool(ctrl.get("detection_desired"))
                desired_conf = ctrl.get("confidence_desired", yolo.conf_thresh)

                if desired_stream != stream_enabled:
                    stream_enabled = desired_stream
                    print("[HTTP] 摄像头流状态 ->", "开启" if stream_enabled else "暂停")

                if desired_det != detection_enabled:
                    detection_enabled = desired_det
                    print("[HTTP] 检测状态 ->", "开启" if detection_enabled else "关闭")

                # 置信度阈值
                if isinstance(desired_conf, (int, float)) and 0.01 <= desired_conf <= 0.99:
                    yolo.conf_thresh = desired_conf

                report_runtime()

            gc.collect()
    except KeyboardInterrupt:
        print("\n[系统] 捕获 Ctrl+C，正在退出...")
    finally:
        try:
            yolo.deinit()
        except Exception:
            pass
        try:
            pl.destroy()
        except Exception:
            pass
        report_runtime()
        print("[系统] 已清理资源，程序结束")


if __name__ == "__main__":
    main()

