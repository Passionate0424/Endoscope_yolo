# HTTP服务器与YOLO流式传输调试过程文档

## 1. 问题概述

### 1.1 初始问题

- **现象**：固件加载后，通过浏览器访问HTTP页面时，RT-Smart串口输出`dump`错误
- **错误类型**：`Instruction Page Fault`（`scause=0xc`，`sepc=0`，`ra=0`）
- **错误信息**：`[E/DBG] User Fault, killing thread: micropython`
- **触发条件**：HTTP服务器启动后，浏览器发起HTTP请求时立即崩溃

### 1.2 问题演进

1. **第一阶段**：HTTP请求导致崩溃 → 怀疑栈溢出
2. **第二阶段**：增加栈大小后仍崩溃 → 发现`pthread_tls_stubs.c`问题
3. **第三阶段**：修复TLS问题后，YOLO推流时崩溃 → 怀疑多线程栈问题
4. **第四阶段**：改为单循环架构后，出现图像格式问题 → 彩格图像显示

## 2. 问题分析与解决过程

### 2.1 栈溢出问题（第一阶段）

#### 2.1.1 问题分析

- **症状**：`Instruction Page Fault`，`sepc=0`，`ra=0`（返回地址被破坏）
- **推测原因**：栈溢出导致返回地址被覆盖
- **影响范围**：MicroPython主线程和HTTP服务器的pthread

#### 2.1.2 解决方案

**A. 增加LWP主线程栈大小**

- **位置**：RT-Smart内核配置
- **方法**：使用`make menuconfig`
- **配置项**：`CONFIG_RTSMART_LWP_APP_STACK_SIZE`
- **修改**：从`0x10000`（64KB）增加到`0x40000`（256KB）

**B. 增加HTTP服务器pthread栈大小**

- **文件**：`rtsmart_userapp/src/http_server.c`
- **修改**：

  ```c
  // 初始值：使用系统默认（通常8KB）
  // 第一次修改：32KB
  #define PTHREAD_STACK_SIZE (32 * 1024)

> 另：本次出现“花屏/彩格”问题的专门记录已补充到 `docs/DEBUGGING_HTTP_YOLO_FLOWER_SCREEN.md`，包含修复要点和示例代码片段。
  
  // 第二次修改：64KB
  #define PTHREAD_STACK_SIZE (64 * 1024)
  ```

- **应用位置**：
  - `accept_thread`：接收连接的线程
  - `worker_threads`：处理HTTP请求的工作线程池（4个线程）

**C. 显式设置pthread属性**

```c
// 工作线程
pthread_attr_t worker_attr;
pthread_attr_init(&worker_attr);
pthread_attr_setstacksize(&worker_attr, PTHREAD_STACK_SIZE);
for (int i = 0; i < WORKER_COUNT; i++) {
    pthread_create(&worker_threads[i], &worker_attr, worker_thread_entry, NULL);
}
pthread_attr_destroy(&worker_attr);

// 接收线程
pthread_attr_t accept_attr;
pthread_attr_init(&accept_attr);
pthread_attr_setstacksize(&accept_attr, PTHREAD_STACK_SIZE);
pthread_create(&accept_thread, &accept_attr, accept_thread_func, NULL);
pthread_attr_destroy(&accept_attr);
```

#### 2.1.3 验证结果

- **部分解决**：仅启动HTTP服务器时不再崩溃
- **新问题**：启动YOLO推流后仍崩溃，说明问题不仅在于HTTP服务器本身

### 2.2 pthread TLS弱符号问题（第二阶段）

#### 2.2.1 问题分析

- **症状**：上电即崩溃，`Store/AMO Page Fault`（`stval=0x48`，`sepc=0x200740de2`）
- **错误位置**：`mp_thread_init`（`mpthreadport.c:138`）
- **根本原因**：`pthread_tls_stubs.c`中的弱符号覆盖了libc的真实pthread TLS实现

