"""
YOLO检测控制器
封装原有的YOLO检测逻辑，提供启动/停止/配置接口
"""

import _thread
import utime as time
import gc


class YOLOController:
    """YOLO检测控制器"""
    
    def __init__(self, detection_callback=None):
        """
        初始化控制器
        
        参数:
            detection_callback: 检测回调函数 callback(image, bbox, confidence)
        """
        self.detection_callback = detection_callback
        
        # 状态标志
        self.camera_running = False
        self.detection_enabled = False
        self.thread = None
        self.stop_flag = False
        
        # YOLO配置
        self.confidence_threshold = 0.5
        self.iou_threshold = 0.45
        
        # 帧更新回调（用于视频流）
        self.frame_callback = None
        
        # 统计信息
        self.stats = {
            'total_frames': 0,
            'total_detections': 0,
            'fps': 0
        }
        
    def set_frame_callback(self, callback):
        """设置帧更新回调（用于视频流）"""
        self.frame_callback = callback
        
    def start_camera(self):
        """启动摄像头"""
        if self.camera_running:
            print("摄像头已在运行")
            return False
            
        self.stop_flag = False
        self.camera_running = True
        
        # 在新线程中运行 - 使用K230的_thread模块
        _thread.start_new_thread(self._camera_loop, ())
        
        print("摄像头已启动")
        return True
        
    def stop_camera(self):
        """停止摄像头"""
        if not self.camera_running:
            print("摄像头未运行")
            return False
            
        self.stop_flag = True
        
        # K230的_thread没有join方法，等待一段时间让线程自行结束
        time.sleep(1)
            
        self.camera_running = False
        print("摄像头已停止")
        return True
        
    def enable_detection(self):
        """启用YOLO检测"""
        self.detection_enabled = True
        print("YOLO检测已启用")
        return True
        
    def disable_detection(self):
        """禁用YOLO检测"""
        self.detection_enabled = False
        print("YOLO检测已禁用")
        return True
        
    def set_confidence_threshold(self, threshold):
        """设置置信度阈值"""
        if 0 < threshold < 1:
            self.confidence_threshold = threshold
            print(f"置信度阈值已设置为: {threshold}")
            return True
        return False
        
    def get_statistics(self):
        """获取统计信息"""
        return self.stats.copy()
        
    def _camera_loop(self):
        """摄像头主循环"""
        print("[YOLO线程] 开始执行")
        pl = None  # 初始化为None,避免finally块中的NameError
        yolo_detector = None  # 初始化为None,避免finally块中的NameError
        
        try:
            # 导入必要的模块
            print("[YOLO线程] 导入模块...")
            try:
                from libs.PipeLine import PipeLine, ScopedTiming
                from libs.YOLO import YOLOv5
            except ImportError as e:
                print(f"[YOLO线程] ❌ 导入模块失败: {e}")
                print("[YOLO线程] 请确保libs模块在正确的路径")
                return
            
            # 初始化摄像头 - 添加display_mode以显示到IDE
            print("[YOLO线程] 初始化摄像头...")
            try:
                pl = PipeLine(rgb888p_size=[640, 360], display_mode="lcd")
                pl.create()
            except Exception as e:
                print(f"[YOLO线程] ❌ PipeLine初始化失败: {e}")
                print("[YOLO线程] 可能原因: 1)摄像头未连接 2)摄像头被占用 3)显示设备问题")
                import sys
                sys.print_exception(e)
                return
                
            display_size = pl.get_display_size()
            
            print(f"[YOLO线程] PipeLine已创建, 显示尺寸: {display_size}")
            
            # 初始化YOLO模型
            print("[YOLO线程] 初始化YOLO模型...")
            try:
                yolo_detector = YOLOv5(
                    task_type='detect',
                    mode='video',
                    kmodel_path='/data/model.kmodel',
                    labels=['polyp'],
                    rgb888p_size=[640, 360],
                    model_input_size=[640, 640],
                    display_size=display_size,
                    conf_thresh=self.confidence_threshold,
                    nms_thresh=self.iou_threshold,
                    debug_mode=0
                )
                yolo_detector.config_preprocess()
                print("[YOLO线程] ✅ YOLO模型已加载")
            except Exception as e:
                print(f"[YOLO线程] ❌ YOLO模型加载失败: {e}")
                print("[YOLO线程] 请检查: 1)/data/model.kmodel是否存在 2)模型文件是否损坏")
                import sys
                sys.print_exception(e)
                # 即使YOLO加载失败,也清理PipeLine
                if pl is not None:
                    try:
                        pl.destroy()
                    except:
                        pass
                return
            
            print("[YOLO线程] 开始主循环")
            
            # FPS计算
            frame_count = 0
            debug_frame_count = 0  # 用于调试打印的独立计数器
            start_time = time.time()
            
            print("[YOLO线程] 进入主循环")
            
            while not self.stop_flag:
                # 关闭ScopedTiming的打印输出,避免串口阻塞
                # 参数1改为0,禁用每帧的耗时打印
                with ScopedTiming("total", 0):
                    # 获取图像
                    frame = pl.get_frame()
                    
                    if frame is None:
                        print("[YOLO线程] 警告: 获取帧失败")
                        continue
                        
                    # 更新统计
                    frame_count += 1
                    debug_frame_count += 1
                    self.stats['total_frames'] += 1
                    
                    # 计算FPS
                    if frame_count >= 30:
                        elapsed = time.time() - start_time
                        self.stats['fps'] = frame_count / elapsed
                        frame_count = 0
                        start_time = time.time()
                    
                    # YOLO检测
                    results = None
                    if self.detection_enabled:
                        # 关闭YOLO推理耗时打印,避免阻塞
                        with ScopedTiming("YOLO inference", 0):
                            results = yolo_detector.run(frame)
                            
                        # 绘制检测结果到osd_img
                        if results:
                            yolo_detector.draw_result(results, pl.osd_img)
                            
                            # 处理检测结果（检查是否有息肉检测）
                            # results格式: list of detections
                            for det in results:
                                # 更新统计
                                self.stats['total_detections'] += 1
                                
                                # 调用检测回调（保存图像等）
                                if self.detection_callback:
                                    try:
                                        # 从frame获取完整图像用于保存
                                        self.detection_callback(frame, det, 0.0)
                                    except Exception as e:
                                        print(f"检测回调错误: {e}")
                    
                    # 更新视频流帧 - 始终发送osd_img
                    if self.frame_callback:
                        try:
                            # pl.osd_img 包含了绘制的结果（如果有检测）或原始图像
                            self.frame_callback(pl.osd_img)
                            
                            # 调试：每100帧打印一次,减少串口输出
                            if debug_frame_count % 100 == 0:
                                print(f"[YOLO] 已处理 {debug_frame_count} 帧, FPS: {self.stats['fps']:.1f}")
                        except Exception as e:
                            print(f"帧回调错误: {e}")
                    
                    # 显示到屏幕
                    pl.show_image()
                    
                    # 内存管理
                    gc.collect()
            
            print("[YOLO线程] 主循环正常结束")
                    
        except Exception as e:
            print(f"[YOLO线程] ❌ 摄像头循环错误: {e}")
            # MicroPython使用sys.print_exception
            import sys
            sys.print_exception(e)
            
            # 设置错误标志,让前端知道出错了
            self.camera_running = False
            self.stop_flag = True
            
        finally:
            print("[YOLO线程] 开始清理资源...")
            # 清理资源 - 检查变量是否已初始化
            if yolo_detector is not None:
                try:
                    yolo_detector.deinit()
                    print("[YOLO线程] YOLO模型已释放")
                except Exception as e:
                    print(f"[YOLO线程] 释放YOLO模型失败: {e}")
                    
            if pl is not None:
                try:
                    pl.destroy()
                    print("[YOLO线程] PipeLine已销毁")
                except Exception as e:
                    print(f"[YOLO线程] 销毁PipeLine失败: {e}")
                    
            print("[YOLO线程] 摄像头资源已释放，线程结束")
            self.camera_running = False  # 确保标志被重置
