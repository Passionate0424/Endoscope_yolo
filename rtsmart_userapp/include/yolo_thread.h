/*
 * YOLO 检测线程 C 接口
 * 与 HTTP 服务器配合，读取 web_state 控制状态
 */

#ifndef YOLO_THREAD_H
#define YOLO_THREAD_H

#include <rtthread.h>
#include "web_state.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 初始化 YOLO 检测线程
 * @param kmodel_path kmodel 文件路径
 * @param labels_path 标签文件路径
 * @return 0 成功，-1 失败
 */
int yolo_thread_init(const char *kmodel_path, const char *labels_path);

/**
 * @brief 启动 YOLO 检测线程
 * @return 0 成功，-1 失败
 */
int yolo_thread_start(void);

/**
 * @brief 停止 YOLO 检测线程
 */
void yolo_thread_stop(void);

/**
 * @brief 释放 YOLO 检测线程资源
 */
void yolo_thread_deinit(void);

/**
 * @brief 检查 YOLO 线程是否运行中
 * @return RT_TRUE 运行中，RT_FALSE 未运行
 */
rt_bool_t yolo_thread_is_running(void);

#ifdef __cplusplus
}
#endif

#endif /* YOLO_THREAD_H */



