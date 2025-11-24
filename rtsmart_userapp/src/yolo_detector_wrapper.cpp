/*
 * YOLO 检测器 C++ 包装层
 * 基于参考代码: https://github.com/canmv-k230/k230_rtsmart_examples/tree/canmv_k230/YOLO/src
 * 提供 C 接口供 C 代码调用
 */

#include <cstring>
#include <vector>
#include <string>
#include <fstream>

// 注意：这里需要包含参考代码的头文件
// 由于参考代码在 k230_yolo_ref 目录，我们需要添加路径或复制文件
// 暂时使用前向声明，实际使用时需要包含正确的头文件

// 前向声明（实际需要包含参考代码）
// #include "../../k230_yolo_ref/YOLO/src/yolov5.h"
// #include "../../k230_yolo_ref/YOLO/src/utils.h"

// 临时结构定义（实际应该使用参考代码的定义）
struct YOLODetector {
    // void *yolo_impl;  // 实际是 Yolov5* 类型
    // 暂时用 void* 占位
    void *yolo_impl;
    std::vector<std::string> labels;
    float conf_threshold;
    float nms_threshold;
    int input_width;
    int input_height;
    int image_width;
    int image_height;
};

// 检测框结构（与 C 端匹配）
struct DetectionBox {
    int x;
    int y;
    int width;
    int height;
    float confidence;
    int class_id;
};

// 读取标签文件
static std::vector<std::string> read_labels(const char *labels_path)
{
    std::vector<std::string> labels;
    std::ifstream file(labels_path);
    if (!file.is_open())
    {
        return labels;
    }

    std::string line;
    while (std::getline(file, line))
    {
        if (!line.empty())
        {
            // 去掉末尾的 '\r'（Windows CRLF 兼容）
            if (!line.empty() && line.back() == '\r')
            {
                line.pop_back();
            }
            labels.push_back(line);
        }
    }
    return labels;
}

extern "C" {

void* yolo_detector_create(const char *kmodel_path, const char *labels_path,
                          float conf_threshold, float nms_threshold,
                          int input_width, int input_height,
                          int image_width, int image_height)
{
    YOLODetector *detector = new YOLODetector();
    if (!detector)
    {
        return nullptr;
    }

    detector->conf_threshold = conf_threshold;
    detector->nms_threshold = nms_threshold;
    detector->input_width = input_width;
    detector->input_height = input_height;
    detector->image_width = image_width;
    detector->image_height = image_height;

    // 读取标签
    detector->labels = read_labels(labels_path);

    // TODO: 创建 Yolov5 实例
    // 需要包含参考代码并调用：
    // FrameSize image_wh = {image_width, image_height};
    // detector->yolo_impl = new Yolov5(
    //     "detect", "video", kmodel_path,
    //     conf_threshold, nms_threshold, 0.5f,
    //     detector->labels, image_wh, 0
    // );

    detector->yolo_impl = nullptr; // 临时占位

    return detector;
}

void yolo_detector_destroy(void *detector_ptr)
{
    if (!detector_ptr)
    {
        return;
    }

    YOLODetector *detector = static_cast<YOLODetector*>(detector_ptr);

    // TODO: 删除 Yolov5 实例
    // if (detector->yolo_impl)
    // {
    //     delete static_cast<Yolov5*>(detector->yolo_impl);
    // }

    delete detector;
}

int yolo_detector_run(void *detector_ptr, const uint8_t *image_data,
                      int image_width, int image_height,
                      void *detections_ptr, int max_detections)
{
    if (!detector_ptr || !image_data || !detections_ptr)
    {
        return 0;
    }

    YOLODetector *detector = static_cast<YOLODetector*>(detector_ptr);
    DetectionBox *detections = static_cast<DetectionBox*>(detections_ptr);

    // TODO: 实现 YOLO 检测
    // 1. 将 image_data 转换为 OpenCV Mat 或 runtime_tensor
    // 2. 调用 Yolov5::pre_process
    // 3. 调用 Yolov5::inference
    // 4. 调用 Yolov5::post_process 获取结果
    // 5. 转换为 DetectionBox 数组

    // 临时返回 0（无检测结果）
    return 0;
}

void yolo_detector_draw_results(void *detector_ptr, uint8_t *image_data,
                                int image_width, int image_height,
                                void *detections_ptr, int num_detections)
{
    if (!detector_ptr || !image_data || !detections_ptr)
    {
        return;
    }

    YOLODetector *detector = static_cast<YOLODetector*>(detector_ptr);
    DetectionBox *detections = static_cast<DetectionBox*>(detections_ptr);

    // TODO: 实现绘制检测结果
    // 1. 将 image_data 转换为 OpenCV Mat
    // 2. 调用 Yolov5::draw_results
    // 3. 将结果写回 image_data
}

void yolo_detector_set_confidence(void *detector_ptr, float threshold)
{
    if (!detector_ptr)
    {
        return;
    }

    YOLODetector *detector = static_cast<YOLODetector*>(detector_ptr);
    detector->conf_threshold = threshold;

    // TODO: 更新 Yolov5 实例的置信度阈值
    // if (detector->yolo_impl)
    // {
    //     static_cast<Yolov5*>(detector->yolo_impl)->conf_thres_ = threshold;
    // }
}

} // extern "C"





