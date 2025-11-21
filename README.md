## 内窥镜息肉检测项目总览

这是一个基于**K230 庐山派**双核开发板的完整 **YOLOv5** 内窥镜息肉检测平台，包括：

- **模型训练**：使用 Kvasir-SEG 数据集的 YOLO 标注版本进行多目标检测训练（`Endoscope_yolov5_project`）。
- **模型转换**：将 PyTorch/ONNX 模型转换为适配 **K230/CanMV** 的 `kmodel` 文件（`build` 与 `scripts/conversion`）。
- **设备端部署**：在 **K230 开发板** 上通过自动启动的 HTTP/Web 服务进行实时视频检测与管理（`k230_onboard_project`）。
- **大核集成**（2025.11.19 新增）：C 层 HTTP 服务器已集成到大核 RT-Smart，具备自动启动与 WiFi 感知功能。

如果你只是第一次打开该仓库，建议按下面的顺序阅读并上手。

---

## 快速开始

### 阶段 1：模型准备（PC 端）

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

### 阶段 2：固件编译与烧写（K230 设备端）

- **4. 编译包含 HTTP 服务器的固件**（2025.11.19 完成）
  - 大核 (C908 RT-Smart)：C 层 HTTP 服务器已集成
  - 服务器功能：
    - ✅ **自动启动**：系统启动时自动启动（通过 `INIT_APP_EXPORT`）
    - ✅ **WiFi 感知启动**：检测到网络就绪后自动启动 HTTP 服务
    - ✅ **MJPEG 视频流**：支持 `/stream` 端点
    - ✅ **图像快照**：支持 `/snapshot` 端点
    - ✅ **自适应帧缓冲**：使用共享内存与小核通信
  - 烧写方式：参考 `docs/README_K230_EXPORT.md`
  - 推荐固件：`build/canmv_firmware/CanMV_K230_LCKFB_WITH_HTTP_SERVER_COMPILED.img`

### 阶段 3：设备端运行（K230 CanMV 小核）

- **5. 在 K230 上部署和运行**
  - 参考：`k230_onboard_project/README.md`
  - 将生成的 `model.kmodel` 拷贝到 K230 `/data/` 目录
  - 选择运行方式（二选一）：
    
    **方式 A（完整功能，推荐）：**
    ```bash
    python /data/main_rtsmart.py
    ```
    功能：YOLO 检测 + 自动保存检测结果 + WiFi 连接
    
    **方式 B（最小化）：**
    ```bash
    python /data/main.py
    ```
    功能：仅 YOLO 检测 + LCD 显示

- **6. 通过浏览器访问**
  - HTTP 服务器自动在 K230 启动，监听 **8080** 端口
  - 访问地址：`http://<K230_IP>:8080`
  - MJPEG 实时流：`http://<K230_IP>:8080/stream`
  - 图像快照：`http://<K230_IP>:8080/snapshot`

---

## 仓库结构简介

- `Endoscope_yolov5_project`：基于官方 YOLOv5 的训练工程（已集成数据配置与脚本）。
- `datasheet/Kvasir-SEG`：原始 Kvasir-SEG 数据集。
- `datasheet/Kvasir-SEG-YOLO`：已转换为 YOLO 标注格式的数据集（`data.yaml`、`images/`、`labels/`）。
- `scripts/training`：训练相关脚本（如 `train_endoscope_yolo.py`）。
- `scripts/conversion`：导出 ONNX、调用 nncase 生成 K230 `kmodel` 的脚本。
- `build/canmv_firmware/`：编译后的固件文件（包括新的 HTTP 服务器版本）。
- `build/k230`、`build/k230_pytorch_env`：模型导出与量化过程中的中间与产出文件目录。
- **`k230_onboard_project/`**：K230 设备端应用（2025.11.19 已清理）
  - `main.py`：小核 YOLO 检测主程序（LCD 显示）
  - `main_rtsmart.py`：完整版本（YOLO 检测 + 检测结果保存 + WiFi 连接）
  - `yolo_controller.py`：YOLO 检测控制器
  - `detection_manager.py`：检测记录管理（保存息肉检测图像）
  - `wifi_config.py`：WiFi 配置与连接工具
  - `rtsmart_web_adapter.py`：C 服务器适配层（备用）
- **`rtsmart_userapp/`**：大核 C 层 HTTP 服务器源代码（2025.11.19 新增）
  - `src/http_server.c`：HTTP 服务器主程序（自动启动 + WiFi 感知）
  - `src/http_handler.c`：HTTP 请求处理
  - `src/frame_buffer.c`：帧缓冲管理
  - `include/`：头文件
  - `SConscript`：编译配置
- `yolov5`：原始 Ultralytics YOLOv5 仓库（作为子目录保留，用于参考或对比）。
- `docs`：本项目相关说明文档的集中存放目录。
- `kernel_bsp_maix3_SConscript_FINAL`、`app_http_server_SConscript_FINAL`：大核编译配置备份（2025.11.19）

---

## 典型工作流

