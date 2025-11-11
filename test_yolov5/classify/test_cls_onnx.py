import cv2
import numpy as np
import onnxruntime as ort


def preprocess(image, input_width=224,input_height=224,mean=[0,0,0],std=[1,1,1]):
    """
    预处理输入图像，调整大小、归一化、转换通道顺序、添加批次维度。
    """
    # 获取原始图像尺寸
    orig_h, orig_w = image.shape[:2]
    # 计算缩放比例，保持长宽比
    m = min(orig_h,orig_w)
    top,left=(orig_h - m) // 2, (orig_w - m) // 2
    # 缩放图像
    resized_image = cv2.resize(image[top:top+m,left:left+m,:], (input_height,input_width),interpolation=cv2.INTER_LINEAR)
    # BGR 转 RGB
    img = resized_image[:, :, ::-1]
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
    return onnx_input

def softmax(z):
    e_z = np.exp(z - np.max(z, axis=1, keepdims=True))  # 减去每行的最大值
    return e_z / e_z.sum(axis=1, keepdims=True)  # 沿着列求和

def postprocess(predictions, conf_threshold=0.25, classes=None):
    """
    后处理推理结果,softmax+argmax
    """
    scores=softmax(predictions)[0]
    max_score=float(np.max(scores))
    max_ids=int(np.argmax(scores))
    if max_score>conf_threshold:
        return max_ids,max_score
    else:
        return -1,0.0

def draw_result(image, ids,score, class_names):
    """
    在图像上绘制类别标签和分数
    """
    text=f"result: {class_names[ids]} score: {score:.4f}"
    cv2.putText(image, text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 4)
    return image

def main():
    # 设置参数
    model_path = '../../runs/train-cls/exp/weights/best.onnx'  # 替换为你的 ONNX 模型路径
    image_path = '../test_images/test_apple.jpg'  # 替换为你要检测的图像路径
    input_width = 224
    input_height = 224
    mean=[0.485, 0.456, 0.406]
    std=[0.229, 0.224, 0.225]
    conf_threshold = 0.5
    # 加载类别名称（根据你的数据集修改）
    class_names = ["apple","banana","orange"]
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
    img_input = preprocess(image, input_width,input_height,mean,std)
    # 运行推理
    outputs = ort_session.run(None, {input_name: img_input})
    # 假设模型只有一个输出
    predictions = outputs[0]
    # 后处理
    ids,score = postprocess(predictions, conf_threshold, class_names)
    # 绘制检测结果
    result_image = draw_result(image.copy(), ids,score, class_names)
    # 保存结果图像
    cv2.imwrite("onnx_cls_result.jpg", result_image)
    print("onnx_cls_result.jpg is saved!")

if __name__ == "__main__":
    main()
