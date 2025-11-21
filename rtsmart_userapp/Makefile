# RT-Smart Userapp Makefile for K230 SDK
# 用于编译 rtsmart_webserver

# RT-Smart SDK 路径（需要在 SDK 环境中编译）
RTT_ROOT ?= $(shell pwd)/../../../

# 工具链
CC = riscv64-unknown-linux-musl-gcc
AR = riscv64-unknown-linux-musl-ar
LD = riscv64-unknown-linux-musl-ld

# 编译选项
CFLAGS = -O2 -Wall -Wextra
CFLAGS += -I./include
CFLAGS += -I$(RTT_ROOT)/rt-smart/kernel/bsp/maix3/
CFLAGS += -I$(RTT_ROOT)/rt-smart/kernel/include
CFLAGS += -march=rv64imafdcv -mabi=lp64d
CFLAGS += -DRT_USING_SMART

# 链接选项
LDFLAGS = -lpthread
LDFLAGS += -L$(RTT_ROOT)/rt-smart/userapps/sdk/rt-thread/lib

# 源文件
SRCS = src/http_server.c \
       src/http_handler.c \
       src/frame_buffer.c \
       src/static_assets.c \
       src/web_state.c

OBJS = $(SRCS:.c=.o)

# 目标
TARGET = rtsmart_webserver

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
	@echo "✅ Built $(TARGET)"

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)
	@echo "🗑️  Cleaned"

install: $(TARGET)
	@mkdir -p $(INSTALL_DIR)/bin
	cp $(TARGET) $(INSTALL_DIR)/bin/
	@echo "📦 Installed to $(INSTALL_DIR)/bin/$(TARGET)"

.PHONY: all clean install

# 注意：
# 1. 这个 Makefile 需要在 K230 SDK 的 RT-Smart 环境中使用
# 2. 确保工具链在 PATH 中：riscv64-unknown-linux-musl-gcc
# 3. 编译前需要先编译 RT-Smart 内核，获取头文件路径
