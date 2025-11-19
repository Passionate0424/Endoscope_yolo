#ifndef FRAME_BUFFER_H
#define FRAME_BUFFER_H

#include <stdint.h>
#include <stddef.h>

// 环形缓冲区配置
#define MAX_FRAME_SLOTS 3
#define MAX_JPEG_SIZE (512 * 1024) // 512KB per frame

// 帧数据结构
typedef struct
{
    uint8_t *data;
    size_t size;
    uint32_t timestamp_ms;
    uint8_t valid;
} frame_slot_t;

// 环形缓冲区
typedef struct
{
    frame_slot_t slots[MAX_FRAME_SLOTS];
    int write_idx;
    int read_idx;
    int quality;
    volatile int initialized;
} frame_buffer_t;

// API 函数
int frame_buffer_init(int quality);
void frame_buffer_deinit(void);
int frame_buffer_push(const uint8_t *jpeg_data, size_t size);
int frame_buffer_get_latest(uint8_t **out_data, size_t *out_size);
int frame_buffer_is_ready(void);

#endif // FRAME_BUFFER_H
