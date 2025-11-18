from libs.PipeLine import PipeLine
from libs.YOLO import YOLOv5
from libs.Utils import *
import os, sys, gc
import ulab.numpy as np
import image

# --------- 可按需修改的配置 ----------
KMODEL_PATH = "/data/model.kmodel"          # 你的 kmodel 路径
LABELS = ["polyp"]                          # 如果有多类别就扩展这个列表
MODEL_INPUT_SIZE = [640, 640]               # 与导出的 kmodel 保持一致
DISPLAY_MODE = "lcd"                        # hdmi/lcd/lt9611/st7701/hx8399
RGB888P_SIZE = [640, 360]                   # 相机输入尺寸
CONF_THRESHOLD = 0.35                       # 置信度阈值
NMS_THRESHOLD = 0.45                        # NMS 阈值
# --------------------------------------

def main():
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=DISPLAY_MODE)
    pl.create()
    display_size = pl.get_display_size()

    yolo = YOLOv5(
        task_type="detect",
        mode="video",
        kmodel_path=KMODEL_PATH,
        labels=LABELS,
        rgb888p_size=RGB888P_SIZE,
        model_input_size=MODEL_INPUT_SIZE,
        display_size=display_size,
        conf_thresh=CONF_THRESHOLD,
        nms_thresh=NMS_THRESHOLD,
        debug_mode=0
    )
    yolo.config_preprocess()

    try:
        while True:
            with ScopedTiming("total", 1):
                frame = pl.get_frame()
                results = yolo.run(frame)
                yolo.draw_result(results, pl.osd_img)
                pl.show_image()
                gc.collect()
    finally:
        yolo.deinit()
        pl.destroy()

if __name__ == "__main__":
    main()