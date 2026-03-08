"""
诊断生成失败问题 - 检查所有可能的原因
"""
import logging
import sys
import os

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('diagnose.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def check_config():
    """检查配置文件"""
    logger.info("=" * 60)
    logger.info("1. 检查配置文件")
    logger.info("=" * 60)

    config_path = "config.json"
    if os.path.exists(config_path):
        logger.info(f"✅ 配置文件存在: {config_path}")
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 检查必要配置
        required_keys = ['llm_interface', 'api_key', 'base_url', 'model']
        for key in required_keys:
            if key in config:
                logger.info(f"  ✅ {key}: {config[key] if key != 'api_key' else '***'}")
            else:
                logger.error(f"  ❌ 缺少配置: {key}")
        return config
    else:
        logger.error(f"❌ 配置文件不存在: {config_path}")
        return None

def check_wxhyj_dir():
    """检查wxhyj目录"""
    logger.info("\n" + "=" * 60)
    logger.info("2. 检查wxhyj目录")
    logger.info("=" * 60)

    wxhyj_path = "wxhyj"
    if os.path.exists(wxhyj_path):
        logger.info(f"✅ 目录存在: {wxhyj_path}")

        # 列出文件
        files = os.listdir(wxhyj_path)
        logger.info(f"  文件数量: {len(files)}")
        for f in files:
            logger.info(f"    - {f}")

        # 检查日志目录
        log_dir = os.path.join(wxhyj_path, "llm_conversation_logs")
        if os.path.exists(log_dir):
            logger.info(f"  ✅ 日志目录存在: {log_dir}")
        else:
            logger.warning(f"  ⚠️ 日志目录不存在: {log_dir}")
            logger.info(f"  📝 尝试创建日志目录...")
            try:
                os.makedirs(log_dir, exist_ok=True)
                logger.info(f"  ✅ 日志目录已创建")
            except Exception as e:
                logger.error(f"  ❌ 创建日志目录失败: {e}")
    else:
        logger.error(f"❌ 目录不存在: {wxhyj_path}")

def test_generator_init():
    """测试生成器初始化"""
    logger.info("\n" + "=" * 60)
    logger.info("3. 测试生成器初始化")
    logger.info("=" * 60)

    try:
        from novel_generator.blueprint import StrictChapterGenerator
        logger.info("✅ 成功导入 StrictChapterGenerator")

        # 创建测试实例
        generator = StrictChapterGenerator(
            interface_format="openai",
            api_key="test_key",
            base_url="http://test.com",
            llm_model="test-model"
        )
        logger.info("✅ 生成器实例创建成功")

        # 测试自动修复方法
        test_content = """
第1章 - 测试

## 1. 基础元信息
内容

## 2. 张力与冲突
内容

## 3. 匠心思维应用
内容

## 4. 伏笔与信息差
内容

## 6. 剧情精要
内容

## 7. 衔接设计
内容
"""

        validation = {
            "is_valid": False,
            "errors": ["🚨 节完整性检测：第1章缺失: 暗恋与修罗场"]
        }

        fixed, was_fixed = generator._auto_fix_missing_sections(test_content, validation)
        logger.info(f"自动修复测试: {'✅ 通过' if was_fixed else '❌ 失败'}")

        if was_fixed:
            logger.info("✅ 自动修复功能正常")

        return True
    except Exception as e:
        logger.error(f"❌ 生成器初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    logger.info("🔍 开始诊断...")
    logger.info(f"工作目录: {os.getcwd()}")

    # 运行检查
    config = check_config()
    check_wxhyj_dir()
    test_generator_init()

    logger.info("\n" + "=" * 60)
    logger.info("诊断完成")
    logger.info("=" * 60)

    # 给出建议
    logger.info("\n📋 建议检查项：")
    logger.info("1. 确认config.json中的API配置正确")
    logger.info("2. 确认API key有效且有足够配额")
    logger.info("3. 确认网络连接正常，可以访问LLM API")
    logger.info("4. 确认wxhyj目录有写入权限")
    logger.info("5. 查看完整的控制台输出，寻找其他错误信息")

if __name__ == "__main__":
    main()
