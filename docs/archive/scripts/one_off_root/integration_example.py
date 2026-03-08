# -*- coding: utf-8 -*-
"""
集成示例：使用Schema验证和错误处理

该示例展示如何将新的Schema验证器和错误处理机制
集成到现有的章节生成流程中
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from novel_generator.schema_validator import SchemaValidator
from novel_generator.error_handler import (
    ErrorHandler,
    intelligent_retry,
    context_sensitive_retry,
    APITimeoutError,
    APIRateLimitError,
    ValidationError,
    RetryConfig
)
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def example_1_basic_validation():
    """示例1：基础的Schema验证"""

    print("=" * 80)
    print("示例1：基础的Schema验证")
    print("=" * 80)

    validator = SchemaValidator(strict_mode=True)

    # 示例数据
    chapter_data = {
        "chapter_number": 1,
        "chapter_title": "测试章节",
        "chapter_role": "第1卷",
        "chapter_purpose": "测试目的",
        "suspense_level": "SS级",
        "chapter_summary": "这是测试章节",
        "target_word_count": 4000
    }

    # 执行验证
    report = validator.validate_chapter_directory_entry(chapter_data, chapter_number=1)

    # 打印报告
    SchemaValidator.print_report(report, verbose=True)

    return report.is_valid


def example_2_intelligent_retry():
    """示例2：智能重试机制"""

    print("\n" + "=" * 80)
    print("示例2：智能重试机制")
    print("=" * 80)

    # 模拟一个可能失败的函数
    @intelligent_retry(
        config=RetryConfig(max_attempts=3, base_delay=0.5),
        retry_on=(APITimeoutError, APIRateLimitError),
        log_errors=True
    )
    def simulate_api_call(attempt_failures: int = 1):
        """模拟API调用"""
        import random

        # 模拟前几次失败
        call_count = getattr(simulate_api_call, 'call_count', 0)
        simulate_api_call.call_count = call_count + 1

        if simulate_api_call.call_count <= attempt_failures:
            if simulate_api_call.call_count % 2 == 0:
                raise APITimeoutError("API超时", timeout=30.0)
            else:
                raise APIRateLimitError("API限流")

        logger.info("✅ API调用成功！")
        return "成功的结果"

    try:
        result = simulate_api_call(attempt_failures=2)
        logger.info(f"最终结果: {result}")
    except Exception as e:
        logger.error(f"所有重试都失败: {e}")


def example_3_error_handler():
    """示例3：统一错误处理"""

    print("\n" + "=" * 80)
    print("示例3：统一错误处理")
    print("=" * 80)

    error_handler = ErrorHandler()

    # 模拟多个错误
    errors_to_simulate = [
        ValidationError("字段验证失败", field="chapter_title"),
        APITimeoutError("API响应超时", timeout=45.0, chapter_number=1),
        ValidationError("格式错误", field="suspense_level"),
    ]

    for i, error in enumerate(errors_to_simulate, 1):
        print(f"\n【错误 {i}】模拟...")
        try:
            raise error
        except Exception as e:
            error_handler.handle_exception(
                e,
                context={"attempt": i, "timestamp": "2026-01-11"}
            )

    # 打印错误统计
    stats = error_handler.get_error_statistics()
    print(f"\n{'=' * 80}")
    print("错误统计:")
    print(f"  总错误数: {stats['total_errors']}")
    print(f"  唯一错误类型: {stats['unique_error_types']}")
    print(f"  各类错误计数:")
    for error_type, count in stats['error_counts'].items():
        print(f"    {error_type}: {count}")

    # 打印最近的错误
    print(f"\n最近的 {min(3, stats['recent_errors_count'])} 个错误:")
    recent = error_handler.get_recent_errors(limit=3)
    for error in recent:
        print(f"  [{error['timestamp']}] {error['type']}: {error['message']}")


def example_4_complete_workflow():
    """示例4：完整的工作流程"""

    print("\n" + "=" * 80)
    print("示例4：完整工作流程")
    print("=" * 80)

    error_handler = ErrorHandler()
    validator = SchemaValidator(strict_mode=True)

    @context_sensitive_retry(
        error_types=(APITimeoutError, APIRateLimitError),
        max_retries=3
    )
    def generate_chapter_with_validation(chapter_number: int):
        """
        章节生成与验证的完整流程
        """
        # 1. 验证输入数据
        chapter_data = {
            "chapter_number": chapter_number,
            "chapter_title": f"第{chapter_number}章",
            "chapter_role": "第1卷",
            "chapter_purpose": "测试目的",
            "chapter_summary": "测试摘要"
        }

        report = validator.validate_chapter_directory_entry(
            chapter_data,
            chapter_number=chapter_number
        )

        if not report.is_valid:
            raise ValidationError(
                "章节数据验证失败",
                field="chapter_data"
            )

        # 2. 模拟API调用
        logger.info(f"正在生成第 {chapter_number} 章...")

        # 模拟偶发的API错误
        import random
        if random.random() < 0.3:  # 30% 概率失败
            if random.random() < 0.5:
                raise APITimeoutError("API超时", timeout=30.0)
            else:
                raise APIRateLimitError("API限流")

        # 3. 生成成功
        logger.info(f"✅ 第 {chapter_number} 章生成成功")
        return {"status": "success", "chapter_number": chapter_number}

    # 执行完整流程
    chapter_numbers = [1, 2, 3, 4, 5]
    results = []

    for chapter_num in chapter_numbers:
        try:
            result = generate_chapter_with_validation(chapter_num)
            results.append(result)
        except Exception as e:
            error_handler.handle_exception(
                e,
                context={"chapter_number": chapter_num},
                reraise=False
            )
            results.append({
                "status": "failed",
                "chapter_number": chapter_num,
                "error": str(e)
            })

    # 总结
    print(f"\n{'=' * 80}")
    print("执行总结:")
    print(f"  总章节数: {len(chapter_numbers)}")
    print(f"  成功: {sum(1 for r in results if r['status'] == 'success')}")
    print(f"  失败: {sum(1 for r in results if r['status'] == 'failed')}")


def main():
    """主函数"""

    print("\n" + "🚀" * 40)
    print("\n   集成示例：Schema验证 + 错误处理\n")
    print("🚀" * 40 + "\n")

    # 运行所有示例
    example_1_basic_validation()
    example_2_intelligent_retry()
    example_3_error_handler()
    example_4_complete_workflow()

    print("\n" + "=" * 80)
    print("✅ 所有示例执行完成！")
    print("=" * 80)

    print("\n下一步建议:")
    print("1. 将SchemaValidator集成到strict_blueprint_generator.py")
    print("2. 在LLM调用处添加intelligent_retry装饰器")
    print("3. 使用ErrorHandler统一管理所有异常")
    print("4. 在主流程中添加完整的错误恢复机制")


if __name__ == "__main__":
    main()
