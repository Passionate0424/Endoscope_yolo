/*
 * YOLO 线程占位实现
 * 未集成 RT-Smart 可用的推理依赖时，仅保持控制状态循环，不做实际推理。
 */

#include "yolo_thread.h"
#include "frame_buffer.h"
#include "web_state.h"
#include <rtthread.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// YOLO 线程状态
static struct {
    rt_thread_t thread;
    rt_bool_t running;
    void *detector;  // 占位
    char kmodel_path[256];
    char labels_path[256];
    int initialized;
} yolo_thread_ctx = {0};

#define YOLO_THREAD_STACK_SIZE (64 * 1024)
#define YOLO_THREAD_PRIORITY (RT_THREAD_PRIORITY_MAX - 5)

// YOLO 线程主函数（占位）
static void yolo_thread_entry(void *parameter)
{
    rt_kprintf("[YOLO] Thread started (placeholder, no inference)\n");

    while (yolo_thread_ctx.running)
    {
        web_control_info_t ctrl;
        web_state_get_control_info(&ctrl);

        if (ctrl.desired_camera_running != ctrl.actual_camera_running)
        {
            if (ctrl.desired_camera_running)
            {
                rt_kprintf("[YOLO] Camera start requested (noop)\n");
                web_state_set_camera_running(RT_TRUE);
            }
            else
            {
                rt_kprintf("[YOLO] Camera stop requested (noop)\n");
                web_state_set_camera_running(RT_FALSE);
            }
        }

        if (!ctrl.actual_camera_running)
        {
            rt_thread_mdelay(100);
            continue;
        }

        if (ctrl.desired_confidence != ctrl.actual_confidence)
        {
            web_state_set_confidence(ctrl.desired_confidence);
        }

        // TODO: 在此接入摄像头抓帧、推理、画框、JPEG 推送 frame_buffer、更新统计
        rt_thread_mdelay(33); // ~30fps 占位
    }

    rt_kprintf("[YOLO] Thread stopped\n");
}

int yolo_thread_init(const char *kmodel_path, const char *labels_path)
{
    if (yolo_thread_ctx.initialized)
    {
        rt_kprintf("[YOLO] Already initialized\n");
        return 0;
    }

    if (!kmodel_path || !labels_path)
    {
        rt_kprintf("[YOLO] Invalid parameters\n");
        return -1;
    }

    rt_strncpy(yolo_thread_ctx.kmodel_path, kmodel_path, sizeof(yolo_thread_ctx.kmodel_path) - 1);
    rt_strncpy(yolo_thread_ctx.labels_path, labels_path, sizeof(yolo_thread_ctx.labels_path) - 1);

    yolo_thread_ctx.initialized = 1;
    rt_kprintf("[YOLO] Initialized (placeholder, no detector loaded). kmodel: %s\n", kmodel_path);
    return 0;
}

int yolo_thread_start(void)
{
    if (!yolo_thread_ctx.initialized)
    {
        rt_kprintf("[YOLO] Not initialized\n");
        return -1;
    }

    if (yolo_thread_ctx.running)
    {
        rt_kprintf("[YOLO] Already running\n");
        return 0;
    }

    yolo_thread_ctx.running = RT_TRUE;
    yolo_thread_ctx.thread = rt_thread_create("yolo",
                                              yolo_thread_entry,
                                              RT_NULL,
                                              YOLO_THREAD_STACK_SIZE,
                                              YOLO_THREAD_PRIORITY,
                                              20);

    if (yolo_thread_ctx.thread == RT_NULL)
    {
        rt_kprintf("[YOLO] Failed to create thread\n");
        yolo_thread_ctx.running = RT_FALSE;
        return -1;
    }

    rt_thread_startup(yolo_thread_ctx.thread);
    rt_kprintf("[YOLO] Thread started\n");
    return 0;
}

void yolo_thread_stop(void)
{
    if (!yolo_thread_ctx.running)
    {
        return;
    }

    yolo_thread_ctx.running = RT_FALSE;

    if (yolo_thread_ctx.thread)
    {
        rt_thread_delete(yolo_thread_ctx.thread);
        yolo_thread_ctx.thread = RT_NULL;
    }

    rt_kprintf("[YOLO] Thread stopped\n");
}

void yolo_thread_deinit(void)
{
    yolo_thread_stop();
    yolo_thread_ctx.initialized = 0;
    rt_kprintf("[YOLO] Deinitialized\n");
}

rt_bool_t yolo_thread_is_running(void)
{
    return yolo_thread_ctx.running;
}
