# CanMV SDK 集成修改说明

本文档详细说明在官方 CanMV SDK 源码基础上所做的修改，以集成 RT-Smart Web 服务器和 MicroPython 绑定模块。

**重要架构说明**: 在 K230 CanMV 固件中，**只开启大核运行 RT-Smart 操作系统**，小核并不运行。MicroPython 是运行在 RT-Smart 上的一个应用程序，而非运行在小核上。HTTP 服务器作为 RT-Smart 内核组件运行，MicroPython 通过 C 绑定模块与 HTTP 服务器通信。

## 修改概览

### 1. 代码文件复制

将 `rtsmart_userapp` 目录下的代码复制到 SDK 的两个位置：

#### 位置 1: RT-Smart 内核组件目录（编译进 rtthread.bin）

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

#### 位置 2: MicroPython 应用模块目录（编译进 micropython 可执行文件）

```bash
src/canmv/port/modules/
└── rtsmart_web_module.c    # MicroPython C 绑定模块
```

---

## 2. 完整构建过程

### 2.1 初始化 SDK 环境

在 WSL 环境中，首先创建干净的工作目录并初始化 CanMV SDK：

```bash
# 创建新的工作目录
mkdir -p ~/canmv_k230_clean && cd ~/canmv_k230_clean

# 使用 Gitee 初始化 repo（国内用户推荐）
repo init -u git@gitee.com:canmv-k230/manifest.git -b master \
    --repo-url=git@gitee.com:canmv-k230/git-repo.git \
    --repo-branch stable

# 同步代码（需要配置 SSH 密钥）
repo sync
```

**注意**: 如果使用 HTTPS 或遇到 SSH 密钥问题，可以使用：

```bash
repo init -u https://gitee.com/canmv-k230/manifest.git -b master \
    --repo-url=https://gitee.com/canmv-k230/git-repo.git \
    --repo-branch stable
```

### 2.2 生成静态资源 .inc 文件

在复制代码之前，需要先将前端 HTML/JS 文件转换为 C 数组格式（.inc 文件），这些文件会被编译进固件。

#### 2.2.1 静态资源生成脚本

项目提供了自动生成脚本：`rtsmart_userapp/scripts/generate_static_assets.py`

**脚本功能**：

- 读取 `k230_onboard_project/static/` 目录下的 HTML/JS 文件
- 将文件内容转换为 C 数组格式（十六进制字节数组）
- 生成 `.inc` 文件到 `rtsmart_userapp/src/` 目录

**生成的文件**：

- `index_html.inc` - HTML 页面（包含 `STATIC_INDEX_HTML_DATA` 数组）
- `app_js.inc` - JavaScript 代码（包含 `STATIC_APP_JS_DATA` 数组）

#### 2.2.2 使用方法

在项目根目录执行：

```bash
# Windows PowerShell 或 WSL
cd E:\project\Endoscope_yolo
python rtsmart_userapp/scripts/generate_static_assets.py
```

**输出示例**：

```text
[OK] Generated: E:\project\Endoscope_yolo\rtsmart_userapp\src\index_html.inc (9775 bytes)
[OK] Generated: E:\project\Endoscope_yolo\rtsmart_userapp\src\app_js.inc (25165 bytes)

[SUCCESS] Generated 2 files

[INFO] Next steps:
   1. Recompile C layer code
   2. Reflash firmware
```

#### 2.2.3 工作流程

```text
1. 修改前端文件
   k230_onboard_project/static/app.js
   k230_onboard_project/static/index.html
        ↓
2. 运行生成脚本
   python rtsmart_userapp/scripts/generate_static_assets.py
        ↓
3. 生成 .inc 文件
   rtsmart_userapp/src/index_html.inc
   rtsmart_userapp/src/app_js.inc
        ↓
4. 复制到 SDK（见 2.3）
        ↓
5. 编译进固件
```

#### 2.2.4 脚本实现原理

生成脚本的工作原理：

