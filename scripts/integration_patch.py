# integration_patch.py
# -*- coding: utf-8 -*-
"""
系统集成补丁
将优化方案集成到现有的novel_generator系统中
"""
import os
import shutil
from datetime import datetime

def create_backup(original_file: str) -> str:
    """创建文件备份"""
    if not os.path.exists(original_file):
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"{original_file}.backup_{timestamp}"
    shutil.copy2(original_file, backup_file)
    return backup_file

def apply_blueprint_optimization():
    """应用蓝图生成器优化"""
    blueprint_file = "novel_generator/blueprint.py"
    optimized_file = "blueprint_optimized.py"

    if os.path.exists(blueprint_file) and os.path.exists(optimized_file):
        # 备份原文件
        backup = create_backup(blueprint_file)
        print(f"✅ 原文件已备份：{backup}")

        # 复制优化版本
        shutil.copy2(optimized_file, blueprint_file)
        print("✅ 蓝图生成器已更新为优化版本")
        return True
    else:
        print("❌ 缺少必要文件")
        return False

def update_generation_handlers():
    """更新生成处理器，使用优化版本"""
    handlers_file = "ui/generation_handlers.py"

    if not os.path.exists(handlers_file):
        print("❌ 找不到generation_handlers.py")
        return False

    # 备份原文件
    backup = create_backup(handlers_file)
    print(f"✅ 原文件已备份：{backup}")

    # 读取原文件
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 修改导入语句
    new_import = """from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,  # 使用优化版本
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text,
    build_chapter_prompt
)"""

    # 如果还没有优化，则添加注释
    if "Optimized_Chapter_blueprint_generate" not in content:
        content = content.replace(
            "Chapter_blueprint_generate,",
            "Chapter_blueprint_generate,  # 使用优化版本"
        )

    # 添加优化配置选项
    config_note = """
# ==================== 优化配置 ====================
# 以下配置已集成到blueprint.py的优化版本中：
# - 智能分块大小计算
# - 频率限制控制（60秒间隔）
# - 宽松验证机制
# - 降级生成策略
# - 占位符保障机制
# ==================== 优化配置 ====================
"""

    if config_note not in content:
        content = config_note + "\n" + content

    # 保存更新后的文件
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ generation_handlers.py 已更新")
    return True

def create_quick_fix_tool():
    """创建快速修复工具"""
    tool_content = '''# quick_fix.py
# -*- coding: utf-8 -*-
"""
章节目录快速修复工具
使用优化算法修复缺失的章节
"""
import os
import sys

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chapter_completeness_fixer import fix_missing_chapters, analyze_directory_issues

def main():
    """主函数"""
    print("🔧 章节目录快速修复工具")
    print("=" * 50)

    # 配置文件路径 - 从命令行参数获取
    if len(sys.argv) > 1:
        novel_folder = sys.argv[1]
    else:
        print("Usage: python quick_fix.py <novel_folder>")
        print("Example: python quick_fix.py wxhyj")
        return
    
    directory_file = os.path.join(novel_folder, "Novel_directory.txt")

    if not os.path.exists(directory_file):
        print(f"❌ 找不到文件：{directory_file}")
        return

    # 分析当前状态
    print("\\n📊 分析当前状态...")
    analysis = analyze_directory_issues(directory_file)

    if "error" in analysis:
        print(f"❌ 分析失败：{analysis['error']}")
        return

    print(f"✅ 分析完成：")
    print(f"   总章节数：{analysis['total_chapters']}")
    print(f"   完整章节：{analysis['complete_chapters']}")
    print(f"   缺失章节：{len(analysis['missing_chapters'])}")
    print(f"   完整率：{analysis['completeness_rate']}")

    if not analysis['missing_chapters'] and analysis['title_only_chapters'] == 0:
        print("\\n🎉 目录完整，无需修复！")
        return

    # 询问是否继续修复
    print("\\n⚠️ 检测到问题章节，是否开始修复？")
    response = input("输入 'y' 继续，其他键取消: ").strip().lower()

    if response != 'y':
        print("❌ 用户取消修复")
        return

    # 读取配置
    config_file = "config.json"
    if not os.path.exists(config_file):
        print(f"❌ 找不到配置文件：{config_file}")
        return

    import json
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 获取LLM配置
    llm_name = config.get("choose_configs", {}).get("chapter_outline_llm", "")
    if not llm_name:
        print("❌ 配置中未找到章节大纲LLM设置")
        return

    llm_config = config["llm_configs"][llm_name]

    print(f"\\n🔧 开始修复，使用模型：{llm_name}")
    print("这可能需要较长时间，请耐心等待...")

    # 执行修复
    success = fix_missing_chapters(
        directory_file=directory_file,
        interface_format=llm_config["interface_format"],
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        llm_model=llm_config["model_name"],
        temperature=llm_config.get("temperature", 0.7),
        max_tokens=min(llm_config.get("max_tokens", 30000), 20000),  # 保守设置
        timeout=llm_config.get("timeout", 1200)
    )

    if success:
        print("\\n🎉 修复完成！")
        print("\\n📊 修复后状态：")
        final_analysis = analyze_directory_issues(directory_file)
        if "error" not in final_analysis:
            print(f"   完整率：{final_analysis['completeness_rate']}")
            print(f"   缺失章节：{len(final_analysis['missing_chapters'])}")
    else:
        print("\\n❌ 修复过程中遇到问题")
        print("请检查日志文件获取详细信息")

if __name__ == "__main__":
    main()
'''

    with open("quick_fix.py", 'w', encoding='utf-8') as f:
        f.write(tool_content)

    print("✅ 快速修复工具已创建：quick_fix.py")
    return True

