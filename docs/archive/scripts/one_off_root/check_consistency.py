# check_consistency.py
# -*- coding: utf-8 -*-
"""
架构一致性检查工具
验证章节目录与架构的一致性
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from architecture_consistency_checker import check_architecture_consistency

def main():
    import sys as _sys
    
    if len(_sys.argv) > 1:
        novel_folder = _sys.argv[1]
    else:
        print("Usage: python check_consistency.py <novel_folder>")
        _sys.exit(1)
    
    print("🔍 架构一致性检查工具")
    print("=" * 50)

    # 检查文件
    directory_file = os.path.join(novel_folder, "Novel_directory.txt")
    architecture_file = os.path.join(novel_folder, "Novel_architecture.txt")

    if not os.path.exists(directory_file):
        print(f"❌ 找不到目录文件: {directory_file}")
        return

    if not os.path.exists(architecture_file):
        print(f"❌ 找不到架构文件: {architecture_file}")
        return

    print("📋 检查项目:")
    print("- 叙事流畅性")
    print("- 角色弧光一致性")
    print("- 情节推进合理性")
    print("- 世界构建一致性")
    print("- 主题一致性")
    print()

    try:
        # 执行检查
        result = check_architecture_consistency(architecture_file, directory_file)

        # 显示结果
        print(f"📊 总体得分: {result['overall_score']:.2f}/1.00")

        if result["overall_score"] >= 0.9:
            print("🎉 架构一致性优秀!")
        elif result["overall_score"] >= 0.7:
            print("✅ 架构一致性良好")
        elif result["overall_score"] >= 0.5:
            print("⚠️ 架构一致性一般")
        else:
            print("❌ 架构一致性需要改进")

        if result["issues"]:
            print()
            print("❌ 发现问题:")
            for issue in result["issues"]:
                print(f"  - {issue}")

        if result["recommendations"]:
            print()
            print("💡 建议:")
            for rec in result["recommendations"]:
                print(f"  - {rec}")

        print()
        print("📋 详细检查结果:")
        for check_name, check_result in result["checks"].items():
            status = "✅" if check_result["consistent"] else "❌"
            score_emoji = "🌟" if check_result["score"] >= 0.9 else "⭐" if check_result["score"] >= 0.7 else "🔶" if check_result["score"] >= 0.5 else "❌"
            print(f"  {status} {score_emoji} {check_name}: {check_result['score']:.2f}")

            if check_result["issues"]:
                for issue in check_result["issues"]:
                    print(f"    - {issue}")

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        print("请检查文件格式和内容")

if __name__ == "__main__":
    main()