1. **读取源文件**：以二进制模式读取 HTML/JS 文件，确保正确处理所有字符（包括中文、特殊符号等）
2. **转换为 C 数组**：将每个字节转换为十六进制格式（`0xXX`）
3. **格式化输出**：每行 12 个字节，便于阅读和编译
4. **生成变量**：
   - 数组变量：`STATIC_INDEX_HTML_DATA[]` 和 `STATIC_APP_JS_DATA[]`
   - 长度变量：`STATIC_INDEX_HTML_LEN` 和 `STATIC_APP_JS_LEN`

**生成的 .inc 文件格式示例**：

```c
const unsigned char STATIC_APP_JS_DATA[] = {
  0x2f, 0x2f, 0x20, 0xe5, 0x86, 0x85, 0xe7, 0xaa, 0xa5, 0xe9, 0x95, 0x9c,
  0xe6, 0xa3, 0x80, 0xe6, 0xb5, 0x8b, 0xe5, 0xb9, 0xb3, 0xe5, 0x8f, 0xb0,
  // ... 更多字节
};
const unsigned int STATIC_APP_JS_LEN = 25165;
```

这些 `.inc` 文件会被 `static_assets.c` 包含，编译进 RT-Smart 内核。

#### 2.2.5 重要说明

- **不需要手动将 HTML/JS 放到 K230 设备**：这些文件会被编译进固件，HTTP 服务器会直接从内存中提供这些静态资源
- **修改前端代码后必须重新生成**：每次修改 `app.js` 或 `index.html` 后，都需要运行生成脚本并重新编译固件
- **浏览器缓存**：修改后需要在浏览器中硬刷新（`Ctrl + Shift + R`）才能看到最新版本
- **console.log 输出位置**：`app.js` 中的 `console.log()` 输出显示在**浏览器开发者工具控制台**中，不会出现在 K230 串口或 C 层日志中

---

### 2.3 复制代码文件

将项目代码（包括生成的 .inc 文件）复制到 SDK 的相应位置：

```bash
# 复制到 RT-Smart 内核应用目录（包含 .inc 文件）
rsync -av --delete /mnt/e/project/Endoscope_yolo/rtsmart_userapp/ \
    /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/

# 复制到 MicroPython 模块目录
cp /mnt/e/project/Endoscope_yolo/rtsmart_userapp/micropython_binding/rtsmart_web_module.c \
    /root/canmv_k230_clean/src/canmv/port/modules/
```

**注意**：确保在复制之前已经运行了 `generate_static_assets.py` 生成最新的 .inc 文件。

### 2.4 创建 SConscript 构建脚本

为 HTTP 服务器创建 RT-Smart 构建脚本：

```bash
cat > /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/SConscript << 'EOF'
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
EOF
```

### 2.4 修改构建配置文件

#### 修改 RT-Smart SConstruct

```bash
cd /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3

# 使用 Python 脚本修改 SConstruct
python3 << 'PY'
from pathlib import Path
path = Path("SConstruct")
text = path.read_text()

old = "objs = PrepareBuilding(env, RTT_ROOT, has_libcpu = True)"
new = """objs = PrepareBuilding(env, RTT_ROOT, has_libcpu = True)

# 添加 app_http_server 组件
if os.path.exists("app_http_server/SConscript"):
    objs = objs + SConscript("app_http_server/SConscript")"""

text = text.replace(old, new, 1)
path.write_text(text)
print("SConstruct 已更新")
PY
```

#### 修改 MicroPython Makefile

