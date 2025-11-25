# K230 RT-Smart Web 服务器

## 架构设计

### 混合架构（C + Python）
```
┌─────────────────────────────────────────────┐
│          Python 层 (MicroPython)             │
│  - YOLO 检测 (yolo_controller.py)          │
│  - CanMV IDE 监控                            │
│  - 业务逻辑 (detection_manager.py)         │
│  - 帧推送 (rtsmart_web.push_frame())       │
└───────────────┬─────────────────────────────┘
                │ MicroPython C Module
┌───────────────▼─────────────────────────────┐
│         C 层 (RT-Smart userapp)             │
│  - HTTP 服务器 (pthread + lwIP)            │
│  - MJPEG 流发送 (http_handler.c)           │
│  - 帧缓冲区 (frame_buffer.c)               │
│  - 网络调度 (RT-Thread API)                │
└─────────────────────────────────────────────┘
```

### 优势
- **C 层高性能**: HTTP + MJPEG 由 RT-Smart 原生 pthread 处理
- **Python 灵活性**: YOLO 检测使用现有 CanMV 框架
- **CanMV IDE 支持**: 可在 IDE 中监控和调试

## 集成到 K230 SDK

### 1. 复制代码到 SDK
```bash
# 假设你的 SDK 路径是 /path/to/k230_sdk
cp -r rtsmart_userapp /path/to/k230_sdk/src/big/rt-smart/userapps/rtsmart_webserver
```

### 2. 修改 SDK Makefile
编辑 `/path/to/k230_sdk/src/big/rt-smart/userapps/Makefile`，添加：
```makefile
# RT-Smart Web Server
SUBDIRS += rtsmart_webserver
```

### 3. 创建 userapp Makefile
在 `/path/to/k230_sdk/src/big/rt-smart/userapps/rtsmart_webserver/` 创建 `Makefile`:
```makefile
# RT-Smart Web Server Makefile
include $(RTT_ROOT)/userapps/sdk.mk

CFLAGS += -I./include
LDFLAGS += -lpthread

SRCS := src/http_server.c \
        src/http_handler.c \
        src/frame_buffer.c

OBJS := $(SRCS:.c=.o)

TARGET := rtsmart_webserver.elf

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

install:
	cp $(TARGET) $(INSTALL_DIR)/bin/

.PHONY: all clean install
```

### 4. 集成 MicroPython 模块
复制绑定代码到 CanMV 模块目录：
```bash
cp micropython_binding/rtsmart_web_module.c \
   /path/to/k230_sdk/src/big/rt-smart/kernel/bsp/maix3/applications/canmv/port/modules/
```

修改 `/path/to/k230_sdk/src/big/rt-smart/kernel/bsp/maix3/applications/canmv/port/Makefile`:
```makefile
# 在 SRC_C 中添加
SRC_C += modules/rtsmart_web_module.c
```

### 5. 编译 SDK
```bash
cd /path/to/k230_sdk

# 配置为 CanMV 双系统
make CONF=k230_canmv_defconfig

# 或 RT-Smart 单系统
# make CONF=k230_canmv_only_rtt_defconfig

# 编译
make
```

### 6. 烧录固件
生成的镜像在 `output/k230_canmv_defconfig/images/sysimage-sdcard.img`，使用 rufus 或 dd 烧录到 SD 卡。

## 使用方法

### RT-Smart 串口启动 HTTP 服务器
插入 SD 卡，板子上电后，在大核串口（COM47）输入：
```bash
msh />http_start
[HTTP] Server listening on port 8080
[HTTP] Server started successfully
```

### Python 层推送帧
在 CanMV IDE 或小核串口（COM48）运行：
```python
from rtsmart_web_adapter import RTWebAdapter
from yolo_controller import YOLOController

# 初始化
# 推荐：禁用 HTTP API 控制读取（改为直接使用 C 绑定），并限制 control poll 频率与推帧速率
web_adapter = RTWebAdapter(quality=75, control_poll_interval_ms=5000, use_http_api_for_control=False, min_push_interval_ms=100)
yolo_controller = YOLOController()

# 设置帧回调（YOLO 检测完后推送）
yolo_controller.set_frame_callback(web_adapter.update_frame)

# 启动 YOLO
yolo_controller.start_camera()
yolo_controller.enable_detection()

# 检查状态
print(web_adapter.get_stats())
```

