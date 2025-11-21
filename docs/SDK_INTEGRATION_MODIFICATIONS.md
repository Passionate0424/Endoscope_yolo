# CanMV SDK 集成修改说明

本文档详细说明在官方 CanMV SDK 源码基础上所做的修改，以集成 RT-Smart Web 服务器和 MicroPython 绑定模块。

## 修改概览

### 1. 代码文件复制

将 `rtsmart_userapp` 目录下的代码复制到 SDK 的两个位置：

#### 位置 1: RT-Smart 内核应用目录
```bash
src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/
├── http_service.c          # HTTP 服务器启动服务
├── include/                # 头文件目录
│   ├── config.h
│   ├── frame_buffer.h
│   ├── http_handler.h
│   ├── http_server.h
│   ├── static_assets.h
│   └── web_state.h
├── src/                    # 源文件目录
│   ├── frame_buffer.c      # 帧缓冲区实现
│   ├── http_handler.c      # HTTP 请求处理
│   ├── http_server.c       # HTTP 服务器核心
│   ├── static_assets.c     # 静态资源
│   └── web_state.c         # Web 状态管理
└── SConscript              # 构建脚本（新增）
```

#### 位置 2: MicroPython 模块目录
```bash
src/canmv/port/modules/
└── rtsmart_web_module.c    # MicroPython C 绑定模块
```

---

## 2. RT-Smart 内核构建系统修改

### 2.1 创建 SConscript 文件

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/SConscript`

```python
from building import *

cwd = GetCurrentDir()
CPPPATH = [cwd, cwd + "/include"]

# HTTP 服务器源文件
src = Glob("http_service.c")
src += Glob("src/*.c")

group = DefineGroup("app_http_server", src, depend = [""], CPPPATH = CPPPATH)

objs = [group]

# 递归处理子目录（如果有）
list = os.listdir(cwd)
for item in list:
    if os.path.isdir(os.path.join(cwd, item)) and os.path.isfile(os.path.join(cwd, item, "SConscript")):
        objs = objs + SConscript(os.path.join(item, "SConscript"))

Return("objs")
```

**作用**: 定义 HTTP 服务器组件的编译规则，包含所有 C 源文件和头文件路径。

### 2.2 修改主 SConstruct

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/SConstruct`

**修改位置**: 在 `PrepareBuilding` 调用之后添加：

```python
objs = PrepareBuilding(env, RTT_ROOT, has_libcpu = True)

# 添加 app_http_server 组件
if os.path.exists("app_http_server/SConscript"):
    objs = objs + SConscript("app_http_server/SConscript")
```

**作用**: 显式将 `app_http_server` 组件添加到 RT-Smart 内核构建中。

---

## 3. MicroPython 构建系统修改

### 3.1 修改 Makefile - 添加头文件路径

**文件**: `src/canmv/port/Makefile`

**添加的包含路径**:
```makefile
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/components/finsh
```

**作用**: 让 MicroPython 编译时能找到 `web_state.h`、`frame_buffer.h` 等头文件。

### 3.2 修改 Makefile - 添加编译标志

**文件**: `src/canmv/port/Makefile`

**添加的编译标志**:
```makefile
CFLAGS += -DRTSMART_WEB_PORTABLE
```

**作用**: 定义 `RTSMART_WEB_PORTABLE` 宏，启用 MicroPython 环境下的兼容层实现。

### 3.3 修改 Makefile - 添加源文件

**文件**: `src/canmv/port/Makefile`

**添加的源文件**:
```makefile
CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c
CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c
```

**作用**: 将 `frame_buffer.c` 和 `web_state.c` 编译进 MicroPython 可执行文件。

**注意**: `rtsmart_web_module.c` 通过 `CANMV_SRC_C += $(wildcard modules/*.c)` 自动包含。

---

## 4. 源代码兼容性修改

