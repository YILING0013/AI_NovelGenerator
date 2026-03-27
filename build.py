import subprocess
import os
import shutil
import sys

def build_project():
    """执行前端Next.js项目的构建任务，并将生成的静态文件移动到后端指定的static目录。"""
    print("开始构建前端 Next.js 项目...")
    
    # 路径定义
    base_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(base_dir, "frontend")
    target_static_dir = os.path.join(base_dir, "static")
    next_out_dir = os.path.join(frontend_dir, "out")
    
    if not os.path.exists(frontend_dir):
        print(f"错误: 找不到目录 {frontend_dir}")
        return

    try:
        is_windows = sys.platform == "win32"
        
        print("正在安装前端依赖 (npm install)...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True, shell=is_windows)
        
        print("正在打包前端文件 (npm run build)...")
        subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=True, shell=is_windows)
        
        print("正在同步静态文件到根目录...")
        
        if os.path.exists(target_static_dir):
            shutil.rmtree(target_static_dir)
            
        if os.path.exists(next_out_dir):
            shutil.move(next_out_dir, target_static_dir)
            print(f"✅ 已将 {next_out_dir} 移动至 {target_static_dir}")
        else:
            print(f"❌ 错误: 未能在 {next_out_dir} 找到构建输出。请检查 next.config.mjs 是否配置了 output: 'export'")
            return

        print("\n✨ 全部构建任务已完成！")
        print("现在你可以运行 'python main.py' 启动服务了。")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 构建过程中出错 (Exit Code {e.returncode})")
    except Exception as e:
        print(f"\n❌ 发生未知错误: {e}")

if __name__ == "__main__":
    build_project()