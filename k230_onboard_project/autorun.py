"""
CanMV 自启动脚本
将此文件放在 /data/autorun.py，系统启动时会自动运行

如果 /data/autorun.py 存在，CanMV IDE 会在启动时自动执行它
"""

def main():
    """自动启动主函数"""
    print("=" * 60)
    print("[AutoStart] CanMV 自启动脚本")
    print("=" * 60)
    
    # 导入并运行主应用
    try:
        print("[AutoStart] 导入主应用...")
        import main_rtsmart
        
        print("[AutoStart] 启动应用...")
        main_rtsmart.main()
        
    except KeyboardInterrupt:
        print("\n[AutoStart] 用户中断")
    except Exception as e:
        print("[AutoStart] 错误: " + str(e))
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