```bash
cd /root/canmv_k230_clean/src/canmv/port

# 添加头文件路径
python3 << 'PY'
from pathlib import Path
path = Path("Makefile")
text = path.read_text()

# 在 INC 部分添加
old = "INC += -I$(SDK_RTSMART_SRC_DIR)/mpp/middleware/src/mp4_format/include\n\nINC += -I$(TOP)"
new = """INC += -I$(SDK_RTSMART_SRC_DIR)/mpp/middleware/src/mp4_format/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/components/finsh

INC += -I$(TOP)"""

text = text.replace(old, new, 1)
path.write_text(text)
print("Makefile INC 已更新")
PY

# 添加编译标志
python3 << 'PY'
from pathlib import Path
path = Path("Makefile")
text = path.read_text()

old = "CFLAGS += -g -gdwarf-2\n\nCFLAGS += -fopenmp"
new = "CFLAGS += -g -gdwarf-2\nCFLAGS += -DRTSMART_WEB_PORTABLE\n\nCFLAGS += -fopenmp"

text = text.replace(old, new, 1)
path.write_text(text)
print("Makefile CFLAGS 已更新")
PY

# 添加源文件
python3 << 'PY'
from pathlib import Path
path = Path("Makefile")
text = path.read_text()

marker = "CANMV_SRC_C += $(wildcard modules/*.c)\n"
addition = marker + """CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c
CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c
"""

text = text.replace(marker, addition, 1)
path.write_text(text)
print("Makefile 源文件已更新")
PY
```

### 2.5 添加源代码兼容层

#### 修改 web_state.h

```bash
cd /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/include

python3 << 'PY'
from pathlib import Path
path = Path("web_state.h")
text = path.read_text()

old = "#include <rtthread.h>\n#include <stdint.h>"
new = """#ifndef RTSMART_WEB_PORTABLE
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
#include <stdint.h>

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
#endif"""

text = text.replace(old, new, 1)
path.write_text(text)
print("web_state.h 已更新")
PY
```

#### 修改 frame_buffer.c 和 web_state.c

```bash
cd /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src

# 为 frame_buffer.c 添加兼容层
python3 << 'PY'
from pathlib import Path
path = Path("frame_buffer.c")
text = path.read_text()

old = """#include "frame_buffer.h"
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
#include <string.h>

extern rt_tick_t rt_tick_get_millisecond(void);

// 全局缓冲区实例
static frame_buffer_t g_frame_buffer = {0};
static struct rt_mutex g_buffer_mutex;"""

new = """#include "frame_buffer.h"

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
#include "py/mphal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef pthread_mutex_t rt_mutex_t;
typedef int32_t rt_int32_t;
typedef uint32_t rt_tick_t;
#define RT_IPC_FLAG_PRIO 0
#define RT_WAITING_FOREVER (-1)
#define rt_kprintf printf
#define rt_malloc malloc
#define rt_free free
static inline void rt_mutex_init(rt_mutex_t *m, const char *name, int flag) {
    (void)name; (void)flag;
    pthread_mutex_init(m, NULL);
}
static inline void rt_mutex_detach(rt_mutex_t *m) {
    pthread_mutex_destroy(m);
}
static inline int rt_mutex_take(rt_mutex_t *m, int timeout) {
    (void)timeout;
    return pthread_mutex_lock(m);
}
static inline void rt_mutex_release(rt_mutex_t *m) {
    pthread_mutex_unlock(m);
}
static inline rt_tick_t rt_tick_get_millisecond(void) {
    return (rt_tick_t)mp_hal_ticks_ms();
}
#endif
#include <string.h>

// 全局缓冲区实例
static frame_buffer_t g_frame_buffer = {0};
#ifndef RTSMART_WEB_PORTABLE
static struct rt_mutex g_buffer_mutex;
#else
static rt_mutex_t g_buffer_mutex;
#endif"""

text = text.replace(old, new, 1)
path.write_text(text)
print("frame_buffer.c 已更新")
PY

# 为 web_state.c 添加兼容层
python3 << 'PY'
from pathlib import Path
path = Path("web_state.c")
text = path.read_text()

old = """#include "web_state.h"

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
#include <stddef.h>
#include <string.h>

typedef struct
{
    struct rt_mutex lock;"""

new = """#include "web_state.h"

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
#include "py/mphal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef pthread_mutex_t rt_mutex_t;
#define rt_mutex_init(m, name, flag) pthread_mutex_init((m), NULL)
#define rt_mutex_detach(m) pthread_mutex_destroy((m))
static inline int rt_mutex_take(rt_mutex_t *m, int timeout) { (void)timeout; return pthread_mutex_lock(m); }
static inline void rt_mutex_release(rt_mutex_t *m) { pthread_mutex_unlock(m); }
#define rt_kprintf printf
#define rt_snprintf snprintf
#endif
#include <stddef.h>
#include <string.h>

typedef struct
{
#ifndef RTSMART_WEB_PORTABLE
    struct rt_mutex lock;
#else
    rt_mutex_t lock;
#endif"""

text = text.replace(old, new, 1)
path.write_text(text)
print("web_state.c 已更新")
PY
```

