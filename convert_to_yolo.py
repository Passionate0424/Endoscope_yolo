"""
将 Kvasir-SEG 数据集转换为 YOLO 格式
"""
import os
import csv
import cv2
import yaml
from pathlib import Path
from tqdm import tqdm

# 配置路径
DATASET_ROOT = Path("datasheet/Kvasir-SEG/Kvasir-SEG")
IMAGES_DIR = DATASET_ROOT / "images"
BBOX_DIR = DATASET_ROOT / "bbox"
TRAIN_TXT = Path("datasheet/train.txt")
VAL_TXT = Path("datasheet/val.txt")

# 输出路径
OUTPUT_ROOT = Path("datasheet/Kvasir-SEG-YOLO")
OUTPUT_IMAGES_TRAIN = OUTPUT_ROOT / "images" / "train"
OUTPUT_IMAGES_VAL = OUTPUT_ROOT / "images" / "val"
OUTPUT_LABELS_TRAIN = OUTPUT_ROOT / "labels" / "train"
OUTPUT_LABELS_VAL = OUTPUT_ROOT / "labels" / "val"

# 创建输出目录
OUTPUT_IMAGES_TRAIN.mkdir(parents=True, exist_ok=True)
OUTPUT_IMAGES_VAL.mkdir(parents=True, exist_ok=True)
OUTPUT_LABELS_TRAIN.mkdir(parents=True, exist_ok=True)
OUTPUT_LABELS_VAL.mkdir(parents=True, exist_ok=True)


def load_image_ids(txt_file):
    """从txt文件加载图片ID列表"""
    with open(txt_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def convert_bbox_to_yolo(xmin, ymin, xmax, ymax, img_width, img_height):
    """
    将边界框坐标从 (xmin, ymin, xmax, ymax) 转换为 YOLO 格式 (x_center, y_center, width, height)
    坐标需要归一化到 0-1
    """
    # 计算中心点和宽高
    x_center = (xmin + xmax) / 2.0
    y_center = (ymin + ymax) / 2.0
    width = xmax - xmin
    height = ymax - ymin
    
    # 归一化
    x_center /= img_width
    y_center /= img_height
    width /= img_width
    height /= img_height
    
    return x_center, y_center, width, height


def get_class_id(class_name, class_map):
    """获取类别ID，如果不存在则添加"""
    if class_name not in class_map:
        class_map[class_name] = len(class_map)
    return class_map[class_name]


def convert_dataset(image_ids, split_name, class_map):
    """转换数据集"""
    images_dir = OUTPUT_IMAGES_TRAIN if split_name == "train" else OUTPUT_IMAGES_VAL
    labels_dir = OUTPUT_LABELS_TRAIN if split_name == "train" else OUTPUT_LABELS_VAL
    
    converted_count = 0
    skipped_count = 0
    
    for img_id in tqdm(image_ids, desc=f"Converting {split_name}"):
        # 源文件路径
        img_path = IMAGES_DIR / f"{img_id}.jpg"
        csv_path = BBOX_DIR / f"{img_id}.csv"
        
        # 检查文件是否存在
        if not img_path.exists():
            print(f"Warning: Image not found: {img_path}")
            skipped_count += 1
            continue
        
        if not csv_path.exists():
            print(f"Warning: CSV not found: {csv_path}")
            skipped_count += 1
            continue
        
        # 读取图片获取尺寸
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Warning: Cannot read image: {img_path}")
            skipped_count += 1
            continue
        
        img_height, img_width = img.shape[:2]
        
        # 读取CSV标注
        annotations = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    class_name = row['class_name'].strip()
                    xmin = int(row['xmin'])
                    ymin = int(row['ymin'])
                    xmax = int(row['xmax'])
                    ymax = int(row['ymax'])
                    
                    # 转换为YOLO格式
                    x_center, y_center, width, height = convert_bbox_to_yolo(
                        xmin, ymin, xmax, ymax, img_width, img_height
                    )
                    
                    # 获取类别ID
                    class_id = get_class_id(class_name, class_map)
                    
                    annotations.append((class_id, x_center, y_center, width, height))
        except Exception as e:
            print(f"Error reading CSV {csv_path}: {e}")
            skipped_count += 1
            continue
        
        # 复制图片到输出目录
        output_img_path = images_dir / f"{img_id}.jpg"
        cv2.imwrite(str(output_img_path), img)
        
        # 创建YOLO格式的标注文件
        label_path = labels_dir / f"{img_id}.txt"
        with open(label_path, 'w', encoding='utf-8') as f:
            for class_id, x_center, y_center, width, height in annotations:
                f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
        
        converted_count += 1
    
    return converted_count, skipped_count


def create_yaml_config(class_map, output_path):
    """创建YOLO配置文件"""
    # 反转类别映射，从ID到名称
    id_to_name = {v: k for k, v in class_map.items()}
    
    # 获取绝对路径
    dataset_path = OUTPUT_ROOT.absolute()
    
    config = {
        'path': str(dataset_path),
        'train': 'images/train',
        'val': 'images/val',
        'nc': len(class_map),
        'names': id_to_name
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    
    print(f"\nYAML config saved to: {output_path}")
    print(f"Classes: {id_to_name}")


def main():
    print("=" * 60)
    print("Kvasir-SEG to YOLO Format Converter")
    print("=" * 60)
    
    # 加载数据集分割
    print("\n1. Loading dataset splits...")
    train_ids = load_image_ids(TRAIN_TXT)
    val_ids = load_image_ids(VAL_TXT)
    print(f"   Train images: {len(train_ids)}")
    print(f"   Val images: {len(val_ids)}")
    
    # 类别映射
    class_map = {}
    
    # 转换训练集
    print("\n2. Converting training set...")
    train_converted, train_skipped = convert_dataset(train_ids, "train", class_map)
    
    # 转换验证集
    print("\n3. Converting validation set...")
    val_converted, val_skipped = convert_dataset(val_ids, "val", class_map)
    
    # 创建配置文件
    print("\n4. Creating YAML configuration...")
    yaml_path = OUTPUT_ROOT / "data.yaml"
    create_yaml_config(class_map, yaml_path)
    
    # 输出统计信息
    print("\n" + "=" * 60)
    print("Conversion Summary")
    print("=" * 60)
    print(f"Train: {train_converted} converted, {train_skipped} skipped")
    print(f"Val: {val_converted} converted, {val_skipped} skipped")
    print(f"Total classes: {len(class_map)}")
    print(f"Output directory: {OUTPUT_ROOT.absolute()}")
    print(f"YAML config: {yaml_path.absolute()}")
    print("=" * 60)
    print("\n✅ Conversion completed!")
    print(f"\nYou can now train YOLOv5 with:")
    print(f"  python yolov5/train.py --data {yaml_path.absolute()} --weights yolov5s.pt --img 640 --epochs 100")


if __name__ == "__main__":
    main()