### 4.1 头文件兼容层

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/include/web_state.h`

**修改**: 添加条件编译，支持 MicroPython 环境：

```c
#ifndef RTSMART_WEB_PORTABLE
#ifndef HAVE_SIGVAL
#define HAVE_SIGVAL
#endif
#ifndef HAVE_SIGEVENT
#define HAVE_SIGEVENT
#endif
#ifndef HAVE_SIGINFO
#define HAVE_SIGINFO
#endif
#include <rtthread.h>
#else
#include <stdbool.h>
#endif

#ifdef RTSMART_WEB_PORTABLE
typedef bool rt_bool_t;
#ifndef RT_TRUE
#define RT_TRUE true
#endif
#ifndef RT_FALSE
#define RT_FALSE false
#endif
#ifndef RT_WAITING_FOREVER
#define RT_WAITING_FOREVER (-1)
#endif
#endif
```

**作用**: 
- 在 RT-Smart 环境下使用 RT-Thread API
- 在 MicroPython 环境下使用标准 C 库和 pthread

### 4.2 源文件兼容层

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c`

**修改**: 添加条件编译的兼容实现：

```c
#ifndef RTSMART_WEB_PORTABLE
// RT-Smart 环境：使用 RT-Thread API
#include <rtthread.h>
#else
// MicroPython 环境：使用 pthread 和标准库
#include "py/mphal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef pthread_mutex_t rt_mutex_t;
typedef int32_t rt_int32_t;
typedef uint32_t rt_tick_t;

// 兼容函数实现
static inline void rt_mutex_init(rt_mutex_t *m, const char *name, int flag) {
    (void)name; (void)flag;
    pthread_mutex_init(m, NULL);
}
// ... 其他兼容函数
#endif
```