#### 2.2.2 问题根源

- **文件**：`rtsmart_userapp/src/pthread_tls_stubs.c`
- **内容**：包含弱符号stub实现：

  ```c
  __attribute__((weak)) int pthread_key_create(...) { return 0; }
  __attribute__((weak)) int pthread_key_delete(...) { return 0; }
  __attribute__((weak)) void* pthread_getspecific(...) { return NULL; }
  __attribute__((weak)) int pthread_setspecific(...) { return 0; }
  ```

- **问题**：这些弱符号被链接到MicroPython构建中，覆盖了libc的真实实现，导致MicroPython初始化TLS时写入空指针

#### 2.2.3 地址解析过程

```bash
# 在WSL中执行
cd /root/canmv_k230_http_mp
/root/.kendryte/k230_toolchains/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin/riscv64-unknown-linux-musl-addr2line \
  -e output/k230_canmv_lckfb_defconfig/canmv/micropython \
  -a -f 0x200740de2 0x200740ddc

# 结果
=> mp_thread_init (/root/canmv_k230_http_mp/src/canmv/port/core/mpthreadport.c:138)
```

#### 2.2.4 解决方案

1. **临时方案**：在`pthread_tls_stubs.c`中添加条件编译

   ```c
   #ifndef RTSMART_WEB_PORTABLE
   // 弱符号stub实现
   #endif
   ```

   - 这样在MicroPython构建（定义了`RTSMART_WEB_PORTABLE`）时不会编译这些stub

2. **最终方案**：删除`pthread_tls_stubs.c`文件
   - **原因**：用户明确要求删除，且该文件在MicroPython环境下不需要
   - **操作**：从项目中完全移除该文件

#### 2.2.5 验证结果

- **解决**：上电不再崩溃，MicroPython正常初始化

### 2.3 YOLO推流栈溢出问题（第三阶段）

#### 2.3.1 问题分析

- **症状**：HTTP服务器单独运行正常，但启动YOLO推流后仍崩溃
- **测试方法**：注释掉`main_rtsmart.py`中的`yolo.start_camera()`，HTTP服务器正常工作
- **推测原因**：
  1. MicroPython的`_thread.start_new_thread`使用默认栈大小（可能较小）
  2. YOLO推理和图像处理需要较大栈空间
  3. 多线程并发导致栈压力叠加

#### 2.3.2 解决方案：单循环架构

**A. 架构变更**

- **原架构**：使用`_thread.start_new_thread`创建独立线程运行YOLO循环
- **新架构**：所有逻辑在主线程单循环中顺序执行

**B. 新文件**：`k230_onboard_project/main_http_loop.py`

```python
def main():
    # 初始化HTTP服务器
    rtsmart_web.start_server()
    # 推荐：禁用 HTTP API 控制读取以避免额外的 socket 请求，并限制推帧率
    web = RTWebAdapter(quality=50, control_poll_interval_ms=5000, use_http_api_for_control=False, min_push_interval_ms=100)
    
    # 初始化Pipeline和YOLO
    pl = PipeLine(rgb888p_size=[640, 360], display_mode="lcd")
    pl.create()
    yolo = YOLOv5(...)
    
    # 单循环：所有逻辑在主线程执行
    while True:
        frame = pl.get_frame()
        
        # YOLO检测（如果启用）
        if detection_enabled:
            results = yolo.run(frame)
            yolo.draw_result(results, pl.osd_img)
        
        pl.show_image()
        
        # HTTP推流
        if stream_enabled:
            web.update_frame(frame)
        
        # 同步控制命令和统计信息
        ctrl = web.pull_control()
        web.update_stats_remote(...)
        
        gc.collect()
```

**C. 优势**

- 避免`_thread`的栈限制问题
- 简化线程同步，减少竞态条件
- 更好的资源控制和调试能力

#### 2.3.3 验证结果

