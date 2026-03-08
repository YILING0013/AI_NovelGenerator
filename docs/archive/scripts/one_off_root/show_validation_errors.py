"""
在控制台显示详细的验证错误
"""
import logging
import json
import os

# 设置控制台日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

def patch_strict_validation():
    """修补StrictChapterGenerator类，使其在验证失败时打印详细信息"""

    from novel_generator import blueprint

    # 保存原始的_strict_validation方法
    original_validation = blueprint.StrictChapterGenerator._strict_validation

    def enhanced_validation(self, content, start_chapter, end_chapter):
        """增强的验证方法，打印详细信息"""
        print("\n" + "=" * 80)
        print("🔍 开始验证")
        print("=" * 80)

        # 调用原始验证
        result = original_validation(self, content, start_chapter, end_chapter)

        # 打印详细结果
        print(f"验证结果: {'✅ 通过' if result['is_valid'] else '❌ 失败'}")
        print(f"生成的章节: {result.get('generated_chapters', [])}")

        if result.get('errors'):
            print("\n❌ 错误列表:")
            for i, error in enumerate(result.get('errors', []), 1):
                print(f"  {i}. {error}")

        if result.get('missing_chapters'):
            print(f"\n⚠️ 缺失章节: {result.get('missing_chapters')}")

        print("=" * 80 + "\n")

        return result

    # 替换方法
    blueprint.StrictChapterGenerator._strict_validation = enhanced_validation

    print("✅ 验证方法已增强，将显示详细信息")

def main():
    print("=" * 80)
    print("测试生成并显示详细验证错误")
    print("=" * 80)

    # 应用补丁
    patch_strict_validation()

    # 读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    last_interface = config.get('last_interface_format')
    llm_configs = config.get('llm_configs', {})

    # 找到匹配的配置
    llm_config = None
    for key, value in llm_configs.items():
        if last_interface in key or key in last_interface:
            llm_config = value
            print(f"使用LLM配置: {key}")
            break

    if not llm_config:
        print("使用第一个可用配置")
        llm_config = list(llm_configs.values())[0]

    # 初始化生成器
    from novel_generator.blueprint import StrictChapterGenerator

    generator = StrictChapterGenerator(
        interface_format=llm_config.get('interface_format'),
        api_key=llm_config.get('api_key'),
        base_url=llm_config.get('base_url'),
        llm_model=llm_config.get('model_name'),
        temperature=llm_config.get('temperature', 0.7),
        max_tokens=llm_config.get('max_tokens', 60000)
    )

    print("✅ 生成器初始化成功\n")

    # 读取架构
    arch_path = "wxhyj/Novel_architecture.txt"
    with open(arch_path, 'r', encoding='utf-8') as f:
        architecture_text = f.read()

    print(f"架构文件: {len(architecture_text)} 字符\n")

    # 尝试生成
    try:
        print("开始生成第1章...\n")

        result = generator.generate_complete_directory_strict(
            architecture_text=architecture_text,
            start_chapter=1,
            end_chapter=1,
            filepath="wxhyj"
        )

        print("\n✅ 生成成功！")
        print(f"结果长度: {len(result)} 字符")

    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
