"""
RT-Smart Web 服务器 Python 适配层
C 层 HTTP 服务器 + Python YOLO 检测
"""

import utime as time
import gc

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
    
    def __init__(self, quality=75):
        self.quality = quality
        self.use_c_server = HAS_C_SERVER
        self._frame_count = 0
        
        if not self.use_c_server:
            print("[RTWeb] ❌ C 服务器不可用，系统无法工作")
            raise RuntimeError("RT-Smart web server module not found")
        
        # 尝试启动 C 层服务器
        try:
            rtsmart_web.start()
            print("[RTWeb] 📍 已向 C 层发送启动信号")
        except Exception as e:
            print("[RTWeb] ⚠️ C 层启动失败: " + str(e))
    
    def update_frame(self, image):
        """
        由 YOLO 检测线程调用，推送帧到 C 层
        
        Args:
            image: CanMV image 对象
        """
        if not self.use_c_server:
            return
        
        try:
            # 编码为 JPEG
            jpeg_bytes = image.compress(quality=self.quality)
            
            # 推送到 C 层 frame_buffer
            rtsmart_web.push_frame(jpeg_bytes)
            
            self._frame_count += 1
            if self._frame_count % 100 == 0:
                print("[RTWeb] 已推送 %d 帧到 C 服务器" % self._frame_count)
                gc.collect()  # 定期 GC
            
        except Exception as e:
            print("[RTWeb] ❌ 推送帧失败: " + str(e))
    
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
        try:
            return rtsmart_web.get_control()
        except Exception as e:
            print("[RTWeb] ⚠️ 获取控制信息失败:", e)
            return None

    def update_runtime(self, camera_running, detection_enabled, confidence):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.set_runtime(camera_running, detection_enabled, confidence)
        except Exception as e:
            print("[RTWeb] ⚠️ 更新运行状态失败:", e)

    def update_stats_remote(self, total_frames, total_detections, fps):
        if not self.use_c_server:
            return
        try:
            rtsmart_web.set_stats(total_frames, total_detections, fps)
        except Exception as e:
            print("[RTWeb] ⚠️ 更新统计失败:", e)

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
