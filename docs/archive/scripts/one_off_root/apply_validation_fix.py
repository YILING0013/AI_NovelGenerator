"""
应用验证逻辑修复
"""

def main():
    with open("novel_generator/blueprint.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经应用过修复
    if "_auto_fix_missing_sections(result, validation)" in content:
        print("✅ 验证逻辑修复已应用，无需重复")
        return

    # 替换验证逻辑
    old_code = """                # 严格验证
                validation = self._strict_validation(result, start_chapter, end_chapter)

                if validation["is_valid"]:"""

    new_code = """                # 严格验证
                validation = self._strict_validation(result, start_chapter, end_chapter)

                # 🆕 尝试自动修复缺失的节
                if not validation["is_valid"]:
                    result, was_fixed = self._auto_fix_missing_sections(result, validation)
                    if was_fixed:
                        # 重新验证修复后的内容
                        validation = self._strict_validation(result, start_chapter, end_chapter)
                        logging.info(f"🔧 自动修复后重新验证...")

                if validation["is_valid"]:"""

    if old_code in content:
        content = content.replace(old_code, new_code)

        with open("novel_generator/blueprint.py", "w", encoding="utf-8") as f:
            f.write(content)

        print("✅ 成功应用验证逻辑修复")
        print("📝 在验证失败后将尝试自动修复缺失的节")
    else:
        print("❌ 无法找到要替换的代码")
        print("📋 请手动应用修复")

if __name__ == "__main__":
    main()