- **部分解决**：不再出现栈溢出崩溃
- **新问题**：HTTP服务器可以接收请求，但MJPEG流显示"Waiting for frames..."

### 2.4 MJPEG流无数据问题（第四阶段）

#### 2.4.1 问题分析

- **症状**：HTTP服务器正常，但MJPEG流显示"Waiting for frames..."或"slot invalid"
- **原因**：`RTWebAdapter.update_frame()`被临时禁用（用于调试）

#### 2.4.2 解决方案

- **文件**：`k230_onboard_project/rtsmart_web_adapter.py`
- **修改**：恢复`update_frame()`的完整功能

  ```python
  def update_frame(self, image):
      if not self.use_c_server or image is None:
          return
      
      try:
          # 压缩图像为JPEG
          jpeg_bytes = image.compress(quality=self.quality)
          # 推送到C层
          import rtsmart_web
          rtsmart_web.push_frame(jpeg_bytes)
      except Exception as e:
          print("[RTWeb] ⚠️ 推帧失败:", e)
  ```

#### 2.4.3 验证结果

- **解决**：MJPEG流开始接收数据
- **新问题**：浏览器显示彩格图像（patterned image）而非实际视频流

### 2.5 图像格式问题（第五阶段）

#### 2.5.1 问题分析

- **症状**：浏览器显示彩格图像（类似OSD层），而非实际摄像头画面
- **原因**：
  1. 使用了`pl.osd_img`（OSD层）而非原始帧数据
  2. 图像格式转换不正确（NV12/YUV420SP → RGB565 → JPEG）

#### 2.5.2 解决方案

**A. 修改主循环使用原始帧**

- **文件**：`k230_onboard_project/main_http_loop.py`
- **修改**：

  ```python
  # 原代码
  web.update_frame(frame)  # frame可能是ndarray
  
  # 修改后
  web.update_frame(pl.cur_frame)  # 使用image.Image对象
  ```

**B. 修改YOLO控制器同时绘制到原始帧**

- **文件**：`k230_onboard_project/yolo_controller.py`（如果存在）
- **修改**：在检测结果绘制时，同时绘制到`pl.osd_img`和原始`frame`

**C. 图像格式转换处理**

- **文件**：`k230_onboard_project/rtsmart_web_adapter.py`
- **问题**：`PipeLine.get_frame()`返回的可能是`numpy.ndarray`（NV12格式），需要转换为`image.Image`
- **尝试方案**：添加`_ensure_image_obj()`方法处理格式转换

  ```python
  def _ensure_image_obj(self, src):
      if src is None:
          return None
      
      # 如果已经是image.Image对象，直接返回
      if hasattr(src, "compress"):
          return src
      
      # 处理numpy.ndarray（NV12或RGB888）
      if isinstance(src, np.ndarray):
          # NV12格式转换逻辑
          # ...
      
      return None
  ```

#### 2.5.3 最终解决方案（参考CanMV官方API）

**根据CanMV官方API文档**：<https://www.kendryte.com/k230_canmv/zh/main/zh/api/index.html>

1. **PipeLine图像对象说明**：
   - `pl.get_frame()`：返回`numpy.ndarray`（NV12或RGB888格式），**不是**`image.Image`对象
   - `pl.cur_frame`：PipeLine内部维护的当前帧`image.Image`对象（如果存在），格式为RGB565或RGB888
   - `pl.osd_img`：OSD层`image.Image`对象，包含绘制结果，格式为RGB565

2. **正确的图像获取方式**：
   - **优先使用**`pl.cur_frame`：原始摄像头画面，`image.Image`对象，可直接调用`compress()`
   - **回退到**`pl.osd_img`：包含检测结果绘制，也是`image.Image`对象
   - **避免使用**`pl.get_frame()`返回的`frame`：这是`ndarray`，需要复杂转换

