# HTTP + YOLO 花屏（彩格）问题调试报告

## 概述

- 本文档记录一次真实修复场景：在 K230 CanMV 上，使用 RT-Smart C 层服务器 + MicroPython YOLO 推流时，网页端 MJPEG 流出现“花屏（patterned image）”。
- 目标：记录发现问题、分析、解决步骤、代码变更、验证方法与后续建议，便于团队复现/参考。

---

## 1. 问题重现环境

- K230 CanMV 板子，传感器：GC2093（或类似），默认显示分辨率 800x480，YOLO 输入 640x360。
- 运行代码：`k230_onboard_project/main_http_loop.py`（单循环）
- RTWebAdapter 用途：把 Python 层的 Image 对象或 JPEG bytes 推送到 C 层 MJPEG 缓冲区。

---

## 2. 现象描述

- 前端页面显示的 MJPEG 流为小块重复的花屏/彩格，而非实际摄像头画面。
- 串口/日志显示收到推送帧（RTWeb 输出 JPEG bytes），但图像内容不对。

---

## 3. 问题排查与根因

### 3.1 首要发现

- `PipeLine.get_frame()` 返回 `ulab.ndarray`（CHW 或 NV12 等），不是 `image.Image`。
- 代码曾尝试把 `ndarray` 转 `image.Image`（使用 ALLOC_REF 或 data bytes）以便推流或保存，但在该固件/实现上兼容性差，导致构造失败或生成非法的 JPEG bytes。

### 3.2 所导致的问题

- 向 `RTWebAdapter.update_frame()` 传入不合法对象（ndarray 或错误构造的 Image）导致 adapter 调用 compress/推送生成的 bytes 无效；C 层 pushFrame 导致浏览器接收到错误 JPEG，显示为花屏。

---

## 4. 修复思路

1. 取消复杂/易错的 `ulab.ndarray` → `image.Image` 转换逻辑。
2. 优先使用 `sensor.snapshot(chn=...)` 返回的 `image.Image` 对象（通道0用于推流，通道2用于AI/saving）。
3. 支持 YUV420SP 直接 `compress()`，如果 `compress()` 失败，尝试 `to_rgb888()` 转换后压缩。
4. 对 RTWebAdapter 的 `update_frame()` 做容错处理：支持 bytes 和 `image.Image`，若非这两种数据类型打印提示并 skip。

---

## 5. 关键代码片段（已修改/新增）

### 5.1 主循环（`main_http_loop.py`）

```python
from media.sensor import CAM_CHN_ID_0, CAM_CHN_ID_2

# 推流使用通道0（YUV420SP，显示分辨率）
stream_img = pl.sensor.snapshot(chn=CAM_CHN_ID_0)
if detection_enabled and pl.osd_img is not None:
    stream_img.draw_image(pl.osd_img, 0, 0, alpha=256)
web.update_frame(stream_img)

# 保存检测记录使用通道2（RGB888，AI分辨率）
save_img = pl.sensor.snapshot(chn=CAM_CHN_ID_2)
if save_img:
    save_detection_records(results, detection_manager, save_img, threshold)
```

### 5.2 `RTWebAdapter.update_frame()` 容错实现（`rtsmart_web_adapter.py`）

```python
def update_frame(self, image):
    if not self.use_c_server or image is None:
        return

    # 如果传入已经压缩的jpeg字节
    if isinstance(image, (bytes, bytearray)):
        rtsmart_web.push_frame(image)
        return

    # 如果传入 image.Image 对象
    if hasattr(image, 'compress'):
        try:
            jpeg_bytes = image.compress(quality=self.quality)
        except Exception:
            # fallback: 先 to_rgb888 再 compress
            rgb = image.to_rgb888()
            jpeg_bytes = rgb.compress(quality=self.quality)

        rtsmart_web.push_frame(jpeg_bytes)
    else:
        print("[RTWeb] ⚠️ Unsupported frame type: %s" % type(image))
```

---

## 6. 验证流程

1. 启动主脚本 `main_http_loop.py`。
2. 打开浏览器访问 `http://<板子IP>:8080/`。
3. 观察串口输出：
   - `RTWeb` 的日志应显示 `帧类型: <class 'Image'>, has_compress=True`。
   - `RTWeb` 输出 `✅ JPEG格式正确` 等日志。
4. 浏览器应显示摄像头实时画面，检测框（OSD）叠加正常，花屏问题消失。

---

## 7. 验证日志示例

```
[RTWeb] 帧类型: <class 'Image'>, has_compress=True
[RTWeb] ✅ JPEG格式正确，大小: 15896 字节
[RTWeb] 推送第 1 帧，大小 15896 字节
[HTTP] ✅ 使用通道0 YUV420SP 直接推流, 尺寸: 800x480
[HTTP] 摄像头流状态 -> 暂停
```

