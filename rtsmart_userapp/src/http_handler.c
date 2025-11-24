/*
 * HTTP 请求处理器
 * 处理不同类型的 HTTP 请求（MJPEG 流、快照、API 等）
 */

#include "http_handler.h"
#include "frame_buffer.h"
#include "static_assets.h"
#ifndef RTSMART_WEB_PORTABLE
#include <rtthread.h>
#include <dfs_posix.h>
#else
#include "py/mphal.h"
#include <time.h>
#include <unistd.h>
#include <errno.h>
typedef uint32_t rt_uint32_t;
#ifndef RT_TICK_PER_SECOND
#define RT_TICK_PER_SECOND 1000
#endif
// Use POSIX time/sleep in portable build to avoid depending on MicroPython per-thread state
static inline rt_uint32_t portable_tick_get(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (rt_uint32_t)(ts.tv_sec * 1000U + ts.tv_nsec / 1000000U);
}
static inline void portable_thread_mdelay(int ms)
{
    if (ms > 0)
    {
        usleep((useconds_t)ms * 1000U);
    }
}
#define rt_tick_get() portable_tick_get()
#define rt_thread_mdelay(ms) portable_thread_mdelay(ms)
#define rt_kprintf printf
#define rt_snprintf snprintf
#define rt_malloc malloc
#define rt_free free
#endif
#include "web_state.h"
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <ctype.h>

// ⭐ 使用标准 libc 的 snprintf（支持浮点数），而不是 RT-Thread 的 rt_snprintf
// 因为 RT_USING_LIBC 已启用，标准 snprintf 应该可用
#ifdef RT_USING_LIBC
// 使用标准 C 库的 snprintf（支持 %f）
#else
// 如果未启用 libc，使用手动格式化
#endif

#define MJPEG_BOUNDARY "frame"
#define MAX_FPS 30
#define DETECTION_DIR "/data/detections"

static rt_uint32_t http_get_tick_ms(void)
{
    return (rt_tick_get() * 1000U) / RT_TICK_PER_SECOND;
}

static int http_send_response(int fd, int status, const char *content_type, const char *body, int body_len)
{
    char header[256];
    const char *status_text = "OK";

    if (status == 404)
        status_text = "Not Found";
    else if (status == 500)
        status_text = "Internal Server Error";
    else if (status == 400)
        status_text = "Bad Request";

    int header_len = snprintf(header, sizeof(header),
                              "HTTP/1.1 %d %s\r\n"
                              "Content-Type: %s\r\n"
                              "Content-Length: %d\r\n"
                              "Connection: close\r\n"
                              "Cache-Control: no-cache\r\n"
                              "\r\n",
                              status, status_text, content_type, body_len);

    if (send(fd, header, header_len, 0) < 0)
    {
        return -1;
    }

    if (body && body_len > 0)
    {
        if (send(fd, body, body_len, 0) < 0)
        {
            return -1;
        }
    }

    return 0;
}

static int http_send_binary(int fd, const char *content_type, const unsigned char *data, size_t len)
{
    return http_send_response(fd, 200, content_type, (const char *)data, len);
}

static int http_send_json(int fd, const char *json)
{
    return http_send_response(fd, 200, "application/json", json, strlen(json));
}

static int http_send_file(int fd, const char *filepath, const char *content_type)
{
    struct stat st;
    int file_fd = open(filepath, O_RDONLY);
    if (file_fd < 0)
    {
        return http_send_404(fd);
    }

    if (fstat(file_fd, &st) != 0 || st.st_size <= 0)
    {
        close(file_fd);
        return http_send_404(fd);
    }

    if (http_send_response(fd, 200, content_type, NULL, st.st_size) != 0)
    {
        close(file_fd);
        return -1;
    }

    char buffer[1024];
    ssize_t read_len;
    while ((read_len = read(file_fd, buffer, sizeof(buffer))) > 0)
    {
        if (send(fd, buffer, read_len, 0) < 0)
        {
            close(file_fd);
            return -1;
        }
    }

    close(file_fd);
    return 0;
}