3. **最终实现**（`main_http_loop.py`）：

   ```python
   if stream_enabled:
       try:
           # 根据CanMV API，优先使用cur_frame（image.Image对象）
           stream_img = None
           if hasattr(pl, 'cur_frame') and pl.cur_frame is not None:
               # 优先使用cur_frame（原始摄像头画面）
               stream_img = pl.cur_frame
           elif hasattr(pl, 'osd_img') and pl.osd_img is not None:
               # 回退到osd_img（包含检测结果绘制）
               stream_img = pl.osd_img
           
           if stream_img is not None:
               web.update_frame(stream_img)  # stream_img是image.Image对象
       except Exception as err:
           print("[HTTP] 推帧失败：", err)
   ```

4. **JPEG压缩处理**（`rtsmart_web_adapter.py`）：

   ```python
   def update_frame(self, image):
       # image必须是image.Image对象（有compress方法）
       if hasattr(image, 'compress'):
           jpeg_bytes = image.compress(quality=self.quality)
           rtsmart_web.push_frame(jpeg_bytes)
       else:
           # 不支持的类型，不进行复杂转换
           print("[RTWeb] ⚠️ Unsupported frame type: %s" % type(image))
   ```

5. **关键要点**：
   - ✅ **正确**：使用`pl.cur_frame`或`pl.osd_img`（都是`image.Image`对象）
   - ✅ **正确**：直接调用`image.compress(quality)`进行JPEG压缩
   - ❌ **错误**：使用`pl.get_frame()`返回的`ndarray`直接压缩
   - ❌ **错误**：尝试将`ndarray`转换为`image.Image`（复杂且容易出错）

#### 2.5.4 验证结果

- **解决**：使用`pl.cur_frame`或`pl.osd_img`获取`image.Image`对象
- **解决**：直接调用`compress()`方法进行JPEG压缩，无需格式转换
- **状态**：彩格问题应已解决（前提是`pl.cur_frame`或`pl.osd_img`包含正确的摄像头画面数据）
- **注意**：如果`pl.cur_frame`不存在或为None，会回退到`pl.osd_img`，此时显示的是包含检测结果绘制的画面

## 3. 关键文件修改记录

### 3.1 C层文件

#### `rtsmart_userapp/src/http_server.c`

- **修改1**：增加pthread栈大小定义

  ```c
  #define PTHREAD_STACK_SIZE (64 * 1024)  // 64KB
  ```

- **修改2**：显式设置pthread属性
  - 为`accept_thread`和`worker_threads`设置栈大小

#### `rtsmart_userapp/src/pthread_tls_stubs.c`

- **状态**：已删除
- **原因**：弱符号覆盖导致MicroPython TLS初始化失败

### 3.2 Python层文件

#### `k230_onboard_project/main_http_loop.py`

- **创建**：新的单循环架构脚本
- **关键特性**：
  - 不使用`_thread`
  - 主循环中顺序执行所有逻辑
  - 集成控制命令和统计信息同步

#### `k230_onboard_project/rtsmart_web_adapter.py`

- **修改1**：恢复`update_frame()`功能
- **修改2**：优化图像处理逻辑，仅接受`image.Image`对象或JPEG bytes
- **修改3**：添加调试日志输出（仅前几帧）
- **修改4**：移除复杂的ndarray转换逻辑，简化代码
- **关键实现**：

  ```python
  # 仅接受image.Image对象（有compress方法）或JPEG bytes
  if hasattr(image, 'compress'):
      jpeg_bytes = image.compress(quality=self.quality)
      rtsmart_web.push_frame(jpeg_bytes)
  elif isinstance(image, (bytes, bytearray)):
      rtsmart_web.push_frame(image)  # 直接推送JPEG bytes
  else:
      # 不支持的类型，不进行转换
      print("[RTWeb] ⚠️ Unsupported frame type")
  ```

## 4. 调试工具与方法

### 4.1 地址解析工具

