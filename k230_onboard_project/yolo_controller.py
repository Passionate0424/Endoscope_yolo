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
        self._initialization_done = False  # 初始化就绪标志
        
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
    
    def set_detection_callback(self, callback):
        """设置检测结果回调"""
        self.detection_callback = callback
    
    def is_ready(self):
        """供其他组件查询YOLO线程是否完成初始化"""
        return self._initialization_done
        
    def start_camera(self):
        """启动摄像头"""
        if self.camera_running:
            print("摄像头已在运行")
            return False
            
        self.stop_flag = False
        self.camera_running = True
        self._initialization_done = False  # 添加初始化完成标志
        
        # 在新线程中运行 - 使用K230的_thread模块
        _thread.start_new_thread(self._camera_loop, ())
        
        # ⭐ 关键修复：不要等待初始化！
        # 在K230的非抢占式线程模型中，等待会阻塞HTTP响应
        # 让YOLO线程自己初始化，HTTP立即返回
        print("✅ 摄像头启动命令已发送，正在后台初始化...")
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
            time.sleep(0.02)  # 让出CPU
            
            try:
                pl = PipeLine(rgb888p_size=[640, 360], display_mode="lcd")
                time.sleep(0.05)  # PipeLine构造后让出CPU
                
                print("[YOLO线程] 调用 pl.create() ...")
                create_start = time.time()
                pl.create()
                create_elapsed = time.time() - create_start
                print(f"[YOLO线程] pl.create() 完成，耗时 {create_elapsed:.2f}s")
                time.sleep(0.05)  # create()后让出CPU
            except Exception as e:
                print(f"[YOLO线程] ❌ PipeLine初始化失败: {e}")
                print("[YOLO线程] 可能原因: 1)摄像头未连接 2)摄像头被占用 3)显示设备问题")
                import sys
                sys.print_exception(e)
                return
                
            print("[YOLO线程] 准备获取显示尺寸...")
            try:
                display_size = pl.get_display_size()
            except Exception as e:
                print(f"[YOLO线程] ❌ 获取显示尺寸失败: {e}")
                import sys
                sys.print_exception(e)
                display_size = [640, 480]
            
            print(f"[YOLO线程] PipeLine已创建, 显示尺寸: {display_size}")
            time.sleep(0.05)  # 让出CPU
            
            # 初始化YOLO模型
            print("[YOLO线程] 初始化YOLO模型...")
            time.sleep(0.05)  # 让出CPU
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
                time.sleep(0.05)  # 模型加载后让出CPU
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
            time.sleep(0.05)  # 让出CPU
            
            # ⭐ 标记初始化完成
            self._initialization_done = True
            print("[YOLO线程] ✅ 初始化完成，通知主线程")
            time.sleep(0.05)  # 让出CPU
            
            # ⭐ 关键修复：初始化完成后，通知主线程同步状态到C层
            # 这样页面刷新后能读取到正确的状态
            try:
                # 尝试获取frame_callback，如果它设置了web_adapter，则通知更新
                if self.frame_callback:
                    # frame_callback是web_adapter.update_frame，我们需要通知主线程
                    # 但这里无法直接访问主线程的web_adapter
                    # 所以我们在主线程中会定期检查并同步状态
                    pass
            except:
                pass
            
            # FPS计算
            frame_count = 0  # 用于打印的计数器（会重置）
            fps_calc_count = 0  # 用于FPS计算的计数器（定期重置）
            debug_frame_count = 0  # 用于调试打印的独立计数器
            start_time = time.time()
            fps_start_time = time.time()  # FPS计算的起始时间
            fps_reset_interval = 5.0  # 每5秒重置一次FPS计算，保持准确性
            
            # 添加循环计数器
            loop_iteration = 0
            first_frame_sent = False  # 标记是否已发送第一帧
            
            print("[YOLO线程] 进入主循环，开始获取帧数据...")
            time.sleep(0.01)  # 让出CPU，确保打印能输出
            
            # 🔧 分多次sleep，每次都让出CPU给其他线程
            print("[YOLO线程] 等待硬件就绪（分段延时）...")
            time.sleep(0.05)  # 50ms
            
            print("[YOLO线程] 延时 50ms...")
            time.sleep(0.05)  # 再50ms
            
            print("[YOLO线程] 延时 100ms...")
            time.sleep(0.1)   # 再100ms
            
            print("[YOLO线程] 延时 200ms...")
            time.sleep(0.1)   # 再100ms (总共300ms)
            
            print("[YOLO线程] ✅ 硬件已就绪，开始主循环")
            time.sleep(0.01)  # 让出CPU，确保打印能输出
            
            while not self.stop_flag:
                loop_iteration += 1
                
                # 前3次迭代每次都打印，之后每10次打印一次
                if loop_iteration <= 3 or loop_iteration % 10 == 0:
                    print(f"[YOLO线程] 循环迭代 #{loop_iteration}, 准备获取帧...")
                
                # 🔧 在每次循环开始时，先让出CPU
                time.sleep(0.01)  # 10ms让出CPU给其他线程
                
                # 🔧 在第一次迭代时，打印线程信息
                if loop_iteration == 1:
                    try:
                        import _thread
                        print(f"[YOLO线程] 当前线程ID: {_thread.get_ident()}")
                        time.sleep(0.01)  # 打印后让出CPU
                    except:
                        pass
                
                # 🔧 使用看门狗变量检测阻塞
                get_frame_start = time.time()
                
                # ⚠️ 关键诊断：在调用get_frame前后打印
                if loop_iteration <= 3:
                    print(f"[YOLO线程] 即将调用 pl.get_frame()... (迭代#{loop_iteration})")
                    time.sleep(0.01)  # 打印后让出CPU
                
                # 获取图像 - 这是阻塞调用
                # ⚠️ get_frame() 可能会阻塞，我们无法设置超时
                # 但可以通过定期打印来确认它是否卡住
                try:
                    frame = pl.get_frame()
                    
                    # ⭐ 如果执行到这里，说明get_frame返回了
                    if loop_iteration <= 3:
                        print(f"[YOLO线程] pl.get_frame() 已返回 (迭代#{loop_iteration})")
                        time.sleep(0.01)  # 打印后让出CPU
                    get_frame_elapsed = time.time() - get_frame_start
                    
                    # 前3次打印获取帧耗时
                    if loop_iteration <= 3:
                        print(f"[YOLO线程] get_frame() 耗时: {get_frame_elapsed:.3f}s")
                    
                    # 打印获取帧的结果（前3次）
                    if loop_iteration <= 3:
                        if frame is not None:
                            print(f"[YOLO线程] ✅ 成功获取帧 #{loop_iteration}")
                        else:
                            print(f"[YOLO线程] ❌ 获取帧失败 #{loop_iteration}")
                    
                    if frame is None:
                        print("[YOLO线程] 警告: 获取帧失败")
                        time.sleep(0.1)
                        continue
                        
                except Exception as e:
                    print(f"[YOLO线程] ❌ get_frame()异常: {e}")
                    time.sleep(0.1)
                    continue
                    
                # 更新统计
                frame_count += 1
                fps_calc_count += 1  # FPS计算计数器
                debug_frame_count += 1
                self.stats['total_frames'] += 1

                # ⭐ 优化FPS计算：使用滑动窗口（每5秒重置一次，保持准确性）
                current_time = time.time()
                elapsed = current_time - fps_start_time
                
                if elapsed > 0.1:  # 至少 100ms 才计算，避免除零
                    self.stats['fps'] = fps_calc_count / elapsed
                else:
                    self.stats['fps'] = 0.0
                
                # 每5秒重置FPS计算，保持准确性（避免初始化时间影响）
                if elapsed >= fps_reset_interval:
                    fps_calc_count = 0
                    fps_start_time = current_time
                
                # 每30帧打印一次
                if frame_count >= 30:
                    print("[YOLO线程] FPS: %.2f (总帧数: %d)" % (self.stats['fps'], self.stats['total_frames']))
                    frame_count = 0  # 只重置打印计数器
                    
                # YOLO检测
                results = None
                if self.detection_enabled:
                    # 执行YOLO推理
                    results = yolo_detector.run(frame)
                    
                    # 绘制检测结果到osd_img
                    if results:
                        yolo_detector.draw_result(results, pl.osd_img)
                        
                        # 处理检测结果（检查是否有息肉检测）
                        for det in results:
                            # 更新统计
                            self.stats['total_detections'] += 1
                            
                            # 调用检测回调（保存图像等）
                            if self.detection_callback:
                                try:
                                    # 尝试从检测结果中提取置信度
                                    # YOLO 检测结果通常是 [x, y, w, h, confidence, class_id] 或类似结构
                                    confidence = 0.0
                                    if isinstance(det, (list, tuple)) and len(det) >= 5:
                                        confidence = float(det[4])  # 第5个元素通常是置信度
                                    elif hasattr(det, 'confidence'):
                                        confidence = float(det.confidence)
                                    elif hasattr(det, 'conf'):
                                        confidence = float(det.conf)
                                    
                                    # 使用 pl.osd_img（Image对象）而不是 frame（ndarray）
                                    self.detection_callback(pl.osd_img, det, confidence)
                                except Exception as e:
                                    print("[YOLO线程] 检测回调错误: " + str(e))
                
                # 更新视频流帧 - 始终发送osd_img
                if self.frame_callback:
                    try:
                        # 确保osd_img不为None才发送
                        if pl.osd_img is not None:
                            if loop_iteration <= 5:
                                print("[YOLO线程] [迭代#%d] 调用 frame_callback..." % loop_iteration)
                            self.frame_callback(pl.osd_img)
                            # 第一帧特别提示
                            if not first_frame_sent:
                                print("[YOLO线程] ✅ 已发送第一帧到视频流")
                                first_frame_sent = True
                        elif loop_iteration <= 10:  # 前10次迭代时打印警告
                            print("[YOLO线程] [迭代#%d] 警告: osd_img为None" % loop_iteration)
                    except Exception as e:
                        print("[YOLO线程] [迭代#%d] 帧回调错误: %s" % (loop_iteration, str(e)))
                        import sys
                        sys.print_exception(e)
                else:
                    # 调试：检查 frame_callback 是否被设置
                    if loop_iteration <= 10:
                        print("[YOLO线程] [迭代#%d] ⚠️ 警告: frame_callback 未设置！" % loop_iteration)
                
                # 显示到屏幕
                try:
                    pl.show_image()
                except Exception as e:
                    pass  # 静默处理显示错误
                
                # 内存管理 - 每100帧执行一次
                if debug_frame_count % 100 == 0:
                    print(f"[YOLO线程] 已处理 {debug_frame_count} 帧, 检测次数: {self.stats['total_detections']}")
                    gc.collect()
                
                # ⚠️ 关键：MicroPython是非抢占式线程，必须主动让出CPU！
                # 否则会阻塞HTTP服务器等其他线程
                time.sleep(0.01)  # 10ms让出CPU - 理论最大100fps，实际受硬件限制约30fps
            
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
