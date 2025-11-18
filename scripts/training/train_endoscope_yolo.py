"""
训练脚本 - 内窥镜息肉检测 YOLOv5 模型
使用 Kvasir-SEG 数据集训练 YOLOv5 模型

注意：YOLOv5 默认会启用 TensorBoard 日志记录
训练完成后，可以使用以下命令查看 TensorBoard：
    cd yolov5_project
    tensorboard --logdir runs/train
"""
import subprocess
import sys
from pathlib import Path

# 配置参数
YOLOV5_DIR = Path("yolov5_project")
DATA_YAML = YOLOV5_DIR / "data" / "Kvasir-SEG.yaml"
WEIGHTS = "yolov5s.pt"  # 可选: yolov5n.pt, yolov5s.pt, yolov5m.pt, yolov5l.pt, yolov5x.pt
IMG_SIZE = 640
EPOCHS = 1000
BATCH_SIZE = 16
DEVICE = ""  # 空字符串表示自动选择，或指定 "0", "0,1" 等

# 检查数据集配置文件是否存在
if not DATA_YAML.exists():
    print(f"错误: 数据集配置文件不存在: {DATA_YAML}")
    print("请确保数据集已转换并配置文件已创建")
    sys.exit(1)

# 构建训练命令（注意：切换到yolov5_project目录后，路径需要调整）
train_cmd = [
    sys.executable,
    "train.py",  # 相对路径，因为会切换到yolov5_project目录
    "--data", "data/Kvasir-SEG.yaml",  # 相对路径
    "--weights", WEIGHTS,
    "--img", str(IMG_SIZE),
    "--epochs", str(EPOCHS),
    "--batch", str(BATCH_SIZE),
    "--device", DEVICE if DEVICE else "0",
    "--name", "endoscope_polyp_detection",
    "--project", "runs/train",
]

print("=" * 60)
print("开始训练 YOLOv5 内窥镜息肉检测模型")
print("=" * 60)
print(f"数据集: {DATA_YAML}")
print(f"预训练权重: {WEIGHTS} (如果不存在会自动下载)")
print(f"图片尺寸: {IMG_SIZE}")
print(f"训练轮数: {EPOCHS}")
print(f"批次大小: {BATCH_SIZE}")
print(f"设备: {DEVICE if DEVICE else '自动选择'}")
print("=" * 60)
print()

# 切换到yolov5目录执行训练
import os
original_dir = os.getcwd()
try:
    os.chdir(YOLOV5_DIR)
    print(f"工作目录: {os.getcwd()}")
    print(f"执行命令: {' '.join(train_cmd)}")
    print()
    
    # 执行训练
    result = subprocess.run(train_cmd, check=False)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("✅ 训练完成！")
        print("=" * 60)
        print(f"模型保存在: {YOLOV5_DIR / 'runs' / 'train' / 'endoscope_polyp_detection'}")
        print(f"\n📊 查看 TensorBoard 可视化：")
        print(f"   cd {YOLOV5_DIR}")
        print(f"   tensorboard --logdir runs/train")
        print(f"   然后在浏览器中打开: http://localhost:6006")
    else:
        print("\n" + "=" * 60)
        print("❌ 训练失败，请检查错误信息")
        print("=" * 60)
        sys.exit(result.returncode)
finally:
    os.chdir(original_dir)


