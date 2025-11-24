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
#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <wlan_mgnt.h>
#include <errno.h>

#include "frame_buffer.h"
#include "http_handler.h"
#include "../include/config.h"

#ifndef RTSMART_WEB_PORTABLE

#define SERVER_PORT 8080
#define MAX_CLIENTS 5
#define STACK_SIZE (16 * 1024)
#define WORKER_COUNT 4               /* 固定工作线程数 */
#define TASK_QUEUE_LEN 16            /* 任务队列长度 */
#define ACCEPT_THREAD_PRIORITY (RT_THREAD_PRIORITY_MAX - 4)
#define CLIENT_THREAD_PRIORITY (RT_THREAD_PRIORITY_MAX - 3)

#ifndef WIFI_CONNECT_TIMEOUT_MS
#define WIFI_CONNECT_TIMEOUT_MS 10000
#endif

#ifndef WIFI_CONNECT_MAX_RETRY
#define WIFI_CONNECT_MAX_RETRY 3
#endif

// 客户端上下文
typedef struct client_ctx_t
{
    int client_fd;
    struct sockaddr_in client_addr;
} client_ctx_t;


// 全局服务器状态
static int server_fd = -1;
static int server_running = 0;
static rt_thread_t accept_thread = RT_NULL;
static rt_uint16_t client_thread_index = 0;
static rt_sem_t wifi_ready_sem = RT_NULL;
static rt_bool_t wifi_handlers_registered = RT_FALSE;
/* 任务队列和 worker */
static client_ctx_t task_queue[TASK_QUEUE_LEN];
static int queue_head = 0;
static int queue_tail = 0;
static rt_mutex_t queue_lock = RT_NULL;
static rt_sem_t queue_sem = RT_NULL; /* 记录未处理任务数 */
static rt_thread_t worker_threads[WORKER_COUNT];


static int queue_is_full(void)
{
    int next = (queue_tail + 1) % TASK_QUEUE_LEN;
    return next == queue_head;
}

static int queue_is_empty(void)
{
    return queue_head == queue_tail;
}

static void queue_push(const client_ctx_t *ctx)
{
    task_queue[queue_tail] = *ctx;
    queue_tail = (queue_tail + 1) % TASK_QUEUE_LEN;
}

static int queue_pop(client_ctx_t *out)
{
    if (queue_is_empty())
    {
        return -1;
    }
    *out = task_queue[queue_head];
    queue_head = (queue_head + 1) % TASK_QUEUE_LEN;
    return 0;
}

static void client_handler_thread(void *parameter)
{
    client_ctx_t *ctx = (client_ctx_t *)parameter;
    char buffer[2048];
    int n;

    rt_kprintf("[HTTP] Client connected from %s:%d\n",
               inet_ntoa(ctx->client_addr.sin_addr),
               ntohs(ctx->client_addr.sin_port));

    n = recv(ctx->client_fd, buffer, sizeof(buffer) - 1, 0);
    if (n <= 0)
    {
        rt_kprintf("[HTTP] Failed to read request\n");
        goto cleanup;
    }
    buffer[n] = '\0';

    char method[8] = {0};
    char url[256] = {0};

    if (sscanf(buffer, "%7s %255s", method, url) != 2)
    {
        http_send_404(ctx->client_fd);
        goto cleanup;
    }

    char *body = strstr(buffer, "\r\n\r\n");
    if (body)
        body += 4;
    else
        body = buffer + n;

    char path[256];
    rt_strncpy(path, url, sizeof(path));
    char *query = NULL;
    char *query_pos = strchr(path, '?');
    if (query_pos)
    {
        *query_pos = '\0';
        query = query_pos + 1;
    }

    if (strcmp(method, "GET") == 0)
    {
        if (strcmp(path, "/stream") == 0)
        {
            http_handle_mjpeg_stream(ctx->client_fd);
        }
        else if (strcmp(path, "/snapshot") == 0)
        {
            http_handle_snapshot(ctx->client_fd);
        }
        else if (strncmp(path, "/api/", 5) == 0)
        {
            http_handle_api_request(ctx->client_fd, method, path, query, body);
        }
        else
        {
            http_handle_static_request(ctx->client_fd, path);
        }
    }
    else if (strcmp(method, "POST") == 0 || strcmp(method, "DELETE") == 0)
    {
        if (strncmp(path, "/api/", 5) == 0)
        {
            http_handle_api_request(ctx->client_fd, method, path, query, body);
        }
        else
        {
            http_send_404(ctx->client_fd);
        }
    }
    else
    {
        http_send_404(ctx->client_fd);
    }

cleanup:
    close(ctx->client_fd);
    rt_kprintf("[HTTP] Client disconnected\n");
    return;
}

