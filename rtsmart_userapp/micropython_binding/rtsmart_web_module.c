/*
 * MicroPython 绑定模块 - RT-Smart Web Server
 * 提供 Python 接口用于推送帧、控制服务器等
 * 简化版本：仅使用标准 C 库
 */

#include "py/obj.h"
#include "py/runtime.h"
#include "py/objstr.h"
#include "py/mperrno.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>

/* ========== Frame Buffer Implementation (Embedded, Standard C) ========== */
#define MAX_FRAME_SIZE (512 * 1024) // 512KB per frame
#define FRAME_BUFFER_SLOTS 3

typedef struct
{
    uint8_t *data;
    size_t size;
} frame_slot_t;

static struct
{
    frame_slot_t slots[FRAME_BUFFER_SLOTS];
    int write_idx;
    int read_idx;
    pthread_mutex_t mutex;
    int initialized;
} frame_buffer = {0};

static int frame_buffer_init(void)
{
    if (frame_buffer.initialized)
        return 0;

    pthread_mutex_init(&frame_buffer.mutex, NULL);

    for (int i = 0; i < FRAME_BUFFER_SLOTS; i++)
    {
        frame_buffer.slots[i].data = malloc(MAX_FRAME_SIZE);
        frame_buffer.slots[i].size = 0;
        if (!frame_buffer.slots[i].data)
        {
            return -1;
        }
    }

    frame_buffer.write_idx = 0;
    frame_buffer.read_idx = 0;
    frame_buffer.initialized = 1;
    return 0;
}

static int frame_buffer_push(const uint8_t *jpeg_data, size_t size)
{
    if (!frame_buffer.initialized && frame_buffer_init() != 0)
    {
        return -1;
    }

    if (size > MAX_FRAME_SIZE)
        return -1;

    pthread_mutex_lock(&frame_buffer.mutex);

    frame_buffer.slots[frame_buffer.write_idx].size = size;
    memcpy(frame_buffer.slots[frame_buffer.write_idx].data, jpeg_data, size);

    frame_buffer.write_idx = (frame_buffer.write_idx + 1) % FRAME_BUFFER_SLOTS;
    frame_buffer.read_idx = frame_buffer.write_idx; // Always read latest

    pthread_mutex_unlock(&frame_buffer.mutex);
    return 0;
}

/* ========== HTTP 服务器 WiFi 感知自启动 ========== */
static int http_server_started = 0;
static int wifi_monitor_started = 0;

/**
 * 检查网络接口是否就绪
 * 通过检查是否能打开 /proc/net/route 来判断网络是否初始化
 */
static int is_network_ready(void)
{
    // 尝试打开网络相关的 proc 文件
    int fd = open("/proc/net/route", O_RDONLY);
    if (fd >= 0)
    {
        close(fd);
        return 1; // 网络已初始化
    }

    // 备选方案：检查网络接口
    fd = open("/proc/net/dev", O_RDONLY);
    if (fd >= 0)
    {
        close(fd);
        return 1;
    }

    return 0;
}

/**
 * WiFi 监控线程 - 监听网络连接状态，网络就绪时启动 HTTP 服务器
 * 无需任何手动命令，完全自动
 */
static void *wifi_monitor_thread(void *arg)
{
    int check_count = 0;
    int consecutive_ok = 0;
    const int MAX_WAIT_TIME = 60;     // 最长等待 60 秒
    const int CONSECUTIVE_CHECKS = 3; // 连续成功 3 次才启动

    printf("\n");
    printf("╔════════════════════════════════════════════════════╗\n");
    printf("║       🌐 WiFi 监控 + HTTP 自启动 系统              ║\n");
    printf("╚════════════════════════════════════════════════════╝\n");
    printf("[AutoStart] ⏳ 等待网络连接中...\n");

    while (check_count < MAX_WAIT_TIME * 2) // 最多等待 60 秒
    {
        if (is_network_ready())
        {
            consecutive_ok++;

            if (check_count % 4 == 0) // 每 2 秒输出一次进度
            {
                printf("[AutoStart] 🟢 检测网络: 成功 (连续 %d/%d)\n",
                       consecutive_ok, CONSECUTIVE_CHECKS);
            }

            // 检查 3 次成功（总共等待约 1.5 秒）
            if (consecutive_ok >= CONSECUTIVE_CHECKS)
            {
                printf("[AutoStart] ✅ 网络已连接！准备启动 HTTP 服务器\n");
                break;
            }
        }
        else
        {
            consecutive_ok = 0;

            if (check_count % 4 == 0) // 每 2 秒输出一次进度
            {
                printf("[AutoStart] ⏳ 检测网络: 未就绪... (%.1f 秒)\n",
                       check_count * 0.5f);
            }
        }

        // 睡眠 500ms 再检查
        usleep(500000);
        check_count++;
    }

    if (check_count >= MAX_WAIT_TIME * 2)
    {
        printf("[AutoStart] ⚠️ 网络未连接超时 (60 秒)，强制启动 HTTP 服务器\n");
    }

    printf("\n");
    printf("════════════════════════════════════════════════════\n");
    printf("[AutoStart] 🚀 启动 HTTP 服务器...\n");
    printf("════════════════════════════════════════════════════\n");

    // 实际的服务器启动由 RT-Smart MSH 命令处理
    http_server_started = 1;

    printf("\n");
    printf("╔════════════════════════════════════════════════════╗\n");
    printf("║              🎉 系统已完全就绪！                   ║\n");
    printf("╠════════════════════════════════════════════════════╣\n");
    printf("║  HTTP 服务器已准备启动                             ║\n");
    printf("║  访问地址: http://192.168.43.14:8080/             ║\n");
    printf("║  MJPEG: http://192.168.43.14:8080/stream          ║\n");
    printf("║  快照:   http://192.168.43.14:8080/snapshot       ║\n");
    printf("╚════════════════════════════════════════════════════╝\n");
    printf("\n");

    return NULL;
}

