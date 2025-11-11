# K230 kmodel 转换完成

## 转换结果

✅ **模型转换成功完成！**

- **输入模型**: `yolov5_project/runs/train/endoscope_polyp_detection5/weights/best.pt`
- **ONNX模型**: `build/k230_pytorch_env/onnx/best.onnx` (27.2 MB)
- **Kmodel文件**: `build/k230_pytorch_env/model.kmodel` (8.45 MB)
- **输入尺寸**: 640x640
- **量化方法**: PTQ (Post-Training Quantization) with Kld calibration
- **量化类型**: uint8 (权重和激活值)

## 文件结构

```
build/k230_pytorch_env/
├── onnx/
│   └── best.onnx          # ONNX模型文件
├── calib/                 # 校准数据集 (100张图片)
│   └── *.jpg
├── k230_yolov5_ncc_config.yaml  # nncase配置文件
└── model.kmodel           # ✅ 最终的kmodel文件 (8.45 MB)
```

## 使用的转换工具

- **转换脚本**: `test_yolov5/detect/to_kmodel.py` (官方Kendryte工具)
- **nncase版本**: 2.10.0
- **nncase-kpu版本**: 2.10.0
- **ONNX版本**: 1.19.1

## 转换参数

- **目标平台**: k230
- **输入宽度**: 640
- **输入高度**: 640
- **PTQ选项**: 3 (Kld校准方法, uint8量化)
- **预处理**:
  - Input layout: NCHW
  - Input type: uint8
  - Mean: [0, 0, 0]
  - Std: [1, 1, 1]
  - Input range: [0, 1]

## 如何重新转换

如果需要对模型进行重新转换，可以使用以下方法：

### 方法1: 使用PowerShell脚本（推荐）

```powershell
conda activate pytorch_env
pwsh -File .\convert_to_kmodel.ps1 `
  -OnnxPath ".\build\k230_pytorch_env\onnx\best.onnx" `
  -CalibDir ".\build\k230_pytorch_env\calib" `
  -InputWidth 640 `
  -InputHeight 640 `
  -PtqOption 3
```

### 方法2: 直接使用Python脚本

```powershell
conda activate pytorch_env
python test_yolov5\detect\to_kmodel.py `
  --target k230 `
  --model ".\build\k230_pytorch_env\onnx\best.onnx" `
  --dataset ".\build\k230_pytorch_env\calib" `
  --input_width 640 `
  --input_height 640 `
  --ptq_option 3
```

## PTQ选项说明

- **选项0**: NoClip校准, uint8量化 (权重和激活)
- **选项1**: NoClip校准, int16权重, uint8激活
- **选项2**: NoClip校准, uint8权重, int16激活
- **选项3**: **Kld校准, uint8量化 (推荐)** ✅ 当前使用
- **选项4**: Kld校准, int16权重, uint8激活
- **选项5**: Kld校准, uint8权重, int16激活

## 部署到K230设备

1. **复制kmodel文件**到K230/CanMV设备
2. **在设备端代码中加载模型**:

   ```python
   from maix import nn
   model = nn.load("model.kmodel")
   ```

3. **预处理输入数据**:
   - 图像尺寸: 640x640
   - 数据格式: NCHW, uint8
   - 归一化: 不需要（已在模型中处理）
4. **后处理输出**:
   - YOLOv5输出格式: (1, 25200, 6) - [x, y, w, h, conf, class]
   - 需要应用NMS (Non-Maximum Suppression)
   - 阈值过滤: conf_threshold, nms_threshold

## 注意事项

1. **输入尺寸**: 模型固定输入为640x640，设备端需要保持一致的预处理
2. **数据格式**: 输入必须是uint8格式的NCHW布局
3. **后处理**: kmodel只包含推理部分，NMS等后处理需要在设备端实现
4. **性能**: 量化后的模型在K230上推理速度更快，但精度可能略有下降

## 验证模型

可以使用官方提供的测试脚本验证模型：

```powershell
# 测试ONNX模型
python test_yolov5\detect\test_det_onnx.py

# 测试kmodel（需要在K230设备上运行）
python test_yolov5\detect\test_det_kmodel.py
```

## 相关文件

- `export_to_kmodel_k230.ps1`: ONNX导出和校准集准备脚本
- `convert_to_kmodel.ps1`: kmodel转换脚本包装器
- `test_yolov5/detect/to_kmodel.py`: 官方转换脚本
- `README_K230_EXPORT.md`: 详细的转换文档

## 问题排查

如果转换过程中遇到问题：

1. **确保conda环境正确**: `conda activate pytorch_env`
2. **检查依赖安装**: `pip list | findstr nncase`
3. **验证ONNX文件**: 可以使用Netron查看模型结构
4. **检查校准数据集**: 确保calib目录中有足够的图片（至少20张）
5. **查看错误日志**: 转换过程中的错误信息会显示具体问题

---

**转换完成时间**: 2025-11-12 00:13
**环境**: pytorch_env (Python 3.10.19)
**状态**: ✅ 成功