#### 修改 rtsmart_web_module.c

```bash
cd /root/canmv_k230_clean/src/canmv/port/modules

python3 << 'PY'
from pathlib import Path
path = Path("rtsmart_web_module.c")
text = path.read_text()

old = """#include "py/mperrno.h"

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

#include "frame_buffer.h"
#include "web_state.h"
#include "config.h\""""

new = """#include "py/mperrno.h"

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
#include <stdio.h>
#endif

#include "frame_buffer.h"
#include "web_state.h"
#include "config.h\""""

text = text.replace(old, new, 1)
path.write_text(text)
print("rtsmart_web_module.c 已更新")
PY
```

### 2.6 配置和编译

```bash
cd /root/canmv_k230_clean

# 列出可用配置
make list-def

# 配置为 LCKFB 板型
make k230_canmv_lckfb_defconfig

# 清理之前的编译产物（可选）
make clean

# 执行完整编译（首次编译可能需要 30-60 分钟）
time make

# 或者只编译 RT-Smart 部分
cd src/rtsmart && scons

# 或者只编译 MicroPython 部分
cd src/canmv/port && make
```

### 2.7 验证编译结果

```bash
cd /root/canmv_k230_clean

# 验证 RT-Smart 内核包含 HTTP 服务器
strings output/k230_canmv_lckfb_defconfig/images/rtsmart/rtthread.bin | \
    grep -E "(http_server|http_start|HTTPService)"

# 预期输出示例：
# HTTP Server Status:
# [HTTP] Server listening on port %d
# [HTTP] Server started successfully
# __cmd_http_start

# 验证 MicroPython 包含 rtsmart_web 模块
strings output/k230_canmv_lckfb_defconfig/canmv/micropython | \
    grep rtsmart_web

# 预期输出示例：
# rtsmart_web
# .text.rtsmart_web_is_ready
# .text.rtsmart_web_get_stats
# .text.rtsmart_web_clear_records
# .text.rtsmart_web_delete_record
# .text.rtsmart_web_add_record
# .text.rtsmart_web_set_stats
# .text.rtsmart_web_get_control
# .text.rtsmart_web_push_frame
# .text.rtsmart_web_set_runtime

# 检查编译的文件
find output/k230_canmv_lckfb_defconfig/rtsmart -name "*http*" -o -name "*app_http*"

# 检查编译过程中的输出（确认 HTTP 服务器文件被编译）
make 2>&1 | grep -E "(app_http_server|http_service|http_server|http_handler)"
```

**编译过程输出示例**：

```text
CC app_http_server/http_service.o
CC app_http_server/src/frame_buffer.o
CC app_http_server/src/http_handler.o
CC app_http_server/src/http_server.o
CC app_http_server/src/static_assets.o
CC app_http_server/src/web_state.o
LINK rtthread.elf
```

**最终编译成功输出**：

```text
Build K230 done, board k230_canmv_lckfb, config k230_canmv_lckfb_defconfig
Generated image done, at /root/canmv_k230_clean//output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img
```

### 2.8 复制镜像到 Windows

