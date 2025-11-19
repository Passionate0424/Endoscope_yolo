/*
 * RT-Smart HTTP 服务器主程序
 * 基于 K230 SDK RT-Smart 系统
 * 支持 MJPEG 流发送、多客户端并发
 */

#include <rtthread.h>
#include <dfs_posix.h>
#include <sys/socket.h>
#include <netdb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <ifaddrs.h>
#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>

#include "frame_buffer.h"
#include "http_handler.h"
#include "config.h"

#define SERVER_PORT 8080
#define MAX_CLIENTS 5
#define STACK_SIZE (8 * 1024)

// 全局服务器状态
static int server_fd = -1;
static int server_running = 0;
static pthread_t accept_thread;

// 客户端连接处理
typedef struct
{
    int client_fd;
    struct sockaddr_in client_addr;
    pthread_t thread;
} client_ctx_t;

static void *client_handler_thread(void *arg)
{
    client_ctx_t *ctx = (client_ctx_t *)arg;
    char buffer[2048];
    int n;

    rt_kprintf("[HTTP] Client connected from %s:%d\n",
               inet_ntoa(ctx->client_addr.sin_addr),
               ntohs(ctx->client_addr.sin_port));

    // 读取 HTTP 请求
    n = recv(ctx->client_fd, buffer, sizeof(buffer) - 1, 0);
    if (n <= 0)
    {
        rt_kprintf("[HTTP] Failed to read request\n");
        goto cleanup;
    }
    buffer[n] = '\0';

    // 解析请求
    if (strncmp(buffer, "GET /stream", 11) == 0)
    {
        // MJPEG 流请求
        http_handle_mjpeg_stream(ctx->client_fd);
    }
    else if (strncmp(buffer, "GET /snapshot", 13) == 0)
    {
        // 快照请求
        http_handle_snapshot(ctx->client_fd);
    }
    else if (strncmp(buffer, "GET /", 5) == 0)
    {
        // 主页
        http_handle_index(ctx->client_fd);
    }
    else if (strncmp(buffer, "POST /api/", 10) == 0)
    {
        // API 请求
        http_handle_api(ctx->client_fd, buffer, n);
    }
    else
    {
        // 404
        http_send_404(ctx->client_fd);
    }

cleanup:
    close(ctx->client_fd);
    rt_kprintf("[HTTP] Client disconnected\n");
    rt_free(ctx);
    return NULL;
}

// 接受连接线程
static void *accept_thread_func(void *arg)
{
    struct sockaddr_in client_addr;
    socklen_t addr_len;
    int client_fd;

    rt_kprintf("[HTTP] Accept thread started\n");

    while (server_running)
    {
        addr_len = sizeof(client_addr);
        client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addr_len);

        if (client_fd < 0)
        {
            if (server_running)
            {
                rt_kprintf("[HTTP] Accept failed: %d\n", errno);
                rt_thread_mdelay(100);
            }
            continue;
        }

        // 创建客户端处理线程
        client_ctx_t *ctx = (client_ctx_t *)rt_malloc(sizeof(client_ctx_t));
        if (!ctx)
        {
            rt_kprintf("[HTTP] Failed to allocate client context\n");
            close(client_fd);
            continue;
        }

        ctx->client_fd = client_fd;
        ctx->client_addr = client_addr;

        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, STACK_SIZE);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);

        if (pthread_create(&ctx->thread, &attr, client_handler_thread, ctx) != 0)
        {
            rt_kprintf("[HTTP] Failed to create client thread\n");
            close(client_fd);
            rt_free(ctx);
        }

        pthread_attr_destroy(&attr);
    }

    rt_kprintf("[HTTP] Accept thread stopped\n");
    return NULL;
}

