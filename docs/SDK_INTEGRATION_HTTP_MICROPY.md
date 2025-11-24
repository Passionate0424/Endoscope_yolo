# CanMV HTTP Server 移植到 MicroPython 构建说明（当前工作总结）

本说明梳理本次将 HTTP 服务器从 RT-Smart 内核侧移至 MicroPython 侧的操作与修改，风格与 `SDK_INTEGRATION_MODIFICATIONS.md` 类似，供后续同步参考。

## 1. 环境与目录
- Windows 工程目录：`E:\project\Endoscope_yolo`
- WSL 工作目录：`/root/canmv_k230_http_mp`（由 `/root/canmv_k230_clean` 复制）
- 代码同步：使用 `rsync -av --delete /mnt/e/project/Endoscope_yolo/rtsmart_userapp/ /root/canmv_k230_http_mp/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/`
- MicroPython 模块同步：`rtsmart_userapp/micropython_binding/rtsmart_web_module.c` 已复制到 WSL 的 `src/canmv/port/modules/`

## 2. 主要修改

### 2.1 仅在 MicroPython 构建 HTTP 服务器
- **内核 SConstruct**（路径：`/root/canmv_k230_http_mp/src/rtsmart/rtsmart/kernel/bsp/maix3/SConstruct`）  
  移除 `app_http_server` 组件的引入，避免 HTTP 服务器再编入内核。

- **MicroPython Makefile**（路径：`/root/canmv_k230_http_mp/src/canmv/port/Makefile`）  
  - 头文件路径保持：`app_http_server/include`、`rt-thread/include`、`finsh`、`dfs/include`、`drivers/include`、`drivers/wlan`、`bsp/maix3`、`libcpu/risc-v/t-head/c906` 等。  
  - 源文件加入：`frame_buffer.c`、`web_state.c`、`static_assets.c`、`http_handler.c`、`http_server.c`（均来自 `app_http_server/src/`）。  
  - 便携宏：`CFLAGS += -DRTSMART_WEB_PORTABLE`，同时保留现有优化/硬件宏。  
  - 额外库/依赖：确保 `-lpthread`、`-lrt`、`-lm`（如需要）及 POSIX 路径满足线程/套接字；保持 CFLAGS/LDFLAGS 与官方模板一致。  
  - MicroPython modules 目录保留原有 `modmedia*`、`modvbmgmt` 等，新增/覆盖 `rtsmart_web_module.c`。

### 2.2 C 代码便携化（HTTP 服务器侧）
- **文件**：`rtsmart_userapp/src/http_handler.c`  
  - 增加 `RTSMART_WEB_PORTABLE` 分支：用 `mp_hal_ticks_ms/mp_hal_delay_ms` 映射 `rt_tick_get/rt_thread_mdelay`，用 `printf/snprintf/malloc/free` 替代内核接口，定义 `rt_bool_t/RT_TRUE/RT_FALSE/RT_NULL` 以避免冲突。  
  - 逻辑保持一致：MJPEG/HTTP API/静态资源路由不变。  
- 其他源（`frame_buffer.c`、`web_state.c`、`static_assets.c`、`http_server.c`）保留便携宏，使用 pthread/posix sem 替代 rt-thread 线程/信号量；Wi-Fi 相关在便携模式下短路（不自动连）。  
- `rtsmart_web_module.c` 在 MicroPython 侧暴露 `start_server()` 调用 C 端 `http_server_autostart/http_server_init`。

## 3. 构建步骤（WSL）
1) 进入工作区：`cd /root/canmv_k230_http_mp`  
2) 选择配置：`make k230_canmv_lckfb_defconfig`  
3) 清理可选：`make clean`  
4) 编译：`make`（HTTP 服务器随 MicroPython 编译，内核不再包含）  
5) 产物：`output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img` 及 `.img.gz/.md5`

## 4. Windows 侧固件
- 已拷贝到：`build/canmv_firmware/`  
  - `CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img`  
  - `CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img.gz`  
  - `CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img.gz.md5`