---

## 8. 后续建议与注意事项

1. **避免直接把 ndarray 转 image.Image**，除非你非常确定固件版本对 `data` 参数/ALLOC_REF 的实现；如果必须，请实现完整的回退与日志记录。
2. **优先使用 `sensor.snapshot()` 返回 `image.Image`**，它更可靠，且支持 compress/to_rgb888 接口。
3. **RTWebAdapter 只接受 `image.Image` 或 JPEG bytes**（明确设计）；不要传入 `ndarray`。
4. **增加 `debug_verbose`** 选项打印 `update_frame()` 的分支信息（是 compress 成功还是 fallback 转 RGB 再压缩），便于下一次排查。
5. **在长时间运行的场景加入检测/自动复位机制**，以防某些极端边界条件导致内存或网路错误。

---

## 9. 总结

通过本次排查，我们识别并修复了花屏的核心原因：错误的数据类型与错误的 Image 构造路径，最终采用 `sensor.snapshot()` 与 `update_frame()` 的容错策略（compress 或 to_rgb888 转换后 compress）稳定了视频流，并且保证 OSD 检测框能正确叠加。

---

## 10. 附：调试工具/命令示例

- addr2line 地址解析工具示例（用于 c 层回溯）：

```bash
# 在WSL中执行
/root/.kendryte/k230_toolchains/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin/riscv64-unknown-linux-musl-addr2line \
  -e output/k230_canmv_lckfb_defconfig/canmv/micropython -a -f 0x200740de2 0x200740ddc
```

---

*End of report.*

---

## 附录 A：检测记录已识别但未保存（补充）

### 问题描述
- 在网页端看到检测框、RTWeb 也推送帧（画面与检测框正常），但 `/api/records` 页面没有新增记录，`/data/detections` 目录内也没有对应的图片文件。

### 根因分析
- 保存函数 `save_detection_records()` 原本只支持字典列表形式的检测结果（例如 `[{ 'bbox':[x,y,w,h], 'confidence':0.9 }, ...]`），但部分 YOLO 驱动会返回 `(dets, ids, scores)` 或 `(dets, scores)` 的元组/列表形式。
- 当 `save_detection_records()` 以字典方式读取 `result.get('confidence')` 时，如果 `result` 是数组/tuple（例如 `dets`），`get` 方法不存在，导致保存条件判断失效或异常被吞掉，从而未执行保存逻辑。

### 已施行的修复（简要）
1. 兼容返回格式：在 `k230_onboard_project/main_http_loop.py` 中改写 `save_detection_records()`，能解析：
    - 字典列表格式（`result.get('confidence')`）；
    - `(dets, ids, scores)` 或 `(dets, scores)` 格式，从 scores 中读取置信度并取对应 bbox。
2. 添加详细日志：保存成功时打印记录 ID、置信度与 bbox；若保存异常则打印异常信息。
3. 在保存前增加调试打印（snapshot/stream 保存尝试）以记录 `results` 数据格式、置信度及 yolo 阈值，方便定位问题。

### 验证步骤
1. 启动 `main_http_loop.py`（确保不是 `main_http_loop copy.py`）。
2. 打开 Web UI：`http://<板子IP>:8080/`。
3. 观察以下串口/日志项：
    - `[检测管理] 尝试保存 snapshot（通道2），结果类型=<class 'Image'>, 检测数量=N, yolo.conf_thresh=0.XX, save阈值=0.XX`
    - `[检测管理-结果] bbox=[..], confidence=..`
    - `[检测管理] 已保存记录 id=..., 置信度=.., bbox=[..]`
4. 在浏览器上通过 `/api/records` 或 `/detections/<filename>` 确认记录和图片。

### 已知后续改进（建议）
- 避免重复保存：主循环在 snapshot（通道2）和 stream（通道0）都尝试保存，可能对同一检测保存两次。建议加去重逻辑（例如基于时间窗口 + bbox IoU 阈值）。
- 将调试输出封装为开关（`DEBUG_SAVE`），便于在生产环境关闭日志。
- 如果需要把图片写入交由 C 层或通过 HTTP API 上传，建议实现 C 层接口 `/api/records/upload` 并在 Python 层通过 HTTP POST 上传 jpeg bytes（但这涉及 C 层代码变更并需重新编译）。

### 变更文件参考
- `k230_onboard_project/main_http_loop.py`（改写 `save_detection_records()`；增加调试打印）
- `k230_onboard_project/detection_manager.py`（保存逻辑仍然由此文件负责执行）

### 小结
- 在兼容 YOLO 返回格式并增强调试之后，检测框显示但未保存的问题已解决；保存与 C 层元数据注册链路均已验证成功。
