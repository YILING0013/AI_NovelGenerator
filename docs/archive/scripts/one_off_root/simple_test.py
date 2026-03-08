"""
简单测试 - 直接调用生成并查看输出
"""
import logging
import sys
import json

# 设置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def main():
    print("=" * 80)
    print("测试生成第1章")
    print("=" * 80)

    # 读取配置
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    last_interface = config.get('last_interface_format')
    llm_configs = config.get('llm_configs', {})

    # 找到配置
    for key, value in llm_configs.items():
        if last_interface in key or key in last_interface:
            llm_config = value
            print(f"\n使用LLM: {key}")
            break
    else:
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

    # 读取架构
    with open('wxhyj/Novel_architecture.txt', 'r', encoding='utf-8') as f:
        architecture_text = f.read()

    print(f"\n架构文件: {len(architecture_text)} 字符")

    # 测试日志初始化
    print("\n测试日志初始化...")
    generator._init_llm_log("wxhyj", 1, 1)
    print(f"日志文件: {generator.current_log_file}")

    # 如果日志文件创建失败，手动创建
    if not generator.current_log_file:
        print("\n⚠️ 日志文件创建失败，尝试手动创建...")
        import os
        log_dir = os.path.join("wxhyj", "llm_conversation_logs")
        os.makedirs(log_dir, exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"manual_test_{timestamp}.md")
        generator.current_log_file = log_file
        print(f"手动创建日志文件: {log_file}")

    # 尝试生成
    print("\n" + "=" * 80)
    print("开始生成...")
    print("=" * 80)

    try:
        result = generator.generate_complete_directory_strict(
            architecture_text=architecture_text,
            start_chapter=1,
            end_chapter=1,
            filepath="wxhyj"
        )
        print("\n✅ 生成成功！")
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()

    # 检查日志文件
    if generator.current_log_file and os.path.exists(generator.current_log_file):
        print(f"\n📄 日志文件已创建: {generator.current_log_file}")
        with open(generator.current_log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"日志文件大小: {len(content)} 字符")
    else:
        print("\n⚠️ 日志文件未创建")

if __name__ == "__main__":
    main()
