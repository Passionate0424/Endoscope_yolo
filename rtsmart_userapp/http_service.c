/*
 * RT-Smart HTTP 服务器启动服务
 * 在系统启动时自动启动 HTTP 服务器
 *
 * 使用方法：
 * 1. 将此文件编译为 RT-Smart 应用
 * 2. 在启动脚本中调用此服务
 * 或在 msh 命令行中直接执行
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>

/* HTTP 服务器启动函数（来自原有的 http_server.c） */
extern int http_server_start(void);
extern int http_server_stop(void);
extern int http_server_is_running(void);

/**
 * HTTP 服务器后台运行线程
 */
static void *http_server_thread(void *arg)
{
    printf("[HTTPService] 后台服务线程已启动\n");

    // 启动 HTTP 服务器
    int ret = http_server_start();

    if (ret == 0)
    {
        printf("[HTTPService] ✅ HTTP 服务器已启动在 0.0.0.0:8080\n");
    }
    else
    {
        printf("[HTTPService] ❌ HTTP 服务器启动失败，错误码: %d\n", ret);
    }

    // 线程保持运行（服务器在后台运行）
    while (1)
    {
        sleep(10); // 每 10 秒检查一次

        if (!http_server_is_running())
        {
            printf("[HTTPService] ⚠️ HTTP 服务器已停止，尝试重启...\n");
            http_server_start();
        }
    }

    return NULL;
}

/**
 * 启动 HTTP 服务器服务
 * 可以在 msh 命令行中调用：http_service_start
 */
int http_service_start(void)
{
    printf("[HTTPService] 启动 HTTP 服务器服务...\n");

    pthread_t tid;
    int ret = pthread_create(&tid, NULL, http_server_thread, NULL);

    if (ret != 0)
    {
        printf("[HTTPService] ❌ 创建线程失败: %d\n", ret);
        return -1;
    }

    // 分离线程，让它在后台运行
    pthread_detach(tid);

    printf("[HTTPService] ✅ HTTP 服务已在后台启动\n");
    return 0;
}

/**
 * 停止 HTTP 服务器服务
 */
int http_service_stop(void)
{
    printf("[HTTPService] 停止 HTTP 服务器服务...\n");
    return http_server_stop();
}

/**
 * 检查 HTTP 服务器状态
 */
int http_service_status(void)
{
    if (http_server_is_running())
    {
        printf("[HTTPService] HTTP 服务器状态: 🟢 运行中\n");
        return 1;
    }
    else
    {
        printf("[HTTPService] HTTP 服务器状态: 🔴 已停止\n");
        return 0;
    }
}

/* MSH 命令导出 */
#ifdef RT_USING_MSH_COMMANDS
#include <rtdef.h>

MSH_CMD_EXPORT(http_service_start, "启动 HTTP 服务");
MSH_CMD_EXPORT(http_service_stop, "停止 HTTP 服务");
MSH_CMD_EXPORT(http_service_status, "查看 HTTP 服务状态");
#endif

/* 模块初始化 */
#ifdef RT_USING_MODULE
static int http_service_init(void)
{
    printf("[HTTPService] 模块初始化\n");
    return http_service_start();
}

INIT_APP_EXPORT(http_service_init);
#endif