def create_status_monitor():
    """创建状态监控工具"""
    monitor_content = '''# status_monitor.py
# -*- coding: utf-8 -*-
"""
章节目录状态监控工具
实时监控目录生成过程
"""
import os
import time
import re
from datetime import datetime

def monitor_directory_generation(directory_file: str, interval: int = 30):
    """
    监控目录文件变化
    """
    print(f"🔍 开始监控：{directory_file}")
    print(f"📊 监控间隔：{interval}秒")
    print("按 Ctrl+C 停止监控")

    last_size = 0
    last_chapter_count = 0

    try:
        while True:
            if os.path.exists(directory_file):
                # 获取文件大小
                current_size = os.path.getsize(directory_file)

                # 获取章节数量
                with open(directory_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                chapter_pattern = r'第\\s*(\\d+)\\s*章'
                chapters = re.findall(chapter_pattern, content)
                current_chapter_count = len(set(chapters))

                # 显示状态
                timestamp = datetime.now().strftime('%H:%M:%S')

                if current_size != last_size or current_chapter_count != last_chapter_count:
                    print(f"[{timestamp}] 📝 文件大小：{current_size:,} 字节 | 📚 章节数：{current_chapter_count}")

                    # 显示最新章节
                    if chapters:
                        latest_chapter = max([int(ch) for ch in chapters if ch.isdigit()])
                        print(f"[{timestamp}] 🆕 最新章节：第{latest_chapter}章")

                    last_size = current_size
                    last_chapter_count = current_chapter_count
                else:
                    print(f"[{timestamp}] ⏸️ 无变化")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\\n👋 监控已停止")
    except Exception as e:
        print(f"\\n❌ 监控异常：{e}")

def main():
    """主函数"""
    # 从命令行参数获取
    if len(sys.argv) > 1:
        novel_folder = sys.argv[1]
    else:
        print("Usage: python status_monitor.py <novel_folder>")
        return
    
    directory_file = os.path.join(novel_folder, "Novel_directory.txt")

    if not os.path.exists(directory_file):
        print(f"❌ 找不到文件：{directory_file}")
        return

    print("🔍 章节目录状态监控工具")
    print("=" * 40)

    monitor_directory_generation(directory_file, interval=30)

if __name__ == "__main__":
    main()
'''

    with open("status_monitor.py", 'w', encoding='utf-8') as f:
        f.write(monitor_content)

    print("✅ 状态监控工具已创建：status_monitor.py")
    return True

def main():
    """主集成函数"""
    print("🔧 AI小说生成器 - 系统优化补丁")
    print("=" * 50)

    print("\\n📦 应用优化方案...")

    success_count = 0
    total_operations = 4

    # 1. 应用蓝图生成器优化
    if apply_blueprint_optimization():
        success_count += 1

    # 2. 更新生成处理器
    if update_generation_handlers():
        success_count += 1

    # 3. 创建快速修复工具
    if create_quick_fix_tool():
        success_count += 1

    # 4. 创建状态监控工具
    if create_status_monitor():
        success_count += 1

    print(f"\\n📊 集成结果：{success_count}/{total_operations} 项成功")

    if success_count == total_operations:
        print("\\n🎉 系统优化补丁应用成功！")
        print("\\n📋 后续步骤：")
        print("1. 运行 'python quick_fix.py' 修复缺失章节")
        print("2. 运行 'python status_monitor.py' 监控生成过程")
        print("3. 重启GUI应用以加载优化版本")
        print("\\n⚠️ 注意：优化版本包含以下改进：")
        print("   - 智能分块大小（避免400错误）")
        print("   - 频率限制控制（避免API限制）")
        print("   - 宽松验证机制（减少误判）")
        print("   - 降级生成策略（提高成功率）")
        print("   - 占位符保障机制（避免跳过章节）")
    else:
        print("\\n❌ 部分优化应用失败")
        print("请检查错误信息并手动应用缺失的优化")

if __name__ == "__main__":
    main()