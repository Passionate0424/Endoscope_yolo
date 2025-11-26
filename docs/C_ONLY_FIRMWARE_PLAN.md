# K230 纯 C 固件方案（无 MicroPython）

> 目标：在 WSL 内创建一个仅用 C/C++ 的 K230 固件，复用现有 `rtsmart_userapp` 的 HTTP/MJPEG 代码，接入 `k230_yolo_ref/YOLO/src` 的 YOLO 推理，去除 MicroPython 依赖。

## 1. 架构概要
- **HTTP/MJPEG**：沿用 `rtsmart_userapp` 中的 `http_server.c / http_handler.c / frame_buffer.c / web_state.c`。
- **YOLO 推理**：在 `yolo_thread.c` 启动独立线程，调用 C++ 包装 `yolo_detector_wrapper.cpp`，底层直接移植 `k230_yolo_ref/YOLO/src` 的 Pipeline + Yolov5/8/11 代码。
- **前端**：继续使用生成的 `.inc` 静态资源，内置于 RT-Smart。
- **数据流**：ISP/Pipeline 获取 RGB888 → YOLO 推理 → 叠加结果 → JPEG 压缩 → `frame_buffer_push` → `/stream` MJPEG。
- **默认参数（参考 MicroPython 现用值）**：kmodel `/data/model.kmodel`，labels `/data/labels.txt`，输入尺寸 640x640，RGB888，阈值 conf=0.5，nms=0.45。

## 2. WSL 一键脚本
新增 `scripts/bootstrap_c_firmware_wsl.sh`（需自行创建），作用：
1) 准备 SDK 基线 `~/canmv_k230_clean`（若不存在可按 `docs/SDK_INTEGRATION_MODIFICATIONS.md` 初始化；首次 `repo init/sync` 可手动执行，脚本只做注释提示）。
2) 复制到新目录 `~/canmv_k230_c_firmware` 作为 C-only 工程。
3) 覆盖 `app_http_server/`（HTTP + web_state 等）。
4) 拷贝 `k230_yolo_ref/YOLO/src` 到 `app_http_server/yolo_ref/`，供 SCons 编译。
5) 更新 SCons/Makefile：
   - `app_http_server/SConscript` 同时编译 C 与 C++，包含 `yolo_ref/*`。
   - `kernel/bsp/maix3/SConstruct` 引入 `app_http_server/SConscript`。
   - 移除 MicroPython 相关改动（纯 C 固件无需 `canmv/port` 变更）。
6) 添加 `app_http_server/main.c` 作为 userapp 入口：启动 HTTP、启动 YOLO 线程、主循环维持心跳。

运行示例：
 ```bash
 # Windows PowerShell
 wsl bash /mnt/e/project/Endoscope_yolo/scripts/bootstrap_c_firmware_wsl.sh
 ```

## 3. 目录布局（WSL 内）
```
~/canmv_k230_c_firmware/
└─ src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/
   ├─ SConscript           # 编译入口，含 C/C++ 源
   ├─ main.c               # C-only 启动入口（新增）
   ├─ include/             # 原有头文件
   ├─ src/                 # HTTP/MJPEG/web_state 实现
   ├─ yolo_thread.c        # YOLO 线程调度
   ├─ yolo_detector_wrapper.cpp  # C++ 封装
   └─ yolo_ref/            # 来自 k230_yolo_ref/YOLO/src 的参考实现
```

## 4. 构建步骤
```bash
cd ~/canmv_k230_c_firmware
make k230_canmv_lckfb_defconfig   # 或你的目标 defconfig
make clean && make -j$(nproc)
```

## 5. 验证
```bash
# HTTP 相关符号
strings output/.../images/rtsmart/rtthread.bin | grep http_server

# 确认无 MicroPython 依赖
```

## 6. 运行路径
- `http_start` 或在 `main.c` 中自动调用 `http_server_autostart()`。
- YOLO 线程从 Pipeline 取帧，推理后调用 `frame_buffer_push()` 输出 MJPEG。
- 前端访问 `http://<设备IP>:8080/`。

## 7. 待办
- [ ] 在 `yolo_detector_wrapper.cpp` 落地调用 Yolov5/8/11（pre_process / inference / post_process / draw_results）。
-, [ ] 选择 JPEG 路径：优先 K230 VENC（高效）；如缺省可用 OpenCV `cv::imencode`（需确认工具链支持）。
-, [ ] 默认模型/标签路径：`/data/model.kmodel`、`/data/labels.txt`。
-, [ ] 根据堆栈需求调大 YOLO 线程与 HTTP 线程栈（如 64 KB+）。

## 8. 交付物列表
- 新脚本：`scripts/bootstrap_c_firmware_wsl.sh`
- 新入口：`app_http_server/main.c`
- SCons/Makefile 更新：支持 C/C++、加入 `yolo_ref`
- 关键源码：`yolo_thread.c`、`yolo_detector_wrapper.cpp`、`yolo_ref/*`

## 9. 使用建议
- 构建与调试都在 WSL 完成，生成的 `img/img.gz` 拷贝回 Windows `build/canmv_firmware/`。
- 建议先跑通纯 C 固件，再考虑与 Python 版本并行维护。
- 如果你的 kmodel 已在本仓库 `build/k230_pytorch_env/model.kmodel`，复制到板端 `/data/model.kmodel`（或自定义路径），并同步更新入口代码的 kmodel/label 路径；标签缺省为 `build/k230_pytorch_env/labels.txt`（若存在）。

## 10. 设备侧运行
- 引导后在 msh 直接运行：`main`（入口在 `rtsmart_userapp/main.c`），HTTP 端口 8080，默认模型/标签 `/data/model.kmodel`、`/data/labels.txt`。
- Web 访问：`http://<设备IP>:8080/`；MJPEG：`http://<设备IP>:8080/stream`。
- 如需更换模型路径/输入尺寸，修改 `main.c` 和 `yolo_thread.c` 默认参数后重新编译。
