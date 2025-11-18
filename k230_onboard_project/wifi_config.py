"""
WiFi连接配置模块
用于K230连接WiFi网络
"""

import network
import utime as time


def connect_wifi(ssid, password, timeout=30):
    """
    连接WiFi网络
    
    参数:
        ssid: WiFi名称
        password: WiFi密码
        timeout: 超时时间（秒）
    返回:
        (success, ip_address)
    """
    print("=" * 50)
    print("开始连接WiFi...")
    print(f"SSID: {ssid}")
    print("=" * 50)
    
    # 创建WLAN对象（STA模式 - 客户端模式）
    wlan = network.WLAN(network.STA_IF)
    
    # 激活网络接口
    wlan.active(True)
    
    # 扫描可用网络（可选，用于调试）
    print("正在扫描WiFi网络...")
    try:
        networks = wlan.scan()
        print(f"找到 {len(networks)} 个WiFi网络")
        for net in networks:
            print(f"  - {net}")
    except Exception as e:
        print(f"扫描网络失败: {e}")
    
    # 连接到指定WiFi
    print(f"\n正在连接到 '{ssid}'...")
    wlan.connect(ssid, password)
    
    # 等待连接成功
    start_time = time.time()
    while not wlan.isconnected():
        if time.time() - start_time > timeout:
            print("❌ 连接超时！")
            return False, None
        
        print(".", end="")
        time.sleep(1)
    
    print("\n✅ WiFi连接成功！")
    
    # 获取网络配置信息
    ifconfig = wlan.ifconfig()
    ip_address = ifconfig[0]
    subnet = ifconfig[1]
    gateway = ifconfig[2]
    dns = ifconfig[3]
    
    print("\n" + "=" * 50)
    print("网络信息:")
    print(f"  IP地址:    {ip_address}")
    print(f"  子网掩码:  {subnet}")
    print(f"  网关:      {gateway}")
    print(f"  DNS:       {dns}")
    print("=" * 50)
    
    # 显示详细连接状态
    try:
        status = wlan.status()
        print("\n连接详情:")
        print(status)
    except:
        pass
    
    print(f"\n🌐 请在浏览器访问: http://{ip_address}:8080")
    print("=" * 50)
    
    return True, ip_address


def disconnect_wifi():
    """断开WiFi连接"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.disconnect()
        wlan.active(False)
        print("WiFi已断开")
    except Exception as e:
        print(f"断开WiFi失败: {e}")


def get_wifi_status():
    """获取WiFi连接状态"""
    try:
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            ifconfig = wlan.ifconfig()
            return {
                'connected': True,
                'ip': ifconfig[0],
                'subnet': ifconfig[1],
                'gateway': ifconfig[2],
                'dns': ifconfig[3]
            }
        else:
            return {'connected': False}
    except Exception as e:
        print(f"获取WiFi状态失败: {e}")
        return {'connected': False}


# WiFi配置
WIFI_SSID = "Passionate的Mate70Pro+"
WIFI_PASSWORD = "20050424"


if __name__ == '__main__':
    # 测试WiFi连接
    success, ip = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    if success:
        print(f"\n测试成功！IP地址: {ip}")
    else:
        print("\n测试失败！")
