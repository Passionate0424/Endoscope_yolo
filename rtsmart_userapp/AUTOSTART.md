# RT-Smart HTTP 服务器 - 自动启动配置

## 🚀 开机自启动方案

### 方案 1: RT-Smart 应用初始化（推荐）

#### 已添加代码
在 `http_server.c` 末尾添加了：
```c
int http_server_autostart(void)
{
    rt_thread_mdelay(3000);  // 等待网络
    rt_kprintf("[AutoStart] Starting HTTP server...\n");
    return http_server_init();
}

INIT_APP_EXPORT(http_server_autostart);
```

#### 工作原理
- `INIT_APP_EXPORT()` 会在 RT-Smart 系统启动后自动调用
- 延迟 3 秒确保网络驱动就绪
- 无需手动在串口输入 `http_start`

#### 编译启用
确保 RT-Smart 配置中开启了组件初始化：
```makefile
# 在 rtconfig.h 或 Kconfig 中
#define RT_USING_COMPONENTS_INIT
```

### 方案 2: 启动脚本（替代方案）

如果方案 1 不生效，使用 init 脚本：

#### 1. 复制脚本到 rootfs
```bash
# 在 SDK 编译时
cp init_scripts/S99_http_server.sh \
   /path/to/k230_sdk/board/common/post_copy_rootfs/etc/init.d/
chmod +x .../etc/init.d/S99_http_server.sh
```

#### 2. 重新编译固件
```bash
make CONF=k230_canmv_defconfig
make
```

#### 3. 烧录后自动运行
系统启动时会执行 `/etc/init.d/S99_*` 脚本。

## 🔍 验证自启动

### 查看启动日志（大核串口 COM47）
```
...
[AutoStart] Starting HTTP server...
[FrameBuffer] Initialized with 3 slots, quality=75
[HTTP] Server listening on port 8080
[AutoStart] ✅ HTTP server started successfully
msh />
```

### 手动检查
```bash
msh />http_status
HTTP Server Status:
  Running: Yes
  Port: 8080
  Frame Buffer: Ready
```

### Python 层无需改动
```python
# 直接运行，会自动检测 C 服务器是否就绪
import main_rtsmart
main_rtsmart.main()
```

## 🛠️ 故障排查

### 如果未自启动

#### 1. 检查是否编译进固件
```bash
msh />list
# 应该看到 http_start 命令
```

#### 2. 手动启动测试
```bash
msh />http_start
```

#### 3. 检查启动日志
查看串口输出是否有 `[AutoStart]` 日志。

### 禁用自启动

如果需要临时禁用，编辑代码：
```c
// 注释掉这行
// INIT_APP_EXPORT(http_server_autostart);
```

或在运行时停止：
```bash
msh />http_stop
```

## 📝 总结

- ✅ **方案 1（推荐）**: `INIT_APP_EXPORT()` 系统级自启动
- ⚙️ **方案 2（备用）**: `/etc/init.d/` 启动脚本
- 🎯 **目标**: 板子上电 → HTTP 服务器自动运行 → Python 层直接连接

开机后无需任何手动操作，HTTP 服务器自动在后台运行！
