"""
单循环版 HTTP + YOLO 推流示例：
- 不再创建额外线程，所有逻辑在主线程顺序执行
- 周期性同步 HTTP 控制命令与运行/统计状态
- 集成检测记录管理功能
"""

import gc
import utime as time

from libs.PipeLine import PipeLine
from libs.YOLO import YOLOv5

from rtsmart_web_adapter import RTWebAdapter
from detection_manager import DetectionManager
from wifi_config import WIFI_PASSWORD, WIFI_SSID, connect_wifi

# ============================================
# 配置参数
# ============================================
RGB888P_SIZE = [640, 360]
MODEL_INPUT_SIZE = [640, 640]
LABELS = ["polyp"]
DISPLAY_MODE = "lcd"
CONF_THRESHOLD = 0.5
NMS_THRESHOLD = 0.45
FRAME_PUSH_INTERVAL_MS = 100  # 控制 update_stats_remote 周期
DETECTION_SAVE_THRESHOLD = 0.3  # 保存检测记录的置信度阈值
MAX_CONSECUTIVE_FAILURES = 5
RECORD_CHECK_INTERVAL_MS = 1000  # 每秒检查一次记录删除/清空请求


# ============================================
# 辅助函数
# ============================================
def save_detection_records(results, detection_manager, save_img, threshold):
    """
    保存检测记录（兼容不同 YOLO 返回格式）
    
    可以处理两类常见格式：
    1) 列表字典格式：[{"bbox":[x,y,w,h], "confidence":0.9}, ...]
    2) 模型返回的元组/列表格式：(dets, ids, scores)，其中 dets=[[x,y,w,h],...], scores=[...]

    Args:
        results: YOLO 检测结果（见上）
        detection_manager: 检测管理器实例
        save_img: 要保存的图像对象
        threshold: 置信度阈值
    """
    if save_img is None or results is None:
        return

    try:
        # 1) 处理字典列表格式
        if isinstance(results, (list, tuple)) and len(results) > 0 and hasattr(results[0], 'get'):
            for result in results:
                confidence = float(result.get('confidence', 0.0))
                if confidence >= threshold:
                    bbox = result.get('bbox', [0, 0, 0, 0])
                    try:
                        rec_id = detection_manager.add_detection(image=save_img, bbox=bbox, confidence=confidence)
                        if rec_id:
                            print(f"[检测管理] 已保存记录 id={rec_id}, 置信度={confidence:.2f}, bbox={bbox}")
                    except Exception as e:
                        # 保存失败不影响主流程
                        print(f"[检测管理] 保存检测记录异常: {e}")
                        pass
            return

        # 2) 处理 (dets, ids, scores) 格式：dets 为 list, scores 为 list/array
        if isinstance(results, (list, tuple)) and len(results) >= 3:
            dets = results[0]
            scores = results[2]
            # dets 可能为空
            if dets:
                for i, bbox in enumerate(dets):
                    try:
                        confidence = float(scores[i]) if (scores is not None and i < len(scores)) else 0.0
                    except Exception:
                        confidence = 0.0
                    if confidence >= threshold:
                        try:
                            rec_id = detection_manager.add_detection(image=save_img, bbox=bbox, confidence=confidence)
                            if rec_id:
                                print(f"[检测管理] 已保存记录 id={rec_id}, 置信度={confidence:.2f}, bbox={bbox}")
                        except Exception as e:
                            print(f"[检测管理] 保存检测记录异常: {e}")
                            # 保存失败不影响主流程
                            pass
                return

        # 3) 兼容：results 为 (dets, scores) 之类简化格式
        if isinstance(results, (list, tuple)) and len(results) == 2:
            dets = results[0]
            scores = results[1]
            if dets:
                for i, bbox in enumerate(dets):
                    try:
                        confidence = float(scores[i]) if (scores is not None and i < len(scores)) else 0.0
                    except Exception:
                        confidence = 0.0
                    if confidence >= threshold:
                        try:
                            rec_id = detection_manager.add_detection(image=save_img, bbox=bbox, confidence=confidence)
                            if rec_id:
                                print(f"[检测管理] 已保存记录 id={rec_id}, 置信度={confidence:.2f}, bbox={bbox}")
                        except Exception as e:
                            print(f"[检测管理] 保存检测记录异常: {e}")
                            pass
            return
    except Exception as e:
        # 出现未知格式或处理异常，打印调试信息（但不阻塞主流程）
        try:
            print("[检测管理] 保存检测记录失败，解析results时异常: ", e)
        except Exception:
            pass
        return


