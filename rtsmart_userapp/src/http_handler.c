/*
 * HTTP 请求处理器
 * 处理不同类型的 HTTP 请求（MJPEG 流、快照、API 等）
 */

#include "http_handler.h"
#include "frame_buffer.h"
#include <rtthread.h>
#include <sys/socket.h>
#include <string.h>
#include <stdio.h>

#define MJPEG_BOUNDARY "frame"
#define MAX_FPS 30

// HTML 主页
static const char INDEX_HTML[] =
    "<!DOCTYPE html>\n"
    "<html>\n"
    "<head>\n"
    "    <meta charset='UTF-8'>\n"
    "    <title>K230 Endoscope</title>\n"
    "    <style>\n"
    "        body { font-family: Arial; text-align: center; background: #222; color: #fff; }\n"
    "        img { max-width: 90%; height: auto; border: 2px solid #fff; }\n"
    "        .btn { padding: 10px 20px; margin: 10px; font-size: 16px; }\n"
    "    </style>\n"
    "</head>\n"
    "<body>\n"
    "    <h1>K230 Endoscope Platform</h1>\n"
    "    <img src='/stream' />\n"
    "    <div>\n"
    "        <button class='btn' onclick='fetch(\"/api/detection/enable\", {method:\"POST\"})'>Enable Detection</button>\n"
    "        <button class='btn' onclick='fetch(\"/api/detection/disable\", {method:\"POST\"})'>Disable Detection</button>\n"
    "    </div>\n"
    "</body>\n"
    "</html>";

// 发送 HTTP 响应
static int http_send_response(int fd, int status, const char *content_type,
                              const char *body, int body_len)
{
    char header[512];
    const char *status_text = "OK";

    if (status == 404)
        status_text = "Not Found";
    else if (status == 500)
        status_text = "Internal Server Error";

    int header_len = snprintf(header, sizeof(header),
                              "HTTP/1.1 %d %s\r\n"
                              "Content-Type: %s\r\n"
                              "Content-Length: %d\r\n"
                              "Connection: close\r\n"
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

// 处理主页请求
int http_handle_index(int client_fd)
{
    return http_send_response(client_fd, 200, "text/html",
                              INDEX_HTML, strlen(INDEX_HTML));
}

// 处理 MJPEG 流请求
int http_handle_mjpeg_stream(int client_fd)
{
    uint8_t *jpeg_data = NULL;
    size_t jpeg_size = 0;
    char boundary_header[256];
    int frame_count = 0;
    int frame_interval_ms = 1000 / MAX_FPS;
    rt_tick_t last_send_time = 0;

    // 发送 MJPEG 响应头
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

    // 流式发送循环
    while (1)
    {
        // 帧率控制
        rt_tick_t now = rt_tick_get();
        if (rt_tick_get_millisecond() - rt_tick_get_millisecond(last_send_time) < frame_interval_ms)
        {
            rt_thread_mdelay(5);
            continue;
        }

        // 获取最新帧
        if (frame_buffer_get_latest(&jpeg_data, &jpeg_size) != 0)
        {
            rt_thread_mdelay(10);
            continue;
        }

        // 发送 boundary
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

        // 发送 JPEG 数据
        if (send(client_fd, jpeg_data, jpeg_size, 0) < 0)
        {
            rt_kprintf("[MJPEG] Client disconnected (data)\n");
            break;
        }

        frame_count++;
        last_send_time = now;

        if (frame_count % 100 == 0)
        {
            rt_kprintf("[MJPEG] Sent %d frames\n", frame_count);
        }
    }

    rt_kprintf("[MJPEG] Stream ended, sent %d frames\n", frame_count);
    return 0;
}

// 处理快照请求
int http_handle_snapshot(int client_fd)
{
    uint8_t *jpeg_data = NULL;
    size_t jpeg_size = 0;
    char header[256];

    if (frame_buffer_get_latest(&jpeg_data, &jpeg_size) != 0)
    {
        const char *error = "No frame available";
        return http_send_response(client_fd, 503, "text/plain",
                                  error, strlen(error));
    }

    // 发送响应头
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

    // 发送 JPEG 数据
    if (send(client_fd, jpeg_data, jpeg_size, 0) < 0)
    {
        return -1;
    }

    rt_kprintf("[Snapshot] Sent %zu bytes\n", jpeg_size);
    return 0;
}

// 处理 API 请求（预留接口，由 Python 层处理具体业务）
int http_handle_api(int client_fd, const char *request, int request_len)
{
    // 简单返回 JSON
    const char *json = "{\"success\":true,\"message\":\"API handled by Python\"}";
    return http_send_response(client_fd, 200, "application/json",
                              json, strlen(json));
}

// 发送 404 响应
int http_send_404(int client_fd)
{
    const char *body = "404 Not Found";
    return http_send_response(client_fd, 404, "text/plain",
                              body, strlen(body));
}