**作用**: 让同一份代码可以在 RT-Smart 和 MicroPython 两种环境下编译。

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c`

**修改**: 类似的兼容层实现。

### 4.3 MicroPython 模块兼容

**文件**: `src/canmv/port/modules/rtsmart_web_module.c`

**修改**: 条件包含 RT-Thread 头文件：

```c
#ifndef RTSMART_WEB_PORTABLE
#ifndef HAVE_SIGVAL
#define HAVE_SIGVAL
#endif
// ... 信号类型保护
#include <rtthread.h>
#else
#include <stdio.h>
#endif
```

**作用**: 避免在 MicroPython 环境下引入 RT-Thread 头文件导致的类型冲突。

---

## 5. 编译结果验证

### 5.1 RT-Smart 内核验证

编译后的 `rtthread.bin` 应包含以下符号：
- `http_server_start`
- `http_server_stop`
- `http_server_is_running`
- `__cmd_http_start` (MSH 命令)

验证命令：
```bash
strings output/.../rtthread.bin | grep -E "(http_server|http_start|HTTPService)"
```

### 5.2 MicroPython 验证

编译后的 `micropython` 可执行文件应包含以下 API：
- `rtsmart_web_get_control`
- `rtsmart_web_set_runtime`
- `rtsmart_web_set_stats`
- `rtsmart_web_add_record`
- `rtsmart_web_delete_record`
- `rtsmart_web_clear_records`
- `rtsmart_web_get_stats`
- `rtsmart_web_push_frame`
- `rtsmart_web_is_ready`

验证命令：
```bash
strings output/.../micropython | grep rtsmart_web
```

---

## 6. 修改文件清单

### 新增文件
1. `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/SConscript`
2. `src/canmv/port/modules/rtsmart_web_module.c`

### 修改文件
1. `src/rtsmart/rtsmart/kernel/bsp/maix3/SConstruct` - 添加 app_http_server 组件
2. `src/canmv/port/Makefile` - 添加头文件路径、编译标志、源文件
3. `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/include/web_state.h` - 添加兼容层
4. `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c` - 添加兼容层
5. `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c` - 添加兼容层
6. `src/canmv/port/modules/rtsmart_web_module.c` - 添加条件编译

### 复制的文件（从 rtsmart_userapp）
- `app_http_server/http_service.c`
- `app_http_server/include/*.h`
- `app_http_server/src/*.c`
- `modules/rtsmart_web_module.c`

---

## 7. 架构说明

### 7.1 双环境支持

```
┌─────────────────────────────────────────┐
│      RT-Smart 内核（大核）               │
│  - http_service.c (启动服务)            │
│  - http_server.c (HTTP 服务器)         │
│  - http_handler.c (请求处理)           │
│  - frame_buffer.c (RT-Thread 版本)     │
│  - web_state.c (RT-Thread 版本)        │
└─────────────────────────────────────────┘
              ↑ 共享内存/IPC
┌─────────────────────────────────────────┐
│   MicroPython 运行时（小核）            │
│  - rtsmart_web_module.c (C 绑定)       │
│  - frame_buffer.c (pthread 版本)       │
│  - web_state.c (pthread 版本)          │
│  - Python 业务逻辑                      │
└─────────────────────────────────────────┘
```

### 7.2 兼容层设计

通过 `RTSMART_WEB_PORTABLE` 宏实现同一份代码在两种环境下的编译：

- **RT-Smart 环境**: 使用 RT-Thread API (`rt_mutex_t`, `rt_kprintf`, `rt_malloc` 等)
- **MicroPython 环境**: 使用 POSIX/pthread API (`pthread_mutex_t`, `printf`, `malloc` 等)

---

## 8. 使用方法

### 8.1 烧录新镜像

使用新生成的镜像文件：
```
build/canmv_firmware/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img
```

### 8.2 启动 HTTP 服务器

在 RT-Smart 串口（大核）输入：
```bash
msh />http_start
[HTTPService] ✅ HTTP 服务器已启动在 0.0.0.0:8080
```

### 8.3 Python 层使用

在 MicroPython 环境（小核）中：
```python
import rtsmart_web

# 推送帧
rtsmart_web.push_frame(jpeg_bytes)

# 获取控制信息
control = rtsmart_web.get_control()

# 设置运行时参数
rtsmart_web.set_runtime(camera_running=True, detection_enabled=True, confidence=0.5)

# 获取统计信息
stats = rtsmart_web.get_stats()
```

---

## 9. 注意事项

1. **信号类型冲突**: 通过 `HAVE_SIGVAL`、`HAVE_SIGEVENT`、`HAVE_SIGINFO` 宏避免 RT-Thread 和 musl libc 的信号类型定义冲突。

2. **互斥锁类型**: 
   - RT-Smart: `struct rt_mutex`
   - MicroPython: `pthread_mutex_t`

3. **内存管理**:
   - RT-Smart: `rt_malloc` / `rt_free`
   - MicroPython: `malloc` / `free`

4. **时间获取**:
   - RT-Smart: `rt_tick_get_millisecond()`
   - MicroPython: `mp_hal_ticks_ms()`

---

## 10. 后续维护

如果需要更新代码：

1. **更新 RT-Smart 层代码**: 修改 `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/` 下的文件
2. **更新 MicroPython 层代码**: 修改 `src/canmv/port/modules/rtsmart_web_module.c`
3. **重新编译**: `cd /root/canmv_k230_clean && make clean && make`
4. **复制镜像**: 将新镜像复制到 `build/canmv_firmware/`

---

## 总结

通过以上修改，我们成功将 RT-Smart Web 服务器集成到官方 CanMV SDK 中，实现了：

✅ **RT-Smart 内核层**: HTTP 服务器作为内核组件编译，可通过 MSH 命令启动  
✅ **MicroPython 层**: C 绑定模块编译进 Micropython，提供完整的 Python API  
✅ **双环境兼容**: 同一份核心代码（frame_buffer、web_state）可在两种环境下编译  
✅ **完整功能**: 支持帧推送、状态管理、控制接口、统计信息等所有功能

现在可以在板子上同时使用 C 层的 HTTP 服务器和 Python 层的 YOLO 检测功能了！

