"""
RTSP 视频推流服务器模块
用于 K230 CanMV 环境，提供 RTSP 视频流
适用于庐山派 K230 开发板

参考: https://wiki.lckfb.com/zh-hans/lushan-pi-k230/api/mpp/k230_canmv_rtsp_module_api.html
"""

import time
import gc
import _thread
from time import sleep

# 导入 K230 多媒体模块
try:
    import multimedia as mm
    from media.vencoder import *
    from media.sensor import *
    from media.media import *
    import uctypes
    MM_AVAILABLE = True
except ImportError as e:
    print(f"Warning: K230 multimedia modules not available: {e}")
    MM_AVAILABLE = False

class RTSPServer:
    """
    RTSP 推流服务器
    基于 K230 CanMV 官方 RTSP API 实现
    使用 multimedia.rtsp_server 进行 H264/H265 视频推流
    """
    
    def __init__(self, port=8554, stream_name="live", video_type="h264"):
        """
        初始化 RTSP 服务器
        
        Args:
            port: RTSP 服务端口 (默认 8554)
            stream_name: 流名称/会话名称 (默认 "live")
            video_type: 视频编码类型 "h264" 或 "h265" (默认 "h264")
        """
        self.session_name = stream_name  # 会话名称
        self.port = port                 # RTSP 服务器端口号
        self.video_type = video_type     # 视频编码类型
        self.enable_audio = False        # 是否启用音频
        self.running = False
        self.start_stream = False        # 是否启动推流线程
        self.runthread_over = False      # 推流线程是否结束
        
        # K230 模块实例
        self.rtspserver = None
        self.encoder = None
        self.sensor = None
        self.link = None
        self.venc_chn = VENC_CHN_ID_0 if MM_AVAILABLE else 0
        
    def start(self, camera_device=None, width=640, height=360, fps=30, bitrate=2000000):
        """
        启动 RTSP 推流服务器
        
        Args:
            camera_device: 摄像头设备对象 (保留参数,兼容旧代码)
            width: 视频宽度
            height: 视频高度  
            fps: 帧率
            bitrate: 码率 (bps, 默认 2Mbps)
        
        Returns:
            bool: 启动成功返回 True, 失败返回 False
        """
        if not MM_AVAILABLE:
            print("错误: K230 multimedia 模块不可用")
            print("请确认:")
            print("  1. 运行在 K230 设备上")
            print("  2. 固件版本支持 RTSP")
            return False
        
        try:
            # 对齐宽度到16的倍数 (K230要求)
            width = self._align_up(width, 16)
            
            print(f"初始化 RTSP 服务器...")
            print(f"  端口: {self.port}")
            print(f"  会话名称: {self.session_name}")
            print(f"  编码类型: {self.video_type.upper()}")
            print(f"  分辨率: {width}x{height}")
            print(f"  帧率: {fps} fps")
            print(f"  码率: {bitrate / 1000000:.1f} Mbps")
            
            # 保存配置
            self.width = width
            self.height = height
            self.fps = fps
            self.bitrate = bitrate
            
            # 1. 创建 RTSP 服务器实例
            self.rtspserver = mm.rtsp_server()
            
            # 2. 初始化媒体流 (camera + encoder)
            self._init_stream()
            
            # 3. 初始化 RTSP 服务器
            self.rtspserver.rtspserver_init(self.port)
            
            # 4. 创建 RTSP 会话
            # 设置视频编码类型
            if self.video_type.lower() == "h265":
                video_type_enum = mm.multi_media_type.media_h265
            else:
                video_type_enum = mm.multi_media_type.media_h264
            
            self.rtspserver.rtspserver_createsession(
                self.session_name,
                video_type_enum,
                self.enable_audio
            )
            
            # 5. 启动 RTSP 服务器
            self.rtspserver.rtspserver_start()
            
            # 6. 启动编码器和摄像头
            self._start_stream()
            
            # 7. 启动推流线程
            self.start_stream = True
            self.running = True
            _thread.start_new_thread(self._do_rtsp_stream, ())
            
            # 获取并打印 RTSP URL
            url = self.get_rtsp_url()
            print(f"✓ RTSP 服务器启动成功")
            print(f"  RTSP URL: {url}")
            print(f"  VLC 播放: vlc {url}")
            
            return True
            
        except Exception as e:
            print(f"启动 RTSP 服务器失败: {e}")
            try:
                import sys
                sys.print_exception(e)
            except:
                pass
            self.running = False
            return False
    
    def _align_up(self, value, alignment):
        """将数值向上对齐到指定倍数"""
        return ((value + alignment - 1) // alignment) * alignment
    
    def _init_stream(self):
        """初始化视频流 (摄像头 + 编码器)"""
        # 初始化传感器 (摄像头)
        self.sensor = Sensor()
        self.sensor.reset()
        self.sensor.set_framesize(width=self.width, height=self.height, alignment=12)
        self.sensor.set_pixformat(Sensor.YUV420SP)
        
        # 实例化视频编码器
        self.encoder = Encoder()
        self.encoder.SetOutBufs(self.venc_chn, 8, self.width, self.height)
        
        # 绑定 camera 和 venc
        self.link = MediaManager.link(
            self.sensor.bind_info()['src'],
            (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, self.venc_chn)
        )
        
        # 初始化 media manager
        MediaManager.init()
        
        # 创建编码器
        if self.video_type.lower() == "h265":
            payload_type = self.encoder.PAYLOAD_TYPE_H265
            profile = self.encoder.H265_PROFILE_MAIN
        else:
            payload_type = self.encoder.PAYLOAD_TYPE_H264
            profile = self.encoder.H264_PROFILE_MAIN
        
        chnAttr = ChnAttrStr(payload_type, profile, self.width, self.height)
        self.encoder.Create(self.venc_chn, chnAttr)
    
    def _start_stream(self):
        """启动视频流"""
        # 开始编码
        self.encoder.Start(self.venc_chn)
        # 启动 camera
        self.sensor.run()
    
    def _stop_stream(self):
        """停止视频流"""
        try:
            # 停止 camera
            if self.sensor:
                self.sensor.stop()
            
            # 解绑 camera 和 venc
            if self.link:
                del self.link
                self.link = None
            
            # 停止编码器
            if self.encoder:
                self.encoder.Stop(self.venc_chn)
                self.encoder.Destroy(self.venc_chn)
            
            # 清理 buffer
            MediaManager.deinit()
        except Exception as e:
            print(f"停止视频流时出错: {e}")
    
    def _do_rtsp_stream(self):
        """RTSP 推流线程"""
        try:
            import os
            streamData = StreamData()
            
            while self.start_stream:
                os.exitpoint()
                
                # 获取一帧编码后的数据
                self.encoder.GetStream(self.venc_chn, streamData)
                
                # 推送每个数据包
                for pack_idx in range(0, streamData.pack_cnt):
                    stream_data = bytes(uctypes.bytearray_at(
                        streamData.data[pack_idx],
                        streamData.data_size[pack_idx]
                    ))
                    
                    # 发送视频数据到 RTSP 服务器
                    self.rtspserver.rtspserver_sendvideodata(
                        self.session_name,
                        stream_data,
                        streamData.data_size[pack_idx],
                        1000  # timestamp
                    )
                
                # 释放一帧码流
                self.encoder.ReleaseStream(self.venc_chn, streamData)
                
        except Exception as e:
            print(f"RTSP 推流线程异常: {e}")
            try:
                import sys
                sys.print_exception(e)
            except:
                pass
        finally:
            self.runthread_over = True
            print("RTSP 推流线程已退出")
    
    def push_frame(self, frame):
        """
        推送一帧到 RTSP 流
        
        Args:
            frame: 图像帧 (ndarray 或 Image 对象)
        
        注意: 在K230 RTSP实现中,帧数据通过编码器自动获取并推送
              此方法仅用于兼容性,实际推送在 _do_rtsp_stream 线程中完成
        
        Returns:
            bool: 如果服务器正在运行返回 True, 否则返回 False
        """
        return self.running and self.start_stream
    
    def get_rtsp_url(self):
        """
        获取 RTSP URL
        
        Returns:
            str: RTSP 流的 URL
        """
        if self.rtspserver:
            try:
                return self.rtspserver.rtspserver_getrtspurl(self.session_name)
            except:
                pass
        return f"rtsp://<设备IP>:{self.port}/{self.session_name}"
    
    def stop(self):
        """停止 RTSP 服务器"""
        if not self.running:
            return
        
        print("正在停止 RTSP 服务器...")
        
        try:
            # 停止推流线程
            self.start_stream = False
            
            # 等待推流线程退出
            timeout = 30  # 3秒超时
            while not self.runthread_over and timeout > 0:
                sleep(0.1)
                timeout -= 1
            
            if timeout <= 0:
                print("警告: 推流线程未在超时时间内退出")
            
            self.runthread_over = False
            
            # 停止视频流
            self._stop_stream()
            
            # 停止 RTSP 服务器
            if self.rtspserver:
                self.rtspserver.rtspserver_stop()
                self.rtspserver.rtspserver_destroysession(self.session_name)
                self.rtspserver.rtspserver_deinit()
                self.rtspserver = None
            
            self.running = False
            print("✓ RTSP 服务器已停止")
            gc.collect()
            
        except Exception as e:
            print(f"停止 RTSP 服务器时出错: {e}")
            try:
                import sys
                sys.print_exception(e)
            except:
                pass


# 使用示例
"""
基于 K230 CanMV 官方 RTSP API 的使用示例

示例代码:
---------
from rtsp_server import RTSPServer

# 创建 RTSP 服务器实例
rtsp = RTSPServer(
    port=8554,
    stream_name="endoscope",
    video_type="h264"  # 或 "h265"
)

# 启动 RTSP 服务器
# 注意: start() 会自动初始化摄像头和编码器，并启动推流线程
if rtsp.start(width=640, height=360, fps=30, bitrate=2000000):
    print(f"RTSP URL: {rtsp.get_rtsp_url()}")
    
    # RTSP 服务器会自动推流，无需手动调用 push_frame()
    # 推流在后台线程中自动进行
    
    # 运行一段时间...
    import time
    time.sleep(60)  # 推流60秒
    
    # 停止 RTSP 服务器
    rtsp.stop()

客户端访问方式:
--------------
VLC播放器: 媒体 -> 打开网络串流 -> rtsp://192.168.x.x:8554/endoscope
ffplay: ffplay rtsp://192.168.x.x:8554/endoscope
OBS Studio: 添加媒体源 -> 输入 rtsp://192.168.x.x:8554/endoscope

注意事项:
--------
1. K230 的 RTSP 服务器会自动管理摄像头和编码器
2. 不需要手动推送帧，编码后的数据会自动发送到 RTSP 流
3. 确保设备固件支持 multimedia 模块
4. 视频宽度会自动对齐到16的倍数
5. 推流在独立线程中进行，不会阻塞主程序
"""