## 5. 后续同步与修改建议
- 若在 Windows 端调整 `rtsmart_userapp` 源码，记得 `rsync` 到 WSL 对应目录后再执行 `make`。  
- 若需重新让 HTTP 进入内核，只需在内核 `SConstruct` 恢复 `app_http_server` 引入，并在 MicroPython Makefile 中移除相关源/宏。  
- 测试建议：刷写 `.img` 后，在 MicroPython 中启动 YOLO 推流，验证 HTTP API/MJPEG 与 C 层状态同步。

## 6. Commands actually used (for traceability)

- Clone clean SDK into working dir (WSL):  
  ```bash
  wsl cp -a /root/canmv_k230_clean /root/canmv_k230_http_mp
  ```
- Sync project HTTP/MicroPython sources from Windows to WSL:  
  ```bash
  rsync -av --delete /mnt/e/project/Endoscope_yolo/rtsmart_userapp/ /root/canmv_k230_http_mp/src/rtsmart/rtsmart/kernel/bsp/maix3/app_http_server/
  cp /mnt/e/project/Endoscope_yolo/rtsmart_userapp/micropython_binding/rtsmart_web_module.c /root/canmv_k230_http_mp/src/canmv/port/modules/
  ```
- Configure & (optionally) clean:  
  ```bash
  cd /root/canmv_k230_http_mp
  make k230_canmv_lckfb_defconfig
  make clean      # optional full clean
  ```
- Build (HTTP only in MicroPython):  
  ```bash
  make            # first full build ~30–60 minutes
  ```
- Copy firmware back to Windows:  
  ```bash
  mkdir -p /mnt/e/project/Endoscope_yolo/build/canmv_firmware
  cp /root/canmv_k230_http_mp/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img /mnt/e/project/Endoscope_yolo/build/canmv_firmware/
  cp /root/canmv_k230_http_mp/output/k230_canmv_lckfb_defconfig/CanMV_K230_LCKFB_micropython_local_nncase_v2.9.0.img.gz* /mnt/e/project/Endoscope_yolo/build/canmv_firmware/
  ```

## 7. 近期调试摘要（2025-11-24）
- 目标：HTTP 服务器在 Micropython 用户态运行（RTSMART_WEB_PORTABLE），使用线程池避免每请求建线程。
- 变更：`src/canmv/port/Makefile` 启用 `HTTP_SERVER_FORCE_PORTABLE`，编译 http_server.c/http_handler.c/frame_buffer.c/web_state.c/static_assets.c 进入 Micropython；移除将 `pthread_tls_stubs.c` 链入 Micropython（防止弱符号覆盖 TLS）。
- 问题1：上电即崩溃，sepc 映射到 `mpthreadport.c:138 (mp_thread_init)`，原因是 TLS 被 stub 覆盖为空；处理：从 Micropython 构建中删除 `pthread_tls_stubs.c`，重编未 strip 固件。
- 当前状态：固件可生成并复制到 `build/`、`build/canmv_firmware/`。需在板上验证 HTTP 请求是否仍会触发原来的崩溃；如再现，请记录 sepc/stval 并用带符号的 `micropython`/`rtthread.elf` 执行 addr2line 反馈。
- 排查建议：先运行最小脚本只启 HTTP 不启 YOLO/取帧；若稳定，再逐步打开摄像头推流定位；崩溃时将地址解析结果附上。

