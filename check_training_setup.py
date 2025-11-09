"""检查训练环境配置"""
import yaml
from pathlib import Path

print("=" * 60)
print("检查训练环境配置")
print("=" * 60)

# 检查数据集配置
yaml_path = Path("yolov5_project/data/Kvasir-SEG.yaml")
print(f"\n1. 数据集配置文件: {yaml_path}")
if yaml_path.exists():
    print("   ✅ 配置文件存在")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    print(f"   - 数据集路径: {data['path']}")
    print(f"   - 训练集: {data['train']}")
    print(f"   - 验证集: {data['val']}")
    print(f"   - 类别数: {data['nc']}")
    print(f"   - 类别名称: {data['names']}")
    
    # 检查实际路径
    dataset_root = Path(data['path']).resolve()
    print(f"\n2. 数据集路径检查:")
    print(f"   完整路径: {dataset_root}")
    if dataset_root.exists():
        print("   ✅ 数据集根目录存在")
        
        train_dir = dataset_root / data['train']
        val_dir = dataset_root / data['val']
        train_labels = dataset_root / "labels" / "train"
        val_labels = dataset_root / "labels" / "val"
        
        print(f"\n3. 数据文件检查:")
        if train_dir.exists():
            train_imgs = list(train_dir.glob("*.jpg"))
            print(f"   ✅ 训练图片目录存在: {len(train_imgs)} 张图片")
        else:
            print(f"   ❌ 训练图片目录不存在: {train_dir}")
        
        if val_dir.exists():
            val_imgs = list(val_dir.glob("*.jpg"))
            print(f"   ✅ 验证图片目录存在: {len(val_imgs)} 张图片")
        else:
            print(f"   ❌ 验证图片目录不存在: {val_dir}")
        
        if train_labels.exists():
            train_labels_count = list(train_labels.glob("*.txt"))
            print(f"   ✅ 训练标注目录存在: {len(train_labels_count)} 个标注文件")
        else:
            print(f"   ❌ 训练标注目录不存在: {train_labels}")
        
        if val_labels.exists():
            val_labels_count = list(val_labels.glob("*.txt"))
            print(f"   ✅ 验证标注目录存在: {len(val_labels_count)} 个标注文件")
        else:
            print(f"   ❌ 验证标注目录不存在: {val_labels}")
    else:
        print(f"   ❌ 数据集根目录不存在: {dataset_root}")
else:
    print("   ❌ 配置文件不存在")

# 检查YOLOv5项目
yolov5_dir = Path("yolov5_project")
print(f"\n4. YOLOv5项目目录: {yolov5_dir}")
if yolov5_dir.exists():
    print("   ✅ YOLOv5项目目录存在")
    train_py = yolov5_dir / "train.py"
    if train_py.exists():
        print("   ✅ train.py 存在")
    else:
        print("   ❌ train.py 不存在")
else:
    print("   ❌ YOLOv5项目目录不存在")

# 检查权重文件（可选，会自动下载）
print(f"\n5. 预训练权重检查:")
weights_file = yolov5_dir / "yolov5s.pt"
if weights_file.exists():
    print(f"   ✅ 权重文件存在: {weights_file}")
    print(f"   文件大小: {weights_file.stat().st_size / 1024 / 1024:.2f} MB")
else:
    print(f"   ⚠️  权重文件不存在: {weights_file}")
    print("   （训练时会自动下载）")

print("\n" + "=" * 60)
print("检查完成！")
print("=" * 60)


