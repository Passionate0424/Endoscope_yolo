#include "web_state.h"

#ifndef RTSMART_WEB_PORTABLE
#include <rtthread.h>
#else
#include "py/mphal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
typedef pthread_mutex_t rt_mutex_t;
typedef int32_t rt_int32_t;
#define RT_IPC_FLAG_PRIO 0
#define RT_WAITING_FOREVER (-1)
#define rt_kprintf printf
#define rt_snprintf snprintf
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
#endif
#include <string.h>

typedef struct
{
#ifndef RTSMART_WEB_PORTABLE
    struct rt_mutex lock;
#else
    rt_mutex_t lock;
#endif
    rt_bool_t camera_running;
    rt_bool_t detection_enabled;
    float confidence_threshold;

    rt_bool_t desired_camera_running;
    rt_bool_t desired_detection_enabled;
    float desired_confidence;
    uint32_t command_version;

    web_stats_info_t stats;
    web_record_info_t records[WEB_STATE_MAX_RECORDS];
    uint16_t record_count;
    uint32_t next_record_id;
    rt_bool_t initialized;
} web_state_t;

static web_state_t g_web_state = {0};

static void web_state_touch_command_locked(void)
{
    g_web_state.command_version++;
    if (g_web_state.command_version == 0)
    {
        g_web_state.command_version = 1;
    }
}

void web_state_init(void)
{
    if (g_web_state.initialized)
    {
        return;
    }

    rt_mutex_init(&g_web_state.lock, "web_lock", RT_IPC_FLAG_PRIO);
    g_web_state.confidence_threshold = 0.5f;
    g_web_state.desired_confidence = 0.5f;
    g_web_state.record_count = 0;
    g_web_state.next_record_id = 1;
    g_web_state.camera_running = RT_FALSE;
    g_web_state.detection_enabled = RT_FALSE;
    g_web_state.desired_camera_running = RT_FALSE;
    g_web_state.desired_detection_enabled = RT_FALSE;
    g_web_state.command_version = 1;
    memset(&g_web_state.stats, 0, sizeof(g_web_state.stats));
    g_web_state.initialized = RT_TRUE;
}

void web_state_deinit(void)
{
    if (!g_web_state.initialized)
    {
        return;
    }

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.initialized = RT_FALSE;
    g_web_state.record_count = 0;
    rt_mutex_release(&g_web_state.lock);
    rt_mutex_detach(&g_web_state.lock);
}

void web_state_set_camera_running(rt_bool_t running)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.camera_running = running;
    rt_mutex_release(&g_web_state.lock);
}

rt_bool_t web_state_get_camera_running(void)
{
    if (!g_web_state.initialized)
        return RT_FALSE;

    rt_bool_t value;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    value = g_web_state.camera_running;
    rt_mutex_release(&g_web_state.lock);
    return value;
}

void web_state_set_detection_enabled(rt_bool_t enabled)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.detection_enabled = enabled;
    rt_mutex_release(&g_web_state.lock);
}

rt_bool_t web_state_get_detection_enabled(void)
{
    if (!g_web_state.initialized)
        return RT_FALSE;

    rt_bool_t value;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    value = g_web_state.detection_enabled;
    rt_mutex_release(&g_web_state.lock);
    return value;
}

void web_state_set_confidence(float value)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    if (value < 0.01f)
        value = 0.01f;
    if (value > 0.99f)
        value = 0.99f;
    g_web_state.confidence_threshold = value;
    rt_mutex_release(&g_web_state.lock);
}

float web_state_get_confidence(void)
{
    if (!g_web_state.initialized)
        return 0.5f;

    float value;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    value = g_web_state.confidence_threshold;
    rt_mutex_release(&g_web_state.lock);
    return value;
}

void web_state_request_camera(rt_bool_t running)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.desired_camera_running = running;
    web_state_touch_command_locked();
    rt_mutex_release(&g_web_state.lock);
}

void web_state_request_detection(rt_bool_t enabled)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.desired_detection_enabled = enabled;
    web_state_touch_command_locked();
    rt_mutex_release(&g_web_state.lock);
}

void web_state_request_confidence(float value)
{
    if (!g_web_state.initialized)
        return;

    if (value < 0.01f)
        value = 0.01f;
    if (value > 0.99f)
        value = 0.99f;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.desired_confidence = value;
    web_state_touch_command_locked();
    rt_mutex_release(&g_web_state.lock);
}