```bash
# 复制所有镜像文件到 Windows 项目目录
cp /root/canmv_k230_clean/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img \
    /mnt/e/project/Endoscope_yolo/build/canmv_firmware/

cp /root/canmv_k230_clean/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img.gz \
    /mnt/e/project/Endoscope_yolo/build/canmv_firmware/

cp /root/canmv_k230_clean/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img.gz.md5 \
    /mnt/e/project/Endoscope_yolo/build/canmv_firmware/

echo "镜像复制完成"
```

### 2.9 编译输出位置

编译完成后，主要文件位置：

```text
output/k230_canmv_lckfb_defconfig/
├── images/
│   ├── rtsmart/
│   │   └── rtthread.bin          # RT-Smart 内核（包含 HTTP 服务器）
│   ├── rtapp/
│   │   └── rtapp.elf.gz           # RT-Smart 应用
│   └── ...
├── canmv/
│   └── micropython                # MicroPython 可执行文件（包含 rtsmart_web 模块）
└── CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img  # 最终镜像
```

---

## 3. RT-Smart 内核构建系统修改

### 3.1 创建 SConscript 文件

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

### 3.2 修改主 SConstruct

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

## 4. MicroPython 构建系统修改

### 4.1 修改 Makefile - 添加头文件路径

**文件**: `src/canmv/port/Makefile`

**添加的包含路径**:

```makefile
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/include
INC += -I$(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/rt-thread/components/finsh
```

**作用**: 让 MicroPython 编译时能找到 `web_state.h`、`frame_buffer.h` 等头文件。

### 4.2 修改 Makefile - 添加编译标志

**文件**: `src/canmv/port/Makefile`

**添加的编译标志**:

```makefile
CFLAGS += -DRTSMART_WEB_PORTABLE
```

**作用**: 定义 `RTSMART_WEB_PORTABLE` 宏，启用 MicroPython 编译上下文下的兼容层实现。

### 4.3 修改 Makefile - 添加源文件

**文件**: `src/canmv/port/Makefile`

**添加的源文件**:

```makefile
CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c
CANMV_SRC_C += $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c
```

**作用**: 将 `frame_buffer.c` 和 `web_state.c` 编译进 MicroPython 可执行文件。

**注意**: `rtsmart_web_module.c` 通过 `CANMV_SRC_C += $(wildcard modules/*.c)` 自动包含。

---

## 5. 源代码兼容性修改

### 5.1 头文件兼容层

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/include/web_state.h`

**修改**: 添加条件编译，支持 MicroPython 编译上下文：

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

- 在 RT-Smart 内核编译上下文中使用 RT-Thread API
- 在 MicroPython 编译上下文中使用标准 C 库和 pthread

### 5.2 源文件兼容层

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/frame_buffer.c`

**修改**: 添加条件编译的兼容实现：

```c
#ifndef RTSMART_WEB_PORTABLE
// RT-Smart 内核编译上下文：使用 RT-Thread API
#include <rtthread.h>
#else
// MicroPython 编译上下文：使用 pthread 和标准库
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

**作用**: 让同一份代码可以在 RT-Smart 内核和 MicroPython 两种编译上下文中编译。

**文件**: `src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/web_state.c`

**修改**: 类似的兼容层实现。

### 5.3 MicroPython 模块兼容

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

**作用**: 避免在 MicroPython 编译上下文中引入 RT-Thread 头文件导致的类型冲突。

---

## 6. 编译结果验证

### 6.1 RT-Smart 内核验证

编译后的 `rtthread.bin` 应包含以下符号：

- `http_server_start`
- `http_server_stop`
- `http_server_is_running`
- `__cmd_http_start` (MSH 命令)

验证命令：

```bash
strings output/.../rtthread.bin | grep -E "(http_server|http_start|HTTPService)"
```

### 6.2 MicroPython 验证

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

## 7. 修改文件清单

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

## 8. 架构说明

### 8.1 K230 CanMV 固件架构

**重要说明**: 在 K230 CanMV 固件中，**只开启大核运行 RT-Smart 操作系统**，小核并不运行。MicroPython 是运行在 RT-Smart 上的一个应用程序，而非运行在小核上。

```text
┌─────────────────────────────────────────────────────────────┐
│              K230 大核 - RT-Smart 操作系统                  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  RT-Smart 内核层（编译进 rtthread.bin）              │  │
│  │  - http_service.c (HTTP 服务器启动服务)             │  │
│  │  - http_server.c (HTTP 服务器核心)                  │  │
│  │  - http_handler.c (HTTP 请求处理)                   │  │
│  │  - frame_buffer.c (RT-Thread 版本)                  │  │
│  │  - web_state.c (RT-Thread 版本)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↑ IPC/共享内存                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  RT-Smart 应用层 - MicroPython 运行时               │  │
│  │  - micropython 可执行文件                            │  │
│  │  - rtsmart_web_module.c (C 绑定模块)                │  │
│  │  - frame_buffer.c (pthread 兼容版本)                 │  │
│  │  - web_state.c (pthread 兼容版本)                    │  │
│  │  - Python 业务逻辑 (YOLO 检测等)                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              K230 小核 - 未运行（CanMV 固件中）              │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 双编译上下文设计

