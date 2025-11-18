"""
从训练结果 CSV 文件生成 TensorBoard 事件文件
用于可视化已完成的训练过程
"""
import pandas as pd
import sys
from pathlib import Path
from torch.utils.tensorboard import SummaryWriter

def create_tensorboard_logs_from_csv(csv_path, output_dir=None):
    """
    从 CSV 文件读取训练结果并生成 TensorBoard 事件文件
    
    Args:
        csv_path: results.csv 文件路径
        output_dir: 输出目录（如果为 None，则在 CSV 文件同一目录）
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"错误: CSV 文件不存在: {csv_path}")
        return False
    
    # 确定输出目录
    if output_dir is None:
        output_dir = csv_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"读取 CSV 文件: {csv_path}")
    print(f"输出目录: {output_dir}")
    
    # 读取 CSV 文件
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"错误: 无法读取 CSV 文件: {e}")
        return False
    
    # 清理列名（去除前后空格）
    df.columns = df.columns.str.strip()
    
    print(f"找到 {len(df)} 个训练 epoch")
    print(f"指标列: {list(df.columns)}")
    
    # 创建 TensorBoard SummaryWriter
    writer = SummaryWriter(log_dir=str(output_dir))
    
    try:
        # 遍历每一行（每个 epoch）
        for idx, row in df.iterrows():
            # 获取 epoch 值（处理可能的空格）
            epoch_col = [col for col in df.columns if 'epoch' in col.lower()][0]
            epoch = int(row[epoch_col])
            
            # 记录所有指标
            for col in df.columns:
                if 'epoch' in col.lower():
                    continue
                
                try:
                    value = float(row[col])
                    # 清理指标名称（去除多余空格）
                    metric_name = col.strip()
                    writer.add_scalar(metric_name, value, epoch)
                except (ValueError, TypeError) as e:
                    # 跳过无法转换的值
                    continue
        
        print(f"✅ 成功生成 TensorBoard 事件文件")
        print(f"   事件文件保存在: {output_dir}")
        print(f"   使用命令查看: tensorboard --logdir {output_dir.parent}")
        return True
        
    except Exception as e:
        print(f"错误: 生成 TensorBoard 日志时出错: {e}")
        return False
    finally:
        writer.close()


if __name__ == "__main__":
    # 默认使用最新的训练结果
    default_csv = Path("yolov5_project/runs/train/endoscope_polyp_detection4/results.csv")
    
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        csv_path = default_csv
    
    if not csv_path.exists():
        print(f"错误: CSV 文件不存在: {csv_path}")
        print(f"用法: python create_tensorboard_logs.py [csv_file_path]")
        sys.exit(1)
    
    success = create_tensorboard_logs_from_csv(csv_path)
    sys.exit(0 if success else 1)

