"""
单循环版 HTTP + YOLO 简化版：
- 不再创建额外线程，所有逻辑在主线程顺序执行
- 周期性同步 HTTP 控制命令与运行/统计状态
- 只保留网页控制开关，去掉图片推流和保存功能
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
    print("HTTP + YOLO 单线程简化模式（无推流）")
    print("=" * 60)

    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("[Wi-Fi] 连接失败，退出")
        return

    # 启动 C 端 HTTP 服务器
    import rtsmart_web

    rtsmart_web.start_server()
    print("[HTTP] 服务器已启动")

    # 初始化web适配器（简化模式，不需要推流参数）
    try:
        web = RTWebAdapter(quality=50, control_poll_interval_ms=5000, use_http_api_for_control=False)
    except TypeError:
        # 兼容旧版本：只使用基本参数
        print("[HTTP] ⚠️ 使用兼容模式初始化RTWebAdapter（旧版本不支持新参数）")
        web = RTWebAdapter(quality=50)
        # 如果支持setter方法，尝试设置
        if hasattr(web, 'set_control_poll_interval'):
            web.set_control_poll_interval(5000)

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
    total_frames = 0
    total_detections = 0
    last_stats_ts = time.ticks_ms()
    last_frames = 0

    def report_runtime():
        web.update_runtime(False, detection_enabled, yolo.conf_thresh)  # 推流始终关闭

    report_runtime()
    print("[提示] 浏览器访问 http://<板子IP>:8080/")

    try:
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5

        while True:
            try:
                frame = pl.get_frame()
                consecutive_failures = 0  # 重置失败计数
                total_frames += 1
            except RuntimeError as e:
                # 处理传感器快照失败
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    print(f"[PipeLine] ⚠️ get_frame()失败 (连续{consecutive_failures}次): {e}")
                elif consecutive_failures == MAX_CONSECUTIVE_FAILURES:
                    print(f"[PipeLine] ❌ get_frame()连续失败{MAX_CONSECUTIVE_FAILURES}次，可能传感器异常")
                # 短暂延迟后重试
                time.sleep_ms(50)
                continue
            except Exception as e:
                # 其他异常
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    print(f"[PipeLine] ⚠️ get_frame()异常: {e}")
                time.sleep_ms(50)
                continue

            results = None
            if detection_enabled:
                results = yolo.run(frame)
                if results:
                    total_detections += len(results)
                    yolo.draw_result(results, pl.osd_img)

            pl.show_image()

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
                desired_det = bool(ctrl.get("detection_desired"))
                desired_conf = ctrl.get("confidence_desired", yolo.conf_thresh)

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
        try:
            pass
        except Exception:
            pass
        report_runtime()
        print("[系统] 已清理资源，程序结束")


if __name__ == "__main__":
    main()