- **工具**：`riscv64-unknown-linux-musl-addr2line`
- **位置**：`/root/.kendryte/k230_toolchains/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin/`
- **用法**：

  ```bash
  riscv64-unknown-linux-musl-addr2line \
    -e output/k230_canmv_lckfb_defconfig/canmv/micropython \
    -a -f <崩溃地址>
  ```

### 4.2 构建配置

- **未strip构建**：`make STRIP=:`（保留调试符号）
- **符号文件位置**：
  - `output/k230_canmv_lckfb_defconfig/canmv/micropython`
  - `output/k230_canmv_lckfb_defconfig/rtthread.elf`

### 4.3 测试方法

1. **最小化测试**：仅启动HTTP服务器，不启动YOLO
2. **逐步增加**：先启动HTTP，再启动摄像头，最后启动YOLO
3. **隔离测试**：注释可疑代码段，定位问题范围

## 5. 经验总结

### 5.1 栈大小配置

- **LWP主线程**：至少256KB（`0x40000`）
- **pthread工作线程**：至少64KB（`64 * 1024`）
- **MicroPython _thread**：避免使用，使用单循环架构

### 5.2 弱符号陷阱

- **问题**：弱符号可能意外覆盖库函数
- **解决**：在MicroPython构建中避免使用弱符号stub
- **检查**：确保所有符号都来自正确的库

### 5.3 架构选择

- **多线程**：在资源受限环境下容易导致栈溢出
- **单循环**：更稳定，但需要合理设计循环逻辑
- **建议**：对于嵌入式系统，优先考虑单循环架构

### 5.4 图像格式处理（CanMV API最佳实践）

- **问题**：不同API返回的图像格式可能不同
- **解决**：统一使用`image.Image`对象，避免直接处理`ndarray`
- **CanMV API说明**：
  - `PipeLine.get_frame()`返回`numpy.ndarray`（NV12或RGB888），**不是**`image.Image`
  - `PipeLine.cur_frame`是`image.Image`对象（如果存在），可直接调用`compress()`
  - `PipeLine.osd_img`是`image.Image`对象，包含OSD层绘制结果
- **推荐做法**：
  1. 优先使用`pl.cur_frame`获取原始摄像头画面
  2. 回退到`pl.osd_img`获取包含检测结果的画面
  3. 直接调用`image.compress(quality)`进行JPEG压缩
  4. **避免**将`ndarray`转换为`image.Image`（复杂且容易出错）
- **参考文档**：<https://www.kendryte.com/k230_canmv/zh/main/zh/api/index.html>

## 6. CanMV API代码检查与优化

### 6.1 代码检查结果

根据CanMV官方API文档（<https://www.kendryte.com/k230_canmv/zh/main/zh/api/index.html>），对Python代码进行了全面检查，发现并修复了以下问题：

#### 6.1.1 发现的问题

1. **`detection_manager.py`使用了错误的API方法名**
   - **问题**：使用了`image.compressed()`方法（不存在）
   - **正确**：应该使用`image.compress()`方法
   - **位置**：`detection_manager.py:88-90`

2. **`main_http_loop.py`中检测记录保存使用了ndarray**
   - **问题**：当`pl.cur_frame`不存在时，回退到使用`frame`（ndarray），但`detection_manager`需要`image.Image`对象
   - **影响**：可能导致保存失败或格式错误

3. **`rtsmart_web_adapter.py`中存在未使用的代码**
   - **问题**：`_ensure_image_obj()`方法未被使用，增加了代码复杂度

#### 6.1.2 已修复的优化

**A. 修复`detection_manager.py`的JPEG压缩方法**

```python
# 修复前（错误）
if hasattr(image, 'compressed'):
    jpeg_data = image.compressed(quality=85)  # ❌ 错误的方法名

# 修复后（正确）
if hasattr(image, 'compress'):
    jpeg_data = image.compress(quality=85)  # ✅ CanMV官方API
```

