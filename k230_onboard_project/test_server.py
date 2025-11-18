"""
简单HTTP服务器测试
用于测试K230的socket是否正常工作
"""

import socket
import utime as time

def test_server():
    print("启动测试服务器...")
    
    # 创建socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 8888))
    s.listen(1)
    
    print("测试服务器启动成功，监听端口8888")
    print("请在浏览器访问: http://IP:8888")
    
    while True:
        print("\n等待连接...")
        client, addr = s.accept()
        print(f"新连接: {addr}")
        
        try:
            # 尝试接收数据
            data = client.recv(1024)
            print(f"收到数据长度: {len(data)}")
            try:
                print(f"数据内容:\n{data.decode('utf-8')}")
            except:
                print(f"数据内容:\n{data.decode('latin-1')}")
            
            # 发送简单响应
            response = b"HTTP/1.1 200 OK\r\n"
            response += b"Content-Type: text/html; charset=utf-8\r\n"
            response += b"Connection: close\r\n"
            response += b"\r\n"
            response += b"<html><body><h1>Hello from K230!</h1></body></html>"
            
            client.sendall(response)
            print("响应已发送")
            
        except Exception as e:
            print(f"错误: {e}")
            import sys
            sys.print_exception(e)
        finally:
            client.close()
            print("连接已关闭")

if __name__ == '__main__':
    test_server()