### 7.1 对话中遇到的所有问题与尝试（按时间线简述）
- 早期现象：HTTP 访问即 Instruction Page Fault，多次 dump（scause=0xc，sepc=0）并伴随 `[Func]:vb_do_exit`，推测摄像头/HTTP 交互或线程回收导致。
- preload 讨论：固件中 `preload` 影响 IDE 连接；移除后 IDE 无法连接，说明 IDE 依赖 preload 触发 Micropython/调试入口。
- Micropython/HTTP 崩溃复现：HTTP 启动后客户端访问即 Page Fault，多次 dump sepc=0；尝试只推流不跑检测时相对稳定，表明 YOLO/推流叠加更易触发。
- 线程模型尝试：从“每请求 pthread_create/return 退出”改为“线程池 + 任务队列 + 条件变量”，期望减少频繁建线程导致的崩溃；在 C 侧（http_server.c）实现 portable 线程池。
- 线程池版本崩溃：仍出现 Page Fault/Store-AMO Fault，怀疑 C 层调用需 POSIX 接口；检查官方 RT-Smart LWP 文档，确认用户态应使用 POSIX。
- 任务：保持 Micropython 用户态直接调用 HTTP，避免放回内核态以便 YOLO（同用户态）传递图像。
- 源码状态：Windows 侧 http_server.c 一度损坏，后从 git 恢复旧版，再加入线程池实现；确认 portable 分支使用 POSIX，非 portable 分支用 RT API。
- Makefile 同步：从其他 SDK 复制 Makefile 到 `/root/canmv_k230_http_mp/src/canmv/port/Makefile`，并补齐 HTTP 源文件；期间提醒不要改动其他 SDK 版本。
- 符号丢失/编译报错：Micropython 构建时缺少 dfs_posix.h，修复 include 顺序：portable 分支走 POSIX 头，RT 分支才包含 rtthread/dfs/wlan。
- TLS 弱符号问题：为兼容 portable 线程曾添加 `pthread_tls_stubs.c`（弱符号），结果 Micropython 上电崩溃（Store/AMO Page Fault），addr2line 定位 `mp_thread_init`；结论：不要把 stubs 链入 Micropython，删除后重建。
- 构建成功：`make STRIP=:` 完成；未 strip 的 `micropython`/`rtthread.elf` 可用于 addr2line；镜像复制到 Windows `build/` 与 `build/canmv_firmware/`。
- 后续待查：如果 HTTP 请求仍崩溃，需要新的 sepc/stval，并用带符号二进制解析；建议先最小化脚本仅启 HTTP 服务器再逐步加摄像头/YOLO 以定位。

### 7.2 关键 addr2line 解析记录
- 上电崩溃（Store/AMO Page Fault，stval=0x48，sepc=0x200740de2）：  
  ```
  riscv64-unknown-linux-musl-addr2line -e /root/canmv_k230_http_mp/output/k230_canmv_lckfb_defconfig/canmv/micropython -a -f 0x200740de2 0x200740ddc
  => mp_thread_init (/root/canmv_k230_http_mp/src/canmv/port/core/mpthreadport.c:138)
  ```
  结论：TLS 被弱符号 stub 覆盖导致空指针，已通过移除 `pthread_tls_stubs.c` 解决。
- 其它历史崩溃（sepc=0），多次出现在 HTTP 请求或摄像头初始化后，尚无精确函数映射；需在最新固件上再次捕获地址并解析。

### 7.3 为什么曾尝试使用 pthread_tls_stubs.c（含 addr2line 细节）
- 背景/动机：portable 分支用 POSIX 线程。早期担心 RT-Smart 用户态缺少完整的 pthread TLS 清理实现，可能导致 http_server 或第三方库里调用 pthread TLS 接口时找不到符号，于是临时加入弱符号 stub（`pthread_key_create/delete/getspecific/setspecific` 全空实现），期望“有符号不报错”。
- 崩溃现象：烧录后上电即挂，日志为 Store/AMO Page Fault（stval=0x48，sepc=0x200740de2/0x200740ddc）。
- addr2line 解析：
  ```
  riscv64-unknown-linux-musl-addr2line -e /root/canmv_k230_http_mp/output/k230_canmv_lckfb_defconfig/canmv/micropython -a -f 0x200740de2 0x200740ddc
  => mp_thread_init (/root/canmv_k230_http_mp/src/canmv/port/core/mpthreadport.c:138)
  ```
  即 Micropython TLS 初始化里执行 `pthread_setspecific(tls_key, &mp_state_ctx.thread)` 时崩溃。
- 根因：弱符号 stub 覆盖了 libc 的真实 pthread TLS 实现，导致 `pthread_setspecific` 运行在空 TLS 环境，写入 0x48 偏移触发 Store/AMO Page Fault。
- 结论/处理：Micropython 侧绝不能链接 `pthread_tls_stubs.c`。已从 `src/canmv/port/Makefile` 移除该文件，只保留 portable HTTP 代码。RT 版或其它用户态若确实需要 stub，可单独使用，但默认不启。