**B. 优化`main_http_loop.py`的图像获取逻辑**

```python
# 修复前
detection_manager.add_detection(
    image=pl.cur_frame if hasattr(pl, 'cur_frame') else frame,  # ❌ frame可能是ndarray
    ...
)

# 修复后
save_img = None
if hasattr(pl, 'cur_frame') and pl.cur_frame is not None:
    save_img = pl.cur_frame  # ✅ image.Image对象
elif hasattr(pl, 'osd_img') and pl.osd_img is not None:
    save_img = pl.osd_img  # ✅ image.Image对象

if save_img is not None:
    detection_manager.add_detection(image=save_img, ...)  # ✅ 确保是image.Image
```

**C. 简化推流逻辑**

```python
# 优化前：冗长的条件判断和警告逻辑
stream_img = None
if hasattr(pl, 'cur_frame') and pl.cur_frame is not None:
    stream_img = pl.cur_frame
elif hasattr(pl, 'osd_img') and pl.osd_img is not None:
    stream_img = pl.osd_img
else:
    if total_frames % 30 == 0:
        print("[HTTP] ⚠️ 无法获取有效的图像对象用于推流")
    stream_img = None

# 优化后：简洁清晰
stream_img = None
if hasattr(pl, 'cur_frame') and pl.cur_frame is not None:
    stream_img = pl.cur_frame
elif hasattr(pl, 'osd_img') and pl.osd_img is not None:
    stream_img = pl.osd_img

if stream_img is not None:
    web.update_frame(stream_img)
elif total_frames % 30 == 0:
    print("[HTTP] ⚠️ 无法获取有效的image.Image对象用于推流")
```

**D. 删除未使用的代码**

- 删除了`rtsmart_web_adapter.py`中的`_ensure_image_obj()`方法（未被调用）

### 6.2 CanMV API使用规范总结

#### 6.2.1 图像对象获取

| API | 返回类型 | 用途 | 推荐度 |
|-----|---------|------|--------|
| `pl.get_frame()` | `numpy.ndarray` | 获取原始帧数据（NV12/RGB888） | ⚠️ 不用于JPEG压缩 |
| `pl.cur_frame` | `image.Image` | 当前帧图像对象（RGB565/RGB888） | ✅ 优先使用 |
| `pl.osd_img` | `image.Image` | OSD层图像（包含绘制结果） | ✅ 备选方案 |

#### 6.2.2 JPEG压缩API

```python
# ✅ 正确：使用compress()方法
jpeg_bytes = image.compress(quality=85)  # quality: 1-100

# ❌ 错误：compressed()方法不存在
jpeg_bytes = image.compressed(quality=85)  # 会报错
```

#### 6.2.3 图像保存API

```python
# ✅ 正确：先压缩再保存
jpeg_data = image.compress(quality=85)
with open(filepath, 'wb') as f:
    f.write(bytes(jpeg_data))

# ⚠️ 注意：CanMV的image.Image对象没有save()方法
# 不要使用 image.save(filepath, quality=85)  # 可能不存在
```

### 6.3 代码优化效果

1. **正确性**：
   - ✅ 修复了API方法名错误（`compressed()` → `compress()`）
   - ✅ 确保所有图像处理都使用`image.Image`对象
   - ✅ 避免了ndarray和Image对象混用的问题

2. **可维护性**：
   - ✅ 删除了未使用的代码
   - ✅ 简化了条件判断逻辑
   - ✅ 统一了图像获取方式

3. **性能**：
   - ✅ 减少了不必要的类型检查和转换
   - ✅ 优化了错误处理逻辑

## 7. 待解决问题

### 7.1 当前状态