// 初始化 HTTP 服务器
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

    // 创建 socket
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0)
    {
        rt_kprintf("[HTTP] Failed to create socket\n");
        return -1;
    }

    // 设置 socket 选项
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // 绑定地址
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(SERVER_PORT);

    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        rt_kprintf("[HTTP] Failed to bind socket\n");
        close(server_fd);
        return -1;
    }

    // 监听
    if (listen(server_fd, MAX_CLIENTS) < 0)
    {
        rt_kprintf("[HTTP] Failed to listen\n");
        close(server_fd);
        return -1;
    }

    rt_kprintf("[HTTP] Server listening on port %d\n", SERVER_PORT);

    // 创建接受连接线程
    server_running = 1;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, STACK_SIZE);

    if (pthread_create(&accept_thread, &attr, accept_thread_func, NULL) != 0)
    {
        rt_kprintf("[HTTP] Failed to create accept thread\n");
        close(server_fd);
        return -1;
    }

    pthread_attr_destroy(&attr);

    rt_kprintf("[HTTP] Server started successfully\n");
    return 0;
}

// 停止 HTTP 服务器
void http_server_deinit(void)
{
    if (server_running)
    {
        server_running = 0;

        // 关闭 socket（会让 accept 退出）
        if (server_fd >= 0)
        {
            close(server_fd);
            server_fd = -1;
        }

        // 等待线程退出
        pthread_join(accept_thread, NULL);

        // 清理帧缓冲
        frame_buffer_deinit();

        rt_kprintf("[HTTP] Server stopped\n");
    }
}

// 导出到 MSH 命令行
static int cmd_http_server_start(int argc, char **argv)
{
    if (server_running)
    {
        rt_kprintf("HTTP server already running\n");
        return 0;
    }

    return http_server_init();
}

static int cmd_http_server_stop(int argc, char **argv)
{
    http_server_deinit();
    return 0;
}

static int cmd_http_server_status(int argc, char **argv)
{
    rt_kprintf("HTTP Server Status:\n");
    rt_kprintf("  Running: %s\n", server_running ? "Yes" : "No");
    rt_kprintf("  Port: %d\n", SERVER_PORT);
    rt_kprintf("  Frame Buffer: %s\n", frame_buffer_is_ready() ? "Ready" : "Not Ready");
    return 0;
}

MSH_CMD_EXPORT_ALIAS(cmd_http_server_start, http_start, Start HTTP server);
MSH_CMD_EXPORT_ALIAS(cmd_http_server_stop, http_stop, Stop HTTP server);
MSH_CMD_EXPORT_ALIAS(cmd_http_server_status, http_status, Show HTTP server status);

/* ====== WiFi 监控 + 自动启动 ====== */

/**
 * 检查网络接口是否就绪
 * 通过检查是否存在有效的 IPv4 地址来判断网络是否初始化
 */
static int is_network_ready(void)
{
    struct ifaddrs *ifaddr, *ifa;
    int family;
    int has_valid_ip = 0;

    // 获取网络接口信息
    if (getifaddrs(&ifaddr) == -1)
    {
        printf("[HTTP] getifaddrs() failed\n");
        return 0;
    }

    // 遍历所有网络接口
    for (ifa = ifaddr; ifa != NULL; ifa = ifa->ifa_next)
    {
        if (ifa->ifa_addr == NULL)
            continue;

        family = ifa->ifa_addr->sa_family;

        // 只检查 IPv4 地址
        if (family == AF_INET)
        {
            struct sockaddr_in *sin = (struct sockaddr_in *)ifa->ifa_addr;

            // 检查是否为回环地址 (127.0.0.1)
            if (sin->sin_addr.s_addr == htonl(INADDR_LOOPBACK))
                continue;

            // 检查是否为有效地址 (非全零)
            if (sin->sin_addr.s_addr != 0)
            {
                char ip_str[INET_ADDRSTRLEN];
                inet_ntop(AF_INET, &sin->sin_addr, ip_str, INET_ADDRSTRLEN);
                printf("[HTTP] Found valid IP on %s: %s\n", ifa->ifa_name, ip_str);
                has_valid_ip = 1;
                break;
            }
        }
    }

    freeifaddrs(ifaddr);

    if (has_valid_ip)
    {
        printf("[HTTP] Network is ready!\n");
        return 1;
    }

    return 0;
}

