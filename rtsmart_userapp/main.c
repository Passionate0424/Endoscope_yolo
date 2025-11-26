#include <rtthread.h>
#include <stdlib.h>
#include <string.h>

#include "http_server.h"
#include "web_state.h"
#include "yolo_thread.h"

#define LOG_TAG "[MAIN]"
#define KMODEL_PATH "/data/model.kmodel"
#define LABELS_PATH "/data/labels.txt"

static void log_line(const char *msg)
{
    rt_kprintf("%s %s\n", LOG_TAG, msg);
}

int main(void)
{
    log_line("starting C-only HTTP + YOLO firmware");

    /* initialize web state and HTTP server */
    if (http_server_init() != 0)
    {
        log_line("http_server_init failed");
        return -1;
    }
    log_line("http server ready on port 8080");

    /* init and start YOLO thread */
    if (yolo_thread_init(KMODEL_PATH, LABELS_PATH) != 0)
    {
        log_line("yolo_thread_init failed (check kmodel/labels paths)");
    }
    else
    {
        if (yolo_thread_start() == 0)
        {
            log_line("yolo thread started");
        }
        else
        {
            log_line("yolo_thread_start failed");
        }
    }

    /* main heartbeat loop */
    while (1)
    {
        rt_thread_mdelay(1000);
    }

    return 0;
}
