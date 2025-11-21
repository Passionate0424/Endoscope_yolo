#ifndef HTTP_HANDLER_H
#define HTTP_HANDLER_H

void http_handler_init(void);
void http_handler_deinit(void);

int http_handle_static_request(int client_fd, const char *path);
int http_handle_mjpeg_stream(int client_fd);
int http_handle_snapshot(int client_fd);
int http_handle_api_request(int client_fd,
                            const char *method,
                            const char *path,
                            const char *query,
                            const char *body);
int http_send_404(int client_fd);

#endif // HTTP_HANDLER_H
