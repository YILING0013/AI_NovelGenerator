# -*- coding: utf-8 -*-
"""
AI小说生成器 - 架构一致性验证器
确保所有修复和重构不破坏现有架构的完整性
验证设计模式、接口兼容性和模块边界
"""

import os
import ast
import importlib.util
import inspect
import logging
import sys
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import traceback
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('architecture_validation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ValidationSeverity(Enum):
    """验证严重性级别"""
    INFO = "信息"
    WARNING = "警告"
    ERROR = "错误"
    CRITICAL = "严重"

class DesignPattern(Enum):
    """设计模式类型"""
    ADAPTER = "适配器模式"
    FACTORY = "工厂模式"
    MVC = "MVC模式"
    STRATEGY = "策略模式"
    SINGLETON = "单例模式"
    OBSERVER = "观察者模式"

@dataclass
class ValidationResult:
    """验证结果"""
    pattern: DesignPattern
    severity: ValidationSeverity
    message: str
    file_path: str
    line_number: int = 0
    suggestions: List[str] = field(default_factory=list)

@dataclass
class ArchitectureAnalysis:
    """架构分析结果"""
    patterns_found: Dict[DesignPattern, List[str]] = field(default_factory=dict)
    violations: List[ValidationResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    overall_score: float = 0.0

class ArchitectureConsistencyValidator:
    """架构一致性验证器主类"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.python_files: List[Path] = []
        self.import_graph: Dict[str, Set[str]] = {}
        self.class_hierarchy: Dict[str, List[str]] = {}
        self.interface_definitions: Dict[str, List[str]] = {}

    def scan_project(self) -> bool:
        """扫描项目文件"""
        try:
            logger.info("开始扫描项目文件...")

            # 扫描所有Python文件
            for py_file in self.project_root.rglob("*.py"):
                # 跳过一些特殊目录
                if any(skip in str(py_file) for skip in ["__pycache__", ".git", "venv", "node_modules"]):
                    continue
                self.python_files.append(py_file)

            logger.info(f"找到 {len(self.python_files)} 个Python文件")

            # 构建依赖图
            self._build_import_graph()

            # 分析类层次结构
            self._analyze_class_hierarchy()

            # 提取接口定义
            self._extract_interface_definitions()

            return True

        except Exception as e:
            logger.error(f"项目扫描失败: {e}")
            traceback.print_exc()
            return False

    def _build_import_graph(self):
        """构建导入依赖图"""
        logger.info("构建导入依赖图...")

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                module_name = str(py_file.relative_to(self.project_root)).replace('/', '.')[:-3]

                imports = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.add(node.module.split('.')[0])

                self.import_graph[module_name] = imports

            except Exception as e:
                logger.warning(f"分析文件 {py_file} 失败: {e}")

    def _analyze_class_hierarchy(self):
        """分析类层次结构"""
        logger.info("分析类层次结构...")

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                file_path = str(py_file.relative_to(self.project_root))

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        class_name = node.name
                        bases = []

                        for base in node.bases:
                            if isinstance(base, ast.Name):
                                bases.append(base.id)
                            elif isinstance(base, ast.Attribute):
                                bases.append(ast.unparse(base))

                        if bases:  # 只记录有继承关系的类
                            self.class_hierarchy[f"{file_path}:{class_name}"] = bases

            except Exception as e:
                logger.warning(f"分析类层次结构时处理文件 {py_file} 失败: {e}")

    def _extract_interface_definitions(self):
        """提取接口定义（抽象基类）"""
        logger.info("提取接口定义...")

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                file_path = str(py_file.relative_to(self.project_root))

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # 检查是否是抽象基类或接口
                        methods = []
                        is_interface = False

                        for item in node.body:
                            if isinstance(item, ast.FunctionDef):
                                # 检查是否是抽象方法
                                if any(decorator.id == 'abstractmethod'
                                       for decorator in item.decorator_list
                                       if isinstance(decorator, ast.Name)):
                                    is_interface = True

                                methods.append(item.name)

                        if is_interface or self._is_interface_by_name(node.name):
                            self.interface_definitions[f"{file_path}:{node.name}"] = methods

            except Exception as e:
                logger.warning(f"提取接口定义时处理文件 {py_file} 失败: {e}")

    def _is_interface_by_name(self, class_name: str) -> bool:
        """通过名称判断是否是接口"""
        interface_patterns = [
            "Base", "Abstract", "Interface", "Protocol",
            "Adapter"  # 适配器基类
        ]
        return any(pattern in class_name for pattern in interface_patterns)

    def validate_adapter_pattern(self) -> List[ValidationResult]:
        """验证适配器模式"""
        logger.info("验证适配器模式...")
        results = []

        # 查找适配器类
        adapter_classes = []
        for file_class, bases in self.class_hierarchy.items():
            if any("Adapter" in base or "Base" in base for base in bases):
                adapter_classes.append(file_class)

        logger.info(f"找到 {len(adapter_classes)} 个适配器类")

        # 验证适配器实现
        for class_info in adapter_classes:
            file_path, class_name = class_info.split(':')

            # 检查是否有统一的接口
            try:
                py_file = self.project_root / file_path
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                class_node = None

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == class_name:
                        class_node = node
                        break

                if class_node:
                    # 检查是否有invoke方法
                    has_invoke = any(
                        method.name == 'invoke'
                        for method in class_node.body
                        if isinstance(method, ast.FunctionDef)
                    )

                    if not has_invoke:
                        results.append(ValidationResult(
                            pattern=DesignPattern.ADAPTER,
                            severity=ValidationSeverity.ERROR,
                            message=f"适配器类 {class_name} 缺少标准的 invoke 方法",
                            file_path=file_path,
                            line_number=class_node.lineno,
                            suggestions=["添加 invoke(self, prompt: str) -> str 方法"]
                        ))

                    # 检查方法签名一致性
                    self._check_adapter_method_signatures(class_node, file_path, results)

            except Exception as e:
                logger.warning(f"验证适配器 {class_name} 时出错: {e}")

        return results

    def _check_adapter_method_signatures(self, class_node: ast.ClassDef, file_path: str, results: List[ValidationResult]):
        """检查适配器方法签名一致性"""
        invoke_methods = [
            method for method in class_node.body
            if isinstance(method, ast.FunctionDef) and method.name == 'invoke'
        ]

        if invoke_methods:
            method = invoke_methods[0]

            # 检查参数
            args = [arg.arg for arg in method.args.args]
            if len(args) < 2 or args[1] != 'prompt':
                results.append(ValidationResult(
                    pattern=DesignPattern.ADAPTER,
                    severity=ValidationSeverity.WARNING,
                    message=f"适配器 invoke 方法参数签名不标准",
                    file_path=file_path,
                    line_number=method.lineno,
                    suggestions=["使用标准签名: invoke(self, prompt: str) -> str"]
                ))

            # 检查返回类型注解
            if not method.returns:
                results.append(ValidationResult(
                    pattern=DesignPattern.ADAPTER,
                    severity=ValidationSeverity.INFO,
                    message=f"适配器 invoke 方法缺少返回类型注解",
                    file_path=file_path,
                    line_number=method.lineno,
                    suggestions=["添加返回类型注解: -> str"]
                ))

    def validate_factory_pattern(self) -> List[ValidationResult]:
        """验证工厂模式"""
        logger.info("验证工厂模式...")
        results = []

        # 查找工厂类
        factory_classes = []
        for file_path in self.python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if "Factory" in content or "create_" in content:
                    tree = ast.parse(content)
                    file_str = str(file_path.relative_to(self.project_root))

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and "Factory" in node.name:
                            factory_classes.append(f"{file_str}:{node.name}")

            except Exception as e:
                logger.warning(f"搜索工厂模式时处理文件 {file_path} 失败: {e}")

        logger.info(f"找到 {len(factory_classes)} 个工厂类")

        # 验证工厂实现
        for class_info in factory_classes:
            file_path, class_name = class_info.split(':')

            try:
                py_file = self.project_root / file_path
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                class_node = None

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == class_name:
                        class_node = node
                        break

                if class_node:
                    # 检查是否有create方法
                    create_methods = [
                        method for method in class_node.body
                        if isinstance(method, ast.FunctionDef) and
                        (method.name.startswith('create') or method.name.startswith('get'))
                    ]

                    if not create_methods:
                        results.append(ValidationResult(
                            pattern=DesignPattern.FACTORY,
                            severity=ValidationSeverity.WARNING,
                            message=f"工厂类 {class_name} 缺少标准的创建方法",
                            file_path=file_path,
                            line_number=class_node.lineno,
                            suggestions=["添加 create_xxx 或 get_xxx 静态方法"]
                        ))

            except Exception as e:
                logger.warning(f"验证工厂 {class_name} 时出错: {e}")

        return results

    def validate_mvc_pattern(self) -> List[ValidationResult]:
        """验证MVC模式"""
        logger.info("验证MVC模式...")
        results = []

        # 检查目录结构
        expected_structure = {
            "ui/": "View层",
            "novel_generator/": "Model层",
        }

        for dir_path, description in expected_structure.items():
            full_path = self.project_root / dir_path
            if not full_path.exists():
                results.append(ValidationResult(
                    pattern=DesignPattern.MVC,
                    severity=ValidationSeverity.ERROR,
                    message=f"缺少{description}目录: {dir_path}",
                    file_path=str(full_path),
                    suggestions=[f"创建 {dir_path} 目录并放置相应的{description}代码"]
                ))

        # 检查层级间的依赖关系
        ui_files = [f for f in self.python_files if "ui/" in str(f)]
        model_files = [f for f in self.python_files if "novel_generator/" in str(f)]

        # UI不应该直接引用具体的业务逻辑实现
        for ui_file in ui_files:
            try:
                with open(ui_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 检查是否有直接的业务逻辑导入
                if "from novel_generator." in content and "import " in content:
                    # 检查是否是合理的导入（如接口或常量）
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if "from novel_generator." in line and "import " in line:
                            if not any(keyword in line for keyword in ["common", "constants", "types"]):
                                results.append(ValidationResult(
                                    pattern=DesignPattern.MVC,
                                    severity=ValidationSeverity.WARNING,
                                    message=f"UI层直接导入业务逻辑实现: {line.strip()}",
                                    file_path=str(ui_file.relative_to(self.project_root)),
                                    line_number=i,
                                    suggestions=["使用控制器层来解耦UI和业务逻辑"]
                                ))

            except Exception as e:
                logger.warning(f"验证MVC模式时处理文件 {ui_file} 失败: {e}")

        return results

    def validate_interface_consistency(self) -> List[ValidationResult]:
        """验证接口一致性"""
        logger.info("验证接口一致性...")
        results = []

        # 检查接口实现的完整性
        for interface_class, interface_methods in self.interface_definitions.items():
            interface_path, interface_name = interface_class.split(':')

            # 查找实现这个接口的类
            implementations = []
            for class_info, bases in self.class_hierarchy.items():
                if any(basename.split(':')[-1] == interface_name for basename in bases):
                    implementations.append(class_info)

            # 验证每个实现是否完整
            for impl_class in implementations:
                impl_path, impl_name = impl_class.split(':')

                try:
                    py_file = self.project_root / impl_path
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    tree = ast.parse(content)
                    class_node = None

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef) and node.name == impl_name:
                            class_node = node
                            break

                    if class_node:
                        impl_methods = [
                            method.name for method in class_node.body
                            if isinstance(method, ast.FunctionDef)
                        ]

                        missing_methods = set(interface_methods) - set(impl_methods)
                        if missing_methods:
                            results.append(ValidationResult(
                                pattern=DesignPattern.STRATEGY,  # 接口实现也是一种策略模式
                                severity=ValidationSeverity.ERROR,
                                message=f"类 {impl_name} 未完整实现接口 {interface_name}",
                                file_path=impl_path,
                                line_number=class_node.lineno,
                                suggestions=[f"实现缺少的方法: {', '.join(missing_methods)}"]
                            ))

                except Exception as e:
                    logger.warning(f"验证接口实现时处理类 {impl_name} 失败: {e}")

        return results

    def validate_configuration_consistency(self) -> List[ValidationResult]:
        """验证配置一致性"""
        logger.info("验证配置一致性...")
        results = []

        # 检查配置文件
        config_files = [
            "config.json",
            "config.example.json"
        ]

        for config_file in config_files:
            config_path = self.project_root / config_file
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)

                    # 验证配置结构
                    if isinstance(config_data, dict):
                        self._validate_config_structure(config_data, config_file, results)

                except Exception as e:
                    results.append(ValidationResult(
                        pattern=DesignPattern.SINGLETON,  # 配置管理通常是单例模式
                        severity=ValidationSeverity.ERROR,
                        message=f"配置文件 {config_file} 格式错误: {e}",
                        file_path=config_file,
                        suggestions=["修复JSON格式错误"]
                    ))

        return results

    def _validate_config_structure(self, config_data: dict, config_file: str, results: List[ValidationResult]):
        """验证配置结构"""
        required_sections = ["llm_configs"]
        optional_sections = ["embedding_configs", "choose_configs"]

        # 检查必需的配置段
        for section in required_sections:
            if section not in config_data:
                results.append(ValidationResult(
                    pattern=DesignPattern.SINGLETON,
                    severity=ValidationSeverity.ERROR,
                    message=f"配置文件缺少必需的配置段: {section}",
                    file_path=config_file,
                    suggestions=[f"添加 {section} 配置段"]
                ))

        # 检查LLM配置格式
        if "llm_configs" in config_data:
            llm_configs = config_data["llm_configs"]
            if isinstance(llm_configs, dict):
                for model_name, model_config in llm_configs.items():
                    if isinstance(model_config, dict):
                        required_fields = ["api_key", "base_url", "model_name"]
                        for field in required_fields:
                            if field not in model_config:
                                results.append(ValidationResult(
                                    pattern=DesignPattern.SINGLETON,
                                    severity=ValidationSeverity.WARNING,
                                    message=f"LLM配置 {model_name} 缺少必需字段: {field}",
                                    file_path=config_file,
                                    suggestions=[f"添加 {field} 字段"]
                                ))

    def validate_error_handling_consistency(self) -> List[ValidationResult]:
        """验证错误处理一致性"""
        logger.info("验证错误处理一致性...")
        results = []

        # 检查异常处理模式
        exception_patterns = [
            ("Exception", "过于宽泛的异常捕获"),
            ("except:", "裸异常捕获"),
            ("pass", "空的异常处理")
        ]

        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                tree = ast.parse(content)
                file_str = str(py_file.relative_to(self.project_root))

                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        # 检查异常类型
                        if node.type is None:
                            results.append(ValidationResult(
                                pattern=DesignPattern.STRATEGY,  # 错误处理策略
                                severity=ValidationSeverity.ERROR,
                                message="使用了裸异常捕获",
                                file_path=file_str,
                                line_number=node.lineno,
                                suggestions=["指定具体的异常类型"]
                            ))

                        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                            results.append(ValidationResult(
                                pattern=DesignPattern.STRATEGY,
                                severity=ValidationSeverity.WARNING,
                                message="捕获了过于宽泛的Exception异常",
                                file_path=file_str,
                                line_number=node.lineno,
                                suggestions=["使用更具体的异常类型"]
                            ))

                        # 检查异常处理内容
                        if (len(node.body) == 1 and
                            isinstance(node.body[0], ast.Pass)):
                            results.append(ValidationResult(
                                pattern=DesignPattern.STRATEGY,
                                severity=ValidationSeverity.WARNING,
                                message="异常处理为空（只有pass）",
                                file_path=file_str,
                                line_number=node.lineno,
                                suggestions=["添加适当的异常处理逻辑"]
                            ))

            except Exception as e:
                logger.warning(f"验证错误处理时处理文件 {py_file} 失败: {e}")

        return results

    def validate_dependencies(self) -> List[ValidationResult]:
        """验证依赖关系"""
        logger.info("验证依赖关系...")
        results = []

        # 检查循环依赖
        self._check_circular_dependencies(results)

        # 检查模块间依赖合理性
        self._check_dependency_layers(results)

        return results

    def _check_circular_dependencies(self, results: List[ValidationResult]):
        """检查循环依赖"""
        visited = set()
        rec_stack = set()

        def has_cycle(module):
            if module in rec_stack:
                return True
            if module in visited:
                return False

            visited.add(module)
            rec_stack.add(module)

            for dependency in self.import_graph.get(module, []):
                if dependency in self.import_graph:  # 只检查项目内的模块
                    if has_cycle(dependency):
                        return True

            rec_stack.remove(module)
            return False

        for module in self.import_graph:
            if has_cycle(module):
                results.append(ValidationResult(
                    pattern=DesignPattern.OBSERVER,  # 依赖关系影响观察者模式
                    severity=ValidationSeverity.ERROR,
                    message=f"检测到循环依赖: {module}",
                    file_path=module,
                    suggestions=["重构模块以消除循环依赖"]
                ))

    def _check_dependency_layers(self, results: List[ValidationResult]):
        """检查模块层级依赖合理性"""
        # 定义允许的依赖层级
        layer_rules = {
            "ui": ["common", "utils", "config"],  # UI层可以依赖通用工具和配置
            "novel_generator": ["common", "utils"],  # 业务层可以依赖通用工具
            "llm_adapters": ["common"],  # 适配器层只能依赖通用工具
            "config_manager": [],  # 配置管理层不应该依赖其他业务模块
        }

        for module, dependencies in self.import_graph.items():
            for dependency in dependencies:
                if dependency in self.import_graph:  # 只检查项目内依赖
                    # 检查依赖层级是否合理
                    for prefix, allowed_deps in layer_rules.items():
                        if module.startswith(prefix):
                            # 检查依赖的模块是否在允许列表中
                            dep_prefix = next((p for p in layer_rules.keys()
                                             if dependency.startswith(p)), None)

                            if dep_prefix and dep_prefix not in allowed_deps:
                                results.append(ValidationResult(
                                    pattern=DesignPattern.MVC,
                                    severity=ValidationSeverity.WARNING,
                                    message=f"模块 {module} 不应该依赖 {dependency} (层级违规)",
                                    file_path=module,
                                    suggestions=[f"遵循分层架构原则，避免跨层依赖"]
                                ))

    def run_full_validation(self) -> ArchitectureAnalysis:
        """运行完整的架构验证"""
        logger.info("开始完整架构验证...")

        analysis = ArchitectureAnalysis()

        try:
            # 扫描项目
            if not self.scan_project():
                logger.error("项目扫描失败，无法继续验证")
                return analysis

            # 运行各种验证
            logger.info("执行适配器模式验证...")
            analysis.violations.extend(self.validate_adapter_pattern())

            logger.info("执行工厂模式验证...")
            analysis.violations.extend(self.validate_factory_pattern())

            logger.info("执行MVC模式验证...")
            analysis.violations.extend(self.validate_mvc_pattern())

            logger.info("执行接口一致性验证...")
            analysis.violations.extend(self.validate_interface_consistency())

            logger.info("执行配置一致性验证...")
            analysis.violations.extend(self.validate_configuration_consistency())

            logger.info("执行错误处理一致性验证...")
            analysis.violations.extend(self.validate_error_handling_consistency())

            logger.info("执行依赖关系验证...")
            analysis.violations.extend(self.validate_dependencies())

            # 计算整体得分
            analysis.overall_score = self._calculate_overall_score(analysis.violations)

            # 生成建议
            analysis.recommendations = self._generate_recommendations(analysis.violations)

            logger.info(f"架构验证完成，整体得分: {analysis.overall_score:.1f}")

        except Exception as e:
            logger.error(f"架构验证过程中出错: {e}")
            traceback.print_exc()

        return analysis

    def _calculate_overall_score(self, violations: List[ValidationResult]) -> float:
        """计算架构整体得分"""
        if not violations:
            return 100.0

        # 根据严重程度计算扣分
        severity_penalties = {
            ValidationSeverity.INFO: 0,
            ValidationSeverity.WARNING: 5,
            ValidationSeverity.ERROR: 15,
            ValidationSeverity.CRITICAL: 30
        }

        total_penalty = sum(severity_penalties[violation.severity] for violation in violations)
        score = max(0, 100 - total_penalty)

        return score

    def _generate_recommendations(self, violations: List[ValidationResult]) -> List[str]:
        """基于验证结果生成改进建议"""
        recommendations = []

        # 统计各类问题
        pattern_counts = {}
        severity_counts = {}

        for violation in violations:
            pattern = violation.pattern.value
            severity = violation.severity.value

            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # 生成针对性建议
        if pattern_counts.get("适配器模式", 0) > 0:
            recommendations.append("加强适配器模式的实现，确保所有适配器都遵循统一的接口规范")

        if pattern_counts.get("MVC模式", 0) > 0:
            recommendations.append("完善MVC架构分层，确保UI层、业务层和数据层的清晰分离")

        if pattern_counts.get("工厂模式", 0) > 0:
            recommendations.append("优化工厂模式实现，提供更灵活的对象创建机制")

        if severity_counts.get("错误", 0) > 2:
            recommendations.append("优先解决错误级别的架构问题，确保系统稳定性")

        if severity_counts.get("警告", 0) > 5:
            recommendations.append("关注警告级别的问题，防止小问题累积成大问题")

        # 通用建议
        if len(violations) > 10:
            recommendations.append("建议分阶段进行架构改进，优先处理高优先级问题")

        recommendations.append("定期运行架构一致性验证，建立持续改进机制")

        return recommendations

    def generate_report(self, analysis: ArchitectureAnalysis) -> str:
        """生成验证报告"""
        report = []
        report.append("🏗️ AI小说生成器 - 架构一致性验证报告")
        report.append("=" * 60)
        report.append(f"📅 验证时间: {self._get_current_time()}")
        report.append(f"📁 项目路径: {self.project_root}")
        report.append(f"📊 整体得分: {analysis.overall_score:.1f}/100")
        report.append("")

        # 严重性统计
        severity_stats = {}
        for violation in analysis.violations:
            severity = violation.severity.value
            severity_stats[severity] = severity_stats.get(severity, 0) + 1

        report.append("📈 问题统计:")
        for severity, count in severity_stats.items():
            emoji = {"信息": "ℹ️", "警告": "⚠️", "错误": "❌", "严重": "🚨"}.get(severity, "❓")
            report.append(f"   {emoji} {severity}: {count} 个")
        report.append("")

        # 详细问题列表
        if analysis.violations:
            report.append("🔍 详细问题:")
            report.append("-" * 40)

            # 按严重程度分组显示
            violations_by_severity = {}
            for violation in analysis.violations:
                severity = violation.severity
                if severity not in violations_by_severity:
                    violations_by_severity[severity] = []
                violations_by_severity[severity].append(violation)

            severity_order = [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR,
                            ValidationSeverity.WARNING, ValidationSeverity.INFO]

            for severity in severity_order:
                if severity in violations_by_severity:
                    violations = violations_by_severity[severity]
                    report.append(f"\n{severity.value}:")
                    for violation in violations:
                        report.append(f"   📁 {violation.file_path}")
                        if violation.line_number > 0:
                            report.append(f"   📍 第{violation.line_number}行")
                        report.append(f"   ❗ {violation.message}")
                        if violation.suggestions:
                            report.append(f"   💡 建议: {'; '.join(violation.suggestions)}")
                        report.append("")
        else:
            report.append("✅ 未发现架构一致性问题")
            report.append("")

        # 改进建议
        if analysis.recommendations:
            report.append("💡 改进建议:")
            report.append("-" * 20)
            for i, recommendation in enumerate(analysis.recommendations, 1):
                report.append(f"{i}. {recommendation}")
            report.append("")

        # 结论
        if analysis.overall_score >= 90:
            conclusion = "优秀 - 架构一致性良好"
        elif analysis.overall_score >= 80:
            conclusion = "良好 - 有少量改进空间"
        elif analysis.overall_score >= 70:
            conclusion = "一般 - 需要一些架构改进"
        else:
            conclusion = "需要改进 - 存在较多架构问题"

        report.append("🎯 总体评估:")
        report.append(f"   {conclusion}")
        report.append(f"   建议优先处理错误级别的问题")

        return "\n".join(report)

    def _get_current_time(self) -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def save_report(self, analysis: ArchitectureAnalysis, output_file: str = "architecture_validation_report.txt"):
        """保存验证报告"""
        try:
            report = self.generate_report(analysis)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)

            # 同时保存JSON格式的详细结果
            json_file = output_file.replace('.txt', '.json')
            detailed_results = {
                "timestamp": self._get_current_time(),
                "overall_score": analysis.overall_score,
                "violations": [
                    {
                        "pattern": v.pattern.value,
                        "severity": v.severity.value,
                        "message": v.message,
                        "file_path": v.file_path,
                        "line_number": v.line_number,
                        "suggestions": v.suggestions
                    }
                    for v in analysis.violations
                ],
                "recommendations": analysis.recommendations
            }

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(detailed_results, f, ensure_ascii=False, indent=2)

            logger.info(f"验证报告已保存到: {output_file}")
            logger.info(f"详细结果已保存到: {json_file}")

            return True

        except Exception as e:
            logger.error(f"保存报告失败: {e}")
            return False

def main():
    """主函数"""
    print("🏗️ AI小说生成器 - 架构一致性验证器")
    print("=" * 50)

    # 获取项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))

    # 创建验证器实例
    validator = ArchitectureConsistencyValidator(project_root)

    # 运行验证
    print("\n🔍 开始架构验证...")
    analysis = validator.run_full_validation()

    # 显示结果
    print(f"\n📊 架构验证完成，整体得分: {analysis.overall_score:.1f}/100")
    print(f"🔍 发现问题: {len(analysis.violations)} 个")

    # 保存报告
    success = validator.save_report(analysis)

    if success:
        print("\n✅ 验证报告已保存")
        print("\n📄 查看报告:")
        print("   - architecture_validation_report.txt (可读报告)")
        print("   - architecture_validation_report.json (详细数据)")
    else:
        print("\n❌ 报告保存失败")

    # 显示简要统计
    if analysis.violations:
        severity_counts = {}
        for violation in analysis.violations:
            severity = violation.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        print("\n📈 问题统计:")
        for severity, count in severity_counts.items():
            emoji = {"信息": "ℹ️", "警告": "⚠️", "错误": "❌", "严重": "🚨"}.get(severity, "❓")
            print(f"   {emoji} {severity}: {count} 个")

    print("\n💡 建议:")
    for i, recommendation in enumerate(analysis.recommendations[:3], 1):
        print(f"   {i}. {recommendation}")

if __name__ == "__main__":
    main()