通过 `RTSMART_WEB_PORTABLE` 宏实现同一份核心代码（`frame_buffer.c`、`web_state.c`）在两种编译上下文下的编译：

- **RT-Smart 内核编译上下文**: 编译进 `rtthread.bin`，使用 RT-Thread API (`rt_mutex_t`, `rt_kprintf`, `rt_malloc` 等)
- **MicroPython 编译上下文**: 编译进 `micropython` 可执行文件，使用 POSIX/pthread API (`pthread_mutex_t`, `printf`, `malloc` 等)

**注意**: 虽然代码在两个不同的编译上下文中编译，但它们都运行在同一个 RT-Smart 操作系统上（大核），通过 IPC 和共享内存进行通信。

---

## 9. 使用方法

### 9.1 烧录新镜像

使用新生成的镜像文件：

```text
build/canmv_firmware/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img
```

### 9.2 启动 HTTP 服务器

在 RT-Smart 串口终端输入：

```bash
msh />http_start
[HTTPService] ✅ HTTP 服务器已启动在 0.0.0.0:8080
```

### 9.3 Python 层使用

在 MicroPython 环境中（运行在 RT-Smart 上的应用）：

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

## 10. 注意事项

1. **K230 CanMV 架构**: 在 CanMV 固件中，只开启大核运行 RT-Smart 操作系统，小核不运行。MicroPython 是运行在 RT-Smart 上的应用程序，通过 IPC 和共享内存与 RT-Smart 内核组件（如 HTTP 服务器）通信。

2. **信号类型冲突**: 通过 `HAVE_SIGVAL`、`HAVE_SIGEVENT`、`HAVE_SIGINFO` 宏避免 RT-Thread 和 musl libc 的信号类型定义冲突。

3. **互斥锁类型**（两种编译上下文）:
   - RT-Smart 内核编译上下文: `struct rt_mutex` (RT-Thread API)
   - MicroPython 编译上下文: `pthread_mutex_t` (POSIX API)

4. **内存管理**（两种编译上下文）:
   - RT-Smart 内核编译上下文: `rt_malloc` / `rt_free` (RT-Thread API)
   - MicroPython 编译上下文: `malloc` / `free` (标准 C 库)

5. **时间获取**（两种编译上下文）:
   - RT-Smart 内核编译上下文: `rt_tick_get_millisecond()` (RT-Thread API)
   - MicroPython 编译上下文: `mp_hal_ticks_ms()` (MicroPython HAL API)

---

## 11. 后续维护

### 11.1 更新前端代码（HTML/JS）

如果修改了前端代码（`k230_onboard_project/static/app.js` 或 `index.html`）：