static rt_bool_t parse_json_float(const char *body, const char *key, float *out_value)
{
    if (!body || !key || !out_value)
        return RT_FALSE;

    const char *found = strstr(body, key);
    if (!found)
        return RT_FALSE;

    found = strchr(found, ':');
    if (!found)
        return RT_FALSE;

    found++;
    while (*found && (isspace((unsigned char)*found) || *found == '"'))
    {
        found++;
    }

    *out_value = (float)strtod(found, NULL);
    return RT_TRUE;
}

static int parse_query_int(const char *query, const char *key, int default_value)
{
    if (!query || !key)
        return default_value;

    size_t key_len = strlen(key);
    const char *cursor = query;
    while (cursor && *cursor)
    {
        if (strncmp(cursor, key, key_len) == 0 && cursor[key_len] == '=')
        {
            return atoi(cursor + key_len + 1);
        }

        const char *next = strchr(cursor, '&');
        if (!next)
            break;
        cursor = next + 1;
    }
    return default_value;
}

void http_handler_init(void)
{
    web_state_init();
}

void http_handler_deinit(void)
{
    web_state_deinit();
}

int http_handle_static_request(int client_fd, const char *path)
{
    if (!path)
        return http_send_404(client_fd);

    if (strcmp(path, "/") == 0 || strcmp(path, "/index.html") == 0)
    {
        return http_send_binary(client_fd, "text/html; charset=utf-8",
                                STATIC_INDEX_HTML_DATA, STATIC_INDEX_HTML_LEN);
    }

    if (strcmp(path, "/app.js") == 0)
    {
        return http_send_binary(client_fd, "application/javascript; charset=utf-8",
                                STATIC_APP_JS_DATA, STATIC_APP_JS_LEN);
    }

    if (strncmp(path, "/detections/", 12) == 0)
    {
        char filepath[256];
        rt_snprintf(filepath, sizeof(filepath), "%s/%s", DETECTION_DIR, path + 12);
        return http_send_file(client_fd, filepath, "image/jpeg");
    }

    return http_send_404(client_fd);
}

