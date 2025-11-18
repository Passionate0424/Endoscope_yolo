"""
测试视频流是否正常工作
在K230上运行此脚本测试stream_handler
"""

import utime as time
from stream_handler import MJPEGStreamer

class FakeImage:
    """模拟image对象用于测试"""
    def __init__(self, size=1024):
        self.data = b'\xFF' * size  # 模拟图像数据
        
    def compressed(self, quality=75):
        """模拟compressed方法"""
        # 返回JPEG头 + 数据
        jpeg_header = b'\xFF\xD8\xFF\xE0\x00\x10JFIF'
        return jpeg_header + self.data[:100]  # 简化的JPEG数据

def test_compression():
    """测试图像压缩功能"""
    print("=" * 50)
    print("测试1: 图像压缩")
    print("=" * 50)
    
    streamer = MJPEGStreamer(quality=75)
    fake_img = FakeImage()
    
    print(f"创建假图像, 类型: {type(fake_img)}")
    print(f"是否有compressed方法: {hasattr(fake_img, 'compressed')}")
    
    compressed = streamer.compress_frame(fake_img)
    
    if compressed:
        print(f"✅ 压缩成功! 大小: {len(compressed)} 字节")
        print(f"JPEG头检查: {compressed[:4] == b'\\xFF\\xD8\\xFF\\xE0'}")
        return True
    else:
        print("❌ 压缩失败!")
        return False

def test_frame_update():
    """测试帧更新功能"""
    print("\n" + "=" * 50)
    print("测试2: 帧更新")
    print("=" * 50)
    
    streamer = MJPEGStreamer(quality=75, max_fps=10)
    
    print(f"初始帧: {streamer.current_frame}")
    
    # 更新几帧
    for i in range(5):
        fake_img = FakeImage(size=1024 * (i+1))
        streamer.update_frame(fake_img)
        time.sleep(0.12)  # 超过帧间隔(1/10 = 0.1s)
        print(f"更新帧 {i+1}, 当前帧: {streamer.current_frame is not None}")
    
    if streamer.current_frame is not None:
        print("✅ 帧更新成功!")
        return True
    else:
        print("❌ 帧更新失败!")
        return False

def main():
    print("\n视频流模块测试\n")
    
    test1_ok = test_compression()
    test2_ok = test_frame_update()
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    print(f"图像压缩: {'✅ 通过' if test1_ok else '❌ 失败'}")
    print(f"帧更新:   {'✅ 通过' if test2_ok else '❌ 失败'}")
    print("=" * 50)
    
    if test1_ok and test2_ok:
        print("\n🎉 所有测试通过!")
    else:
        print("\n⚠️ 部分测试失败，请检查!")

if __name__ == '__main__':
    main()
