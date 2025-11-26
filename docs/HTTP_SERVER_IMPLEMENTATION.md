# C层HTTP服务器实现详解

## 1. 概述

本项目中的C层HTTP服务器是专为嵌入式系统设计的轻量级Web服务器，主要用于提供实时视频流(MJPEG)、API接口以及静态资源服务。该服务器支持在RT-Smart内核态和MicroPython用户态两种环境下编译运行，通过条件编译实现跨平台兼容性。

## 2. 架构设计

### 2.1 多线程架构

HTTP服务器采用多线程模型处理并发连接：

1. **监听线程(accept_thread)**：负责接收新的客户端连接
2. **工作线程池(worker_threads)**：固定数量的工作线程处理实际的HTTP请求
3. **任务队列机制**：使用环形缓冲区作为任务队列，协调连接分发

这种设计避免了为每个连接创建新线程的开销，同时保证了良好的并发性能。

### 2.2 双版本实现

服务器通过`RTSMART_WEB_PORTABLE`宏定义区分两个版本：

- **RT-Smart原生版本**：针对RT-Smart实时操作系统优化
- **Portable版本**：可在Linux/MicroPython等POSIX兼容环境中运行

```c
#ifndef RTSMART_WEB_PORTABLE
// RT-Smart 版本实现
#else
// Portable 版本实现
#endif
```

## 3. 核心模块

### 3.1 HTTP请求处理 (http_handler.c)

#### 3.1.1 静态资源服务
处理网页文件请求，如主页(index.html)和JavaScript文件(app.js)。

```c
int http_handle_static_request(int client_fd, const char *path)
{
    if (!path)
        return http_send_404(client_fd);

    if (strcmp(path, "/") == 0 || strcmp(path, "/index.html") == 0)
    {
        return http_send_binary(client_fd, "text/html; charset=utf-8",
                                STATIC_INDEX_HTML_DATA, STATIC_INDEX_HTML_LEN);
    }

    if (strcmp(path, "/app.js") == 0)
    {
        return http_send_binary(client_fd, "application/javascript; charset=utf-8",
                                STATIC_APP_JS_DATA, STATIC_APP_JS_LEN);
    }
    
    // ... 其他处理
}
```

#### 3.1.2 API接口处理
提供RESTful API接口用于控制系统功能：

```c
int http_handle_api_request(int client_fd,
                            const char *method,
                            const char *path,
                            const char *query,
                            const char *body)
{
    if (strcmp(path, "/api/status") == 0 && strcmp(method, "GET") == 0)
    {
        return http_send_status(client_fd);
    }

    if (strcmp(path, "/api/camera/start") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_request_camera(RT_TRUE);
        return http_send_json(client_fd, "{\"success\":true}");
    }
    
    // ... 其他API处理
}
```

#### 3.1.3 MJPEG视频流
核心功能，提供实时视频流服务：

```c
int http_handle_mjpeg_stream(int client_fd)
{
    uint8_t *jpeg_data = NULL;
    size_t jpeg_size = 0;
    char boundary_header[256];
    int frame_count = 0;
    int frame_interval_ms = 1000 / MAX_FPS;
    
    // 发送MJPEG流头部
    const char *stream_header =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: multipart/x-mixed-replace; boundary=" MJPEG_BOUNDARY "\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-cache, no-store, must-revalidate\r\n"
        "\r\n";

    if (send(client_fd, stream_header, strlen(stream_header), 0) < 0)
    {
        rt_kprintf("[MJPEG] Failed to send header\n");
        return -1;
    }

    while (1)
    {
        // 控制帧率
        // 获取最新帧
        // 发送帧数据
    }
}
```

### 3.2 服务器主程序 (http_server.c)

#### 3.2.1 服务器初始化
初始化套接字、帧缓冲区和线程池：

```c
int http_server_init(void)
{
    struct sockaddr_in server_addr;
    int opt = 1;

    // 初始化帧缓冲区
    if (frame_buffer_init(FRAME_BUFFER_QUALITY) != 0)
    {
        rt_kprintf("[HTTP] Failed to init frame buffer\n");
        return -1;
    }

    http_handler_init();

    // 创建 socket
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0)
    {
        rt_kprintf("[HTTP] Failed to create socket, errno=%d\n", errno);
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    // 设置 socket 选项
    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0)
    {
        rt_kprintf("[HTTP] Warning: setsockopt SO_REUSEADDR failed, errno=%d\n", errno);
    }

    // 绑定地址和监听
    // 初始化任务队列
    // 启动工作线程
    // 启动监听线程
}
```

#### 3.2.2 工作线程处理
工作线程从任务队列中取出客户端连接进行处理：