static int http_send_status(int client_fd)
{
    // ⭐ 修复：增加缓冲区大小，避免 JSON 截断
    char json[1024];
    web_stats_info_t stats;
    web_state_get_stats(&stats);
    web_control_info_t ctrl;
    web_state_get_control_info(&ctrl);
    uint16_t record_count = web_state_get_record_count();

    // ⭐ 修复：直接使用足够大的缓冲区，避免截断问题
    // JSON 长度约 280 字节，使用 512 字节缓冲区足够，但为了安全使用 1024
    char *json_buf = json;
    size_t buf_size = sizeof(json);
    
    // ⭐ 关键修复：RT-Thread 内核的 rt_snprintf 不支持 %f 浮点数格式化
    // 即使启用了 RT_USING_LIBC，内核代码中仍然使用 rt_snprintf
    // 因此必须手动格式化浮点数为字符串
    // 如果值为 NaN 或 Inf，使用默认值 0.0
    float actual_conf = (ctrl.actual_confidence == ctrl.actual_confidence) ? ctrl.actual_confidence : 0.0f;
    float desired_conf = (ctrl.desired_confidence == ctrl.desired_confidence) ? ctrl.desired_confidence : 0.0f;
    float fps = (stats.fps == stats.fps) ? stats.fps : 0.0f; // NaN check: NaN != NaN is true
    
    // 手动格式化浮点数：转换为整数（保留2位小数）
    int actual_conf_int = (int)(actual_conf * 100.0f + 0.5f); // 四舍五入
    int desired_conf_int = (int)(desired_conf * 100.0f + 0.5f);
    int fps_int = (int)(fps * 100.0f + 0.5f);
    
    // 处理负数情况
    if (actual_conf_int < 0) actual_conf_int = 0;
    if (desired_conf_int < 0) desired_conf_int = 0;
    if (fps_int < 0) fps_int = 0;
    
    // 手动构建浮点数字符串 (例如: 0.50 -> "0.50")
    char actual_conf_str[16], desired_conf_str[16], fps_str[16];
    
    // 初始化并格式化字符串
    int actual_int = actual_conf_int / 100;
    int actual_frac = actual_conf_int % 100;
    if (actual_frac < 0) actual_frac = -actual_frac;
    rt_snprintf(actual_conf_str, sizeof(actual_conf_str), "%d.%02d", actual_int, actual_frac);
    
    int desired_int = desired_conf_int / 100;
    int desired_frac = desired_conf_int % 100;
    if (desired_frac < 0) desired_frac = -desired_frac;
    rt_snprintf(desired_conf_str, sizeof(desired_conf_str), "%d.%02d", desired_int, desired_frac);
    
    int fps_int_part = fps_int / 100;
    int fps_frac = fps_int % 100;
    if (fps_frac < 0) fps_frac = -fps_frac;
    rt_snprintf(fps_str, sizeof(fps_str), "%d.%02d", fps_int_part, fps_frac);
    
    // ⭐ 使用手动格式化的字符串，避免使用 %f
    int len = rt_snprintf(json, sizeof(json),
             "{\"success\":true,\"data\":{"
             "\"camera\":{\"running\":%s,\"desired\":%s},"
             "\"detection\":{\"enabled\":%s,\"desired\":%s},"
             "\"confidence\":{\"actual\":%s,\"desired\":%s},"
             "\"command_version\":%u,"
             "\"yolo_stats\":{\"fps\":%s,\"total_frames\":%u,\"total_detections\":%u},"
             "\"detection_stats\":{\"total_count\":%u}}}",
             ctrl.actual_camera_running ? "true" : "false",
             ctrl.desired_camera_running ? "true" : "false",
             ctrl.actual_detection_enabled ? "true" : "false",
             ctrl.desired_detection_enabled ? "true" : "false",
             actual_conf_str,
             desired_conf_str,
             ctrl.command_version,
             fps_str,
             stats.total_frames,
             stats.total_detections,
             record_count);
    
    // 检查格式化是否成功
    if (len < 0)
    {
        return http_send_json(client_fd, "{\"success\":false,\"message\":\"Format error\"}");
    }
    
    // ⭐ 修复：检查缓冲区是否足够，如果截断或刚好填满则使用更大的缓冲区
    // snprintf 返回应该写入的字节数（不包括 \0），如果 >= buf_size-1 说明被截断
    if (len >= (int)buf_size - 1)
    {
        // 缓冲区不足，使用动态分配
        buf_size = 2048;
        json_buf = (char *)rt_malloc(buf_size);
        if (!json_buf)
        {
            return http_send_json(client_fd, "{\"success\":false,\"message\":\"Memory error\"}");
        }
        
        len = rt_snprintf(json_buf, buf_size,
                 "{\"success\":true,\"data\":{"
                 "\"camera\":{\"running\":%s,\"desired\":%s},"
                 "\"detection\":{\"enabled\":%s,\"desired\":%s},"
                 "\"confidence\":{\"actual\":%s,\"desired\":%s},"
                 "\"command_version\":%u,"
                 "\"yolo_stats\":{\"fps\":%s,\"total_frames\":%u,\"total_detections\":%u},"
                 "\"detection_stats\":{\"total_count\":%u}}}",
                 ctrl.actual_camera_running ? "true" : "false",
                 ctrl.desired_camera_running ? "true" : "false",
                 ctrl.actual_detection_enabled ? "true" : "false",
                 ctrl.desired_detection_enabled ? "true" : "false",
                 actual_conf_str,
                 desired_conf_str,
                 ctrl.command_version,
                 fps_str,
                 stats.total_frames,
                 stats.total_detections,
                 record_count);
        
        // 如果仍然截断或失败，返回错误
        if (len < 0 || len >= (int)buf_size - 1)
        {
            rt_free(json_buf);
            return http_send_json(client_fd, "{\"success\":false,\"message\":\"JSON format error\"}");
        }
    }
    
    int ret = http_send_json(client_fd, json_buf);
    if (json_buf != json)
    {
        rt_free(json_buf);
    }
    return ret;
}

