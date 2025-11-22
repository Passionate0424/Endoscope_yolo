#ifndef WEB_STATE_H
#define WEB_STATE_H

#ifdef RTSMART_WEB_PORTABLE
#include <stdbool.h>
typedef bool rt_bool_t;
#ifndef RT_TRUE
#define RT_TRUE true
#endif
#ifndef RT_FALSE
#define RT_FALSE false
#endif
#else
#include <rtthread.h>
#endif

#include <stdint.h>

#define WEB_STATE_MAX_RECORDS 50

typedef struct
{
    uint32_t id;
    char filename[64];
    char time_str[32];
    float confidence;
} web_record_info_t;

typedef struct
{
    uint32_t total_frames;
    uint32_t total_detections;
    float fps;
} web_stats_info_t;

typedef struct
{
    rt_bool_t desired_camera_running;
    rt_bool_t desired_detection_enabled;
    float desired_confidence;
    rt_bool_t actual_camera_running;
    rt_bool_t actual_detection_enabled;
    float actual_confidence;
    uint32_t command_version;
} web_control_info_t;

void web_state_init(void);
void web_state_deinit(void);

void web_state_set_camera_running(rt_bool_t running);
rt_bool_t web_state_get_camera_running(void);

void web_state_set_detection_enabled(rt_bool_t enabled);
rt_bool_t web_state_get_detection_enabled(void);

void web_state_set_confidence(float value);
float web_state_get_confidence(void);

void web_state_request_camera(rt_bool_t running);
void web_state_request_detection(rt_bool_t enabled);
void web_state_request_confidence(float value);
float web_state_get_requested_confidence(void);
void web_state_get_control_info(web_control_info_t *info);

void web_state_update_stats(uint32_t total_frames, uint32_t total_detections, float fps);
void web_state_get_stats(web_stats_info_t *out_stats);

uint16_t web_state_get_record_count(void);
uint16_t web_state_get_records(web_record_info_t *out_records, uint16_t max_records);
void web_state_clear_records(void);
rt_bool_t web_state_delete_record(uint32_t record_id);
uint32_t web_state_add_record(const char *filename, const char *time_str, float confidence);

#endif /* WEB_STATE_H */