- **图像获取**：已修复，从`pl.get_frame()`的ndarray转换为`image.Image`对象
- **JPEG压缩**：已修复，统一使用`image.compress()`方法
- **代码优化**：已完成，删除了错误API调用和未使用代码
- **彩格问题**：正在修复中，根据OpenMV官方API实现ndarray到Image的转换
- **待验证**：实际运行测试，确认浏览器显示的是真实摄像头画面而非彩格

### 7.2 最新修复（2025-11-25）

#### 7.2.1 问题：`pl.osd_img`只包含OSD绘制层，显示彩格

**现象**：
- 使用`pl.osd_img`推流时，网页端显示彩格（彩色网格图案）
- `pl.osd_img`只包含OSD绘制层，不包含原始摄像头画面

**根本原因**：
- `pl.osd_img`是用于绘制检测结果的OSD层，可能不包含完整的原始图像数据
- 需要从`pl.get_frame()`返回的RGBP888格式ndarray创建`image.Image`对象

#### 7.2.2 解决方案：根据OpenMV官方API实现ndarray到Image转换

**参考文档**：<https://docs.openmv.io/library/omv.image.html>

**关键发现**：
- `image.Image()`构造函数**不接受**ndarray作为参数
- 需要从bytes/bytearray创建：`image.Image(data, width=w, height=h, format=image.RGB888)`

**实现步骤**：

1. **获取RGBP888格式的ndarray**：
   ```python
   frame = pl.get_frame()  # 返回 (3, H, W) 格式的ndarray
   ```

2. **转换为RGB888格式**：
   ```python
   frame_rgb888 = frame.transpose(1, 2, 0)  # (3, H, W) -> (H, W, 3)
   ```

3. **转换为bytearray**：
   ```python
   # 方法1：尝试使用tobytes()（如果ndarray支持）
   if hasattr(frame_rgb888, 'tobytes'):
       img_bytes = bytearray(frame_rgb888.tobytes())
   else:
       # 方法2：手动转换（兼容性更好，但较慢）
       img_bytes = bytearray(w * h * 3)
       idx = 0
       for y in range(h):
           for x in range(w):
               img_bytes[idx] = int(frame_rgb888[y, x, 0])  # R
               img_bytes[idx + 1] = int(frame_rgb888[y, x, 1])  # G
               img_bytes[idx + 2] = int(frame_rgb888[y, x, 2])  # B
               idx += 3
   ```

4. **创建image.Image对象**：
   ```python
   stream_img = image.Image(img_bytes, width=w, height=h, format=image.RGB888)
   ```

**完整代码**（`main_http_loop.py`）：

```python
if stream_enabled:
    try:
        import image
        stream_img = None
        
        # 优先尝试从frame转换（包含原始摄像头画面）
        frame = pl.get_frame()  # RGBP888格式 (3, H, W)
        if frame is not None and len(frame.shape) == 3 and frame.shape[0] == 3:
            try:
                h, w = frame.shape[1], frame.shape[2]
                # RGBP888格式：分离的RGB平面，形状为(3, H, W)
                # 使用transpose转换为(H, W, 3)格式（RGB888格式）
                frame_rgb888 = frame.transpose(1, 2, 0)
                
                # 将ndarray转换为bytearray
                try:
                    if hasattr(frame_rgb888, 'tobytes'):
                        img_bytes = bytearray(frame_rgb888.tobytes())
                    else:
                        raise AttributeError("ndarray不支持tobytes()方法")
                except Exception as e:
                    # 手动转换（兼容性更好，但较慢）
                    img_bytes = bytearray(w * h * 3)
                    idx = 0
                    for y in range(h):
                        for x in range(w):
                            img_bytes[idx] = int(frame_rgb888[y, x, 0])  # R
                            img_bytes[idx + 1] = int(frame_rgb888[y, x, 1])  # G
                            img_bytes[idx + 2] = int(frame_rgb888[y, x, 2])  # B
                            idx += 3
                
                # 使用OpenMV API创建image.Image对象
                stream_img = image.Image(img_bytes, width=w, height=h, format=image.RGB888)
            except Exception as conv_err:
                print("[HTTP] ⚠️ frame转Image失败:", conv_err)
        
        # 如果转换失败，回退到osd_img（虽然可能只包含绘制结果）
        if stream_img is None and hasattr(pl, 'osd_img') and pl.osd_img is not None:
            stream_img = pl.osd_img
        
        if stream_img is not None:
            web.update_frame(stream_img)
    except Exception as err:
        print("[HTTP] 推帧失败：", err)
```

