import cv2
import numpy as np
import onnxruntime as ort
import getcolors

def preprocess(image, input_width=320,input_height=320,mean=[0,0,0],std=[1,1,1]):
    """
    预处理输入图像，调整大小、归一化、转换通道顺序、添加批次维度。
    """
    # 获取原始图像尺寸
    orig_h, orig_w = image.shape[:2]
    # 计算缩放比例，保持长宽比
    scale = min(input_width / orig_w, input_height / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    # 缩放图像
    resized_image = cv2.resize(image, (new_w, new_h))
    # 创建一个背景图像
    canvas = np.ones((input_height, input_width, 3),dtype=np.uint8)*128
    # 将缩放后的图像粘贴到背景图像中
    canvas[0:new_h, 0:new_w, :] = resized_image
    # BGR 转 RGB
    img = canvas[:, :, ::-1]
    # 转换为 float32
    img = img.astype(np.float32) / 255
    for i in range(3):
        img[:, :, i] -= mean[i]
        img[:, :, i] /= std[i]
    # HWC 转 CHW
    img = np.transpose(img, (2, 0, 1))
    # 添加批次维度
    img = np.expand_dims(img, axis=0)
    onnx_input=img.copy()
    return onnx_input, scale

def postprocess(predictions, scale, original_image, conf_threshold=0.25, iou_threshold=0.45, classes=None):
    """
    后处理推理结果，进行非极大抑制（NMS），并将检测框映射回原始图像。
    """
    predictions = predictions[0]  # 移除批次维度
    # 分离边界框、置信度和类别概率
    boxes = predictions[:, :4]  # x_center, y_center, w, h
    objectness = predictions[:, 4]
    class_probs = predictions[:, 5:]
    # 计算置信度
    scores = objectness * class_probs.max(axis=1)
    class_ids = class_probs.argmax(axis=1)
    # 过滤低置信度的框
    mask = scores > conf_threshold
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]
    # 转换边界框格式，从 (x_center, y_center, w, h) 转为 (x1, y1, x2, y2)
    boxes_xy = boxes[:, :2]
    boxes_wh = boxes[:, 2:4]
    boxes_xy -= boxes_wh / 2
    boxes_xy = boxes_xy/scale
    boxes_wh = boxes_wh/scale
    boxes_xy2 = boxes_xy + boxes_wh
    boxes = np.concatenate([boxes_xy, boxes_xy2], axis=1)
    # 转换为 float32 类型
    boxes = boxes.astype(np.float32)
    scores = scores.astype(np.float32)
    # 使用 OpenCV 的 NMS 进行非极大抑制
    indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf_threshold, iou_threshold)
    # 如果没有检测到目标，返回空列表
    if len(indices) == 0:
        return []
    indices = indices.flatten()
    detections = []
    for i in indices:
        box = boxes[i]
        score = scores[i]
        class_id = class_ids[i]
        detections.append({
            "box": box,
            "score": score,
            "class_id": class_id
        })
    
    return detections

def draw_boxes(image, detections, class_names,colors):
    """
    在图像上绘制检测框和类别标签。
    """
    for det in detections:
        box = det["box"]
        score = det["score"]
        class_id = det["class_id"]
        x1, y1, x2, y2 = map(int, box)
        label = f"{class_names[class_id]}: {score:.2f}"
        # 绘制边界框
        cv2.rectangle(image, (x1, y1), (x2, y2), colors[class_id], 2)
        # 绘制标签
        (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(image, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[class_id], 1)
    return image

def main():
    # 设置参数
    model_path = '../../runs/train/exp/weights/best.onnx'  # 替换为你的 ONNX 模型路径
    image_path = '../test_images/test.jpg'  # 替换为你要检测的图像路径
    input_width = 320
    input_height = 320
    mean=[0,0,0]
    std=[1,1,1]
    conf_threshold = 0.25
    iou_threshold = 0.45
    # 加载类别名称（根据你的数据集修改）
    class_names = ["apple","banana","orange"]
    colors=getcolors.get_colors(len(class_names))
    # 加载 ONNX 模型
    ort_session = ort.InferenceSession(model_path)
    # 获取模型输入名称
    input_name = ort_session.get_inputs()[0].name
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: 无法读取图像 {image_path}")
        return
    # 预处理图像
    img_input, scale = preprocess(image, input_width,input_height,mean,std)
    # 运行推理
    outputs = ort_session.run(None, {input_name: img_input})
    # 假设模型只有一个输出
    predictions = outputs[0]
    # 后处理
    detections = postprocess(predictions, scale, image, conf_threshold, iou_threshold, class_names)
    # 绘制检测结果
    result_image = draw_boxes(image.copy(), detections, class_names,colors)
    # 保存结果图像
    cv2.imwrite("onnx_det_result.jpg", result_image)
    print("onnx_det_result.jpg is saved!")

if __name__ == "__main__":
    main()