float web_state_get_requested_confidence(void)
{
    if (!g_web_state.initialized)
        return 0.5f;

    float value;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    value = g_web_state.desired_confidence;
    rt_mutex_release(&g_web_state.lock);
    return value;
}

void web_state_get_control_info(web_control_info_t *info)
{
    if (!info)
        return;

    if (!g_web_state.initialized)
    {
        memset(info, 0, sizeof(*info));
        info->desired_confidence = 0.5f;
        info->actual_confidence = 0.5f;
        return;
    }

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    info->desired_camera_running = g_web_state.desired_camera_running;
    info->desired_detection_enabled = g_web_state.desired_detection_enabled;
    info->desired_confidence = g_web_state.desired_confidence;
    info->actual_camera_running = g_web_state.camera_running;
    info->actual_detection_enabled = g_web_state.detection_enabled;
    info->actual_confidence = g_web_state.confidence_threshold;
    info->command_version = g_web_state.command_version;
    rt_mutex_release(&g_web_state.lock);
}

void web_state_update_stats(uint32_t total_frames, uint32_t total_detections, float fps)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.stats.total_frames = total_frames;
    g_web_state.stats.total_detections = total_detections;
    g_web_state.stats.fps = fps;
    rt_mutex_release(&g_web_state.lock);
}

void web_state_get_stats(web_stats_info_t *out_stats)
{
    if (!out_stats)
        return;

    if (!g_web_state.initialized)
    {
        memset(out_stats, 0, sizeof(*out_stats));
        return;
    }

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    *out_stats = g_web_state.stats;
    rt_mutex_release(&g_web_state.lock);
}

uint32_t web_state_add_record(const char *filename, const char *time_str, float confidence)
{
    if (!g_web_state.initialized)
        return 0;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);

    uint32_t record_id = g_web_state.next_record_id++;
    if (g_web_state.next_record_id == 0)
        g_web_state.next_record_id = 1;

    if (g_web_state.record_count == WEB_STATE_MAX_RECORDS)
    {
        memmove(&g_web_state.records[1], &g_web_state.records[0],
                sizeof(web_record_info_t) * (WEB_STATE_MAX_RECORDS - 1));
        g_web_state.record_count = WEB_STATE_MAX_RECORDS - 1;
    }

    web_record_info_t *record = &g_web_state.records[g_web_state.record_count++];
    record->id = record_id;
    rt_snprintf(record->filename, sizeof(record->filename), "%s", filename ? filename : "record.jpg");
    rt_snprintf(record->time_str, sizeof(record->time_str), "%s", time_str ? time_str : "--");
    record->confidence = confidence;

    rt_mutex_release(&g_web_state.lock);
    return record_id;
}

uint16_t web_state_get_records(web_record_info_t *out_records, uint16_t max_records)
{
    if (!g_web_state.initialized || !out_records || max_records == 0)
        return 0;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    uint16_t count = g_web_state.record_count;
    if (count > max_records)
        count = max_records;
    memcpy(out_records, g_web_state.records, sizeof(web_record_info_t) * count);
    rt_mutex_release(&g_web_state.lock);
    return count;
}

uint16_t web_state_get_record_count(void)
{
    if (!g_web_state.initialized)
        return 0;

    uint16_t count;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    count = g_web_state.record_count;
    rt_mutex_release(&g_web_state.lock);
    return count;
}

void web_state_clear_records(void)
{
    if (!g_web_state.initialized)
        return;

    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    g_web_state.record_count = 0;
    rt_mutex_release(&g_web_state.lock);
}

rt_bool_t web_state_delete_record(uint32_t record_id)
{
    if (!g_web_state.initialized || record_id == 0)
        return RT_FALSE;

    rt_bool_t removed = RT_FALSE;
    rt_mutex_take(&g_web_state.lock, RT_WAITING_FOREVER);
    for (uint16_t i = 0; i < g_web_state.record_count; i++)
    {
        if (g_web_state.records[i].id == record_id)
        {
            memmove(&g_web_state.records[i], &g_web_state.records[i + 1],
                    sizeof(web_record_info_t) * (g_web_state.record_count - i - 1));
            g_web_state.record_count--;
            removed = RT_TRUE;
            break;
        }
    }
    rt_mutex_release(&g_web_state.lock);
    return removed;
}


