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

# 可按需调整的基础配置
RGB888P_SIZE = [640, 360]
MODEL_INPUT_SIZE = [640, 640]
LABELS = ["polyp"]
DISPLAY_MODE = "lcd"
CONF_THRESHOLD = 0.5
NMS_THRESHOLD = 0.45
FRAME_PUSH_INTERVAL_MS = 100  # 控制 update_stats_remote 周期
DETECTION_SAVE_THRESHOLD = 0.3  # 保存检测记录的置信度阈值


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

    # 减少 control poll 请求频率，避免设备中频繁的 HTTP 连接超时
    # 说明：如果 HTTP API 经常超时，使用 C 绑定来获取控制信息会更可靠且更轻量级。
    # 限制推帧速度：例如 min_push_interval_ms=100 -> 最多 10fps
    # 注意：如果设备上的rtsmart_web_adapter.py版本较旧，可能需要使用位置参数
    try:
        web = RTWebAdapter(quality=50, control_poll_interval_ms=5000, use_http_api_for_control=False, min_push_interval_ms=100)
    except TypeError:
        # 兼容旧版本：只使用基本参数
        print("[HTTP] ⚠️ 使用兼容模式初始化RTWebAdapter（旧版本不支持新参数）")
        web = RTWebAdapter(quality=50)
        # 如果支持setter方法，尝试设置
        if hasattr(web, 'set_control_poll_interval'):
            web.set_control_poll_interval(5000)
        if hasattr(web, 'set_min_push_interval'):
            web.set_min_push_interval(100)

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

    detection_enabled = False
    stream_enabled = True
    total_frames = 0
    total_detections = 0
    last_stats_ts = time.ticks_ms()
    last_frames = 0
    last_record_check_ts = time.ticks_ms()
    RECORD_CHECK_INTERVAL_MS = 1000  # 每秒检查一次记录删除/清空请求

    def report_runtime():
        web.update_runtime(stream_enabled, detection_enabled, yolo.conf_thresh)

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
                    
                    # 保存检测记录（仅保存置信度足够高的检测结果）
                    # 根据官方API文档：get_frame()返回RGBP888格式的ndarray (3, H, W)
                    # 参考：https://www.kendryte.com/k230_canmv/zh/main/zh/api/openmv/image.html
                    # 需要转换为(H, W, 3)格式后使用image.Image()构造函数
                    import image
                    save_img = None
                    
                    # 将frame (RGBP888格式ndarray) 转换为image.Image对象
                    # 使用与推流相同的转换方法
                    if frame is not None:
                        try:
                            # RGBP888格式：分离的RGB平面，形状为(3, H, W)
                            # 使用transpose转换为(H, W, 3)格式（RGB888格式）
                            if len(frame.shape) == 3 and frame.shape[0] == 3:
                                frame_rgb888 = frame.transpose(1, 2, 0)
                                
                                # 使用正确的CanMV API创建 image.Image
                                # 根据CanMV文档：image.Image()只接受1个位置参数，其他参数必须使用关键字参数
                                # 参考：https://www.kendryte.com/k230_canmv/zh/main/zh/api/openmv/image.html
                                h, w = frame_rgb888.shape[0], frame_rgb888.shape[1]
                                try:
                                    # 方法1：转换为bytearray，使用关键字参数形式
                                    if hasattr(frame_rgb888, 'tobytes'):
                                        img_bytes = bytearray(frame_rgb888.tobytes())
                                    else:
                                        # 手动转换
                                        img_bytes = bytearray(w * h * 3)
                                        idx = 0
                                        for y in range(h):
                                            for x in range(w):
                                                img_bytes[idx] = int(frame_rgb888[y, x, 0])
                                                img_bytes[idx + 1] = int(frame_rgb888[y, x, 1])
                                                img_bytes[idx + 2] = int(frame_rgb888[y, x, 2])
                                                idx += 3
                                    save_img = image.Image(width=w, height=h, format=image.RGB888, data=img_bytes)
                                except Exception as e1:
                                    # 方法2：尝试使用ndarray作为data参数（使用ALLOC_REF引用现有数据）
                                    try:
                                        save_img = image.Image(width=w, height=h, format=image.RGB888, data=frame_rgb888, alloc=image.ALLOC_REF)
                                    except Exception as e2:
                                        # 转换失败，将在后面回退到osd_img
                                        if total_detections % 10 == 0:
                                            print(f"[检测管理] frame转Image失败: {e2}")
                                        raise e2
                            elif len(frame.shape) == 3 and frame.shape[2] == 3:
                                # 如果已经是(H, W, 3)格式，使用关键字参数形式创建Image
                                try:
                                    h, w = frame.shape[0], frame.shape[1]
                                    # 转换为bytearray
                                    if hasattr(frame, 'tobytes'):
                                        img_bytes = bytearray(frame.tobytes())
                                    else:
                                        img_bytes = bytearray(w * h * 3)
                                        idx = 0
                                        for y in range(h):
                                            for x in range(w):
                                                img_bytes[idx] = int(frame[y, x, 0])
                                                img_bytes[idx + 1] = int(frame[y, x, 1])
                                                img_bytes[idx + 2] = int(frame[y, x, 2])
                                                idx += 3
                                    save_img = image.Image(width=w, height=h, format=image.RGB888, data=img_bytes)
                                except Exception:
                                    if hasattr(pl, 'osd_img') and pl.osd_img is not None:
                                        save_img = pl.osd_img
                                    else:
                                        save_img = None
                            else:
                                # 格式不对，回退到osd_img
                                if hasattr(pl, 'osd_img') and pl.osd_img is not None:
                                    save_img = pl.osd_img
                                else:
                                    save_img = None
                        except Exception as e:
                            # 转换失败，回退到osd_img
                            if total_detections % 10 == 0:
                                print("[检测管理] frame转Image失败:", e)
                            if hasattr(pl, 'osd_img') and pl.osd_img is not None:
                                save_img = pl.osd_img
                            else:
                                save_img = None
                    elif hasattr(pl, 'osd_img') and pl.osd_img is not None:
                        save_img = pl.osd_img
                    else:
                        save_img = None
                    
                    if save_img is not None:
                        for result in results:
                            confidence = result.get('confidence', 0.0)
                            if confidence >= DETECTION_SAVE_THRESHOLD:
                                # 获取边界框信息
                                bbox = result.get('bbox', [0, 0, 0, 0])
                                # 保存检测记录（使用image.Image对象）
                                try:
                                    detection_manager.add_detection(
                                        image=save_img,
                                        bbox=bbox,
                                        confidence=confidence
                                    )
                                except Exception as e:
                                    # 保存失败不影响主流程
                                    if total_detections % 10 == 0:  # 每10次检测打印一次错误
                                        print("[检测管理] 保存检测记录失败:", e)

            pl.show_image()

            if stream_enabled:
                try:
                    # 根据官方API文档：get_frame()返回RGBP888格式的ndarray (3, H, W)
                    # osd_img只包含OSD绘制层，不包含原始图像，所以显示彩格
                    # 需要从get_frame()的ndarray创建image.Image对象
                    # 参考：https://www.kendryte.com/k230_canmv/zh/main/zh/api/aidemo/PipeLine%20%E6%A8%A1%E5%9D%97%20API%20%E6%89%8B%E5%86%8C.html
                    import image
                    stream_img = None
                    
                    # 优先尝试从frame转换（包含原始摄像头画面）
                    # 参考 OpenMV 文档：https://docs.openmv.io/library/omv.image.html
                    # image.Image() 构造函数不接受 ndarray，需要从 bytes/bytearray 创建
                    if frame is not None and len(frame.shape) == 3 and frame.shape[0] == 3:
                        try:
                            h, w = frame.shape[1], frame.shape[2]
                            # RGBP888格式：分离的RGB平面，形状为(3, H, W)
                            # 使用transpose转换为(H, W, 3)格式（RGB888格式）
                            frame_rgb888 = frame.transpose(1, 2, 0)
                            
                            # 根据CanMV API文档：image.Image()只接受1个位置参数（文件路径），其他参数必须使用关键字参数
                            # 参考：https://www.kendryte.com/k230_canmv/zh/main/zh/api/openmv/image.html
                            # 正确用法：image.Image(width=w, height=h, format=image.RGB888, data=...)
                            try:
                                # 方法1：转换为bytearray，使用关键字参数创建Image对象
                                try:
                                    # 将 ndarray 转换为 bytearray
                                    if hasattr(frame_rgb888, 'tobytes'):
                                        img_bytes = bytearray(frame_rgb888.tobytes())
                                    else:
                                        # 手动转换
                                        img_bytes = bytearray(w * h * 3)
                                        idx = 0
                                        for y in range(h):
                                            for x in range(w):
                                                img_bytes[idx] = int(frame_rgb888[y, x, 0])
                                                img_bytes[idx + 1] = int(frame_rgb888[y, x, 1])
                                                img_bytes[idx + 2] = int(frame_rgb888[y, x, 2])
                                                idx += 3
                                    
                                    # 使用关键字参数：image.Image(width=w, height=h, format=image.RGB888, data=img_bytes)
                                    stream_img = image.Image(width=w, height=h, format=image.RGB888, data=img_bytes)
                                    if total_frames <= 3:
                                        print(f"[HTTP] ✅ 方法1成功：image.Image(width={w}, height={h}, format=RGB888, data=bytearray)，大小: {len(img_bytes)} 字节")
                                except Exception as e1:
                                    if total_frames <= 5:
                                        print(f"[HTTP] ⚠️ 方法1失败（关键字参数）: {e1}")
                                    
                                    # 方法2：尝试使用ndarray作为data参数（使用ALLOC_REF引用现有数据）
                                    try:
                                        stream_img = image.Image(width=w, height=h, format=image.RGB888, data=frame_rgb888, alloc=image.ALLOC_REF)
                                        if total_frames <= 3:
                                            print(f"[HTTP] ✅ 方法2成功：image.Image(width={w}, height={h}, format=RGB888, data=ndarray, alloc=ALLOC_REF)")
                                    except Exception as e2:
                                        if total_frames <= 5:
                                            print(f"[HTTP] ⚠️ 方法2失败（ndarray+ALLOC_REF）: {e2}")
                                        raise e2
                            except Exception as e:
                                if total_frames <= 5:
                                    print(f"[HTTP] ⚠️ frame转Image失败: {e}")
                                raise e
                        except Exception as conv_err:
                            if total_frames <= 5:
                                print("[HTTP] ⚠️ frame转Image失败:", conv_err)
                                print(f"[HTTP]   frame类型: {type(frame)}, shape: {frame.shape if hasattr(frame, 'shape') else 'N/A'}")
                    
                    # 如果转换失败，回退到osd_img（虽然可能只包含绘制结果）
                    if stream_img is None and hasattr(pl, 'osd_img') and pl.osd_img is not None:
                        stream_img = pl.osd_img
                        if total_frames <= 3:
                            print("[HTTP] ⚠️ 回退到pl.osd_img（可能只包含绘制结果，显示彩格）")
                    
                    if stream_img is not None:
                        web.update_frame(stream_img)
                    elif total_frames % 30 == 0:
                        print("[HTTP] ⚠️ 无法获取有效的image.Image对象用于推流")
                except Exception as err:
                    if total_frames % 30 == 0:
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

            # 定期检查并处理记录删除/清空请求（通过C层状态同步）
            # 注意：HTTP API的删除/清空操作直接调用C层函数，Python层需要同步
            # 当前实现：DetectionManager保存记录时会通过web_adapter同步到C层
            # 但C层的删除操作不会自动同步到Python层（这是设计上的限制）
            # 如果需要双向同步，可以通过定期检查C层记录列表来实现
            if time.ticks_diff(now, last_record_check_ts) >= RECORD_CHECK_INTERVAL_MS:
                try:
                    import rtsmart_web
                    # 可以在这里实现记录同步逻辑（如果需要）
                    # 例如：检查C层记录数量，与Python层记录数量对比
                    # 如果差异较大，可能需要重新加载或同步
                except Exception as e:
                    # 忽略错误，不影响主流程
                    pass
                last_record_check_ts = now

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
            # 清理检测记录管理器（如果需要）
            # detection_manager 会在析构时自动保存元数据
            pass
        except Exception:
            pass
        report_runtime()
        print("[系统] 已清理资源，程序结束")


if __name__ == "__main__":
    main()