/**
 * WiFi 监控线程
 * - 每 500ms 检查一次网络状态
 * - 网络就绪后启动 HTTP 服务器
 * - 超时 60 秒后强制启动
 */
static void http_server_autostart_thread(void *param)
{
    int check_count = 0;
    int consecutive_ok = 0;
    const int MAX_WAIT_ITERATIONS = 60; // 最多 120 * 500ms = 60 秒
    const int CONSECUTIVE_CHECKS = 3;   // 连续成功 3 次才启动

    rt_kprintf("\n");
    rt_kprintf("╔════════════════════════════════════════════════════╗\n");
    rt_kprintf("║   🌐 大核: WiFi 网络感知自启动系统                 ║\n");
    rt_kprintf("╚════════════════════════════════════════════════════╝\n");
    rt_kprintf("[AutoStart] ⏳ 大核: 等待网络就绪中...\n");

    // 等待网络就绪
    while (check_count < MAX_WAIT_ITERATIONS)
    {
        if (is_network_ready())
        {
            consecutive_ok++;

            if (check_count % 6 == 0) // 每 3 秒输出一次
            {
                rt_kprintf("[AutoStart] 🟢 大核: 检测网络成功 (%d/%d)\n",
                           consecutive_ok, CONSECUTIVE_CHECKS);
            }

            if (consecutive_ok >= CONSECUTIVE_CHECKS)
            {
                rt_kprintf("[AutoStart] ✅ 大核: 网络已就绪！\n");
                break;
            }
        }
        else
        {
            consecutive_ok = 0;

            if (check_count % 6 == 0) // 每 3 秒输出一次
            {
                rt_kprintf("[AutoStart] ⏳ 大核: 等待网络... (%d秒)\n", check_count / 2);
            }
        }

        rt_thread_mdelay(500); // 睡眠 500ms
        check_count++;
    }

    if (check_count >= MAX_WAIT_ITERATIONS)
    {
        rt_kprintf("[AutoStart] ⚠️ 大核: 网络超时，强制启动服务器\n");
    }

    rt_kprintf("\n");
    rt_kprintf("════════════════════════════════════════════════════\n");
    rt_kprintf("[AutoStart] 🚀 大核: 启动 HTTP 服务器...\n");
    rt_kprintf("════════════════════════════════════════════════════\n");

    int ret = http_server_init();

    if (ret == 0)
    {
        rt_kprintf("\n");
        rt_kprintf("╔════════════════════════════════════════════════════╗\n");
        rt_kprintf("║              🎉 系统已完全就绪！                   ║\n");
        rt_kprintf("╠════════════════════════════════════════════════════╣\n");
        rt_kprintf("║  ✅ HTTP 服务器已启动 (大核)                       ║\n");
        rt_kprintf("║  🌐 访问地址: http://192.168.43.14:8080/         ║\n");
        rt_kprintf("║  📺 MJPEG: http://192.168.43.14:8080/stream      ║\n");
        rt_kprintf("║  📸 快照:   http://192.168.43.14:8080/snapshot   ║\n");
        rt_kprintf("╚════════════════════════════════════════════════════╝\n");
        rt_kprintf("\n");
    }
    else
    {
        rt_kprintf("[AutoStart] ❌ HTTP 服务器启动失败 (错误码: %d)\n", ret);
    }
}
int http_server_autostart(void)
{
    rt_thread_t tid;

    tid = rt_thread_create("http_auto",
                           http_server_autostart_thread,
                           NULL,
                           16384,
                           RT_THREAD_PRIORITY_MAX - 2,
                           10);

    if (tid != RT_NULL)
    {
        rt_thread_startup(tid);
        rt_kprintf("[HTTP] ✅ 自启动监控线程已创建\n");
    }
    else
    {
        rt_kprintf("[HTTP] ❌ 自启动监控线程创建失败\n");
    }

    return 0;
}

// 注册到系统初始化（在 FinSH 之后运行）
INIT_APP_EXPORT(http_server_autostart);
