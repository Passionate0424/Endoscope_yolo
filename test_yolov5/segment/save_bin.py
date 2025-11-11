import os
import cv2
import numpy as np
from PIL import Image
import argparse
import math


def save_bin(img_path, img_name, save_path, mean, std, img_size):
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    image_fp32=cv2.imread(img_path)
    image_fp32=cv2.cvtColor(image_fp32, cv2.COLOR_BGR2RGB)
    image_fp32 = cv2.resize(image_fp32, (img_size[3], img_size[2]))
    image_fp32 = np.asarray(image_fp32, dtype=np.float32)
    image_fp32/=255.0
    for i in range(3):
        image_fp32[:, :, i] -= mean[i]
        image_fp32[:, :, i] /= std[i]
    image_fp32 = np.transpose(image_fp32, (2, 0, 1))
    fp32_bin_file = os.path.join(save_path, "onnx_input_float32.bin")  # 保存 FP32 二进制文件的路径
    image_fp32.tofile(fp32_bin_file)

    image_uint8=cv2.imread(img_path)
    image_uint8=cv2.cvtColor(image_uint8, cv2.COLOR_BGR2RGB)
    image_uint8 = cv2.resize(image_uint8, (img_size[3], img_size[2]))
    image_uint8 = np.asarray(image_uint8, dtype=np.uint8)
    image_uint8 = np.transpose(image_uint8, (2, 0, 1))
    uint8_bin_file = os.path.join(save_path, "kmodel_input_uint8.bin")  # 保存 UINT8 二进制文件的路径
    image_uint8.tofile(uint8_bin_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog="nncase")
    parser.add_argument("--image",type=str, help='image path')
    parser.add_argument("--save_path",type=str, default=".",help='bin file save path')
    parser.add_argument("--input_width", type=int, default=320, help='input_width')
    parser.add_argument("--input_height", type=int, default=320, help='input_height')

    args = parser.parse_args()

    # 更新参数为32倍数
    input_width = int(math.ceil(args.input_width / 32.0)) * 32
    input_height = int(math.ceil(args.input_height / 32.0)) * 32

    save_bin(args.image, '', args.save_path, mean=[0, 0, 0],
             std=[1,1,1], img_size=[1, 3, input_height, input_width])
