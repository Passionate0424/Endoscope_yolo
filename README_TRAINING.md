# YOLOv5 内窥镜息肉检测模型训练指南

## 项目结构

```
Endoscope_yolo/
├── yolov5_project/          # YOLOv5 工程文件夹（从yolov5复制）
├── datasheet/
│   └── Kvasir-SEG-YOLO/     # 转换后的YOLO格式数据集
│       ├── data.yaml        # 数据集配置文件
│       ├── images/
│       │   ├── train/       # 880张训练图片
│       │   └── val/         # 120张验证图片
│       └── labels/
│           ├── train/       # 880个训练标注
│           └── val/         # 120个验证标注
└── train_endoscope_yolo.py  # 训练脚本
```

## 环境要求

- Python 3.10+
- PyTorch 2.5.1+ (CUDA支持)
- 已安装所有依赖（在pytorch_env conda环境中）

## 预训练权重

**需要下载预训练权重吗？**

**答案：不需要手动下载！** YOLOv5 会自动下载预训练权重。

当你运行训练命令时，如果指定的权重文件（如 `yolov5s.pt`）不存在，YOLOv5 会自动从 GitHub 下载。

### 可用的预训练模型

- `yolov5n.pt` - Nano (最小，最快)
- `yolov5s.pt` - Small (推荐，平衡速度和精度)
- `yolov5m.pt` - Medium (中等大小)
- `yolov5l.pt` - Large (更大)
- `yolov5x.pt` - XLarge (最大，最准确)

## 训练方法

### 方法1: 使用训练脚本（推荐）

```bash
# 激活conda环境
conda activate pytorch_env

# 运行训练脚本
python train_endoscope_yolo.py
```

### 方法2: 直接使用train.py

```bash
# 激活conda环境
conda activate pytorch_env

# 进入yolov5_project目录
cd yolov5_project

# 开始训练
python train.py \
    --data data/Kvasir-SEG.yaml \
    --weights yolov5s.pt \
    --img 640 \
    --epochs 100 \
    --batch 16 \
    --device 0 \
    --name endoscope_polyp_detection
```

### 训练参数说明

- `--data`: 数据集配置文件路径
- `--weights`: 预训练权重（会自动下载）
- `--img`: 输入图片尺寸（640, 1280等）
- `--epochs`: 训练轮数（建议100-300）
- `--batch`: 批次大小（根据GPU内存调整，16GB显存建议16）
- `--device`: GPU设备（0, 1, 或 "0,1" 多GPU）
- `--name`: 实验名称

### 批次大小建议

根据GPU显存调整：

- 8GB显存: `--batch 8`
- 16GB显存: `--batch 16`
- 24GB显存: `--batch 32`

## 训练输出

训练完成后，模型和结果保存在：

```
yolov5_project/runs/train/endoscope_polyp_detection/
├── weights/
│   ├── best.pt          # 最佳模型（验证集上mAP最高）
│   └── last.pt          # 最后一轮模型
├── results.png          # 训练曲线图
├── confusion_matrix.png # 混淆矩阵
└── ...
```

## 验证模型

训练完成后，可以使用以下命令验证模型：

```bash
cd yolov5_project
python val.py \
    --weights runs/train/endoscope_polyp_detection/weights/best.pt \
    --data data/Kvasir-SEG.yaml \
    --img 640
```

## 使用训练好的模型进行推理

```bash
cd yolov5_project
python detect.py \
    --weights runs/train/endoscope_polyp_detection/weights/best.pt \
    --source path/to/image.jpg \
    --conf 0.25 \
    --img 640
```

## 常见问题

### 1. 权重文件下载失败

如果自动下载失败，可以手动下载：

- 访问: <https://github.com/ultralytics/yolov5/releases>
- 下载对应的 `.pt` 文件
- 放置在 `yolov5_project/` 目录下

### 2. CUDA out of memory

减少批次大小：

```bash
--batch 8  # 或更小
```

### 3. 训练速度慢

- 使用更小的模型（yolov5n.pt）
- 减少图片尺寸（--img 416）
- 使用多GPU训练

## 数据集信息

- **训练集**: 880张图片
- **验证集**: 120张图片
- **类别**: 1个（polyp - 息肉）
- **标注格式**: YOLO格式（归一化坐标）

## 下一步

1. 训练模型
2. 评估模型性能
3. 在验证集上测试
4. 导出模型（ONNX, TensorRT等）
5. 部署到生产环境