```bash
# 1. 在项目根目录生成新的 .inc 文件
cd E:\project\Endoscope_yolo
python rtsmart_userapp/scripts/generate_static_assets.py

# 2. 同步到 WSL SDK 目录
wsl bash -c "cp /mnt/e/project/Endoscope_yolo/rtsmart_userapp/src/*.inc \
    /root/canmv_k230_clean/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/src/"

# 3. 重新编译固件
wsl bash -c "cd /root/canmv_k230_clean && make clean && make"

# 4. 复制新固件
wsl bash -c "cp /root/canmv_k230_clean/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img* \
    /mnt/e/project/Endoscope_yolo/build/canmv_firmware/"
```

### 11.2 更新 C 层代码

如果需要更新 RT-Smart 内核层代码：

1. **修改源文件**: 编辑 `rtsmart_userapp/src/` 下的 C 文件
2. **同步到 SDK**: 将修改后的文件复制到 WSL SDK 目录
3. **重新编译**: `cd /root/canmv_k230_clean && make clean && make`
4. **复制镜像**: 将新镜像复制到 `build/canmv_firmware/`

### 11.3 更新 MicroPython 绑定

如果需要更新 MicroPython 应用层代码：

1. **修改源文件**: 编辑 `rtsmart_userapp/micropython_binding/rtsmart_web_module.c`
2. **同步到 SDK**: 复制到 `src/canmv/port/modules/`
3. **重新编译**: `cd /root/canmv_k230_clean && make clean && make`
4. **复制镜像**: 将新镜像复制到 `build/canmv_firmware/`

### 11.4 完整更新流程（包含前端）

```bash
# 在项目根目录执行
cd E:\project\Endoscope_yolo

# 1. 生成静态资源（如果修改了前端代码）
python rtsmart_userapp/scripts/generate_static_assets.py

# 2. 同步所有文件到 WSL SDK
wsl bash -c "
    PROJECT_DIR=/mnt/e/project/Endoscope_yolo
    SDK_DIR=/root/canmv_k230_clean
    
    # 同步 RT-Smart 层代码（包含 .inc 文件）
    rsync -av --delete \$PROJECT_DIR/rtsmart_userapp/ \
        \$SDK_DIR/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/
    
    # 同步 MicroPython 绑定
    cp \$PROJECT_DIR/rtsmart_userapp/micropython_binding/rtsmart_web_module.c \
        \$SDK_DIR/src/canmv/port/modules/
"

# 3. 编译固件
wsl bash -c "cd /root/canmv_k230_clean && make clean && make"

# 4. 复制固件
wsl bash -c "
    cp /root/canmv_k230_clean/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img* \
       /mnt/e/project/Endoscope_yolo/build/canmv_firmware/
    echo '✅ 固件已更新'
"
```

**注意**: RT-Smart 内核层和 MicroPython 应用层都运行在同一个 RT-Smart 操作系统上（K230 大核），它们通过 IPC 和共享内存进行通信。

---

## 12. 快速参考命令清单

### 12.1 完整构建流程（一键执行）

以下是一个完整的构建脚本，可以在 WSL 中执行：

```bash
#!/bin/bash
set -e

SDK_DIR="/root/canmv_k230_clean"
PROJECT_DIR="/mnt/e/project/Endoscope_yolo"

# 1. 初始化 SDK（仅首次需要）
if [ ! -d "$SDK_DIR/.repo" ]; then
    cd $(dirname $SDK_DIR)
    mkdir -p $(basename $SDK_DIR) && cd $(basename $SDK_DIR)
    repo init -u git@gitee.com:canmv-k230/manifest.git -b master \
        --repo-url=git@gitee.com:canmv-k230/git-repo.git --repo-branch stable
    repo sync
fi

cd $SDK_DIR

# 2. 生成静态资源（如果修改了前端代码）
cd $PROJECT_DIR
python rtsmart_userapp/scripts/generate_static_assets.py
cd $SDK_DIR

# 3. 复制代码（包含生成的 .inc 文件）
rsync -av --delete $PROJECT_DIR/rtsmart_userapp/ \
    src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/
cp $PROJECT_DIR/rtsmart_userapp/micropython_binding/rtsmart_web_module.c \
    src/canmv/port/modules/

# 4. 配置
make k230_canmv_lckfb_defconfig

# 5. 编译
make clean
time make

# 6. 验证
echo "=== 验证 RT-Smart ==="
strings output/k230_canmv_lckfb_defconfig/images/rtsmart/rtthread.bin | \
    grep -E "(http_server|http_start)" | head -5

echo "=== 验证 MicroPython ==="
strings output/k230_canmv_lckfb_defconfig/canmv/micropython | \
    grep rtsmart_web | head -10

echo "=== 验证静态资源 ==="
strings output/k230_canmv_lckfb_defconfig/images/rtsmart/rtthread.bin | \
    grep -E "(getElementById|startCamera)" | head -3

# 7. 复制镜像
cp output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img* \
    $PROJECT_DIR/build/canmv_firmware/

echo "✅ 构建完成！"
```

