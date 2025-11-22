#!/usr/bin/env python3
"""
生成静态资源 .inc 文件
将 HTML/JS 文件转换为 C 数组格式
"""

import os
import sys

def file_to_c_array(input_file, output_file, array_name, length_name):
    """
    将文件转换为 C 数组格式
    
    Args:
        input_file: 输入文件路径
        output_file: 输出 .inc 文件路径
        array_name: C 数组变量名
        length_name: C 长度变量名
    """
    try:
        # 读取文件内容（二进制模式）
        with open(input_file, 'rb') as f:
            data = f.read()
        
        # 生成 C 数组
        with open(output_file, 'w') as f:
            f.write(f"const unsigned char {array_name}[] = {{\n")
            
            # 每行 12 个字节
            for i in range(0, len(data), 12):
                chunk = data[i:i+12]
                hex_values = ', '.join(f'0x{b:02x}' for b in chunk)
                if i + 12 < len(data):
                    f.write(f"  {hex_values},\n")
                else:
                    f.write(f"  {hex_values}\n")
            
            f.write("};\n")
            f.write(f"const unsigned int {length_name} = {len(data)};\n")
        
        print(f"[OK] Generated: {output_file} ({len(data)} bytes)")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to generate: {e}")
        return False


def main():
    """主函数"""
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    # 源文件路径（相对于项目根目录）
    static_dir = os.path.join(project_root, '..', 'k230_onboard_project', 'static')
    output_dir = os.path.join(project_root, 'src')
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 文件映射
    files = [
        {
            'input': os.path.join(static_dir, 'index.html'),
            'output': os.path.join(output_dir, 'index_html.inc'),
            'array_name': 'STATIC_INDEX_HTML_DATA',
            'length_name': 'STATIC_INDEX_HTML_LEN'
        },
        {
            'input': os.path.join(static_dir, 'app.js'),
            'output': os.path.join(output_dir, 'app_js.inc'),
            'array_name': 'STATIC_APP_JS_DATA',
            'length_name': 'STATIC_APP_JS_LEN'
        }
    ]
    
    success_count = 0
    for file_info in files:
        input_path = os.path.abspath(file_info['input'])
        output_path = os.path.abspath(file_info['output'])
        
        # 检查输入文件是否存在
        if not os.path.exists(input_path):
            print(f"[WARN] Input file not found: {input_path}")
            continue
        
        if file_to_c_array(
            input_path,
            output_path,
            file_info['array_name'],
            file_info['length_name']
        ):
            success_count += 1
    
    if success_count == len(files):
        print(f"\n[SUCCESS] Generated {success_count} files")
        print("\n[INFO] Next steps:")
        print("   1. Recompile C layer code")
        print("   2. Reflash firmware")
        return 0
    else:
        print(f"\n[WARN] Only generated {success_count}/{len(files)} files")
        return 1


if __name__ == '__main__':
    sys.exit(main())

