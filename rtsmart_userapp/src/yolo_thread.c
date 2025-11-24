/*
 * YOLO 检测线程实现
 * 读取 web_state 控制状态，执行 YOLO 检测
 * 将检测结果绘制到图像并推送到 frame_buffer
 */

#include "yolo_thread.h"
#include "frame_buffer.h"
#include "web_state.h"
#include <rtthread.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// 注意：这里需要包含 C++ 实现的头文件
// 由于是 C 文件，我们需要通过 extern 声明来调用 C++ 函数
#ifdef __cplusplus
extern "C" {
#endif

// C++ 实现的函数声明（在 yolo_detector_wrapper.cpp 中实现）
extern void* yolo_detector_create(const char *kmodel_path, const char *labels_path,
                                  float conf_threshold, float nms_threshold,
                                  int input_width, int input_height,
                                  int image_width, int image_height);
extern void yolo_detector_destroy(void *detector);
extern int yolo_detector_run(void *detector, const uint8_t *image_data,
                              int image_width, int image_height,
                              void *detections, int max_detections);
extern void yolo_detector_draw_results(void *detector, uint8_t *image_data,
                                        int image_width, int image_height,
                                        void *detections, int num_detections);
extern void yolo_detector_set_confidence(void *detector, float threshold);

#ifdef __cplusplus
}
#endif

// YOLO 线程状态
static struct {
    rt_thread_t thread;
    rt_bool_t running;
    void *detector;  // C++ YOLO 检测器指针
    char kmodel_path[256];
    char labels_path[256];
    int initialized;
} yolo_thread_ctx = {0};

#define YOLO_THREAD_STACK_SIZE (64 * 1024)
#define YOLO_THREAD_PRIORITY (RT_THREAD_PRIORITY_MAX - 5)

// YOLO 检测框结构（与 C++ 端匹配）
typedef struct {
    int x;
    int y;
    int width;
    int height;
    float confidence;
    int class_id;
} yolo_detection_t;

// YOLO 线程主函数
static void yolo_thread_entry(void *parameter)
{
    rt_kprintf("[YOLO] Thread started\n");

    // TODO: 这里需要实现摄像头捕获和 YOLO 检测循环
    // 1. 读取 web_state 的控制状态
    // 2. 如果 camera_running 为真，捕获图像
    // 3. 如果 detection_enabled 为真，执行 YOLO 检测
    // 4. 绘制检测结果
    // 5. 编码为 JPEG 并推送到 frame_buffer
    // 6. 更新 web_state 统计信息

    while (yolo_thread_ctx.running)
    {
        // 读取控制状态
        web_control_info_t ctrl;
        web_state_get_control_info(&ctrl);

        // 检查是否需要启动/停止摄像头
        if (ctrl.desired_camera_running != ctrl.actual_camera_running)
        {
            if (ctrl.desired_camera_running)
            {
                rt_kprintf("[YOLO] Camera start requested\n");
                // TODO: 初始化摄像头
                web_state_set_camera_running(RT_TRUE);
            }
            else
            {
                rt_kprintf("[YOLO] Camera stop requested\n");
                // TODO: 停止摄像头
                web_state_set_camera_running(RT_FALSE);
            }
        }

        // 如果摄像头未运行，等待
        if (!ctrl.actual_camera_running)
        {
            rt_thread_mdelay(100);
            continue;
        }

        // 检查置信度阈值是否变化
        if (ctrl.desired_confidence != ctrl.actual_confidence)
        {
            if (yolo_thread_ctx.detector)
            {
                yolo_detector_set_confidence(yolo_thread_ctx.detector, ctrl.desired_confidence);
            }
            web_state_set_confidence(ctrl.desired_confidence);
        }

        // TODO: 捕获图像帧
        // TODO: 如果 detection_enabled，执行 YOLO 检测
        // TODO: 绘制检测结果
        // TODO: 编码为 JPEG
        // TODO: 推送到 frame_buffer
        // TODO: 更新统计信息

        rt_thread_mdelay(33); // ~30fps
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

    // 默认配置
    float conf_threshold = 0.5f;
    float nms_threshold = 0.45f;
    int input_width = 640;
    int input_height = 640;
    int image_width = 640;
    int image_height = 360;

    // 创建 C++ YOLO 检测器
    yolo_thread_ctx.detector = yolo_detector_create(
        yolo_thread_ctx.kmodel_path,
        yolo_thread_ctx.labels_path,
        conf_threshold,
        nms_threshold,
        input_width,
        input_height,
        image_width,
        image_height
    );

    if (!yolo_thread_ctx.detector)
    {
        rt_kprintf("[YOLO] Failed to create detector\n");
        return -1;
    }

    yolo_thread_ctx.initialized = 1;
    rt_kprintf("[YOLO] Initialized (kmodel: %s)\n", kmodel_path);
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

    if (yolo_thread_ctx.detector)
    {
        yolo_detector_destroy(yolo_thread_ctx.detector);
        yolo_thread_ctx.detector = NULL;
    }

    yolo_thread_ctx.initialized = 0;
    rt_kprintf("[YOLO] Deinitialized\n");
}

rt_bool_t yolo_thread_is_running(void)
{
    return yolo_thread_ctx.running;
}