### 12.2 常用命令速查

| 操作 | 命令 |
|------|------|
| **初始化 SDK** | `repo init -u git@gitee.com:canmv-k230/manifest.git -b master --repo-url=git@gitee.com:canmv-k230/git-repo.git --repo-branch stable` |
| **同步代码** | `repo sync` |
| **列出配置** | `make list-def` |
| **配置板型** | `make k230_canmv_lckfb_defconfig` |
| **清理编译** | `make clean` |
| **完整编译** | `make` |
| **只编译 RT-Smart** | `cd src/rtsmart && scons` |
| **只编译 MicroPython** | `cd src/canmv/port && make` |
| **验证 RT-Smart** | `strings output/.../rtthread.bin \| grep http_server` |
| **验证 MicroPython** | `strings output/.../micropython \| grep rtsmart_web` |
| **复制镜像** | `cp output/.../*.img* /mnt/e/project/Endoscope_yolo/build/canmv_firmware/` |

### 12.3 编译时间参考

- **首次完整编译**: 30-60 分钟（取决于 CPU 性能）
- **增量编译**: 5-15 分钟（仅修改部分文件）
- **仅 RT-Smart**: 2-5 分钟
- **仅 MicroPython**: 1-3 分钟

### 12.4 常见问题排查

#### 问题 1: 编译错误 - 找不到头文件

```bash
# 检查头文件路径是否正确
grep -r "app_http_server/include" src/canmv/port/Makefile
```

#### 问题 2: 链接错误 - 未定义符号

```bash
# 检查源文件是否被包含
grep -r "frame_buffer.c\|web_state.c" src/canmv/port/Makefile
```

#### 问题 3: RT-Smart 未包含 HTTP 服务器

```bash
# 检查 SConstruct 是否包含 app_http_server
grep -A 3 "app_http_server" src/rtsmart/rtsmart/kernel/bsp/maix3/SConstruct

# 检查 SConscript 是否存在
ls -la src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/SConscript
```

#### 问题 4: 类型冲突错误

```bash
# 检查是否定义了 RTSMART_WEB_PORTABLE
grep -r "RTSMART_WEB_PORTABLE" src/canmv/port/Makefile
```

---

## 总结

通过以上修改，我们成功将 RT-Smart Web 服务器集成到官方 CanMV SDK 中，实现了：

✅ **RT-Smart 内核层**: HTTP 服务器作为内核组件编译进 `rtthread.bin`，可通过 MSH 命令启动  
✅ **MicroPython 应用层**: C 绑定模块编译进 `micropython` 可执行文件，提供完整的 Python API  
✅ **双编译上下文兼容**: 同一份核心代码（frame_buffer、web_state）可在两种编译上下文中编译  
✅ **完整功能**: 支持帧推送、状态管理、控制接口、统计信息等所有功能  
✅ **单核运行**: K230 CanMV 固件只使用大核运行 RT-Smart，MicroPython 作为 RT-Smart 上的应用运行

现在可以在板子上同时使用 C 层的 HTTP 服务器（RT-Smart 内核组件）和 Python 层的 YOLO 检测功能（MicroPython 应用）了！
