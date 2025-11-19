#!/bin/sh
# RT-Smart 启动脚本
# 路径: /etc/init.d/S99_http_server

echo "[Init] 启动 HTTP 服务器..."

# 等待网络就绪
sleep 2

# 启动 HTTP 服务器
if [ -f /bin/rtsmart_webserver ]; then
    /bin/rtsmart_webserver &
    echo "[Init] ✅ HTTP 服务器已启动"
else
    echo "[Init] ❌ HTTP 服务器程序未找到"
fi