/* worker 线程：循环处理任务，避免频繁创建/退出线程 */
static void worker_thread_entry(void *parameter)
{
    (void)parameter;
    client_ctx_t ctx_local;
    while (1)
    {
        if (rt_sem_take(queue_sem, RT_WAITING_FOREVER) != RT_EOK)
            continue;

        rt_mutex_take(queue_lock, RT_WAITING_FOREVER);
        int ret = queue_pop(&ctx_local);
        rt_mutex_release(queue_lock);

        if (ret != 0)
        {
            if (!server_running)
                break;
            continue;
        }

        if (!server_running)
        {
            close(ctx_local.client_fd);
            break;
        }

        client_handler_thread(&ctx_local);
    }
}

// 监听线程
// accept thread
static void accept_thread_func(void *parameter)
{
    (void)parameter;
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

        // enqueue client context
        client_ctx_t ctx;
        ctx.client_fd = client_fd;
        ctx.client_addr = client_addr;

        /* push to task queue */
        rt_mutex_take(queue_lock, RT_WAITING_FOREVER);
        if (queue_is_full())
        {
            rt_mutex_release(queue_lock);
            rt_kprintf("[HTTP] Task queue full, drop connection\n");
            close(client_fd);
            continue;
        }
        queue_push(&ctx);
        rt_mutex_release(queue_lock);
        rt_sem_release(queue_sem);
    }

    rt_kprintf("[HTTP] Accept thread stopped\n");
    accept_thread = RT_NULL;
    return;
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

    // 绑定地址
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(SERVER_PORT);

    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        rt_kprintf("[HTTP] Failed to bind socket, errno=%d\n", errno);
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    // 监听
    if (listen(server_fd, MAX_CLIENTS) < 0)
    {
        rt_kprintf("[HTTP] Failed to listen, errno=%d\n", errno);
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    rt_kprintf("[HTTP] Server listening on port %d\n", SERVER_PORT);
    /* 初始化任务队列 */
    queue_head = queue_tail = 0;
    queue_lock = rt_mutex_create("httpq", RT_IPC_FLAG_PRIO);
    if (queue_lock == RT_NULL)
    {
        rt_kprintf("[HTTP] Failed to create queue mutex\n");
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    queue_sem = rt_sem_create("httpq", 0, RT_IPC_FLAG_PRIO);
    if (queue_sem == RT_NULL)
    {
        rt_kprintf("[HTTP] Failed to create queue semaphore\n");
        rt_mutex_delete(queue_lock);
        queue_lock = RT_NULL;
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    /* 启动 worker 线程 */
    for (int i = 0; i < WORKER_COUNT; i++)
    {
        char name[8];
        rt_snprintf(name, sizeof(name), "httpw%d", i);
        worker_threads[i] = rt_thread_create(name,
                                             worker_thread_entry,
                                             RT_NULL,
                                             STACK_SIZE,
                                             CLIENT_THREAD_PRIORITY,
                                             20);
        if (worker_threads[i])
        {
            rt_thread_startup(worker_threads[i]);
        }
        else
        {
            rt_kprintf("[HTTP] Warning: create worker %d failed\n", i);
        }
    }


    // 创建接受连接线程
    server_running = 1;
    accept_thread = rt_thread_create("http_acc",
                                     accept_thread_func,
                                     RT_NULL,
                                     STACK_SIZE,
                                     ACCEPT_THREAD_PRIORITY,
                                     20);
    if (accept_thread == RT_NULL)
    {
        rt_kprintf("[HTTP] Failed to create accept thread\n");
        close(server_fd);
        server_fd = -1;
        server_running = 0;
        if (queue_sem)
        {
            rt_sem_delete(queue_sem);
            queue_sem = RT_NULL;
        }
        if (queue_lock)
        {
            rt_mutex_delete(queue_lock);
            queue_lock = RT_NULL;
        }
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    rt_thread_startup(accept_thread);

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

        if (queue_sem)
        {
            for (int i = 0; i < WORKER_COUNT; i++)
            {
                rt_sem_release(queue_sem);
            }
        }

        while (accept_thread != RT_NULL)
        {
            rt_thread_mdelay(50);
        }

        http_handler_deinit();
        // 清理帧缓冲
        frame_buffer_deinit();

        if (queue_sem)
        {
            rt_sem_delete(queue_sem);
            queue_sem = RT_NULL;
        }
        if (queue_lock)
        {
            rt_mutex_delete(queue_lock);
            queue_lock = RT_NULL;
        }

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

static void wifi_sta_connected_handler(int event, struct rt_wlan_buff *buff, void *parameter)
{
    (void)event;
    (void)buff;
    (void)parameter;
    rt_kprintf("[WiFi] STA connected to AP\n");
}

static void wifi_sta_disconnect_handler(int event, struct rt_wlan_buff *buff, void *parameter)
{
    (void)event;
    (void)buff;
    (void)parameter;
    rt_kprintf("[WiFi] STA disconnected, will retry...\n");
}

static void wifi_sta_got_ip_handler(int event, struct rt_wlan_buff *buff, void *parameter)
{
    (void)event;
    (void)buff;
    (void)parameter;

    if (wifi_ready_sem)
    {
        rt_sem_release(wifi_ready_sem);
    }
}

static void wifi_register_event_handlers(void)
{
    if (wifi_handlers_registered)
    {
        return;
    }

    rt_wlan_register_event_handler(RT_WLAN_EVT_STA_CONNECTED, wifi_sta_connected_handler, RT_NULL);
    rt_wlan_register_event_handler(RT_WLAN_EVT_STA_DISCONNECTED, wifi_sta_disconnect_handler, RT_NULL);
    rt_wlan_register_event_handler(RT_WLAN_EVT_READY, wifi_sta_got_ip_handler, RT_NULL);
    wifi_handlers_registered = RT_TRUE;
}

static rt_err_t wifi_connect_if_needed(void)
{
    rt_err_t ret;

    if (rt_wlan_is_ready())
    {
        return RT_EOK;
    }

    wifi_register_event_handlers();

    if (wifi_ready_sem == RT_NULL)
    {
        wifi_ready_sem = rt_sem_create("wifiip", 0, RT_IPC_FLAG_PRIO);
        if (wifi_ready_sem == RT_NULL)
        {
            rt_kprintf("[WiFi] Failed to create WiFi semaphore\n");
            return -RT_ENOMEM;
        }
    }
    else
    {
        while (rt_sem_take(wifi_ready_sem, RT_WAITING_NO) == RT_EOK)
        {
        }
    }

    ret = rt_wlan_set_mode(RT_WLAN_DEVICE_STA_NAME, RT_WLAN_STATION);
    if (ret != RT_EOK)
    {
        rt_kprintf("[WiFi] rt_wlan_set_mode failed (%d)\n", ret);
        return ret;
    }

    rt_wlan_config_autoreconnect(RT_TRUE);

    for (int attempt = 0; attempt < WIFI_CONNECT_MAX_RETRY; attempt++)
    {
        rt_kprintf("[WiFi] Connecting to %s (attempt %d/%d)\n",
                   WIFI_DEFAULT_SSID, attempt + 1, WIFI_CONNECT_MAX_RETRY);

        ret = rt_wlan_connect(WIFI_DEFAULT_SSID, WIFI_DEFAULT_PASSWORD);
        if (ret != RT_EOK)
        {
            rt_kprintf("[WiFi] rt_wlan_connect failed (%d)\n", ret);
            continue;
        }

        if (rt_sem_take(wifi_ready_sem, rt_tick_from_millisecond(WIFI_CONNECT_TIMEOUT_MS)) == RT_EOK)
        {
            rt_kprintf("[WiFi] STA got IP successfully\n");
            return RT_EOK;
        }

        rt_kprintf("[WiFi] Wait IP timeout, disconnect and retry\n");
        rt_wlan_disconnect();
    }

    return -RT_ETIMEOUT;
}

/**
 * 检查 WiFi 是否连接
 * 通过检查网络接口状态来判断
 */
static int is_wifi_connected(void)
{
    if (!rt_wlan_is_ready())
    {
        rt_kprintf("[HTTP] ⏳ WiFi not ready yet (link)\n");
        return 0;
    }

    struct sockaddr_in addr;
    int sock;
    struct timeval tv;

    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0)
    {
        rt_kprintf("[HTTP] [WiFi Check] socket failed\n");
        return 0;
    }

    tv.tv_sec = 2;
    tv.tv_usec = 0;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const void *)&tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, (const void *)&tv, sizeof(tv));

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(53);
    addr.sin_addr.s_addr = inet_addr("8.8.8.8");

    char test_data[1] = {0};
    int ret = sendto(sock, test_data, 1, 0, (struct sockaddr *)&addr, sizeof(addr));

    close(sock);

    if (ret >= 0)
    {
        rt_kprintf("[HTTP] ✅ WiFi connected (sendto success)\n");
        return 1;
    }
    else
    {
        rt_kprintf("[HTTP] ⏳ WiFi not ready yet\n");
        return 0;
    }
}

/**
 * 检查网络接口是否就绪
 * 使用 WiFi 连接状态判断
 */
static int is_network_ready(void)
{
    return is_wifi_connected();
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
    int wifi_retry_cooldown = 0;
    rt_err_t wifi_ret;

    rt_kprintf("\n");
    rt_kprintf("╔════════════════════════════════════════════════════╗\n");
    rt_kprintf("║   🌐 大核: WiFi 网络感知自启动系统                 ║\n");
    rt_kprintf("╚════════════════════════════════════════════════════╝\n");
    rt_kprintf("[AutoStart] ⏳ 大核: 等待网络就绪中...\n");

    wifi_ret = wifi_connect_if_needed();
    if (wifi_ret != RT_EOK)
    {
        rt_kprintf("[WiFi] Initial WiFi connect failed (%d), will keep retrying...\n", wifi_ret);
        wifi_retry_cooldown = 6;
    }

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

            if (!rt_wlan_is_ready())
            {
                if (wifi_retry_cooldown <= 0)
                {
                    wifi_ret = wifi_connect_if_needed();
                    if (wifi_ret != RT_EOK)
                    {
                        rt_kprintf("[WiFi] WiFi connect retry failed (%d)\n", wifi_ret);
                    }
                    wifi_retry_cooldown = 6;
                }
                else
                {
                    wifi_retry_cooldown--;
                }
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
#else /* RTSMART_WEB_PORTABLE */

/* POSIX �ļ���: �� MicroPython ���캯���£������̶������̳߳� HTTP ������ */

#include <pthread.h>
#include <semaphore.h>
#include <errno.h>
#include <time.h>
#define rt_strncpy strncpy
/* 避免 dfs_posix.h 与 unistd 的 read/write 冲突，直接声明需要的接口 */
extern int close(int fd);
extern int shutdown(int fd, int how);
extern int usleep(unsigned int usec);

#define SERVER_PORT 8080
#define MAX_CLIENTS 5
#define WORKER_COUNT 4
#define TASK_QUEUE_LEN 16
#define PTHREAD_STACK_SIZE (64 * 1024)

typedef struct
{
    int client_fd;
    struct sockaddr_in client_addr;
} client_ctx_t;

static int server_fd = -1;
static volatile int server_running = 0;
static pthread_t accept_thread;
static pthread_t worker_threads[WORKER_COUNT];
static client_ctx_t task_queue[TASK_QUEUE_LEN];
static int queue_head = 0;
static int queue_tail = 0;
static pthread_mutex_t queue_lock = PTHREAD_MUTEX_INITIALIZER;
static sem_t queue_sem;

static int queue_is_full(void)
{
    int next = (queue_tail + 1) % TASK_QUEUE_LEN;
    return next == queue_head;
}

static int queue_is_empty(void)
{
    return queue_head == queue_tail;
}

static void queue_push(const client_ctx_t *ctx)
{
    task_queue[queue_tail] = *ctx;
    queue_tail = (queue_tail + 1) % TASK_QUEUE_LEN;
}

static int queue_pop(client_ctx_t *out)
{
    if (queue_is_empty())
    {
        return -1;
    }
    *out = task_queue[queue_head];
    queue_head = (queue_head + 1) % TASK_QUEUE_LEN;
    return 0;
}

/* 复用与 RT 版本一致的请求处理逻辑 */
static void client_handler_thread(void *parameter)
{
    client_ctx_t *ctx = (client_ctx_t *)parameter;
    char buffer[2048];
    int n;

    printf("[HTTP] Client connected from %s:%d\n",
           inet_ntoa(ctx->client_addr.sin_addr),
           ntohs(ctx->client_addr.sin_port));

    n = recv(ctx->client_fd, buffer, sizeof(buffer) - 1, 0);
    if (n <= 0)
    {
        printf("[HTTP] Failed to read request\n");
        goto cleanup;
    }
    buffer[n] = '\0';

    char method[8] = {0};
    char url[256] = {0};

    if (sscanf(buffer, "%7s %255s", method, url) != 2)
    {
        http_send_404(ctx->client_fd);
        goto cleanup;
    }

    char *body = strstr(buffer, "\r\n\r\n");
    if (body)
        body += 4;
    else
        body = buffer + n;

    char path[256];
    rt_strncpy(path, url, sizeof(path));
    char *query = NULL;
    char *query_pos = strchr(path, '?');
    if (query_pos)
    {
        *query_pos = '\0';
        query = query_pos + 1;
    }

    if (strcmp(method, "GET") == 0)
    {
        if (strcmp(path, "/stream") == 0)
        {
            http_handle_mjpeg_stream(ctx->client_fd);
        }
        else if (strcmp(path, "/snapshot") == 0)
        {
            http_handle_snapshot(ctx->client_fd);
        }
        else if (strncmp(path, "/api/", 5) == 0)
        {
            http_handle_api_request(ctx->client_fd, method, path, query, body);
        }
        else
        {
            http_handle_static_request(ctx->client_fd, path);
        }
    }
    else if (strcmp(method, "POST") == 0 || strcmp(method, "DELETE") == 0)
    {
        if (strncmp(path, "/api/", 5) == 0)
        {
            http_handle_api_request(ctx->client_fd, method, path, query, body);
        }
        else
        {
            http_send_404(ctx->client_fd);
        }
    }
    else
    {
        http_send_404(ctx->client_fd);
    }

cleanup:
    close(ctx->client_fd);
    printf("[HTTP] Client disconnected\n");
    return;
}

static void *worker_thread_entry(void *parameter)
{
    (void)parameter;
    client_ctx_t ctx_local;
    while (1)
    {
        sem_wait(&queue_sem);

        pthread_mutex_lock(&queue_lock);
        int ret = queue_pop(&ctx_local);
        pthread_mutex_unlock(&queue_lock);

        if (ret != 0)
        {
            if (!server_running)
                break;
            continue;
        }

        if (!server_running)
        {
            close(ctx_local.client_fd);
            break;
        }

        client_handler_thread(&ctx_local);
    }
    return NULL;
}

static void *accept_thread_func(void *parameter)
{
    (void)parameter;
    struct sockaddr_in client_addr;
    socklen_t addr_len;
    int client_fd;

    printf("[HTTP] Accept thread started\n");

    while (server_running)
    {
        addr_len = sizeof(client_addr);
        client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &addr_len);

        if (client_fd < 0)
        {
            if (server_running)
            {
                printf("[HTTP] Accept failed: %d\n", errno);
                usleep(100 * 1000);
            }
            continue;
        }

        client_ctx_t ctx;
        ctx.client_fd = client_fd;
        ctx.client_addr = client_addr;

        pthread_mutex_lock(&queue_lock);
        if (queue_is_full())
        {
            pthread_mutex_unlock(&queue_lock);
            printf("[HTTP] Task queue full, drop connection\n");
            close(client_fd);
            continue;
        }
        queue_push(&ctx);
        pthread_mutex_unlock(&queue_lock);
        sem_post(&queue_sem);
    }

    printf("[HTTP] Accept thread stopped\n");
    return NULL;
}

int http_server_init(void)
{
    struct sockaddr_in server_addr;
    int opt = 1;

    if (frame_buffer_init(FRAME_BUFFER_QUALITY) != 0)
    {
        printf("[HTTP] Failed to init frame buffer\n");
        return -1;
    }

    http_handler_init();

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0)
    {
        printf("[HTTP] Failed to create socket, errno=%d\n", errno);
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(SERVER_PORT);

    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        printf("[HTTP] Failed to bind socket, errno=%d\n", errno);
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    if (listen(server_fd, MAX_CLIENTS) < 0)
    {
        printf("[HTTP] Failed to listen, errno=%d\n", errno);
        close(server_fd);
        server_fd = -1;
        http_handler_deinit();
        frame_buffer_deinit();
        return -1;
    }

    printf("[HTTP] Server listening on port %d\n", SERVER_PORT);

    queue_head = queue_tail = 0;
    sem_init(&queue_sem, 0, 0);

    server_running = 1;

    pthread_attr_t worker_attr;
    pthread_attr_init(&worker_attr);
    pthread_attr_setstacksize(&worker_attr, PTHREAD_STACK_SIZE);
    for (int i = 0; i < WORKER_COUNT; i++)
    {
        if (pthread_create(&worker_threads[i], &worker_attr, worker_thread_entry, NULL) != 0)
        {
            printf("[HTTP] Warning: create worker %d failed\n", i);
        }
    }
    pthread_attr_destroy(&worker_attr);

    pthread_attr_t accept_attr;
    pthread_attr_init(&accept_attr);
    pthread_attr_setstacksize(&accept_attr, PTHREAD_STACK_SIZE);
    if (pthread_create(&accept_thread, &accept_attr, accept_thread_func, NULL) != 0)
    {
        printf("[HTTP] Failed to create accept thread\n");
        server_running = 0;
        close(server_fd);
        server_fd = -1;
        sem_destroy(&queue_sem);
        http_handler_deinit();
        frame_buffer_deinit();
        pthread_attr_destroy(&accept_attr);
        return -1;
    }
    pthread_attr_destroy(&accept_attr);

    printf("[HTTP] Server started successfully\n");
    return 0;
}

void http_server_deinit(void)
{
    if (!server_running)
        return;

    server_running = 0;

    if (server_fd >= 0)
    {
        shutdown(server_fd, SHUT_RDWR);
        close(server_fd);
        server_fd = -1;
    }

    for (int i = 0; i < WORKER_COUNT; i++)
    {
        sem_post(&queue_sem);
    }

    pthread_join(accept_thread, NULL);
    for (int i = 0; i < WORKER_COUNT; i++)
    {
        if (worker_threads[i])
            pthread_join(worker_threads[i], NULL);
    }

    sem_destroy(&queue_sem);

    http_handler_deinit();
    frame_buffer_deinit();

    printf("[HTTP] Server stopped\n");
}

int http_server_autostart(void)
{
    return http_server_init();
}
#endif /* RTSMART_WEB_PORTABLE */