def get_stream_image(pl, detection_enabled=False, overlay_osd=True):
    """
    从 PipeLine 获取用于推流的 image.Image 对象（优先使用通道0）
    Args:
        pl: PipeLine 实例
        detection_enabled: 如果 True，则尝试叠加 pl.osd_img
        overlay_osd: 是否在输出图像上叠加 OSD
    Returns:
        image.Image 或 None
    """
    try:
        from media.sensor import CAM_CHN_ID_0
        img = pl.sensor.snapshot(chn=CAM_CHN_ID_0)
        # 叠加 OSD 图层（检测框）
        if overlay_osd and detection_enabled and getattr(pl, 'osd_img', None) is not None:
            try:
                img.draw_image(pl.osd_img, 0, 0, alpha=256)
            except Exception:
                pass
        return img
    except Exception as e:
        print(f"[HTTP] 获取 stream 图像失败: {e}")
        return None


def init_web_adapter(quality=50, debug_verbose=False):
    """
    初始化 Web 适配器，支持新旧版本兼容
    
    Args:
        quality: JPEG 压缩质量
        
    Returns:
        RTWebAdapter 实例
    """
    try:
        return RTWebAdapter(
            quality=quality,
            control_poll_interval_ms=5000,
            use_http_api_for_control=False,
            min_push_interval_ms=100
            ,debug_verbose=debug_verbose
        )
    except TypeError:
        # 兼容旧版本：只使用基本参数
        print("[HTTP] ⚠️ 使用兼容模式初始化RTWebAdapter（旧版本不支持新参数）")
        web = RTWebAdapter(quality=quality, debug_verbose=debug_verbose)
        # 如果支持setter方法，尝试设置
        if hasattr(web, 'set_control_poll_interval'):
            web.set_control_poll_interval(5000)
        if hasattr(web, 'set_min_push_interval'):
            web.set_min_push_interval(100)
        return web