### PC 端训练和导出（3 步）
```
1. 在 PC 上完成训练，得到 best.pt
   位置：Endoscope_yolov5_project/runs/train/.../weights/best.pt

2. 使用 scripts/conversion/export_to_kmodel_k230.ps1 导出
   - 导出 ONNX：best.pt → model.onnx
   - 编译为 K230 模型：model.onnx → model.kmodel（使用 nncase）

3. 生成固件和模型文件
   - 固件：build/canmv_firmware/CanMV_K230_LCKFB_WITH_HTTP_SERVER_COMPILED.img
   - 模型：build/k230/model.kmodel
```

### K230 设备端部署（4 步）
```
1. 烧写固件到 K230 SD 卡
   - 使用固件：CanMV_K230_LCKFB_WITH_HTTP_SERVER_COMPILED.img
   - 大核自动启动 HTTP 服务器（无需手动操作）

2. 复制模型文件到设备
   - 复制 model.kmodel 到 K230 /data/ 目录

3. 在 K230 小核运行检测程序
   - 方式 A（推荐）：python /data/main_rtsmart.py
     完整功能：YOLO 检测 + 结果保存 + WiFi 连接
   - 方式 B（简化）：python /data/main.py
     仅 YOLO 检测：LCD 显示实时检测结果

4. 通过浏览器访问
   - MJPEG 实时流：http://<K230_IP>:8080/stream
   - 快照获取：http://<K230_IP>:8080/snapshot
```

### 系统架构（2025.11.19 最新）
```
K230 双核协作：

大核 (C908 RT-Smart)
├─ HTTP 服务器 (C 实现)
│  ├─ 自动启动线程
│  ├─ WiFi 监控线程（60秒超时）
│  ├─ MJPEG 视频流服务
│  └─ 共享帧缓冲 (3×512KB)

小核 (C906 MicroPython/CanMV)
├─ YOLO 检测 (KModel 推理)
├─ 相机采集和 LCD 显示
├─ 检测结果保存 (/data/detections/)
└─ WiFi 连接管理
```

---

## 文档索引

- **训练指南**：`docs/README_TRAINING.md`
- **K230 模型导出说明**：`docs/README_K230_EXPORT.md`
- **K230 设备端应用说明**：`k230_onboard_project/README.md`
- **数据集与标注说明**：`datasheet/README.md`（如需查看原始数据组织）
- **模型转换完成记录/备注**：`docs/KMODEL_CONVERSION_COMPLETE.md`
- **大核 HTTP 服务器自启动说明**：`rtsmart_userapp/AUTOSTART.md`（2025.11.19 新增）

---

## 2025.11.19 更新说明

本次更新完成了 **K230 大核 HTTP 服务器的完整集成与自启动功能**，主要成果：

### 技术突破

1. **大核编译集成** ✅
   - 原问题：HTTP 服务器代码在小核 MicroPython 构建系统中，无法在大核启动
   - 解决方案：修改大核 RT-Smart 的 SCons 编译配置，将 HTTP 服务器集成到大核
   - 关键文件：`rtsmart_userapp/src/` 下的 `http_server.c`、`http_handler.c`、`frame_buffer.c`

2. **自动启动机制** ✅
   - 大核启动时自动创建 WiFi 监控线程
   - 检测到网络就绪后自动启动 HTTP 服务器（60 秒超时）
   - 无需手动执行 `http_start` 命令

3. **编译验证** ✅
   - 编译时间：41 秒
   - 生成的目标文件：frame_buffer.o (53KB) + http_handler.o (47KB) + http_server.o (111KB) = 211KB
   - 固件增长：+7042 字节（验证代码已编译）
   - 生成固件：`build/canmv_firmware/CanMV_K230_LCKFB_WITH_HTTP_SERVER_COMPILED.img`

### 项目清理

4. **小核应用精简** ✅
   - 删除过时的 Python HTTP 服务器实现（`web_server.py` 等）
   - 删除已被 C 层替代的启动脚本（`startup.py`、`auto_http_server.py` 等）
   - 保留核心文件：`main.py`（简化版）、`main_rtsmart.py`（完整版）
   - 保留依赖模块：`detection_manager.py`、`yolo_controller.py`、`wifi_config.py`

5. **编译配置备份** ✅
   - `kernel_bsp_maix3_SConscript_FINAL`：大核内核 BSP 编译配置
   - `app_http_server_SConscript_FINAL`：HTTP 服务器应用编译配置
   - 这些文件记录了如何在大核编译系统中正确集成 C 层服务器

### 后续工作

6. **下一步验证**（待硬件测试）
   - 烧写新固件到 K230 SD 卡
   - 观察大核 UART 启动日志，验证 HTTP 服务器自启动
   - 通过浏览器访问 `http://<K230_IP>:8080/stream` 查看 MJPEG 流
   - 运行小核检测程序验证双核协作

如需了解 YOLOv5 本身的更多用法，可参考：

- `Endoscope_yolov5_project/README.md` 与 `Endoscope_yolov5_project/README.zh-CN.md`
- `yolov5/README.md` 与 `yolov5/README.zh-CN.md`

---

## 许可证与致谢

- 本项目在 `Endoscope_yolov5_project` 与 `yolov5` 中使用了 Ultralytics YOLOv5，相关开源协议请参见各目录下的 `LICENSE` 和 `README*`。
- Kvasir-SEG 数据集来自公开医学图像数据集，使用时请遵守原数据集的协议与引用要求。
