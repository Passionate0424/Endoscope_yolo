#ifndef HTTP_HANDLER_H
#define HTTP_HANDLER_H

// HTTP 请求处理函数
int http_handle_index(int client_fd);
int http_handle_mjpeg_stream(int client_fd);
int http_handle_snapshot(int client_fd);
int http_handle_api(int client_fd, const char* request, int request_len);
int http_send_404(int client_fd);

#endif // HTTP_HANDLER_H
