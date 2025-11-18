"""
内窥镜检测平台 - 主程序
整合HTTP服务器、MJPEG流、YOLO检测、记录管理
"""

import gc
import socket
import utime as time
from web_server import HTTPServer
from stream_handler import MJPEGStreamer
from detection_manager import DetectionManager
from yolo_controller import YOLOController
from wifi_config import connect_wifi, WIFI_SSID, WIFI_PASSWORD


class EndoscopeWebPlatform:
    """内窥镜检测Web平台"""
    
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        
        # 初始化组件
        self.server = HTTPServer(host, port)
        self.streamer = MJPEGStreamer(quality=75, max_fps=15)
        self.detection_manager = DetectionManager(save_dir='/data/detections')
        self.yolo_controller = YOLOController(detection_callback=self.on_detection)
        
        # 将streamer附加到server，以便处理流式响应
        self.server.streamer = self.streamer
        
        # 设置帧回调
        self.yolo_controller.set_frame_callback(self.streamer.update_frame)
        
        # 注册路由
        self.register_routes()
        
    def register_routes(self):
        """注册API路由"""
        
        # 静态文件
        @self.server.route('/')
        def index(params):
            return self.server.serve_static_file('/index.html')
            
        @self.server.route('/app.js')
        def app_js(params):
            return self.server.serve_static_file('/app.js')
        
        # 视频流
        @self.server.route('/stream')
        def stream(params):
            # 返回特殊标记，让server调用streamer
            return {'_stream': True}
            
        # 摄像头控制API
        @self.server.route('/api/camera/start', 'POST')
        def start_camera(params):
            success = self.yolo_controller.start_camera()
            return self.server.json_response({
                'success': success,
                'message': '摄像头已启动' if success else '启动失败'
            })
            
        @self.server.route('/api/camera/stop', 'POST')
        def stop_camera(params):
            success = self.yolo_controller.stop_camera()
            return self.server.json_response({
                'success': success,
                'message': '摄像头已停止' if success else '停止失败'
            })
            
        # 检测控制API
        @self.server.route('/api/detection/enable', 'POST')
        def enable_detection(params):
            success = self.yolo_controller.enable_detection()
            return self.server.json_response({
                'success': success,
                'message': '检测已启用' if success else '启用失败'
            })
            
        @self.server.route('/api/detection/disable', 'POST')
        def disable_detection(params):
            success = self.yolo_controller.disable_detection()
            return self.server.json_response({
                'success': success,
                'message': '检测已禁用' if success else '禁用失败'
            })
            
        # 配置API
        @self.server.route('/api/config/confidence', 'POST')
        def set_confidence(params):
            value = float(params.get('value', 0.5))
            success = self.yolo_controller.set_confidence_threshold(value)
            return self.server.json_response({
                'success': success,
                'message': f'置信度已设置为 {value}' if success else '设置失败'
            })
            
        # 状态API
        @self.server.route('/api/status')
        def get_status(params):
            return self.server.json_response({
                'success': True,
                'data': {
                    'camera_running': self.yolo_controller.camera_running,
                    'detection_enabled': self.yolo_controller.detection_enabled,
                    'yolo_stats': self.yolo_controller.get_statistics(),
                    'detection_stats': self.detection_manager.get_statistics()
                }
            })
            
        # 检测记录API
        @self.server.route('/api/records')
        def get_records(params):
            limit = int(params.get('limit', 20))
            offset = int(params.get('offset', 0))
            records = self.detection_manager.get_records(limit, offset)
            return self.server.json_response({
                'success': True,
                'data': records
            })
            
        @self.server.route('/api/records/<id>', 'DELETE')
        def delete_record(params):
            record_id = int(params.get('id', 0))
            success = self.detection_manager.delete_record(record_id)
            return self.server.json_response({
                'success': success,
                'message': '记录已删除' if success else '删除失败'
            })
            
        @self.server.route('/api/records/clear', 'POST')
        def clear_records(params):
            success = self.detection_manager.delete_all()
            return self.server.json_response({
                'success': success,
                'message': '所有记录已清空' if success else '清空失败'
            })
            
        # 检测图像文件 - K230使用/data路径（28GB空间）
        @self.server.route('/detections/<filename>')
        def get_detection_image(params):
            filename = params.get('filename', '')
            filepath = f'/data/detections/{filename}'
            return self.server.serve_static_file(filepath)
            
    def on_detection(self, image, bbox, confidence):
        """检测回调 - 当YOLO检测到息肉时调用"""
        try:
            # 保存检测结果
            record_id = self.detection_manager.save_detection(image, bbox, confidence)
            if record_id:
                print(f"✓ 检测到息肉！置信度: {confidence:.2f}, 记录ID: {record_id}")
        except Exception as e:
            print(f"保存检测结果失败: {e}")
                
    def run(self):
        """启动平台"""
        print("="*50)
        print("内窥镜检测平台启动中...")
        print(f"服务器地址: http://{self.host}:{self.port}")
        print("="*50)
        
        # 启动HTTP服务器（已自动多线程处理）
        self.server.start()


def main():
    """主函数"""
    try:
        # 步骤1: 连接WiFi
        print("\n" + "="*60)
        print("  内窥镜检测平台 - 启动中")
        print("="*60)
        
        success, ip_address = connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=30)
        if not success:
            print("\n❌ WiFi连接失败，无法启动Web服务器")
            print("请检查:")
            print("  1. WiFi名称和密码是否正确")
            print("  2. WiFi信号是否正常")
            print("  3. 路由器是否开启")
            return
        
        print(f"\n✅ 网络已就绪，IP地址: {ip_address}")
        
        # 步骤2: 创建平台实例
        print("\n正在初始化平台组件...")
        platform = EndoscopeWebPlatform(host='0.0.0.0', port=8080)
        
        # 步骤3: 启动服务
        print("\n" + "="*60)
        print(f"🚀 Web平台已启动!")
        print(f"📱 请在浏览器访问: http://{ip_address}:8080")
        print("="*60 + "\n")
        
        platform.run()
        
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
    except Exception as e:
        print(f"平台错误: {e}")
        # MicroPython不支持traceback模块，使用sys.print_exception
        import sys
        sys.print_exception(e)
    finally:
        print("平台已停止")
        gc.collect()


if __name__ == '__main__':
    main()