### 浏览器访问
在电脑浏览器打开：
```
http://<板子IP>:8080/
```

## API 文档

### RT-Smart 命令（大核串口）
| 命令 | 说明 |
|------|------|
| `http_start` | 启动 HTTP 服务器 |
| `http_stop` | 停止 HTTP 服务器 |
| `http_status` | 查看服务器状态 |

### Python API（rtsmart_web 模块）
```python
import rtsmart_web

# 推送 JPEG 帧
jpeg_bytes = image.compress(quality=75)
rtsmart_web.push_frame(jpeg_bytes)

# 检查服务器状态
if rtsmart_web.is_ready():
    print("Server ready!")

# 获取统计信息
stats = rtsmart_web.get_stats()
print(stats)  # {'ready': True, 'port': 8080}
```

### Python 适配层（rtsmart_web_adapter.py）
```python
from rtsmart_web_adapter import RTWebAdapter

# 创建适配器
adapter = RTWebAdapter(quality=75, control_poll_interval_ms=5000, use_http_api_for_control=False, min_push_interval_ms=100)

# 推送帧（由 YOLO 回调）
adapter.update_frame(image)

# 检查状态
if adapter.is_ready():
    stats = adapter.get_stats()
```

## 性能预期

| 指标 | 纯 Python | RT-Smart C 层 |
|------|-----------|--------------|
| HTTP 并发 | 1-2 客户端 | 5+ 客户端 |
| MJPEG 帧率 | 12-15 fps | 30 fps |
| CPU 占用 | 80% | 40% |
| 内存占用 | 8MB (Python heap) | 3MB (C malloc) |
| GC 抖动 | 明显 | 无 |

## 故障排查

### 1. 编译错误
- **找不到 rtthread.h**: 确保在 RT-Smart SDK 环境中编译
- **undefined reference to pthread**: 在 LDFLAGS 添加 `-lpthread`

### 2. 运行时错误
- **ImportError: rtsmart_web**: MicroPython 绑定未编译进固件
- **http_start 命令不存在**: userapp 未编译或未安装到文件系统

### 3. 网络问题
- **无法连接 8080**: 检查 Wi-Fi 连接（使用 `ifconfig` 查看 IP）
- **MJPEG 流卡顿**: 检查帧推送频率（应 >= 15fps）

## 开发建议

### 调试 C 层
使用 T-Head DebugServer + GDB：
```bash
riscv64-unknown-linux-gnu-gdb rtsmart_webserver.elf
(gdb) target remote <板子IP>:1025
(gdb) b http_handle_mjpeg_stream
(gdb) c
```

### 调试 Python 层
在 CanMV IDE 中添加日志：
```python
import rtsmart_web_adapter
rtsmart_web_adapter.print_info()  # 打印系统信息
```

### 性能分析
```bash
# RT-Smart 串口
msh />list_thread  # 查看线程
msh />free         # 查看内存
```

## 扩展功能

### 1. 添加 WebSocket 支持
修改 `http_handler.c`，参考 lwIP WebSocket 示例。

### 2. 多路摄像头
在 `frame_buffer.c` 中支持多个缓冲区实例。

### 3. 硬件 JPEG 编码
集成 K230 VENC 编码器，替换 Python 的 `image.compress()`。

## 参考资料
- [K230 SDK 文档](https://www.kendryte.com/k230/dev/zh/)
- [RT-Thread Smart 文档](https://www.rt-thread.org/document/site/programming-manual/smart/smart/)
- [庐山派 K230 Wiki](https://wiki.lckfb.com/zh-hans/lushan-pi-k230/)
