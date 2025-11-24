"""
极简HTTP服务器测试脚本
目的：只启动Wi-Fi和C层HTTP服务器，不涉及任何摄像头或YOLO逻辑。
用于验证HTTP服务器C代码本身在MicroPython环境下的基本稳定性。
"""

import utime as time
from wifi_config import WIFI_PASSWORD, WIFI_SSID, connect_wifi


def start_http_server():
    """启动 C 层 HTTP 服务器"""
    try:
        import rtsmart_web

        rtsmart_web.start_server()
        print("[RTWeb] HTTP 服务器已启动")
        return True
    except Exception as e:
        print("[RTWeb] 启动 HTTP 服务器失败: %s" % e)
        return False


def main():
    print("=" * 50)
    print("K230 极简HTTP服务器测试")
    print("=" * 50)

    # 1. 连接 Wi-Fi
    if not connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("Wi-Fi 连接失败，退出")
        return

    # 2. 启动 HTTP 服务器
    if not start_http_server():
        print("HTTP 服务器启动失败，退出")
        return

    # 3. 保持运行
    print("服务器已启动。现在您可以从浏览器访问。")
    print("此模式下没有视频流，只测试服务器稳定性。")
    print("按 Ctrl+C 停止\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止中...")
    finally:
        print("程序已退出")


if __name__ == "__main__":
    main()