static int http_send_records(int client_fd, const char *query)
{
    int limit = parse_query_int(query, "limit", WEB_STATE_MAX_RECORDS);
    if (limit <= 0 || limit > WEB_STATE_MAX_RECORDS)
    {
        limit = WEB_STATE_MAX_RECORDS;
    }

    web_record_info_t records[WEB_STATE_MAX_RECORDS];
    uint16_t count = web_state_get_records(records, limit);

    size_t buf_size = 256 + count * 256;
    char *json = (char *)rt_malloc(buf_size);
    if (!json)
    {
        return http_send_response(client_fd, 500, "application/json",
                                  "{\"success\":false,\"message\":\"OOM\"}", 47);
    }

    size_t offset = snprintf(json, buf_size, "{\"success\":true,\"data\":[");
    for (uint16_t i = 0; i < count; i++)
    {
        offset += snprintf(json + offset, buf_size - offset,
                           "%s{\"id\":%u,\"filename\":\"%s\",\"time_str\":\"%s\",\"confidence\":%.3f}",
                           (i == 0) ? "" : ",",
                           records[i].id,
                           records[i].filename,
                           records[i].time_str,
                           records[i].confidence);
    }
    snprintf(json + offset, buf_size - offset, "]}");

    int rc = http_send_json(client_fd, json);
    rt_free(json);
    return rc;
}

int http_handle_api_request(int client_fd,
                            const char *method,
                            const char *path,
                            const char *query,
                            const char *body)
{
    if (!method || !path)
        return http_send_response(client_fd, 400, "application/json",
                                  "{\"success\":false,\"message\":\"Bad request\"}", 53);

    if (strcmp(path, "/api/status") == 0 && strcmp(method, "GET") == 0)
    {
        return http_send_status(client_fd);
    }

    if (strcmp(path, "/api/camera/start") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_request_camera(RT_TRUE);
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strcmp(path, "/api/camera/stop") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_request_camera(RT_FALSE);
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strcmp(path, "/api/detection/enable") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_request_detection(RT_TRUE);
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strcmp(path, "/api/detection/disable") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_request_detection(RT_FALSE);
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strcmp(path, "/api/config/confidence") == 0 && strcmp(method, "POST") == 0)
    {
        float value = web_state_get_requested_confidence();
        parse_json_float(body, "value", &value);
        web_state_request_confidence(value);
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strcmp(path, "/api/records") == 0 && strcmp(method, "GET") == 0)
    {
        return http_send_records(client_fd, query);
    }

    if (strcmp(path, "/api/records/clear") == 0 && strcmp(method, "POST") == 0)
    {
        web_state_clear_records();
        return http_send_json(client_fd, "{\"success\":true}");
    }

    if (strncmp(path, "/api/records/", 13) == 0 && strcmp(method, "DELETE") == 0)
    {
        uint32_t id = (uint32_t)strtoul(path + 13, NULL, 10);
        rt_bool_t removed = web_state_delete_record(id);
        return http_send_json(client_fd, removed ? "{\"success\":true}"
                                                 : "{\"success\":false,\"message\":\"Record not found\"}");
    }

    return http_send_404(client_fd);
}

