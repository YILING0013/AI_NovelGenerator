# 修复pkg_resources警告
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")
# -*- coding: utf-8 -*-
"""
pytest全局配置和共享fixture
"""
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 测试数据目录
TEST_DATA_DIR = project_root / "tests" / "data"


@pytest.fixture(scope="session")
def project_root_path():
    """项目根目录路径"""
    return project_root


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录"""
    return TEST_DATA_DIR


@pytest.fixture
def temp_dir():
    """临时目录fixture"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_config():
    """模拟配置文件"""
    return {
        "choose_configs": {
            "worldview_llm": "test-llm",
            "character_llm": "test-llm",
            "plot_llm": "test-llm",
            "chapter_blueprint_llm": "test-llm",
            "chapter_outline_llm": "test-llm",
            "chapter_content_llm": "test-llm",
            "embedding_model": "test-embedding"
        },
        "llm_configs": {
            "test-llm": {
                "api_key": "test-api-key",
                "base_url": "https://api.test.com",
                "model_name": "test-model",
                "interface_format": "test",
                "temperature": 0.7,
                "max_tokens": 2000,
                "timeout": 60
            }
        },
        "embedding_configs": {
            "test-embedding": {
                "model_path": "test-model-path",
                "dimension": 768
            }
        },
        "filepath": "test_output",
        "vector_db_path": "test_vectorstore",
        "log_level": "INFO"
    }


@pytest.fixture
def config_file(mock_config, temp_dir):
    """创建临时配置文件"""
    config_path = temp_dir / "config.json"
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(mock_config, f, ensure_ascii=False, indent=2)
    return str(config_path)


@pytest.fixture
def mock_llm_adapter():
    """模拟LLM适配器"""
    adapter = Mock()
    adapter.invoke.return_value = "测试生成的文本内容"
    return adapter


@pytest.fixture
def mock_embedding_adapter():
    """模拟嵌入适配器"""
    adapter = Mock()
    adapter.embed_documents.return_value = [
        [0.1] * 768  # 模拟768维向量
    ]
    adapter.embed_query.return_value = [0.1] * 768
    return adapter


@pytest.fixture
def sample_chapter_data():
    """示例章节数据"""
    return {
        "chapter_number": 1,
        "chapter_title": "第一章：冒险的开始",
        "chapter_content": "这是一个关于勇气和冒险的故事。主人公踏上了寻找真相的旅程。",
        "word_count": 100,
        "summary": "主人公开始冒险旅程",
        "characters": ["主人公"],
        "keywords": ["冒险", "勇气", "真相"],
        "creation_time": "2025-01-01T00:00:00"
    }


@pytest.fixture
def sample_architecture_data():
    """示例架构数据"""
    return {
        "worldview": "奇幻世界",
        "main_characters": [
            {
                "name": "主人公",
                "description": "勇敢的冒险者",
                "role": "主角"
            }
        ],
        "plot_outline": "从平凡到英雄的蜕变",
        "themes": ["勇气", "成长", "友情"],
        "style_guide": "面向青少年读者的奇幻小说风格"
    }


@pytest.fixture
def mock_vector_store():
    """模拟向量存储"""
    store = Mock()
    store.add_documents.return_value = None
    store.similarity_search.return_value = [
        Mock(
            page_content="相关文档内容",
            metadata={"source": "test.txt"}
        )
    ]
    return store


@pytest.fixture
def create_test_file(temp_dir):
    """创建测试文件的工厂函数"""
    def _create_file(filename: str, content: str = "") -> Path:
        file_path = temp_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return file_path
    return _create_file


@pytest.fixture
def mock_chroma_collection():
    """模拟ChromaDB集合"""
    collection = Mock()
    collection.add.return_value = None
    collection.query.return_value = {
        "documents": ["文档1", "文档2"],
        "metadatas": [{"source": "test1.txt"}, {"source": "test2.txt"}],
        "distances": [0.1, 0.2]
    }
    return collection


@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """自动清理临时文件"""
    yield
    # 测试后清理
    import glob
    temp_files = glob.glob("test_*") + glob.glob("temp_*")
    for file in temp_files:
        try:
            if os.path.isfile(file):
                os.remove(file)
            elif os.path.isdir(file):
                shutil.rmtree(file)
        except Exception:
            pass


@pytest.fixture
def mock_logger():
    """模拟日志记录器"""
    logger = Mock()
    logger.info.return_value = None
    logger.warning.return_value = None
    logger.error.return_value = None
    logger.debug.return_value = None
    return logger


@pytest.fixture
def sample_chapter_directory():
    """示例章节目录数据"""
    return """第一章：勇气的考验
章节标题：勇气的考验
字数目标：1500
核心冲突：主人公面临第一次真正的挑战
时间地点：迷雾森林，清晨
本章简介：主人公在迷雾森林中遇到了第一个考验，需要展现内心的勇气。

情感弧光：从恐惧到坚定
钩子设计：神秘的森林传说
伏笔线索：古树上的符号
冲突设计：内心恐惧与外在挑战
人物关系：与守护者的第一次相遇
场景描述：迷雾笼罩的神秘森林
动作设计：跨越深渊的决定
对话设计：与守护者的对话
心理描写：内心的挣扎和决心
环境描写：森林中的声音和景象
象征隐喻：迷雾象征内心的困惑
节奏控制：紧张与缓解交替
悬念设置：古树符号的含义
高潮设计：跨越深渊的瞬间
结局安排：获得新的指引
过渡设计：为下一段旅程做准备
风格要求：第一人称视角，细腻的心理描写
创作备注：突出勇气的主题


第二章：智慧的启迪
章节标题：智慧的启迪
字数目标：1800
核心冲突：解决古老的谜题
时间地点：智慧神殿，正午
本章简介：主人公在神殿中需要运用智慧解开古老的谜题。

情感弧光：从迷茫到领悟
钩子设计：神秘的神殿大门
伏笔线索：壁画中的预言
冲突设计：智力与时间的竞赛
人物关系：与智慧的化身交流
场景描述：庄严的神殿内部
动作设计：研究壁画的过程
对话设计：与守护者的问答
心理描写：思考的专注过程
环境描写：神殿中的光影变化
象征隐喻：光明象征智慧
节奏控制：平稳而富有节奏
悬念设置：下一个谜题的暗示
高潮设计：解开谜题的瞬间
结局安排：获得智慧的启示
过渡设计：准备迎接新的挑战
风格要求：第二人称视角，富有哲理
创作备注：强调智慧的珍贵"""


# 测试标记定义
def pytest_configure(config):
    """配置测试标记"""
    config.addinivalue_line(
        "markers", "unit: 单元测试"
    )
    config.addinivalue_line(
        "markers", "integration: 集成测试"
    )
    config.addinivalue_line(
        "markers", "gui: GUI测试"
    )
    config.addinivalue_line(
        "markers", "slow: 慢速测试"
    )
    config.addinivalue_line(
        "markers", "network: 网络测试"
    )
    config.addinivalue_line(
        "markers", "external: 外部服务测试"
    )
    config.addinivalue_line(
        "markers", "smoke: 基础功能测试"
    )
    config.addinivalue_line(
        "markers", "regression: 回归测试"
    )


# 测试收集钩子
def pytest_collection_modifyitems(config, items):
    """修改测试收集"""
    for item in items:
        # 为没有标记的测试自动添加unit标记
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)