```c
static void worker_thread_entry(void *parameter)
{
    client_ctx_t ctx_local;
    while (1)
    {
        // 从任务队列获取任务
        // 处理客户端请求
    }
}
```

#### 3.2.3 监听线程处理
监听线程接收新连接并将其放入任务队列：

```c
static void accept_thread_func(void *parameter)
{
    struct sockaddr_in client_addr;
    socklen_t addr_len;
    int client_fd;

    while (server_running)
    {
        addr_len = sizeof(client_addr);
        client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addr_len);

        if (client_fd < 0)
        {
            // 错误处理
            continue;
        }

        // 将连接放入任务队列
        client_ctx_t ctx;
        ctx.client_fd = client_fd;
        ctx.client_addr = client_addr;

        rt_mutex_take(queue_lock, RT_WAITING_FOREVER);
        if (queue_is_full())
        {
            // 队列满，拒绝连接
        }
        queue_push(&ctx);
        rt_mutex_release(queue_lock);
        rt_sem_release(queue_sem);
    }
}
```

## 4. 技术特点

### 4.1 跨平台适配

通过宏定义和条件编译实现跨平台支持：

```c
#ifndef RTSMART_WEB_PORTABLE
#include <rtthread.h>
#include <dfs_posix.h>
#else
#include "py/mphal.h"
#include <time.h>
#include <unistd.h>
#include <errno.h>
// 重新定义RT-Thread相关函数
#define rt_tick_get() portable_tick_get()
#define rt_thread_mdelay(ms) portable_thread_mdelay(ms)
#define rt_kprintf printf
#define rt_snprintf snprintf
#define rt_malloc malloc
#define rt_free free
#endif
```

### 4.2 浮点数处理优化

由于RT-Thread内核中的snprintf不支持浮点数格式化，代码采用了手动格式化浮点数的方法：

```c
// 手动格式化浮点数：转换为整数（保留2位小数）
int actual_conf_int = (int)(actual_conf * 100.0f + 0.5f); // 四舍五入
int desired_conf_int = (int)(desired_conf * 100.0f + 0.5f);
int fps_int = (int)(fps * 100.0f + 0.5f);

// 构建浮点数字符串
char actual_conf_str[16], desired_conf_str[16], fps_str[16];
int actual_int = actual_conf_int / 100;
int actual_frac = actual_conf_int % 100;
rt_snprintf(actual_conf_str, sizeof(actual_conf_str), "%d.%02d", actual_int, actual_frac);
```

### 4.3 内存管理

对于大JSON响应使用动态内存分配，及时释放临时分配的内存：

```c
static int http_send_status(int client_fd)
{
    char json[1024]; // 静态缓冲区
    char *json_buf = json;
    size_t buf_size = sizeof(json);
    
    // 如果静态缓冲区不够，使用动态分配
    if (len >= (int)buf_size - 1)
    {
        buf_size = 2048;
        json_buf = (char *)rt_malloc(buf_size);
        // 处理完成后释放内存
        if (json_buf != json)
        {
            rt_free(json_buf);
        }
    }
}
```

## 5. 功能模块

### 5.1 实时视频流
- MJPEG视频流传输
- 帧率控制(最大30FPS)
- 超时检测和自动断开机制

### 5.2 API接口
- 系统状态查询(/api/status)
- 相机控制(/api/camera/start, /api/camera/stop)
- 检测功能开关(/api/detection/enable, /api/detection/disable)
- 置信度设置(/api/config/confidence)
- 检测记录管理(/api/records/*)

### 5.3 静态资源服务
- 内嵌Web前端资源
- 检测结果图片查看(/detections/*)

## 6. WiFi自动连接

服务器内置WiFi自动连接和重连机制，确保网络可用后再启动HTTP服务：

```c
static void http_server_autostart_thread(void *param)
{
    // 等待网络就绪
    while (check_count < MAX_WAIT_ITERATIONS)
    {
        if (is_network_ready())
        {
            consecutive_ok++;
            if (consecutive_ok >= CONSECUTIVE_CHECKS)
            {
                break; // 网络已就绪
            }
        }
        rt_thread_mdelay(500);
        check_count++;
    }
    
    // 启动HTTP服务器
    http_server_init();
}
```

## 7. 总结

这个C语言实现的HTTP服务器专为嵌入式环境设计，具备以下特点：

1. **轻量级**：适合资源受限的嵌入式设备
2. **高性能**：线程池+任务队列模式有效处理并发
3. **可扩展**：模块化设计便于添加新功能
4. **可移植**：支持多种运行环境
5. **实用性强**：专门针对视频流应用场景优化

整个实现充分考虑了嵌入式系统的特殊需求，在功能完整性和系统资源占用之间取得了良好平衡。