# ============================================
# 主程序
# ============================================
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

    # 初始化 Web 适配器
    web = init_web_adapter(quality=50, debug_verbose=True)

    # 初始化检测记录管理器
    detection_manager = DetectionManager(save_dir='/data/detections', max_records=100)
    detection_manager.set_web_adapter(web)  # 关联web适配器，用于同步记录到HTTP服务器
    print("[检测管理] 检测记录管理器已初始化")

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

    # 初始化运行时状态
    detection_enabled = False
    stream_enabled = True
    total_frames = 0
    total_detections = 0
    last_stats_ts = time.ticks_ms()
    last_frames = 0
    last_record_check_ts = time.ticks_ms()
    consecutive_failures = 0

    # 更新并打印初始状态
    web.update_runtime(stream_enabled, detection_enabled, yolo.conf_thresh)
    print("[提示] 浏览器访问 http://<板子IP>:8080/")

    # 主循环
    try:
        
        while True:
            # ----------------------------------------
            # 1. 获取摄像头帧
            # ----------------------------------------
            try:
                frame = pl.get_frame()
                consecutive_failures = 0  # 重置失败计数
                total_frames += 1
            except RuntimeError as e:
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    print(f"[PipeLine] ⚠️ get_frame()失败 (连续{consecutive_failures}次): {e}")
                elif consecutive_failures == MAX_CONSECUTIVE_FAILURES:
                    print(f"[PipeLine] ❌ get_frame()连续失败{MAX_CONSECUTIVE_FAILURES}次，可能传感器异常")
                time.sleep_ms(50)
                continue
            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    print(f"[PipeLine] ⚠️ get_frame()异常: {e}")
                time.sleep_ms(50)
                continue

            # ----------------------------------------
            # 2. YOLO 检测处理
            # ----------------------------------------
            results = None
            if detection_enabled:
                results = yolo.run(frame)
                if results:
                    total_detections += len(results)
                    yolo.draw_result(results, pl.osd_img)
                    
                    # 使用 sensor.snapshot() 获取 RGB888 Image 用于保存检测记录
                    try:
                        from media.sensor import CAM_CHN_ID_2
                        save_img = pl.sensor.snapshot(chn=CAM_CHN_ID_2)
                        # Debug: print type and results summary
                        try:
                            print(f"[检测管理] 尝试保存 snapshot（通道2），结果类型={type(save_img)}, 检测数量={len(results) if results else 0}")
                        except Exception:
                            pass
                        save_detection_records(results, detection_manager, save_img, DETECTION_SAVE_THRESHOLD)
                    except Exception as e:
                        if total_detections <= 3:
                            print(f"[检测管理] 获取snapshot失败: {e}")

            # ----------------------------------------
            # 3. 显示图像(OSD层,包含检测框)
            # ----------------------------------------
            pl.show_image()

            # ----------------------------------------
            # 4. HTTP 视频推流
            # ----------------------------------------
            if stream_enabled:
                try:
                    # 从 helper 获取用于推流的 image.Image
                    stream_img = get_stream_image(pl, detection_enabled=detection_enabled, overlay_osd=True)
                    if stream_img is not None:
                        web.update_frame(stream_img)
                        if total_frames <= 3:
                            try:
                                print(f"[HTTP] ✅ 使用 helper 获取并推流, 尺寸: {stream_img.width()}x{stream_img.height()}")
                            except Exception:
                                print(f"[HTTP] ✅ 使用 helper 获取并推流")
                        # 保存检测记录(使用同一张图像)
                        if detection_enabled and results:
                            save_detection_records(results, detection_manager, stream_img, DETECTION_SAVE_THRESHOLD)
                    elif total_frames % 30 == 0:
                        print("[HTTP] ⚠️ 无法获取有效的image.Image对象用于推流")
                except Exception as err:
                    if total_frames % 30 == 0:
                        print("[HTTP] 推帧失败：", err)

            # ----------------------------------------
            # 5. 更新统计信息
            # ----------------------------------------
            now = time.ticks_ms()
            if time.ticks_diff(now, last_stats_ts) >= FRAME_PUSH_INTERVAL_MS:
                elapsed = max(time.ticks_diff(now, last_stats_ts) / 1000, 0.001)
                fps = (total_frames - last_frames) / elapsed
                web.update_stats_remote(total_frames, total_detections, fps)
                last_stats_ts = now
                last_frames = total_frames

            # ----------------------------------------
            # 6. 处理网页控制命令
            # ----------------------------------------
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

                if isinstance(desired_conf, (int, float)) and 0.01 <= desired_conf <= 0.99:
                    yolo.conf_thresh = desired_conf

                web.update_runtime(stream_enabled, detection_enabled, yolo.conf_thresh)

            # ----------------------------------------
            # 7. 定期检查并同步记录（预留接口）
            # ----------------------------------------
            if time.ticks_diff(now, last_record_check_ts) >= RECORD_CHECK_INTERVAL_MS:
                # 注意：HTTP API的删除/清空操作直接调用C层函数
                # 如果需要双向同步，可以在这里实现记录同步逻辑
                last_record_check_ts = now

            # ----------------------------------------
            # 8. 垃圾回收
            # ----------------------------------------
            gc.collect()
            
    except KeyboardInterrupt:
        print("\n[系统] 捕获 Ctrl+C，正在退出...")
    finally:
        # 清理资源
        try:
            yolo.deinit()
        except Exception:
            pass
        try:
            pl.destroy()
        except Exception:
            pass
        
        # 更新最终状态
        web.update_runtime(stream_enabled, detection_enabled, yolo.conf_thresh)
        print("[系统] 已清理资源，程序结束")


if __name__ == "__main__":
    main()