#### 7.2.3 关键要点

- ✅ **正确**：使用`image.Image(data, width=w, height=h, format=image.RGB888)`从bytearray创建
- ✅ **正确**：将RGBP888 (3, H, W) 转换为RGB888 (H, W, 3)，再转换为bytearray
- ❌ **错误**：直接使用`image.Image(ndarray)`（构造函数不接受ndarray）
- ❌ **错误**：使用`pl.osd_img`（只包含OSD绘制层，不包含原始图像）

#### 7.2.4 待验证

- 实际运行测试，确认转换后的图像能正确显示在浏览器中
- 性能测试：手动转换可能较慢，需要优化或使用更高效的转换方法

### 7.3 潜在优化

- **HTTP API轮询**：当前使用HTTP API同步控制信息，可能产生连接超时
- **图像压缩**：JPEG压缩质量可调，需要平衡质量和性能
- **内存管理**：单循环中需要合理使用`gc.collect()`
- **图像格式转换性能**：手动转换ndarray到bytearray可能较慢，需要优化（使用numpy的tobytes()或C扩展）

## 8. 相关文档

- `docs/SDK_INTEGRATION_HTTP_MICROPY.md`：HTTP服务器集成到MicroPython的详细说明
- `docs/SDK_INTEGRATION_MODIFICATIONS.md`：SDK修改记录
- CanMV官方API文档：<https://www.kendryte.com/k230_canmv/zh/main/zh/api/index.html>

## 9. 时间线

- **2025-11-24**：初始问题报告，开始调试栈溢出
- **2025-11-24**：发现并解决`pthread_tls_stubs.c`问题
- **2025-11-25**：改为单循环架构，解决YOLO推流崩溃
- **2025-11-25**：修复MJPEG流无数据问题
- **2025-11-25**：开始处理图像格式问题（进行中）
- **2025-11-25**：根据CanMV官方API，修复图像获取和JPEG压缩逻辑，使用`pl.cur_frame`或`pl.osd_img`
- **2025-11-25**：代码检查与优化，修复`compressed()`→`compress()`API错误，优化图像获取逻辑，删除未使用代码
- **2025-11-25**：发现`pl.osd_img`只包含OSD绘制层，显示彩格；根据OpenMV官方API实现ndarray到Image的转换（使用`image.Image(data, width, height, format)`）

---

**文档版本**：1.1  
**最后更新**：2025-11-25  
**维护者**：开发团队

---

## 10. 最新更新记录（2025-11-25）

### 10.1 彩格问题修复

**问题**：使用`pl.osd_img`推流时，网页端显示彩格（彩色网格图案）

**原因**：`pl.osd_img`只包含OSD绘制层，不包含原始摄像头画面

**解决方案**：
1. 从`pl.get_frame()`获取RGBP888格式的ndarray (3, H, W)
2. 转换为RGB888格式 (H, W, 3)
3. 转换为bytearray
4. 使用`image.Image(img_bytes, width=w, height=h, format=image.RGB888)`创建Image对象

**参考文档**：
- OpenMV官方API：<https://docs.openmv.io/library/omv.image.html>
- CanMV PipeLine API：<https://www.kendryte.com/k230_canmv/zh/main/zh/api/aidemo/PipeLine%20%E6%A8%A1%E5%9D%97%20API%20%E6%89%8B%E5%86%8C.html>

**状态**：已实现，待验证
