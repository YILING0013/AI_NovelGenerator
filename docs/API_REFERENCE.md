# API参考文档

本文档提供AI小说生成工具的详细API参考，包括核心类、方法、配置选项和扩展接口。

## 📋 目录

- [核心模块API](#核心模块api)
- [适配器系统API](#适配器系统api)
- [UI组件API](#ui组件api)
- [配置系统API](#配置系统api)
- [工具函数API](#工具函数api)
- [错误处理](#错误处理)
- [类型定义](#类型定义)
- [扩展接口](#扩展接口)

## 🏗️ 核心模块API

### novel_generator 模块

#### architecture.py - 世界观生成

```python
class NovelArchitectureGenerator:
    """小说世界观生成器

    负责基于指定参数生成完整的世界观设定，包括背景、规则、文化等。
    """

    def __init__(self, llm_adapter: BaseLLMAdapter):
        """初始化世界观生成器

        Args:
            llm_adapter: LLM适配器实例

        Raises:
            ValueError: 当llm_adapter为None时
        """

    async def generate_worldview(
        self,
        genre: str,
        theme: str,
        style: str,
        additional_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成世界观设定

        Args:
            genre: 小说类型（如：科幻、奇幻、现实主义等）
            theme: 核心主题（如：人工智能、爱情、战争等）
            style: 写作风格（如：现实主义、浪漫主义等）
            additional_requirements: 额外的设定要求

        Returns:
            包含世界观信息的字典，结构如下：
            {
                "world_background": str,      # 世界背景描述
                "physical_rules": List[str],  # 物理规则列表
                "social_structure": str,      # 社会结构描述
                "technology_level": str,      # 科技水平描述
                "culture_features": str,      # 文化特色描述
                "geography": str,             # 地理环境描述
                "economics": str,             # 经济体系描述
                "politics": str               # 政治制度描述
            }

        Raises:
            APIError: LLM API调用失败时
            ValidationError: 输入参数验证失败时
        """

    async def generate_rules_system(
        self,
        worldview: Dict[str, Any],
        rule_types: List[str] = None
    ) -> Dict[str, Any]:
        """生成规则体系

        Args:
            worldview: 已生成的世界观信息
            rule_types: 需要生成的规则类型列表，默认生成所有类型

        Returns:
            规则体系字典：
            {
                "physical_laws": List[str],    # 物理法则
                "social_rules": List[str],     # 社会规则
                "cultural_norms": List[str],   # 文化规范
                "economic_principles": List[str], # 经济原则
                "political_system": str        # 政治制度
            }
        """

    def validate_worldview(self, worldview: Dict[str, Any]) -> Dict[str, Any]:
        """验证世界观设定的完整性和一致性

        Args:
            worldview: 待验证的世界观设定

        Returns:
            验证结果：
            {
                "is_valid": bool,        # 是否有效
                "completeness_score": float,  # 完整性评分(0-1)
                "consistency_score": float,   # 一致性评分(0-1)
                "issues": List[str],          # 发现的问题列表
                "suggestions": List[str]      # 改进建议列表
            }
        """
```

#### blueprint.py - 剧情蓝图生成

```python
class StrictBlueprintGenerator:
    """严格章节蓝图生成器

    使用零容忍策略确保生成的蓝图完整无缺。
    """

    def __init__(self, llm_adapter: BaseLLMAdapter, max_retries: int = 5):
        """初始化蓝图生成器

        Args:
            llm_adapter: LLM适配器实例
            max_retries: 最大重试次数
        """

    async def generate_chapter_blueprint(
        self,
        chapter_info: Dict[str, Any],
        world_context: Dict[str, Any],
        previous_chapters: Optional[List[Dict[str, Any]]] = None,
        word_count_target: int = 4000
    ) -> Dict[str, Any]:
        """生成章节蓝图（严格模式）

        Args:
            chapter_info: 章节基本信息
            world_context: 世界观上下文
            previous_chapters: 前面章节的列表
            word_count_target: 目标字数

        Returns:
            章节蓝图字典，包含24个字段的详细信息：
            {
                # 基础字段
                "chapter_number": int,        # 章节编号
                "chapter_title": str,         # 章节标题
                "word_count_target": int,     # 字数目标
                "core_conflict": str,         # 核心冲突
                "time_location": str,         # 时间地点
                "chapter_summary": str,       # 章节简介

                # 扩展字段
                "emotional_arc": str,         # 情感弧光
                "hook_design": str,           # 钩子设计
                "foreshadowing": str,         # 伏笔线索
                "conflict_design": str,       # 冲突设计
                "character_relationships": str, # 人物关系
                "scene_description": str,     # 场景描述
                "action_design": str,         # 动作设计
                "dialogue_design": str,       # 对话设计
                "psychological_description": str, # 心理描写
                "environment_description": str,  # 环境描写
                "symbolism_metaphor": str,    # 象征隐喻
                "rhythm_control": str,        # 节奏控制
                "suspense_setup": str,        # 悬念设置
                "climax_design": str,         # 高潮设计
                "ending_arrangement": str,    # 结局安排
                "transition_design": str,     # 过渡设计
                "style_requirements": str,    # 风格要求
                "creation_notes": str         # 创作备注
            }

        Raises:
            BlueprintGenerationError: 生成失败且重试次数用尽时
            ValidationError: 蓝图验证失败时
        """

    def _validate_blueprint_completeness(self, blueprint: Dict[str, Any]) -> bool:
        """验证蓝图完整性（零容忍策略）

        检查是否包含任何省略内容或不完整信息。

        Args:
            blueprint: 待验证的蓝图

        Returns:
            True if blueprint is complete, False otherwise
        """

    async def repair_blueprint(
        self,
        incomplete_blueprint: Dict[str, Any]
    ) -> Dict[str, Any]:
        """修复不完整的蓝图

        Args:
            incomplete_blueprint: 不完整的蓝图

        Returns:
            修复后的完整蓝图
        """
```

#### chapter.py - 章节内容生成

```python
class ChapterGenerator:
    """章节内容生成器

    结合向量检索和LLM生成完整的章节内容。
    """

    def __init__(
        self,
        llm_adapter: BaseLLMAdapter,
        vectorstore_manager: VectorStoreManager,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化章节生成器

        Args:
            llm_adapter: LLM适配器
            vectorstore_manager: 向量数据库管理器
            config: 生成配置参数
        """

    async def generate_chapter_draft(
        self,
        chapter_blueprint: Dict[str, Any],
        novel_context: Dict[str, Any],
        retrieval_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成章节草稿

        Args:
            chapter_blueprint: 章节蓝图
            novel_context: 小说上下文信息
            retrieval_options: 检索选项

        Returns:
            生成的章节草稿文本

        Raises:
            ContentGenerationError: 内容生成失败
            ValidationError: 生成内容验证失败
        """

    async def get_relevant_context(
        self,
        chapter_blueprint: Dict[str, Any],
        max_context_length: int = 2000
    ) -> List[Dict[str, Any]]:
        """获取相关的上下文信息

        Args:
            chapter_blueprint: 章节蓝图
            max_context_length: 最大上下文长度

        Returns:
            相关上下文列表
        """

    def build_generation_prompt(
        self,
        chapter_blueprint: Dict[str, Any],
        context: List[Dict[str, Any]],
        novel_context: Dict[str, Any]
    ) -> str:
        """构建生成提示

        Args:
            chapter_blueprint: 章节蓝图
            context: 相关上下文
            novel_context: 小说上下文

        Returns:
            构建好的提示文本
        """

    def validate_chapter_content(
        self,
        content: str,
        blueprint: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证章节内容

        Args:
            content: 章节内容
            blueprint: 章节蓝图

        Returns:
            验证结果：
            {
                "is_valid": bool,           # 是否有效
                "completeness_score": float, # 完整性评分
                "consistency_score": float,  # 一致性评分
                "word_count": int,          # 实际字数
                "issues": List[str],        # 问题列表
                "suggestions": List[str]    # 改进建议
            }
        """
```

#### vectorstore_utils.py - 向量数据库管理

```python
class VectorStoreManager:
    """向量存储管理器

    基于ChromaDB管理小说内容的向量存储和检索。
    """

    def __init__(
        self,
        persist_directory: str = "./vectorstore",
        collection_name: str = "novel_chapters",
        embedding_config: Optional[Dict[str, Any]] = None
    ):
        """初始化向量存储管理器

        Args:
            persist_directory: 持久化目录
            collection_name: 集合名称
            embedding_config: 嵌入配置
        """

    async def add_chapter(
        self,
        chapter_id: str,
        content: str,
        metadata: Dict[str, Any],
        chunk_size: int = 1000,
        overlap: int = 200
    ) -> bool:
        """添加章节到向量存储

        Args:
            chapter_id: 章节ID
            content: 章节内容
            metadata: 元数据
            chunk_size: 分块大小
            overlap: 重叠大小

        Returns:
            是否添加成功
        """

    async def search_relevant_content(
        self,
        query: str,
        n_results: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """搜索相关内容

        Args:
            query: 查询文本
            n_results: 返回结果数量
            filters: 过滤条件

        Returns:
            相关内容列表
        """

    async def get_chapter_context(
        self,
        chapter_id: str,
        context_window: int = 3
    ) -> Dict[str, Any]:
        """获取章节上下文

        Args:
            chapter_id: 章节ID
            context_window: 上下文窗口大小

        Returns:
            上下文信息
        """

    def update_chapter(
        self,
        chapter_id: str,
        new_content: str,
        new_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新章节内容

        Args:
            chapter_id: 章节ID
            new_content: 新内容
            new_metadata: 新元数据

        Returns:
            是否更新成功
        """

    def delete_chapter(self, chapter_id: str) -> bool:
        """删除章节

        Args:
            chapter_id: 章节ID

        Returns:
            是否删除成功
        """

    def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息

        Returns:
            统计信息：
            {
                "total_chapters": int,      # 总章节数
                "total_documents": int,     # 总文档数
                "total_tokens": int,        # 总令牌数
                "storage_size": str,        # 存储大小
                "last_updated": str         # 最后更新时间
            }
        """
```

## 🔄 适配器系统API

### llm_adapters.py - LLM适配器

```python
class BaseLLMAdapter(ABC):
    """LLM适配器基类

    定义所有LLM适配器必须实现的接口。
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        **kwargs
    ) -> str:
        """生成文本

        Args:
            prompt: 输入提示
            **kwargs: 额外参数（temperature, max_tokens等）

        Returns:
            生成的文本

        Raises:
            APIError: API调用失败
            ValidationError: 参数验证失败
        """

    @abstractmethod
    def get_rate_limit(self) -> Dict[str, Any]:
        """获取频率限制信息

        Returns:
            频率限制信息：
            {
                "requests_per_hour": int,   # 每小时请求数
                "tokens_per_minute": int,   # 每分钟令牌数
                "min_interval": float,      # 最小间隔(秒)
                "concurrent_limit": int     # 并发限制
            }
        """

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置参数

        Args:
            config: 配置字典

        Returns:
            是否有效
        """
```

```python
class OpenAIAdapter(BaseLLMAdapter):
    """OpenAI API适配器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化OpenAI适配器

        Args:
            config: 配置字典，包含：
            {
                "api_key": str,             # API密钥
                "base_url": str,            # API基础URL
                "model_name": str,          # 模型名称
                "temperature": float,       # 温度参数
                "max_tokens": int,          # 最大令牌数
                "timeout": int,             # 超时时间
                "organization": str         # 组织ID（可选）
            }
        """

    async def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """使用OpenAI API生成文本"""

    async def generate_with_history(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """基于对话历史生成文本

        Args:
            messages: 对话历史列表，格式：
            [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "用户输入"},
                {"role": "assistant", "content": "AI回复"}
            ]
        """
```

```python
class DeepSeekAdapter(BaseLLMAdapter):
    """DeepSeek API适配器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化DeepSeek适配器"""

    async def generate(self, prompt: str, **kwargs) -> str:
        """使用DeepSeek API生成文本"""
```

```python
class GLMAdapter(BaseLLMAdapter):
    """智谱AI GLM适配器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化智谱AI适配器"""

    async def generate(self, prompt: str, **kwargs) -> str:
        """使用智谱AI API生成文本"""
```

```python
def create_llm_adapter(config: Dict[str, Any]) -> BaseLLMAdapter:
    """LLM适配器工厂函数

    Args:
        config: 适配器配置，必须包含"interface_format"字段

    Returns:
        对应的LLM适配器实例

    Raises:
        ValueError: 不支持的接口格式
        ConfigurationError: 配置错误
    """

    interface_format = config.get("interface_format", "OpenAI")

    adapter_map = {
        "OpenAI": OpenAIAdapter,
        "DeepSeek": DeepSeekAdapter,
        "智谱AI": GLMAdapter,
        "zhipuai": GLMAdapter,  # 兼容不同写法
        "Gemini": GeminiAdapter
    }

    adapter_class = adapter_map.get(interface_format)
    if not adapter_class:
        raise ValueError(f"不支持的接口格式: {interface_format}")

    return adapter_class(config)
```

### embedding_adapters.py - 嵌入适配器

```python
class BaseEmbeddingAdapter(ABC):
    """嵌入适配器基类"""

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量列表
        """

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """获取嵌入向量维度"""

    @abstractmethod
    def get_batch_size(self) -> int:
        """获取批处理大小"""
```

```python
class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """OpenAI嵌入适配器"""

    def __init__(self, config: Dict[str, Any]):
        """初始化OpenAI嵌入适配器

        Args:
            config: 配置字典
        """

    async def generate_embedding(self, text: str) -> List[float]:
        """生成OpenAI文本嵌入"""

    async def generate_batch_embeddings(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """批量生成嵌入向量"""
```

```python
def create_embedding_adapter(config: Dict[str, Any]) -> BaseEmbeddingAdapter:
    """嵌入适配器工厂函数"""

    interface_format = config.get("interface_format", "OpenAI")

    adapter_map = {
        "OpenAI": OpenAIEmbeddingAdapter,
        # 可扩展其他嵌入服务
    }

    adapter_class = adapter_map.get(interface_format)
    if not adapter_class:
        raise ValueError(f"不支持的嵌入接口格式: {interface_format}")

    return adapter_class(config)
```

## 🎨 UI组件API

### main_window.py - 主窗口

```python
class NovelGeneratorGUI:
    """小说生成器主GUI类"""

    def __init__(self, root: ctk.CTk):
        """初始化主窗口

        Args:
            root: CustomTkinter根窗口
        """

    def setup_theme(self, theme: str = "dark"):
        """设置主题

        Args:
            theme: 主题名称（"dark"或"light"）
        """

    def setup_main_layout(self):
        """设置主布局"""

    def setup_tabs(self):
        """设置功能标签页"""

    def show_status_message(self, message: str, duration: int = 3000):
        """显示状态消息

        Args:
            message: 消息内容
            duration: 显示时长(毫秒)
        """

    def show_error_dialog(self, title: str, message: str):
        """显示错误对话框

        Args:
            title: 对话框标题
            message: 错误消息
        """

    def update_progress(self, value: int, maximum: int = 100):
        """更新进度条

        Args:
            value: 当前进度值
            maximum: 最大值
        """
```

### generation_handlers.py - 生成处理器

```python
class GenerationHandler:
    """生成处理器

    处理UI与后台生成任务的交互。
    """

    def __init__(
        self,
        ui_instance: NovelGeneratorGUI,
        config_manager: ConfigManager
    ):
        """初始化生成处理器

        Args:
            ui_instance: UI实例
            config_manager: 配置管理器
        """

    async def handle_worldview_generation(
        self,
        genre: str,
        theme: str,
        style: str
    ) -> Dict[str, Any]:
        """处理世界观生成

        Args:
            genre: 小说类型
            theme: 主题
            style: 风格

        Returns:
            生成的世界观信息
        """

    async def handle_chapter_generation(
        self,
        chapter_info: Dict[str, Any],
        progress_callback: Optional[Callable] = None
    ) -> str:
        """处理章节生成

        Args:
            chapter_info: 章节信息
            progress_callback: 进度回调函数

        Returns:
            生成的章节内容
        """

    def on_generation_progress(self, progress: int, message: str):
        """生成进度回调

        Args:
            progress: 进度百分比(0-100)
            message: 进度消息
        """

    def on_generation_complete(self, result: Any):
        """生成完成回调

        Args:
            result: 生成结果
        """

    def on_generation_error(self, error: Exception):
        """生成错误回调

        Args:
            error: 错误信息
        """
```

## ⚙️ 配置系统API

### config_manager.py - 配置管理器

```python
class ConfigManager:
    """配置管理器

    负责应用配置的加载、保存和管理。
    """

    def __init__(self, config_file: str = "config.json"):
        """初始化配置管理器

        Args:
            config_file: 配置文件路径
        """

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            JSONDecodeError: 配置文件格式错误
        """

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """保存配置到文件

        Args:
            config: 要保存的配置，None表示保存当前配置
        """

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键（支持点号分隔的嵌套键）
            default: 默认值

        Returns:
            配置值

        Example:
            value = config_manager.get("llm_configs.OpenAI.api_key")
        """

    def set(self, key: str, value: Any):
        """设置配置项

        Args:
            key: 配置键（支持点号分隔）
            value: 配置值
        """

    def get_llm_config(self, service_name: str) -> Dict[str, Any]:
        """获取LLM服务配置

        Args:
            service_name: 服务名称

        Returns:
            LLM服务配置
        """

    def save_llm_config(self, service_name: str, config: Dict[str, Any]):
        """保存LLM服务配置

        Args:
            service_name: 服务名称
            config: 服务配置
        """

    def create_default_config(self) -> Dict[str, Any]:
        """创建默认配置

        Returns:
            默认配置字典
        """

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置

        Args:
            config: 待验证的配置

        Returns:
            验证结果：
            {
                "is_valid": bool,         # 是否有效
                "errors": List[str],      # 错误列表
                "warnings": List[str]     # 警告列表
            }
        """

    def backup_config(self, backup_path: Optional[str] = None):
        """备份配置文件

        Args:
            backup_path: 备份路径，None表示自动生成
        """

    def restore_config(self, backup_path: str):
        """恢复配置文件

        Args:
            backup_path: 备份文件路径
        """
```

### chapter_directory_parser.py - 章节目录解析器

```python
class ChapterDirectoryParser:
    """章节目录解析器

    解析24字段格式的章节目录信息。
    """

    def __init__(self):
        """初始化解析器"""
        self.setup_patterns()

    def setup_patterns(self):
        """设置正则表达式模式"""
        self.chapter_title_pattern = re.compile(r'^章节标题：\s*(.*)')
        self.emotional_arc_pattern = re.compile(r'^情感弧光：\s*(.*)')
        self.hook_design_pattern = re.compile(r'^钩子设计：\s*(.*)')
        # ... 其他字段的正则表达式

    def parse_chapter_directory(
        self,
        directory_text: str
    ) -> Dict[str, Any]:
        """解析章节目录文本

        Args:
            directory_text: 章节目录文本

        Returns:
            解析结果字典，包含24个字段

        Raises:
            ParseError: 解析失败
        """

    def parse_single_field(self, line: str) -> Optional[Tuple[str, str]]:
        """解析单行字段

        Args:
            line: 文本行

        Returns:
            (字段名, 字段值)元组，如果无法解析则返回None
        """

    def validate_parsed_fields(
        self,
        fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证解析的字段

        Args:
            fields: 解析的字段字典

        Returns:
            验证结果
        """

    def format_chapter_directory(
        self,
        fields: Dict[str, Any]
    ) -> str:
        """格式化章节目录

        Args:
            fields: 字段字典

        Returns:
            格式化的目录文本
        """
```

## 🔧 工具函数API

### novel_generator/common.py - 通用工具

```python
async def call_with_retry(
    func: Callable,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs
) -> Any:
    """带重试机制的函数调用

    Args:
        func: 要调用的函数
        max_retries: 最大重试次数
        retry_delay: 重试间隔(秒)
        exceptions: 需要重试的异常类型
        **kwargs: 函数参数

    Returns:
        函数执行结果

    Raises:
        最后一次调用的异常
    """

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
):
    """设置日志系统

    Args:
        level: 日志级别
        log_file: 日志文件路径
        format_string: 日志格式字符串
    """

def measure_execution_time(func: Callable) -> Callable:
    """执行时间测量装饰器

    Args:
        func: 要装饰的函数

    Returns:
        装饰后的函数
    """

def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """安全除法

    Args:
        a: 被除数
        b: 除数
        default: 除数为0时的默认值

    Returns:
        除法结果
    """

def truncate_text(
    text: str,
    max_length: int,
    suffix: str = "..."
) -> str:
    """截断文本

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀

    Returns:
        截断后的文本
    """
```

### novel_generator/wordcount_utils.py - 字数统计

```python
def count_chinese_words(text: str) -> int:
    """统计中文字数

    Args:
        text: 文本内容

    Returns:
        中文字数
    """

def count_english_words(text: str) -> int:
    """统计英文单词数

    Args:
        text: 文本内容

    Returns:
        英文单词数
    """

def count_total_words(text: str) -> Dict[str, int]:
    """统计总字数（包含中英文）

    Args:
        text: 文本内容

    Returns:
        字数统计：
        {
            "chinese_chars": int,    # 中文字符数
            "english_words": int,    # 英文单词数
            "total_words": int,      # 总字数
            "punctuation_count": int, # 标点符号数
            "paragraph_count": int    # 段落数
        }
    """

def estimate_reading_time(text: str, words_per_minute: int = 300) -> Dict[str, Any]:
    """估算阅读时间

    Args:
        text: 文本内容
        words_per_minute: 每分钟阅读字数

    Returns:
        阅读时间估算：
        {
            "minutes": int,          # 分钟数
            "hours": float,          # 小时数
            "formatted": str         # 格式化时间
        }
    """
```

## ⚠️ 错误处理

### 自定义异常类

```python
class NovelGeneratorError(Exception):
    """小说生成器基础异常类"""
    pass

class APIError(NovelGeneratorError):
    """API调用相关错误"""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code

class ValidationError(NovelGeneratorError):
    """验证错误"""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field

class ConfigurationError(NovelGeneratorError):
    """配置错误"""
    pass

class ContentGenerationError(NovelGeneratorError):
    """内容生成错误"""

    def __init__(self, message: str, retry_count: int = 0):
        super().__init__(message)
        self.retry_count = retry_count

class VectorStoreError(NovelGeneratorError):
    """向量存储错误"""
    pass

class ParseError(NovelGeneratorError):
    """解析错误"""

    def __init__(self, message: str, line_number: Optional[int] = None):
        super().__init__(message)
        self.line_number = line_number
```

### 错误处理装饰器

```python
def handle_exceptions(
    default_return: Any = None,
    log_errors: bool = True,
    reraise: bool = False
):
    """异常处理装饰器

    Args:
        default_return: 发生异常时的默认返回值
        log_errors: 是否记录错误日志
        reraise: 是否重新抛出异常
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"函数 {func.__name__} 执行失败: {e}")
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator
```

## 📝 类型定义

### 基础类型别名

```python
from typing import Dict, List, Optional, Union, Callable, Any, Tuple

# 基础类型别名
ChapterID = str
ChapterContent = str
ChapterBlueprint = Dict[str, Any]
WorldContext = Dict[str, Any]
CharacterProfile = Dict[str, Any]
StorySetting = Dict[str, Any]

# 回调函数类型
ProgressCallback = Callable[[int, str], None]
ErrorCallback = Callable[[Exception], None]
CompletionCallback = Callable[[Any], None]

# 配置类型
LLMConfig = Dict[str, Any]
EmbeddingConfig = Dict[str, Any]
GenerationConfig = Dict[str, Any]

# 验证结果类型
ValidationResult = Dict[str, Any]  # {"is_valid": bool, "errors": List[str], ...}

# 统计信息类型
Statistics = Dict[str, Any]
```

### 数据类定义

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ChapterInfo:
    """章节信息数据类"""
    chapter_id: str
    title: str
    word_count: int
    created_at: datetime
    updated_at: datetime
    status: str  # "draft", "completed", "published"
    blueprint: Optional[ChapterBlueprint] = None
    content: Optional[ChapterContent] = None

@dataclass
class CharacterInfo:
    """角色信息数据类"""
    character_id: str
    name: str
    age: int
    gender: str
    occupation: str
    personality: str
    background: str
    relationships: Dict[str, str]
    current_status: str
    first_appearance: int  # 首次出现的章节号

@dataclass
class ProjectInfo:
    """项目信息数据类"""
    project_id: str
    title: str
    author: str
    genre: str
    theme: str
    style: str
    target_word_count: int
    chapter_count: int
    created_at: datetime
    updated_at: datetime
    status: str  # "planning", "writing", "reviewing", "completed"
```

## 🔌 扩展接口

### 插件系统接口

```python
class BasePlugin:
    """插件基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def get_name(self) -> str:
        """获取插件名称"""

    @abstractmethod
    def get_version(self) -> str:
        """获取插件版本"""

    @abstractmethod
    def initialize(self) -> bool:
        """初始化插件

        Returns:
            是否初始化成功
        """

    def cleanup(self):
        """清理资源"""
        pass

class GenerationPlugin(BasePlugin):
    """生成插件基类"""

    @abstractmethod
    async def pre_generate(
        self,
        blueprint: ChapterBlueprint,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成前处理

        Args:
            blueprint: 章节蓝图
            context: 上下文信息

        Returns:
            处理后的上下文
        """

    @abstractmethod
    async def post_generate(
        self,
        content: ChapterContent,
        blueprint: ChapterBlueprint,
        context: Dict[str, Any]
    ) -> ChapterContent:
        """生成后处理

        Args:
            content: 生成的内容
            blueprint: 章节蓝图
            context: 上下文信息

        Returns:
            处理后的内容
        """

class ValidationPlugin(BasePlugin):
    """验证插件基类"""

    @abstractmethod
    def validate(
        self,
        content: ChapterContent,
        context: Dict[str, Any]
    ) -> ValidationResult:
        """验证内容

        Args:
            content: 待验证内容
            context: 验证上下文

        Returns:
            验证结果
        """
```

### 事件系统接口

```python
class EventEmitter:
    """事件发射器"""

    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}

    def on(self, event: str, callback: Callable):
        """注册事件监听器

        Args:
            event: 事件名称
            callback: 回调函数
        """

    def off(self, event: str, callback: Callable):
        """移除事件监听器

        Args:
            event: 事件名称
            callback: 回调函数
        """

    def emit(self, event: str, *args, **kwargs):
        """发射事件

        Args:
            event: 事件名称
            *args: 位置参数
            **kwargs: 关键字参数
        """

# 预定义事件
EVENT_GENERATION_STARTED = "generation:started"
EVENT_GENERATION_PROGRESS = "generation:progress"
EVENT_GENERATION_COMPLETED = "generation:completed"
EVENT_GENERATION_ERROR = "generation:error"
EVENT_VALIDATION_COMPLETED = "validation:completed"
EVENT_CONTENT_SAVED = "content:saved"
```

### 自定义LLM服务扩展

```python
class CustomLLMAdapter(BaseLLMAdapter):
    """自定义LLM适配器示例

    演示如何扩展支持新的LLM服务。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.api_key = config["api_key"]
        self.base_url = config["base_url"]
        self.model_name = config["model_name"]
        # 初始化自定义API客户端

    async def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """实现自定义LLM的文本生成"""

        # 构建API请求
        request_data = {
            "prompt": prompt,
            "model": self.model_name,
            "temperature": temperature or 0.7,
            "max_tokens": max_tokens or 2000,
            **kwargs
        }

        # 调用自定义API
        try:
            response = await self.api_client.generate(request_data)
            return response.text
        except Exception as e:
            raise APIError(f"自定义LLM API调用失败: {e}")

    def get_rate_limit(self) -> Dict[str, Any]:
        """返回自定义LLM的频率限制"""
        return {
            "requests_per_hour": 1000,
            "tokens_per_minute": 60000,
            "min_interval": 0.5,
            "concurrent_limit": 10
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证自定义LLM的配置"""
        required_fields = ["api_key", "base_url", "model_name"]
        return all(field in config for field in required_fields)

# 注册自定义适配器
def register_custom_adapter():
    """注册自定义适配器到工厂函数"""

    # 修改create_llm_adapter函数中的adapter_map
    adapter_map["CustomLLM"] = CustomLLMAdapter
```

---

## 📞 API支持

如果您在API使用过程中遇到问题，可以通过以下方式获取帮助：

- 📧 **API技术支持**: api-support@ai-novelgenerator.com
- 📖 **API文档更新**: [在线API文档](https://docs.ai-novelgenerator.com/api)
- 🐛 **Bug报告**: [GitHub API Issues](https://github.com/your-username/AI_NovelGenerator/issues)
- 💬 **开发者讨论**: [GitHub Discussions](https://github.com/your-username/AI_NovelGenerator/discussions)

### API版本历史

- **v1.0**: 初始API版本
- **v1.1**: 添加向量存储API
- **v1.2**: 扩展适配器系统
- **v1.3**: 添加插件系统接口
- **v2.0**: 重构核心API，提升性能和可扩展性

---

本文档持续更新，请关注最新版本。