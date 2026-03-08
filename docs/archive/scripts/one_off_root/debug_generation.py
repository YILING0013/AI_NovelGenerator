"""
调试生成失败问题
"""
import logging
import sys

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_generation.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# 模拟一个有缺失节的内容
test_content = """
第1章 - 测试章节

## 1. 基础元信息
*   **章节序号**：第1章
*   **章节标题**：测试章节

## 2. 张力与冲突
*   **冲突类型**：测试

## 3. 匠心思维应用
*   **应用场景**：测试

## 4. 伏笔与信息差
*   **本章植入伏笔**：测试

## 6. 剧情精要
*   **开场**：测试

## 7. 衔接设计
*   **承上**：测试
"""

# 模拟验证结果
validation_result = {
    "is_valid": False,
    "errors": ["🚨 节完整性检测：第1章缺失: 暗恋与修罗场"],
    "generated_chapters": [1]
}

logger.info("=" * 60)
logger.info("开始测试自动修复功能")
logger.info("=" * 60)

# 导入并创建生成器
from novel_generator.blueprint import StrictChapterGenerator

generator = StrictChapterGenerator(
    interface_format="openai",
    api_key="test",
    base_url="http://test",
    llm_model="test-model"
)

logger.info("✅ 生成器创建成功")

# 测试自动修复
logger.info("\n📋 原始验证结果:")
for error in validation_result["errors"]:
    logger.error(f"  - {error}")

logger.info(f"\n验证通过: {validation_result['is_valid']}")

# 调用自动修复
logger.info("\n🔧 调用自动修复功能...")
fixed_content, was_fixed = generator._auto_fix_missing_sections(test_content, validation_result)

logger.info(f"修复状态: {'✅ 已修复' if was_fixed else '❌ 未修复'}")

if was_fixed:
    logger.info("\n修复后的内容:")
    logger.info("-" * 60)
    for line in fixed_content.split('\n'):
        logger.info(line)
    logger.info("-" * 60)

    # 重新验证
    logger.info("\n🔄 重新验证...")
    new_validation = generator._strict_validation(fixed_content, 1, 1)

    logger.info(f"重新验证通过: {new_validation['is_valid']}")

    if not new_validation['is_valid']:
        logger.error("重新验证失败，错误:")
        for error in new_validation.get("errors", []):
            logger.error(f"  - {error}")
    else:
        logger.info("✅ 验证通过！")

logger.info("\n" + "=" * 60)
logger.info("测试完成")
logger.info("=" * 60)
