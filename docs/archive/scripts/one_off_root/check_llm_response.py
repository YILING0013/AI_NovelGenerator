"""检查LLM响应是否包含重复章节"""
import re
from collections import Counter

# 读取第1-5章的LLM日志
with open('wxhyj/llm_conversation_logs/llm_log_chapters_1-5_20260104_171051.md', 'r', encoding='utf-8') as f:
    log_content = f.read()

# 提取LLM Response部分
response_start = log_content.find('### 🤖 Response')
if response_start > 0:
    # 找到Response后面的代码块开始
    code_start = log_content.find('```', response_start)
    if code_start > 0:
        code_start = log_content.find('\n', code_start) + 1
        # 找到代码块结束
        code_end = log_content.find('```', code_start)
        if code_end > 0:
            llm_response = log_content[code_start:code_end]

            print('📊 LLM响应中的章节分析：')
            print(f'响应长度: {len(llm_response)} 字符')

            # 检查章节号
            pattern = r'第(\d+)章'
            chapters_in_response = re.findall(pattern, llm_response)

            print(f'找到章节号: {len(chapters_in_response)} 个')
            print(f'章节列表: {chapters_in_response}')

            # 统计重复
            counts = Counter(chapters_in_response)
            duplicates = {k: v for k, v in counts.items() if v > 1}

            if duplicates:
                print(f'\n⚠️ LLM在单次生成中就产生了重复！')
                for chapter, count in sorted(duplicates.items(), key=lambda x: int(x[0])):
                    print(f'  第{chapter}章: {count}次')
            else:
                print(f'\n✅ LLM单次生成无重复')

            # 显示章节标题
            titles = re.findall(r'(第\d+章[^\n]*)', llm_response)
            print(f'\n📝 所有章节标题:')
            for i, title in enumerate(titles, 1):
                print(f'  {i}. {title}')

            # 保存LLM原始响应到文件
            with open('llm_response_ch1-5.txt', 'w', encoding='utf-8') as f:
                f.write(llm_response)
            print(f'\n📄 LLM原始响应已保存到: llm_response_ch1-5.txt')

            # 检查是否有前言文字
            first_chapter_pos = llm_response.find('第1章')
            if first_chapter_pos > 100:
                preamble = llm_response[:first_chapter_pos]
                print(f'\n⚠️ 发现前言文字 ({len(preamble)} 字符):')
                print(preamble[:200] + '...' if len(preamble) > 200 else preamble)
        else:
            print('❌ 未找到代码块结束标记')
    else:
        print('❌ 未找到代码块开始标记')
else:
    print('❌ 未找到LLM Response')
