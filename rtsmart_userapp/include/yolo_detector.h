/*
 * YOLO 检测器 C 接口
 * 基于参考示例 https://github.com/canmv-k230/k230_rtsmart_examples/tree/canmv_k230/YOLO/src
 * 提供 C 接口供 HTTP 服务器调用
 */

#ifndef YOLO_DETECTOR_H
#define YOLO_DETECTOR_H

#include <stdint.h>
#include <rtthread.h>

#ifdef __cplusplus
extern "C" {
#endif

// YOLO 检测框结构
typedef struct {
    int x;          // 左上角 x 坐标
    int y;          // 左上角 y 坐标
    int width;      // 宽度
    int height;     // 高度
    float confidence; // 置信度
    int class_id;   // 类别 ID
} yolo_detection_t;

// YOLO 检测器配置
typedef struct {
    const char *kmodel_path;      // kmodel 文件路径
    const char *labels_path;       // 标签文件路径
    float conf_threshold;          // 置信度阈值
    float nms_threshold;           // NMS 阈值
    int input_width;               // 模型输入宽度
    int input_height;              // 模型输入高度
    int image_width;               // 图像宽度
    int image_height;              // 图像高度
} yolo_config_t;

// YOLO 检测器句柄
typedef void* yolo_detector_handle_t;

/**
 * @brief 初始化 YOLO 检测器
 * @param config 配置参数
 * @return 检测器句柄，失败返回 NULL
 */
yolo_detector_handle_t yolo_detector_init(const yolo_config_t *config);

/**
 * @brief 释放 YOLO 检测器
 * @param handle 检测器句柄
 */
void yolo_detector_deinit(yolo_detector_handle_t handle);

/**
 * @brief 执行 YOLO 检测
 * @param handle 检测器句柄
 * @param image_data 图像数据 (RGB888, HWC 格式)
 * @param image_width 图像宽度
 * @param image_height 图像高度
 * @param detections 输出检测结果数组
 * @param max_detections 最大检测数量
 * @return 实际检测到的数量
 */
int yolo_detector_run(yolo_detector_handle_t handle,
                      const uint8_t *image_data,
                      int image_width,
                      int image_height,
                      yolo_detection_t *detections,
                      int max_detections);

/**
 * @brief 在图像上绘制检测结果
 * @param image_data 图像数据 (RGB888, HWC 格式)
 * @param image_width 图像宽度
 * @param image_height 图像高度
 * @param detections 检测结果数组
 * @param num_detections 检测数量
 * @param labels 标签数组（可选，用于显示类别名称）
 * @param num_labels 标签数量
 */
void yolo_detector_draw_results(uint8_t *image_data,
                                int image_width,
                                int image_height,
                                const yolo_detection_t *detections,
                                int num_detections,
                                const char **labels,
                                int num_labels);

/**
 * @brief 更新置信度阈值
 * @param handle 检测器句柄
 * @param threshold 新的置信度阈值
 */
void yolo_detector_set_confidence_threshold(yolo_detector_handle_t handle, float threshold);

/**
 * @brief 获取置信度阈值
 * @param handle 检测器句柄
 * @return 当前置信度阈值
 */
float yolo_detector_get_confidence_threshold(yolo_detector_handle_t handle);

#ifdef __cplusplus
}
#endif

#endif /* YOLO_DETECTOR_H */