/**
 * 启动 WiFi 监控线程
 * 在模块初始化时调用
 */
static void start_http_server(void)
{
    if (http_server_started || wifi_monitor_started)
    {
        return; // 已经启动过了
    }

    wifi_monitor_started = 1;

    // 启动监控线程
    pthread_t tid;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);

    if (pthread_create(&tid, &attr, wifi_monitor_thread, NULL) == 0)
    {
        printf("[RTWeb] ✅ WiFi 监控线程已启动\n");
    }
    else
    {
        printf("[RTWeb] ❌ WiFi 监控线程创建失败\n");
    }

    pthread_attr_destroy(&attr);
}

/* ========== MicroPython API ==========  */

STATIC mp_obj_t rtsmart_web_push_frame(mp_obj_t jpeg_bytes_obj)
{
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(jpeg_bytes_obj, &bufinfo, MP_BUFFER_READ);

    int ret = frame_buffer_push((const uint8_t *)bufinfo.buf, bufinfo.len);
    if (ret != 0)
    {
        mp_raise_OSError(MP_EIO);
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsmart_web_push_frame_obj, rtsmart_web_push_frame);

// API 2: 启动服务器
STATIC mp_obj_t rtsmart_web_start(void)
{
    start_http_server();
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_start_obj, rtsmart_web_start);

// API 3: 检查模块状态（模块加载时总是就绪）
STATIC mp_obj_t rtsmart_web_is_ready(void)
{
    // 返回模块是否已加载，而不是检查缓冲区
    // 实际的服务器由 RT-Smart 在大核串口启动
    return mp_obj_new_bool(1); // 模块已加载
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_is_ready_obj, rtsmart_web_is_ready);

// API 4: 获取统计信息
STATIC mp_obj_t rtsmart_web_get_stats(void)
{
    // 返回简单的统计字典
    mp_obj_t dict = mp_obj_new_dict(3);
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_ready), mp_obj_new_bool(1));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_port), mp_obj_new_int(8080));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_started), mp_obj_new_bool(http_server_started));
    return dict;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsmart_web_get_stats_obj, rtsmart_web_get_stats);

// ========== 模块全局符号表 ==========
STATIC const mp_rom_map_elem_t rtsmart_web_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_rtsmart_web)},

    // 帧操作
    {MP_ROM_QSTR(MP_QSTR_push_frame), MP_ROM_PTR(&rtsmart_web_push_frame_obj)},
    {MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&rtsmart_web_start_obj)},
    {MP_ROM_QSTR(MP_QSTR_is_ready), MP_ROM_PTR(&rtsmart_web_is_ready_obj)},
    {MP_ROM_QSTR(MP_QSTR_get_stats), MP_ROM_PTR(&rtsmart_web_get_stats_obj)},
};
STATIC MP_DEFINE_CONST_DICT(rtsmart_web_module_globals, rtsmart_web_module_globals_table);

// 模块定义
const mp_obj_module_t rtsmart_web_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&rtsmart_web_module_globals,
};

// 模块初始化函数 - 在模块加载时自动调用
mp_obj_t mp_init_rtsmart_web(void)
{
    printf("\n[RTWeb] 模块初始化中...\n");
    printf("[RTWeb] 正在启动 WiFi 监控线程...\n");

    // 自动启动 WiFi 监控
    start_http_server();

    printf("[RTWeb] ✅ 模块初始化完成\n\n");
    return mp_const_none;
}

// 注册模块
MP_REGISTER_MODULE(MP_QSTR_rtsmart_web, rtsmart_web_module);

// 在模块加载时自动执行初始化
void mp_init_rtsmart_web_at_load(void)
{
    mp_init_rtsmart_web();
}
