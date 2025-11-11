"""
恢复训练脚本 - 从上次中断的地方继续训练
"""
import subprocess
import sys
from pathlib import Path

# 配置参数
YOLOV5_DIR = Path("yolov5_project")
LAST_CHECKPOINT = YOLOV5_DIR / "runs" / "train" / "endoscope_polyp_detection" / "weights" / "last.pt"

print("=" * 60)
print("恢复 YOLOv5 训练")
print("=" * 60)

# 检查检查点文件是否存在
if not LAST_CHECKPOINT.exists():
    print(f"❌ 检查点文件不存在: {LAST_CHECKPOINT}")
    print("请先运行训练，或者检查训练输出目录")
    sys.exit(1)

print(f"✅ 找到检查点文件: {LAST_CHECKPOINT}")
print(f"   文件大小: {LAST_CHECKPOINT.stat().st_size / 1024 / 1024:.2f} MB")
print()

# 构建恢复训练命令
train_cmd = [
    sys.executable,
    "train.py",
    "--resume", str(LAST_CHECKPOINT.relative_to(YOLOV5_DIR)),
    "--data", "data/Kvasir-SEG.yaml",
    "--img", "640",
    "--epochs", "100",
    "--batch", "16",
    "--device", "0",
    "--name", "endoscope_polyp_detection",
]

print("恢复训练命令:")
print(f"  {' '.join(train_cmd)}")
print("=" * 60)
print()

# 切换到yolov5目录执行训练
import os
original_dir = os.getcwd()
try:
    os.chdir(YOLOV5_DIR)
    print(f"工作目录: {os.getcwd()}")
    print()
    
    # 执行训练
    result = subprocess.run(train_cmd, check=False)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("✅ 训练完成！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 训练中断或失败")
        print("=" * 60)
        sys.exit(result.returncode)
finally:
    os.chdir(original_dir)







