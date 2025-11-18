"""
检测记录管理模块
管理息肉检测图像的保存、查询、删除
"""

import os
import json
import utime as time


class DetectionManager:
    """检测记录管理器"""
    
    def __init__(self, save_dir='/data/detections', max_records=100):
        self.save_dir = save_dir
        self.max_records = max_records
        # MicroPython不支持os.path.join，手动拼接路径
        self.metadata_file = save_dir + '/detections.json'
        self.records = []
        
        # 创建保存目录
        self._ensure_directory()
        
        # 加载已有记录
        self._load_metadata()
        
    def _ensure_directory(self):
        """确保目录存在"""
        try:
            # MicroPython的os.listdir可以用来检查目录
            try:
                os.listdir(self.save_dir)
            except:
                # 目录不存在，创建它
                os.mkdir(self.save_dir)
                print(f"创建检测记录目录: {self.save_dir}")
        except Exception as e:
            print(f"创建目录失败: {e}")
            
    def _load_metadata(self):
        """加载元数据"""
        try:
            # MicroPython检查文件是否存在
            try:
                with open(self.metadata_file, 'r') as f:
                    self.records = json.load(f)
                print(f"已加载 {len(self.records)} 条检测记录")
            except OSError:
                # 文件不存在
                self.records = []
        except Exception as e:
            print(f"加载元数据失败: {e}")
            self.records = []
            
    def _save_metadata(self):
        """保存元数据"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.records, f)
        except Exception as e:
            print(f"保存元数据失败: {e}")
            
    def save_detection(self, image, bbox, confidence):
        """
        保存检测结果
        
        参数:
            image: 图像对象
            bbox: 边界框 [x, y, w, h]
            confidence: 置信度
        返回:
            记录ID或None
        """
        try:
            # 生成文件名（时间戳）
            timestamp = int(time.time() * 1000)
            filename = f"detection_{timestamp}.jpg"
            filepath = self.save_dir + '/' + filename  # MicroPython手动拼接路径
            
            # 保存图像
            if hasattr(image, 'compressed'):
                # K230 image对象使用compressed()方法
                jpeg_data = image.compressed(quality=85)
                with open(filepath, 'wb') as f:
                    f.write(bytes(jpeg_data))
            elif hasattr(image, 'save'):
                # 标准PIL/OpenCV方式
                image.save(filepath, quality=85)
            else:
                print(f"图像对象不支持压缩或保存: {type(image)}")
                return None
                
            # 创建记录
            record = {
                'id': timestamp,
                'filename': filename,
                'filepath': filepath,
                'timestamp': timestamp,
                'time_str': self._format_time(timestamp / 1000),
                'bbox': bbox,
                'confidence': float(confidence),
                'size': self._get_file_size(filepath)
            }
            
            # 添加到记录列表
            self.records.insert(0, record)  # 最新的在前面
            
            # 限制记录数量
            if len(self.records) > self.max_records:
                # 删除最旧的记录和文件
                old_record = self.records.pop()
                self._delete_file(old_record['filepath'])
                
            # 保存元数据
            self._save_metadata()
            
            print(f"检测记录已保存: {filename}, 置信度: {confidence:.2f}")
            return record['id']
            
        except Exception as e:
            print(f"保存检测记录失败: {e}")
            return None
            
    def get_records(self, limit=None, offset=0):
        """
        获取检测记录列表
        
        参数:
            limit: 返回数量限制
            offset: 偏移量
        返回:
            记录列表
        """
        if limit is None:
            return self.records[offset:]
        else:
            return self.records[offset:offset + limit]
            
    def get_record(self, record_id):
        """获取单条记录"""
        for record in self.records:
            if record['id'] == record_id:
                return record
        return None
        
    def delete_record(self, record_id):
        """删除记录"""
        for i, record in enumerate(self.records):
            if record['id'] == record_id:
                # 删除文件
                self._delete_file(record['filepath'])
                # 从列表移除
                self.records.pop(i)
                # 保存元数据
                self._save_metadata()
                print(f"检测记录已删除: {record_id}")
                return True
        return False
        
    def delete_all(self):
        """删除所有记录"""
        try:
            # 删除所有图像文件
            for record in self.records:
                self._delete_file(record['filepath'])
                
            # 清空记录
            self.records = []
            self._save_metadata()
            
            print("所有检测记录已删除")
            return True
        except Exception as e:
            print(f"删除所有记录失败: {e}")
            return False
            
    def get_statistics(self):
        """获取统计信息"""
        if not self.records:
            return {
                'total_count': 0,
                'total_size': 0,
                'avg_confidence': 0,
                'max_confidence': 0,
                'min_confidence': 0
            }
            
        confidences = [r['confidence'] for r in self.records]
        sizes = [r.get('size', 0) for r in self.records]
        
        return {
            'total_count': len(self.records),
            'total_size': sum(sizes),
            'avg_confidence': sum(confidences) / len(confidences),
            'max_confidence': max(confidences),
            'min_confidence': min(confidences),
            'latest_time': self.records[0]['time_str'] if self.records else None
        }
        
    def _delete_file(self, filepath):
        """删除文件"""
        try:
            # MicroPython检查文件是否存在
            try:
                os.stat(filepath)
                os.remove(filepath)
            except OSError:
                pass  # 文件不存在
        except Exception as e:
            print(f"删除文件失败 {filepath}: {e}")
            
    def _get_file_size(self, filepath):
        """获取文件大小"""
        try:
            return os.stat(filepath)[6]  # st_size
        except:
            return 0
            
    def _format_time(self, timestamp):
        """格式化时间戳"""
        try:
            # MicroPython时间格式化
            time_tuple = time.localtime(timestamp)
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
                time_tuple[0], time_tuple[1], time_tuple[2],
                time_tuple[3], time_tuple[4], time_tuple[5]
            )
        except:
            return str(int(timestamp))