int http_handle_mjpeg_stream(int client_fd)
{
    uint8_t *jpeg_data = NULL;
    size_t jpeg_size = 0;
    char boundary_header[256];
    int frame_count = 0;
    int frame_interval_ms = 1000 / MAX_FPS;
    rt_uint32_t last_send_ms = 0;
    rt_uint32_t stream_start_ms = http_get_tick_ms();
    rt_uint32_t last_frame_time_ms = 0;
    int no_frame_count = 0;
    const char *stream_header =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: multipart/x-mixed-replace; boundary=" MJPEG_BOUNDARY "\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-cache, no-store, must-revalidate\r\n"
        "\r\n";

    if (send(client_fd, stream_header, strlen(stream_header), 0) < 0)
    {
        rt_kprintf("[MJPEG] Failed to send header\n");
        return -1;
    }

    rt_kprintf("[MJPEG] Stream started @ %d fps\n", MAX_FPS);

    while (1)
    {
        rt_uint32_t now = http_get_tick_ms();
        
        // 检查是否太久没有收到帧（超时保护）
        if (frame_count == 0)
        {
            // 首次连接，等待最多5秒
            if (now - stream_start_ms > 5000)
            {
                rt_kprintf("[MJPEG] Timeout: No frames received in 5s, closing stream\n");
                break;
            }
        }
        else
        {
            // 已有帧后，如果超过3秒没有新帧，关闭流
            if (last_frame_time_ms > 0 && (now - last_frame_time_ms) > 3000)
            {
                rt_kprintf("[MJPEG] Timeout: No new frames for 3s, closing stream\n");
                break;
            }
        }
        
        // 控制发送频率
        if (now - last_send_ms < (rt_uint32_t)frame_interval_ms)
        {
            rt_thread_mdelay(5);
            continue;
        }

        // 尝试获取最新帧
        if (frame_buffer_get_latest(&jpeg_data, &jpeg_size) != 0)
        {
            no_frame_count++;
            if (no_frame_count == 1)
            {
                rt_kprintf("[MJPEG] Waiting for frames...\n");
            }
            else if (no_frame_count % 100 == 0)
            {
                rt_kprintf("[MJPEG] Still waiting for frames (count=%d)\n", no_frame_count);
            }
            
            rt_thread_mdelay(10);
            continue;
        }

        // 成功获取到帧
        no_frame_count = 0;
        last_frame_time_ms = now;

        int len = snprintf(boundary_header, sizeof(boundary_header),
                           "\r\n--" MJPEG_BOUNDARY "\r\n"
                           "Content-Type: image/jpeg\r\n"
                           "Content-Length: %zu\r\n"
                           "\r\n",
                           jpeg_size);

        if (send(client_fd, boundary_header, len, 0) < 0)
        {
            rt_kprintf("[MJPEG] Client disconnected (boundary)\n");
            break;
        }

        if (send(client_fd, jpeg_data, jpeg_size, 0) < 0)
        {
            rt_kprintf("[MJPEG] Client disconnected (data)\n");
            break;
        }

        frame_count++;
        last_send_ms = now;

        if (frame_count == 1)
        {
            rt_kprintf("[MJPEG] First frame sent, size=%zu bytes\n", jpeg_size);
        }
        else if (frame_count % 100 == 0)
        {
            rt_kprintf("[MJPEG] Sent %d frames\n", frame_count);
        }
    }

    rt_kprintf("[MJPEG] Stream ended, sent %d frames\n", frame_count);
    return 0;
}

int http_handle_snapshot(int client_fd)
{
    uint8_t *jpeg_data = NULL;
    size_t jpeg_size = 0;
    char header[128];

    if (frame_buffer_get_latest(&jpeg_data, &jpeg_size) != 0)
    {
        const char *error = "No frame available";
        return http_send_response(client_fd, 503, "text/plain", error, strlen(error));
    }

    int header_len = snprintf(header, sizeof(header),
                              "HTTP/1.1 200 OK\r\n"
                              "Content-Type: image/jpeg\r\n"
                              "Content-Length: %zu\r\n"
                              "Connection: close\r\n"
                              "\r\n",
                              jpeg_size);

    if (send(client_fd, header, header_len, 0) < 0)
    {
        return -1;
    }

    if (send(client_fd, jpeg_data, jpeg_size, 0) < 0)
    {
        return -1;
    }

    rt_kprintf("[Snapshot] Sent %zu bytes\n", jpeg_size);
    return 0;
}

int http_send_404(int client_fd)
{
    const char *body = "404 Not Found";
    return http_send_response(client_fd, 404, "text/plain", body, strlen(body));
}
