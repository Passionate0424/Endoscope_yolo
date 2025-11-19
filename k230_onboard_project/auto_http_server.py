"""
自动启动 HTTP 服务器的辅助脚本
在大核 RT-Smart 串口执行一次，之后 Python 可以直接推送帧
"""

import os
import sys

def start_http_server():
    """
    通过 RT-Smart 的系统接口启动 HTTP 服务器
    需要在大核 RT-Smart 串口执行，或通过 subprocess 调用
    """
    try:
        # 方法1：尝试通过系统调用执行 msh 命令
        # （需要内核支持）
        cmd = "http_start"
        print("[AutoHTTP] 尝试启动 HTTP 服务器: %s" % cmd)
        
        # 在 RT-Smart 中，可以通过 /dev/console 或系统调用启动命令
        # 这里是一个简化版本
        try:
            # 尝试通过 os.system（如果支持）
            ret = os.system(cmd)
            if ret == 0:
                print("[AutoHTTP] ✅ HTTP 服务器已启动")
                return True
        except:
            pass
        
        # 方法2：通过串口发送命令
        try:
            # 写入 RT-Smart 的 msh 控制接口（如果存在）
            with open("/dev/rtthread-console", "w") as f:
                f.write("http_start\n")
            print("[AutoHTTP] ✅ 已向 RT-Smart 发送启动命令")
            return True
        except:
            pass
        
        print("[AutoHTTP] ⚠️ 无法自动启动服务器")
        print("[AutoHTTP] 请在大核串口手动执行: http_start")
        return False
        
    except Exception as e:
        print("[AutoHTTP] ❌ 启动失败: " + str(e))
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("RT-Smart HTTP 服务器自动启动工具")
    print("=" * 50)
    
    if start_http_server():
        print("✅ HTTP 服务器启动成功")
    else:
        print("❌ HTTP 服务器启动失败")
        print("\n手动启动方法:")
        print("在大核 RT-Smart 串口中执行:")
        print("  > http_start")
        print("\n查看服务器状态:")
        print("  > http_status")
        print("\n停止服务器:")
        print("  > http_stop")


if __name__ == "__main__":
    main()
