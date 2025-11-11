### 将已训练的 YOLOv5 模型转换为 K230 kmodel（CanMV/Kendryte）

下述步骤基于当前工程结构，默认输入尺寸为 640。你可以按需修改。

#### 1. 先导出 ONNX，并准备量化校准集

在 PowerShell 中运行：

```bash
pwsh -File .\export_to_kmodel_k230.ps1 `
  -WeightsPath ".\yolov5_project\runs\train\endoscope_polyp_detection5\weights\best.pt" `
  -ImgSize 640 `
  -OutputDir ".\build\k230" `
  -CalibCount 100 `
  -CalibSource ".\datasheet\Kvasir-SEG-YOLO\images\val"
```

脚本会：
- 使用 `yolov5/export.py` 导出 ONNX（opset 12）
- 在 `build/k230/onnx` 存放导出的 ONNX
- 从校准源目录拷贝前 N 张图片至 `build/k230/calib`
- 生成 `build/k230/k230_yolov5_ncc_config.yaml`（nncase 配置模板）

#### 2. 安装 nncase（ncc）

```bash
pip install nncase
ncc --version
```

确保 `ncc` 在 PATH 中。

#### 3. 使用配置文件进行编译（推荐）

```bash
ncc compile ".\build\k230\onnx\*.onnx" ".\build\k230\model.kmodel" --config ".\build\k230\k230_yolov5_ncc_config.yaml"
```

说明：
- `target: k230`
- 量化：PTQ（使用 `build/k230/calib` 下的图片）
- 预处理：NCHW，mean=[0,0,0]，std=[255,255,255]，letterbox=114，保持比例缩放到 640×640

若你使用不同的输入尺寸，请同步修改 YAML 中的 `model_input_shape` 与脚本参数。

#### 4. 通过命令行参数方式编译（可选）

不同 nncase 版本参数略有差异，以下为常见用法（若报错请用上面的 config 方式）：

```bash
ncc compile ".\build\k230\onnx\your.onnx" ".\build\k230\model.kmodel" `
  --target k230 `
  --dataset ".\build\k230\calib" `
  --input-layout NCHW `
  --input-mean 0 0 0 `
  --input-std 255 255 255 `
  --quantize
```

#### 5. 部署

编译完成后，产物 `.\build\k230\model.kmodel` 即可用于 K230/CanMV 端加载。后处理（解码输出、NMS、阈值等）需在设备端按你的 YOLO 版本和导出头部进行适配。

#### 常见问题
- 如果 `export.py` 导出 ONNX 报错，尝试降低 opset（如 11）或关闭 simplify。
- 如果 nncase 报算子不支持，可尝试不同 opset 或更新 nncase。
- 请确保训练与推理输入尺寸一致（默认 640），否则需要在设备端同步 letterbox/后处理逻辑。







