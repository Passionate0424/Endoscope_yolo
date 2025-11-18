"""
K230 RTSP 支持检测脚本
检查设备是否支持RTSP功能及其API

使用方法:
1. 将此文件上传到K230设备
2. 运行: python test_rtsp_support.py
3. 查看输出了解设备RTSP支持情况
"""

import sys

print("=" * 60)
print("K230 RTSP 支持检测")
print("=" * 60)

# 1. 检查 media 模块
print("\n[1] 检查 media 模块...")
try:
    import media
    print("✓ media 模块可用")
    print(f"  media 模块属性: {[attr for attr in dir(media) if not attr.startswith('_')]}")
except ImportError as e:
    print(f"✗ media 模块不可用: {e}")
    media = None

# 2. 检查 media.rtsp_server
print("\n[2] 检查 media.rtsp_server...")
if media:
    try:
        from media.rtsp_server import RtspServer
        print("✓ media.rtsp_server.RtspServer 可用")
        print(f"  RtspServer 方法: {[attr for attr in dir(RtspServer) if not attr.startswith('_')]}")
    except ImportError as e:
        print(f"✗ media.rtsp_server 不可用: {e}")
    except AttributeError as e:
        print(f"✗ RtspServer 类不存在: {e}")
else:
    print("✗ 跳过 (media 模块不可用)")

# 3. 检查 media.vencoder
print("\n[3] 检查 media.vencoder...")
if media:
    try:
        from media.vencoder import Encoder, EncoderType
        print("✓ media.vencoder 可用")
        print(f"  Encoder 方法: {[attr for attr in dir(Encoder) if not attr.startswith('_')][:10]}")
        if hasattr(EncoderType, 'H264'):
            print(f"  EncoderType.H264: {EncoderType.H264}")
        if hasattr(EncoderType, 'H265'):
            print(f"  EncoderType.H265: {EncoderType.H265}")
    except ImportError as e:
        print(f"✗ media.vencoder 不可用: {e}")
else:
    print("✗ 跳过 (media 模块不可用)")

# 4. 检查 MediaManager
print("\n[4] 检查 MediaManager...")
if media:
    try:
        from media.media import MediaManager
        print("✓ MediaManager 可用")
        print(f"  MediaManager 方法: {[attr for attr in dir(MediaManager) if not attr.startswith('_')][:15]}")
    except ImportError as e:
        print(f"✗ MediaManager 不可用: {e}")
    except AttributeError as e:
        print(f"✗ MediaManager 类不存在: {e}")
else:
    print("✗ 跳过 (media 模块不可用)")

# 5. 检查网络模块
print("\n[5] 检查网络模块...")
try:
    import network
    print("✓ network 模块可用")
    print(f"  network 模块属性: {[attr for attr in dir(network) if not attr.startswith('_')]}")
except ImportError as e:
    print(f"✗ network 模块不可用: {e}")

# 6. 检查 socket
print("\n[6] 检查 socket...")
try:
    import socket
    print("✓ socket 模块可用")
except ImportError as e:
    print(f"✗ socket 模块不可用: {e}")

# 7. 固件信息
print("\n[7] 系统信息...")
try:
    import os
    print(f"  Python 版本: {sys.version}")
    print(f"  Python 实现: {sys.implementation.name if hasattr(sys, 'implementation') else 'Unknown'}")
    if hasattr(os, 'uname'):
        uname = os.uname()
        print(f"  系统信息: {uname}")
except Exception as e:
    print(f"  无法获取系统信息: {e}")

print("\n" + "=" * 60)
print("检测完成")
print("=" * 60)

# 8. 建议
print("\n📋 建议:")
print("1. 如果 media.rtsp_server 不可用:")
print("   - 检查 K230 固件版本（需要最新固件）")
print("   - 访问 https://www.canaan-creative.com/developer 下载最新固件")
print("   - 或使用 HTTP/MJPEG 方式代替 RTSP")
print()
print("2. 如果 MediaManager 可用但 rtsp_server 不可用:")
print("   - 可能需要通过 MediaManager 配置 RTSP")
print("   - 参考官方示例代码")
print()
print("3. 如果所有 media 模块都不可用:")
print("   - 设备可能不是 K230 或固件版本过旧")
print("   - 仅使用 HTTP 服务器功能")
