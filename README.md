## 内窥镜息肉检测项目总览

这是一个基于**k230**庐山派的 **YOLOv5** 内窥镜息肉检测平台完整方案，包括：

- **模型训练**：使用 Kvasir-SEG 数据集的 YOLO 标注版本进行多目标检测训练（`Endoscope_yolov5_project`）。
- **模型转换**：将 PyTorch/ONNX 模型转换为适配 **K230/CanMV** 的 `kmodel` 文件（`build` 与 `scripts/conversion`）。
- **设备端部署**：在 **庐山派 K230 开发板** 上通过 HTTP/Web 前端进行实时视频检测与管理（`k230_onboard_project`）。

如果你只是第一次打开该仓库，建议按下面的顺序阅读并上手。

---

## 快速开始

- **1. 准备环境与数据集**
  - 参考：`docs/README_TRAINING.md`
  - 内容包括：Python/PyTorch 环境、Kvasir-SEG-YOLO 数据集结构与路径说明。

- **2. 训练内窥镜 YOLOv5 模型**
  - 参考：`docs/README_TRAINING.md`
  - 支持两种方式：
    - 直接运行 `scripts/training/train_endoscope_yolo.py`
    - 进入 `Endoscope_yolov5_project` 使用官方 `train.py`

- **3. 导出并转换为 K230 模型**
  - 参考：`docs/README_K230_EXPORT.md`
  - 使用 `scripts/conversion/export_to_kmodel_k230.ps1` 一键导出 ONNX 并调用 **nncase** 生成 `model.kmodel`。

- **4. 在 K230 上部署和测试**
  - 参考：`docs/k230_onboard_project/README.md`
  - 将生成的 `model.kmodel` 拷贝到 K230，运行 `k230_onboard_project/main.py`，通过浏览器访问设备 IP 进行实时检测。

---

## 仓库结构简介

- `Endoscope_yolov5_project`：基于官方 YOLOv5 的训练工程（已集成数据配置与脚本）。
- `datasheet/Kvasir-SEG`：原始 Kvasir-SEG 数据集。
- `datasheet/Kvasir-SEG-YOLO`：已转换为 YOLO 标注格式的数据集（`data.yaml`、`images/`、`labels/`）。
- `scripts/training`：训练相关脚本（如 `train_endoscope_yolo.py`）。
- `scripts/conversion`：导出 ONNX、调用 nncase 生成 K230 `kmodel` 的脚本。
- `build/k230`、`build/k230_pytorch_env`：模型导出与量化过程中的中间与产出文件目录。
- `k230_onboard_project`：K230 设备端 HTTP 服务器与实时检测应用。
- `yolov5`：原始 Ultralytics YOLOv5 仓库（作为子目录保留，用于参考或对比）。
- `docs`：本项目相关说明文档的集中存放目录。

---

## 典型工作流

1. 在 PC 上完成训练，得到 `best.pt`（默认在 `Endoscope_yolov5_project/runs/train/.../weights/best.pt`）。
2. 使用 `scripts/conversion/export_to_kmodel_k230.ps1` 导出 ONNX 并用 nncase 编译为 `model.kmodel`。
3. 将 `model.kmodel` 与 `k230_onboard_project` 代码部署到 K230 设备。
4. 运行 `python main.py`，在浏览器中访问设备 IP，启停视频流与检测，查看检测记录。

---

## 文档索引

- **训练指南**：`docs/README_TRAINING.md`
- **K230 模型导出说明**：`docs/README_K230_EXPORT.md`
- **K230 设备端应用说明**：`k230_onboard_project/README.md`
- **数据集与标注说明**：`datasheet/README.md`（如需查看原始数据组织）
- **模型转换完成记录/备注**：`docs/KMODEL_CONVERSION_COMPLETE.md`

如需了解 YOLOv5 本身的更多用法，可参考：

- `Endoscope_yolov5_project/README.md` 与 `Endoscope_yolov5_project/README.zh-CN.md`
- `yolov5/README.md` 与 `yolov5/README.zh-CN.md`

---

## 许可证与致谢

- 本项目在 `Endoscope_yolov5_project` 与 `yolov5` 中使用了 Ultralytics YOLOv5，相关开源协议请参见各目录下的 `LICENSE` 和 `README*`。
- Kvasir-SEG 数据集来自公开医学图像数据集，使用时请遵守原数据集的协议与引用要求。
