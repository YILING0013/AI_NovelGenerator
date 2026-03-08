# blueprint_optimized.py
# -*- coding: utf-8 -*-
"""
优化版本的章节蓝图生成器
解决原版本中的验证过严、频率限制、错误处理等问题
"""
import os
import re
import time
import logging
from datetime import datetime, timedelta
from novel_generator.common import invoke_with_cleaning
from llm_adapters import create_llm_adapter
from prompt_definitions import BLUEPRINT_EXAMPLE_V3, chunked_chapter_blueprint_prompt
from utils import read_file, clear_file_content, save_string_to_txt

# 配置日志
logging.basicConfig(
    filename='blueprint_optimized.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class OptimizedChapterGenerator:
    def __init__(self, interface_format, api_key, base_url, llm_model,
                 temperature=0.7, max_tokens=30000, timeout=1800):
        """
        优化初始化：降低默认max_tokens避免400错误
        """
        self.interface_format = interface_format
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.temperature = temperature
        self.max_tokens = min(max_tokens, 30000)  # 限制最大tokens避免400错误
        self.timeout = timeout

        self.llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=llm_model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=self.max_tokens,
            timeout=timeout
        )

        # 频率控制
        self.last_call_time = None
        self.min_interval = 60  # 最小间隔60秒
        self.call_history = []

    def _rate_limit_control(self):
        """频率控制：避免触发API限制"""
        current_time = datetime.now()

        # 清理1小时前的调用记录
        self.call_history = [
            call_time for call_time in self.call_history
            if current_time - call_time < timedelta(hours=1)
        ]

        # 如果最近1小时调用超过20次，等待
        if len(self.call_history) >= 20:
            sleep_time = 300  # 等待5分钟
            logging.warning(f"达到频率限制，等待{sleep_time}秒...")
            time.sleep(sleep_time)
            self.call_history.clear()

        # 如果距离上次调用不足60秒，等待
        if self.last_call_time:
            time_diff = (current_time - self.last_call_time).total_seconds()
            if time_diff < self.min_interval:
                sleep_time = self.min_interval - time_diff
                logging.info(f"频率控制：等待{sleep_time:.1f}秒...")
                time.sleep(sleep_time)

        self.last_call_time = datetime.now()
        self.call_history.append(self.last_call_time)

    def _smart_chunk_size(self, number_of_chapters):
        """智能分块大小：根据tokens限制动态调整"""
        # 保守估算：每章需要300 tokens（包括prompt和响应）
        safe_chunk_size = max(5, min(50, self.max_tokens // 300))

        logging.info(f"智能分块：总章节数={number_of_chapters}, tokens限制={self.max_tokens}, 建议分块大小={safe_chunk_size}")
        return safe_chunk_size

    def _validate_chapter_content(self, content, expected_start, expected_end):
        """宽松验证：允许合理的省略，但拒绝明显的偷懒"""
        validation_result = {
            "is_valid": True,
            "warnings": [],
            "missing_chapters": [],
            "suggestions": []
        }

        # 检查章节编号
        chapter_pattern = r"第\s*(\d+)\s*章"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        expected_count = expected_end - expected_start + 1

        # 宽松的完整性检查：至少生成50%的章节
        if len(generated_numbers) < expected_count * 0.5:
            validation_result["is_valid"] = False
            validation_result["warnings"].append(f"章节生成过少：期望{expected_count}章，实际{len(generated_numbers)}章")

        # 检查严重省略（但不惩罚合理的跳跃）
        severe_ellipsis_patterns = [
            r"由于篇幅限制.*省略.*第\d+章.*第\d+章",  # 大范围省略
            r"后续.*章.*都.*类似",  # 明显的偷懒表述
            r"生成.*至.*章.*都.*格式.*相同",  # 模板化偷懒
        ]

        for pattern in severe_ellipsis_patterns:
            if re.search(pattern, content):
                validation_result["is_valid"] = False
                validation_result["warnings"].append(f"检测到严重省略：{pattern}")
                break

        # 计算缺失章节
        if generated_numbers:
            expected_range = set(range(expected_start, expected_end + 1))
            actual_set = set(generated_numbers)
            missing_chapters = sorted(expected_range - actual_set)

            if missing_chapters:
                validation_result["missing_chapters"] = missing_chapters
                if len(missing_chapters) > expected_count * 0.3:  # 缺失超过30%
                    validation_result["warnings"].append(f"大量章节缺失：{len(missing_chapters)}章")
                    validation_result["suggestions"].append("建议重新生成缺失章节")

        return validation_result

    def _generate_fallback_content(self, start_chapter, end_chapter, context):
        """降级生成：当完整生成失败时，生成基本框架"""
        fallback_prompt = f"""
请为第{start_chapter}章到第{end_chapter}章生成基本章节框架。

基于以下上下文：
{context}

要求：
1. 每章只需要提供：标题、核心作用、主要冲突
2. 不要使用省略号或跳过表述
3. 确保章节编号连续
4. 每章控制在100字以内

格式：
第X章 - [标题]
作用：[简要描述]
冲突：[主要冲突]

请严格按照上述格式生成所有章节。
"""

        try:
            self._rate_limit_control()
            result = invoke_with_cleaning(self.llm_adapter, fallback_prompt)
            return result
        except Exception as e:
            logging.error(f"降级生成失败：{e}")
            return None

    def _generate_placeholder_chapters(self, start_chapter, end_chapter):
        """占位符生成：最后的保障机制"""
        placeholder_content = []
        for i in range(start_chapter, end_chapter + 1):
            placeholder_content.append(f"第{i}章 - [待完善]")
            placeholder_content.append(f"作用：待补充详细内容")
            placeholder_content.append(f"冲突：待补充")
            placeholder_content.append("")

        return "\n".join(placeholder_content)

    def generate_chunk_with_fallback(self, start_chapter, end_chapter, architecture_text, existing_content=""):
        """带回退机制的chunk生成"""
        chunk_size = end_chapter - start_chapter + 1
        logging.info(f"开始生成chunk [{start_chapter}..{end_chapter}]，共{chunk_size}章")

        # 尝试完整生成
        for attempt in range(2):  # 最多重试2次
            try:
                self._rate_limit_control()

                chunk_prompt = chunked_chapter_blueprint_prompt.format(
                    novel_architecture=architecture_text,
                    chapter_list=existing_content[-2000:],  # 限制上下文长度
                    n=start_chapter,
                    m=end_chapter,
                    total_chapters=end_chapter - start_chapter + 1,
                    blueprint_example=BLUEPRINT_EXAMPLE_V3
                )

                # 添加严格要求
                strict_instruction = """

🚨【重要要求】🚨
1. 必须生成所有章节，不允许省略
2. 不要使用"由于篇幅限制"等表述
3. 每章都需要有完整的结构和内容
4. 章节编号必须连续
"""

                enhanced_prompt = chunk_prompt + strict_instruction

                result = invoke_with_cleaning(self.llm_adapter, enhanced_prompt)

                if result and result.strip():
                    # 宽松验证
                    validation = self._validate_chapter_content(result, start_chapter, end_chapter)

                    if validation["is_valid"]:
                        logging.info(f"✅ Chunk [{start_chapter}..{end_chapter}] 生成成功")
                        return result
                    else:
                        logging.warning(f"⚠️ Chunk验证失败：{validation['warnings']}")

                        # 尝试降级生成
                        logging.info(f"🔄 尝试降级生成...")
                        fallback_result = self._generate_fallback_content(
                            start_chapter, end_chapter, existing_content[-1000:]
                        )

                        if fallback_result:
                            logging.info(f"✅ 降级生成成功")
                            return fallback_result
                        else:
                            logging.error(f"❌ 降级生成也失败")
                            continue
                else:
                    logging.warning(f"第{attempt+1}次尝试生成空结果")

            except Exception as e:
                logging.error(f"第{attempt+1}次尝试生成异常：{e}")

        # 最后的保障：生成占位符
        logging.error(f"🚨 所有生成尝试都失败，生成占位符章节 [{start_chapter}..{end_chapter}]")
        return self._generate_placeholder_chapters(start_chapter, end_chapter)

    def generate_complete_directory(self, filepath, number_of_chapters, user_guidance=""):
        """生成完整目录的优化流程"""
        logging.info(f"开始生成完整目录：{number_of_chapters}章")

        arch_file = os.path.join(filepath, "Novel_architecture.txt")
        if not os.path.exists(arch_file):
            logging.error("Novel_architecture.txt not found")
            return False

        architecture_text = read_file(arch_file).strip()
        if not architecture_text:
            logging.error("Novel_architecture.txt is empty")
            return False

        filename_dir = os.path.join(filepath, "Novel_directory.txt")

        # 检查现有内容
        existing_blueprint = ""
        if os.path.exists(filename_dir):
            existing_blueprint = read_file(filename_dir).strip()
            if existing_blueprint:
                logging.info("检测到现有目录，将追加生成")

        # 智能分块
        chunk_size = self._smart_chunk_size(number_of_chapters)
        logging.info(f"使用分块大小：{chunk_size}")

        # 确定起始章节
        if existing_blueprint:
            # 解析现有章节
            chapter_pattern = r"第\s*(\d+)\s*章"
            existing_chapters = re.findall(chapter_pattern, existing_blueprint)
            existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
            start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
        else:
            start_chapter = 1

        if start_chapter > number_of_chapters:
            logging.info("所有章节已生成完成")
            return True

        final_blueprint = existing_blueprint

        # 分块生成
        current_start = start_chapter
        chunk_count = 0

        while current_start <= number_of_chapters:
            current_end = min(current_start + chunk_size - 1, number_of_chapters)
            chunk_count += 1

            logging.info(f"生成第{chunk_count}块：章节 [{current_start}..{current_end}]")

            # 生成chunk内容
            chunk_result = self.generate_chunk_with_fallback(
                current_start, current_end, architecture_text, final_blueprint
            )

            if chunk_result:
                final_blueprint += "\n\n" + chunk_result.strip()

                # 立即保存
                clear_file_content(filename_dir)
                save_string_to_txt(final_blueprint.strip(), filename_dir)
                logging.info(f"✅ 第{chunk_count}块已保存")
            else:
                logging.error(f"❌ 第{chunk_count}块生成失败")

            current_start = current_end + 1

        # 最终验证
        logging.info("进行最终验证...")
        final_content = read_file(filename_dir).strip()
        if final_content:
            final_validation = self._validate_chapter_content(final_content, 1, number_of_chapters)
            logging.info(f"最终验证结果：{len(final_validation['warnings'])}个警告")

            for warning in final_validation['warnings']:
                logging.warning(f"最终验证警告：{warning}")

            for suggestion in final_validation['suggestions']:
                logging.info(f"改进建议：{suggestion}")

        logging.info("✅ 目录生成完成")
        return True

def Optimized_Chapter_blueprint_generate(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    number_of_chapters: int,
    user_guidance: str = "",
    temperature: float = 0.7,
    max_tokens: int = 30000,  # 降低默认值
    timeout: int = 1800
) -> None:
    """
    优化版本的章节蓝图生成函数
    """
    try:
        generator = OptimizedChapterGenerator(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        success = generator.generate_complete_directory(
            filepath=filepath,
            number_of_chapters=number_of_chapters,
            user_guidance=user_guidance
        )

        if success:
            logging.info("🎉 章节目录生成成功完成")
        else:
            logging.error("❌ 章节目录生成失败")

    except Exception as e:
        logging.error(f"章节目录生成异常：{e}")
        raise

if __name__ == "__main__":
    # 测试代码
    pass
