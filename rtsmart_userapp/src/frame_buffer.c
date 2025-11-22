/*
 * 环形帧缓冲区实现
 * 用于高效存储最新的 N 帧 JPEG 数据
 * RT-Smart 版本（使用 rt_malloc）
 */

#include "frame_buffer.h"

#ifndef RTSMART_WEB_PORTABLE
#include <rtthread.h>
#else
#include "py/mphal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
typedef pthread_mutex_t rt_mutex_t;
typedef int32_t rt_int32_t;
typedef uint32_t rt_tick_t;
#define RT_IPC_FLAG_PRIO 0
#define RT_WAITING_FOREVER (-1)
#define RT_TICK_PER_SECOND 1000
#define rt_kprintf printf
#define rt_malloc malloc
#define rt_free free
static inline void rt_mutex_init(rt_mutex_t *m, const char *name, int flag) {
    (void)name; (void)flag;
    pthread_mutex_init(m, NULL);
}
static inline void rt_mutex_detach(rt_mutex_t *m) {
    pthread_mutex_destroy(m);
}
static inline int rt_mutex_take(rt_mutex_t *m, int timeout) {
    (void)timeout;
    return pthread_mutex_lock(m);
}
static inline void rt_mutex_release(rt_mutex_t *m) {
    pthread_mutex_unlock(m);
}
static inline rt_tick_t rt_tick_get(void) {
    return (rt_tick_t)(mp_hal_ticks_ms());
}
#endif
#include <string.h>

// 全局缓冲区实例
static frame_buffer_t g_frame_buffer = {0};
#ifndef RTSMART_WEB_PORTABLE
static struct rt_mutex g_buffer_mutex;
#else
static rt_mutex_t g_buffer_mutex;
#endif
static rt_int32_t g_push_count = 0;
static rt_int32_t g_pop_fail_count = 0;

int frame_buffer_init(int quality)
{
    if (g_frame_buffer.initialized)
    {
        rt_kprintf("[FrameBuffer] Already initialized\n");
        return 0;
    }

    // 初始化互斥锁
    rt_mutex_init(&g_buffer_mutex, "fb_lock", RT_IPC_FLAG_PRIO);

    // 初始化所有槽位
    for (int i = 0; i < MAX_FRAME_SLOTS; i++)
    {
        g_frame_buffer.slots[i].data = (uint8_t *)rt_malloc(MAX_JPEG_SIZE);
        if (!g_frame_buffer.slots[i].data)
        {
            rt_kprintf("[FrameBuffer] Failed to allocate slot %d\n", i);
            // 清理已分配的内存
            for (int j = 0; j < i; j++)
            {
                rt_free(g_frame_buffer.slots[j].data);
            }
            rt_mutex_detach(&g_buffer_mutex);
            return -1;
        }
        g_frame_buffer.slots[i].size = 0;
        g_frame_buffer.slots[i].timestamp_ms = 0;
        g_frame_buffer.slots[i].valid = 0;
    }

    g_frame_buffer.write_idx = 0;
    g_frame_buffer.read_idx = 0;
    g_frame_buffer.quality = quality;
    g_frame_buffer.initialized = 1;

    rt_kprintf("[FrameBuffer] Initialized with %d slots, quality=%d\n",
               MAX_FRAME_SLOTS, quality);
    return 0;
}

void frame_buffer_deinit(void)
{
    if (!g_frame_buffer.initialized)
    {
        return;
    }

    rt_mutex_take(&g_buffer_mutex, RT_WAITING_FOREVER);

    for (int i = 0; i < MAX_FRAME_SLOTS; i++)
    {
        if (g_frame_buffer.slots[i].data)
        {
            rt_free(g_frame_buffer.slots[i].data);
            g_frame_buffer.slots[i].data = NULL;
        }
    }

    g_frame_buffer.initialized = 0;

    rt_mutex_release(&g_buffer_mutex);
    rt_mutex_detach(&g_buffer_mutex);

    rt_kprintf("[FrameBuffer] Deinitialized\n");
}

int frame_buffer_push(const uint8_t *jpeg_data, size_t size)
{
    if (!g_frame_buffer.initialized)
    {
        rt_kprintf("[FrameBuffer] Push rejected: not initialized\n");
        rt_kprintf("[FrameBuffer] Not initialized\n");
        return -1;
    }

    if (size > MAX_JPEG_SIZE)
    {
        rt_kprintf("[FrameBuffer] Frame too large: %zu bytes\n", size);
        return -1;
    }

    rt_mutex_take(&g_buffer_mutex, RT_WAITING_FOREVER);

    // 写入当前槽位
    frame_slot_t *slot = &g_frame_buffer.slots[g_frame_buffer.write_idx];
    memcpy(slot->data, jpeg_data, size);
    slot->size = size;
    slot->timestamp_ms = (rt_tick_get() * 1000U) / RT_TICK_PER_SECOND;
    slot->valid = 1;

    // 更新写索引（环形）
    g_frame_buffer.write_idx = (g_frame_buffer.write_idx + 1) % MAX_FRAME_SLOTS;

    rt_mutex_release(&g_buffer_mutex);

    g_push_count++;
    if (g_push_count <= 3 || (g_push_count % 100 == 0))
    {
        rt_kprintf("[FrameBuffer] Push #%d size=%d bytes (slot=%d)\n",
                   g_push_count,
                   (int)size,
                   (g_frame_buffer.write_idx - 1 + MAX_FRAME_SLOTS) % MAX_FRAME_SLOTS);
    }

    return 0;
}

int frame_buffer_get_latest(uint8_t **out_data, size_t *out_size)
{
    if (!g_frame_buffer.initialized)
    {
        return -1;
    }

    rt_mutex_take(&g_buffer_mutex, RT_WAITING_FOREVER);

    // 找到最新的有效帧（从写索引往回找）
    int idx = (g_frame_buffer.write_idx - 1 + MAX_FRAME_SLOTS) % MAX_FRAME_SLOTS;
    frame_slot_t *slot = &g_frame_buffer.slots[idx];

    if (!slot->valid || slot->size == 0)
    {
        g_pop_fail_count++;
        if (g_pop_fail_count <= 3 || (g_pop_fail_count % 50 == 0))
        {
            rt_kprintf("[FrameBuffer] Get failed: slot invalid (count=%d)\n", g_pop_fail_count);
        }
        rt_mutex_release(&g_buffer_mutex);
        return -1; // 没有可用帧
    }

    *out_data = slot->data;
    *out_size = slot->size;

    rt_mutex_release(&g_buffer_mutex);

    return 0;
}

int frame_buffer_is_ready(void)
{
    return g_frame_buffer.initialized;
}
