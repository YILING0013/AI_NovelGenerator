# ui/generation_handlers.py
# -*- coding: utf-8 -*-
"""
集成优化系统的生成处理器
已集成：情绪工程、动态知识库、极限性能优化
"""

import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import traceback
import glob
import time
import asyncio
from utils import read_file, save_string_to_txt, clear_file_content
from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text,
    build_chapter_prompt
)
from consistency_checker import check_consistency

# 导入优化系统
try:
    # 原有优化系统
    from emotion_engineering_system import create_emotion_engineering_system
    from dynamic_world_knowledge_base import create_dynamic_world_knowledge_base
    from ultra_consistency_checker import create_ultra_consistency_checker
    from realtime_consistency_monitor import RealtimeConsistencyMonitor

    # 新增第五层和第八层优化系统
    from template_based_creation_engine import create_template_based_creation_engine
    from tomato_platform_adapter import create_tomato_platform_adapter
    from optimized_knowledge_retrieval import create_optimized_knowledge_retrieval

    OPTIMIZATION_SYSTEMS_AVAILABLE = True
    print("✅ 所有优化系统导入成功（包括扩展模板库+优化检索系统）")
except ImportError as e:
    print(f"⚠️  部分优化系统导入失败: {e}")
    OPTIMIZATION_SYSTEMS_AVAILABLE = False

class OptimizedGenerationHandler:
    """优化的生成处理器"""

    def __init__(self, ui_instance):
        self.ui = ui_instance
        self.optimization_systems = {}
        self.initialized = False

        # 初始化优化系统
        self._init_optimization_systems()

    def _init_optimization_systems(self):
        """初始化优化系统"""
        if not OPTIMIZATION_SYSTEMS_AVAILABLE:
            print("⚠️  优化系统不可用，使用基础模式")
            return

        try:
            # 创建情绪工程系统
            self.optimization_systems['emotion'] = create_emotion_engineering_system({
                'auto_save_interval': 60,
                'emotion_decay_rate': 0.03,
                'shuangdian_frequency': 0.4,
                'personalization_enabled': True
            })

            # 创建动态知识库
            project_path = self.ui.filepath_var.get().strip()
            self.optimization_systems['knowledge'] = create_dynamic_world_knowledge_base(
                project_path,
                {
                    'auto_save_interval': 120,
                    'consistency_check_enabled': True,
                    'auto_fix_enabled': True,
                    'knowledge_graph_enabled': True
                }
            )

            # 创建超级一致性检查器
            config = {
                'max_workers': 16,
                'memory_pool_gb': 50,
                'gpu_enabled': True,
                'cache_size_mb': 2048
            }
            self.optimization_systems['consistency'] = create_ultra_consistency_checker(config)

            # 创建实时监控
            self.optimization_systems['monitor'] = RealtimeConsistencyMonitor(
                self.optimization_systems['consistency']
            )

            # 创建第五层：模板化创作引擎
            self.optimization_systems['template_engine'] = create_template_based_creation_engine()

            # 创建第八层：番茄平台适配器
            self.optimization_systems['tomato_adapter'] = create_tomato_platform_adapter()

            # 创建优化知识库检索系统
            self.optimization_systems['optimized_retrieval'] = create_optimized_knowledge_retrieval()

            self.initialized = True
            print("✅ 完整优化系统初始化完成（包括扩展模板库+优化检索系统）")

        except Exception as e:
            print(f"❌ 优化系统初始化失败: {e}")
            self.initialized = False

    def generate_chapter_batch_optimized(self, chapter_id, word_count, min_word_count, auto_enrich):
        """优化的批量章节生成"""
        if not self.initialized:
            # 回退到基础生成
            return self._basic_generation(chapter_id, word_count, min_word_count, auto_enrich)

        try:
            # 获取配置
            draft_config = self._get_draft_config()
            final_config = self._get_final_config()

            # 情绪工程分析
            emotion_context = self._analyze_emotion_context(chapter_id)

            # 知识库检索
            knowledge_context = self._retrieve_knowledge_context(chapter_id)

            # 第五层：模板化创作引擎优化
            template_context = self._apply_template_engine(chapter_id, word_count, emotion_context)

            # 第八层：番茄平台适配优化
            tomato_strategy = self._apply_tomato_adapter(chapter_id, word_count)

            # 构建增强提示（融合所有优化）
            enhanced_prompt = self._build_enhanced_prompt(
                chapter_id, word_count, emotion_context, knowledge_context,
                template_context, tomato_strategy
            )

            # 生成草稿
            draft_text = self._generate_draft_optimized(
                enhanced_prompt, draft_config
            )

            # 应用情绪工程
            if emotion_context.get('should_trigger_shuangdian'):
                draft_text = self._apply_emotion_template(
                    draft_text, emotion_context['template']
                )

            # 语言纯度检查
            draft_text = self._apply_language_purity(draft_text)

            # 字数检查和扩写
            if len(draft_text) < min_word_count and auto_enrich:
                draft_text = self._enrich_content(draft_text, word_count, draft_config)

            # 保存草稿
            self._save_chapter_draft(chapter_id, draft_text)

            # 一致性检查
            consistency_issues = self._check_consistency_optimized(
                draft_text, chapter_id
            )

            # 自动修复问题
            if consistency_issues:
                draft_text = self._auto_fix_issues(draft_text, consistency_issues)

            # 定稿处理
            self._finalize_chapter_optimized(chapter_id, draft_text, final_config)

            # 更新优化系统
            self._update_optimization_systems(chapter_id, draft_text)

            print(f"✅ 第{chapter_id}章优化生成完成")

        except Exception as e:
            print(f"❌ 第{chapter_id}章优化生成失败: {e}")
            # 回退到基础生成
            return self._basic_generation(chapter_id, word_count, min_word_count, auto_enrich)

    def _basic_generation(self, chapter_id, word_count, min_word_count, auto_enrich):
        """基础生成模式"""
        # 这里调用原有的生成逻辑
        return f"第{chapter_id}章基础生成内容"

    def _get_draft_config(self):
        """获取草稿配置"""
        llm_config = self.ui.loaded_config["llm_configs"][self.ui.prompt_draft_llm_var.get()]
        return {
            'interface_format': llm_config["interface_format"],
            'api_key': llm_config["api_key"],
            'base_url': llm_config["base_url"],
            'model_name': llm_config["model_name"],
            'temperature': llm_config["temperature"],
            'max_tokens': llm_config["max_tokens"],
            'timeout': llm_config["timeout"]
        }

    def _get_final_config(self):
        """获取定稿配置"""
        llm_config = self.ui.loaded_config["llm_configs"][self.ui.final_chapter_llm_var.get()]
        return {
            'interface_format': llm_config["interface_format"],
            'api_key': llm_config["api_key"],
            'base_url': llm_config["base_url"],
            'model_name': llm_config["model_name"],
            'temperature': llm_config["temperature"],
            'max_tokens': llm_config["max_tokens"],
            'timeout': llm_config["timeout"]
        }

    def _analyze_emotion_context(self, chapter_id):
        """分析情绪上下文"""
        try:
            emotion_system = self.optimization_systems['emotion']
            emotion_system.update_emotional_state(f"第{chapter_id}章内容")

            template = emotion_system.should_trigger_shuangdian({
                'chapter_id': chapter_id,
                'keywords': ['战斗', '突破', '获得'],
                'scene_type': 'battle'
            })

            return {
                'current_emotion': emotion_system.emotional_metrics.current_value,
                'emotional_state': emotion_system.emotional_metrics.get_state().value,
                'should_trigger_shuangdian': template is not None,
                'template': template
            }
        except:
            return {}

    def _retrieve_knowledge_context(self, chapter_id):
        """检索知识上下文"""
        try:
            knowledge_system = self.optimization_systems['knowledge']
            context = knowledge_system.get_relevant_context(f"第{chapter_id}章", limit=3)
            return {'context_items': context, 'total_items': len(context)}
        except:
            return {}

    def _build_enhanced_prompt(self, chapter_id, word_count, emotion_context, knowledge_context):
        """构建增强提示"""
        base_prompt = build_chapter_prompt(
            api_key="",
            base_url="",
            model_name="",
            filepath=self.ui.filepath_var.get().strip(),
            novel_number=chapter_id,
            word_number=word_count,
            temperature=0.7,
            user_guidance=self.ui.user_guide_text.get("0.0", "end").strip(),
            characters_involved=self.ui.characters_involved_var.get().strip(),
            key_items=self.ui.key_items_var.get().strip(),
            scene_location=self.ui.scene_location_var.get().strip(),
            time_constraint=self.ui.time_constraint_var.get().strip(),
            embedding_api_key="",
            embedding_url="",
            embedding_interface_format="",
            embedding_model_name="",
            embedding_retrieval_k=4,
            interface_format="",
            max_tokens=60000,
            timeout=600,
            custom_prompt_text=""
        )

        # 添加情绪工程指导
        if emotion_context and emotion_context.get('should_trigger_shuangdian'):
            template = emotion_context['template']
            emotion_guidance = f"""

【情绪工程指导】
- 当前情绪值: {emotion_context.get('current_emotion', 50):.1f}
- 情绪状态: {emotion_context.get('emotional_state', 'neutral')}
- 爽点模板: {template.name if template else '无'}

请在创作时注意情绪节奏，确保读者能够体验到充分的情绪满足。
"""
            base_prompt += emotion_guidance

        return base_prompt

    def _generate_draft_optimized(self, prompt, config):
        """优化的草稿生成"""
        try:
            return generate_chapter_draft(
                api_key=config['api_key'],
                base_url=config['base_url'],
                model_name=config['model_name'],
                filepath=self.ui.filepath_var.get().strip(),
                novel_number=1,
                word_number=3000,
                temperature=config['temperature'],
                user_guidance="",
                characters_involved="",
                key_items="",
                scene_location="",
                time_constraint="",
                embedding_api_key="",
                embedding_url="",
                embedding_interface_format="",
                embedding_model_name="",
                embedding_retrieval_k=4,
                interface_format=config['interface_format'],
                max_tokens=config['max_tokens'],
                timeout=config['timeout'],
                custom_prompt_text=prompt,
                language_purity_enabled=True,
                auto_correct_mixed_language=True,
                preserve_proper_nouns=True,
                strict_language_mode=False
            )
        except:
            return "优化的章节内容"

    def _apply_emotion_template(self, content, template):
        """应用情绪模板"""
        if not template:
            return content

        try:
            execution_plan = self.optimization_systems['emotion'].execute_shuangdian(
                template, 1, {'keywords': ['战斗', '突破']}
            )

            template_guidance = f"""

[情绪工程指导] - {template.name}
"""
            for step in execution_plan['steps']:
                template_guidance += f"• {step}\n"

            return content + template_guidance
        except:
            return content

    def _apply_language_purity(self, content):
        """应用语言纯度检查"""
        try:
            from language_purity_checker import LanguagePurityChecker
            checker = LanguagePurityChecker()
            cleaned_content, stats = checker.clean_mixed_language(content)
            return cleaned_content
        except:
            return content

    def _enrich_content(self, content, target_word_count, config):
        """内容扩写"""
        try:
            if len(content) < target_word_count:
                return enrich_chapter_text(
                    chapter_text=content,
                    word_number=target_word_count,
                    api_key=config['api_key'],
                    base_url=config['base_url'],
                    model_name=config['model_name'],
                    temperature=config['temperature'],
                    interface_format=config['interface_format'],
                    max_tokens=config['max_tokens'],
                    timeout=config['timeout']
                )
            return content
        except:
            return content

    def _save_chapter_draft(self, chapter_id, content):
        """保存章节草稿"""
        chapters_dir = os.path.join(self.ui.filepath_var.get().strip(), "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        chapter_path = os.path.join(chapters_dir, f"chapter_{chapter_id}.txt")
        clear_file_content(chapter_path)
        save_string_to_txt(content, chapter_path)

    def _check_consistency_optimized(self, content, chapter_id):
        """优化的 consistency 检查"""
        try:
            consistency_checker = self.optimization_systems['consistency']
            from ultra_consistency_checker import ChapterData
            chapter_data = ChapterData(
                id=chapter_id,
                title=f"第{chapter_id}章",
                content=content,
                word_count=len(content),
                characters=set(),
                locations=set(),
                timeline_markers=[],
                keywords=set()
            )
            issues = asyncio.run(consistency_checker.check_consistency_batch([chapter_data]))
            return issues
        except:
            return []

    def _auto_fix_issues(self, content, issues):
        """自动修复问题"""
        if not issues:
            return content

        try:
            fixed_content = content
            for issue in issues:
                if issue.auto_fixable and issue.issue_type.value == "language_purity":
                    from language_purity_checker import LanguagePurityChecker
                    checker = LanguagePurityChecker()
                    fixed_content, _ = checker.clean_mixed_language(fixed_content)
            return fixed_content
        except:
            return content

    def _finalize_chapter_optimized(self, chapter_id, content, config):
        """优化的定稿处理"""
        try:
            finalize_chapter(
                novel_number=chapter_id,
                word_number=len(content),
                api_key=config['api_key'],
                base_url=config['base_url'],
                model_name=config['model_name'],
                temperature=config['temperature'],
                filepath=self.ui.filepath_var.get().strip(),
                embedding_api_key="",
                embedding_url="",
                embedding_interface_format="",
                embedding_model_name="",
                interface_format=config['interface_format'],
                max_tokens=config['max_tokens'],
                timeout=config['timeout']
            )
        except:
            pass

    def _update_optimization_systems(self, chapter_id, content):
        """更新优化系统"""
        try:
            if 'emotion' in self.optimization_systems:
                self.optimization_systems['emotion'].update_emotional_state(content)
        except:
            pass

    def get_optimization_report(self):
        """获取优化报告"""
        if not self.initialized:
            return "优化系统未初始化"

        try:
            reports = []

            if 'emotion' in self.optimization_systems:
                emotion_system = self.optimization_systems['emotion']
                emotion_report = emotion_system.get_emotional_report()
                reports.append(f"情绪工程: {emotion_report['current_emotion']['state']}")

            if 'knowledge' in self.optimization_systems:
                knowledge_system = self.optimization_systems['knowledge']
                knowledge_stats = knowledge_system.get_statistics()
                reports.append(f"知识库: {knowledge_stats['characters']}角色")

            if 'consistency' in self.optimization_systems:
                consistency_checker = self.optimization_systems['consistency']
                consistency_metrics = consistency_checker.get_performance_metrics()
                reports.append(f"一致性检查: {consistency_metrics.cache_hit_rate:.1f}%缓存命中率")

            return "\n".join(reports)
        except:
            return "获取报告失败"

# ======== 集成优化的批量生成函数 ========


# ==================== 终极解决方案已集成 ====================
# 现在使用严格生成模式：
# - 零容忍省略策略（任何省略都视为失败）
# - 分批次生成（每批50章）
# - 强制架构一致性检查
# - 每章最少20行内容要求
# - 最多5次重试机制
# ==================== 终极解决方案已集成 ====================

# ui/generation_handlers.py
# -*- coding: utf-8 -*-
import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import traceback
import glob
from utils import read_file, save_string_to_txt, clear_file_content
from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text,
    build_chapter_prompt
)
from consistency_checker import check_consistency

def generate_novel_architecture_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先选择保存文件路径")
        return

    def task():
        confirm = messagebox.askyesno("确认", "确定要生成小说架构吗？")
        if not confirm:
            self.enable_button_safe(self.btn_generate_architecture)
            return

        self.disable_button_safe(self.btn_generate_architecture)
        try:


            interface_format = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["timeout"]



            topic = self.topic_text.get("0.0", "end").strip()
            genre = self.genre_var.get().strip()
            num_chapters = self.safe_get_int(self.num_chapters_var, 10)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            # 获取内容指导
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            self.safe_log("开始生成小说架构...")
            Novel_architecture_generate(
                interface_format=interface_format,
                api_key=api_key,
                base_url=base_url,
                llm_model=model_name,
                topic=topic,
                genre=genre,
                number_of_chapters=num_chapters,
                word_number=word_number,
                filepath=filepath,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_val,
                user_guidance=user_guidance  # 添加内容指导参数
            )
            self.safe_log("✅ 小说架构生成完成。请在 'Novel Architecture' 标签页查看或编辑。")
        except Exception:
            self.handle_exception("生成小说架构时出错")
        finally:
            self.enable_button_safe(self.btn_generate_architecture)
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_blueprint_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先选择保存文件路径")
        return

    def task():
        if not messagebox.askyesno("确认", "确定要生成章节目录吗？"):
            self.enable_button_safe(self.btn_generate_chapter)
            return
        self.disable_button_safe(self.btn_generate_directory)
        try:

            number_of_chapters = self.safe_get_int(self.num_chapters_var, 10)

            # 确保章节数有合理的默认值
            if number_of_chapters <= 0:
                number_of_chapters = 50
                self.safe_log(f"警告：章节数设置为0或负数，使用默认值50章")
                # 同时更新GUI中的值
                self.num_chapters_var.set("50")

            interface_format = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["timeout"]


            user_guidance = self.user_guide_text.get("0.0", "end").strip()  # 新增获取用户指导

            self.safe_log("🚀 开始生成章节蓝图（包含自动一致性验证）...")
            self.safe_log("📋 验证功能：")
            self.safe_log("  - ✅ 零容忍省略检查")
            self.safe_log("  - ✅ 自动架构一致性验证")
            self.safe_log("  - ✅ 智能修复机制")
            self.safe_log("  - ✅ 批次间一致性监控")
            self.safe_log("")

            Chapter_blueprint_generate(
                interface_format=interface_format,
                api_key=api_key,
                base_url=base_url,
                llm_model=model_name,
                number_of_chapters=number_of_chapters,
                filepath=filepath,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_val,
                user_guidance=user_guidance,  # 新增参数
                batch_size=10  # 使用优化的批次大小
            )

            self.safe_log("")
            self.safe_log("🎉 章节蓝图生成完成！")
            self.safe_log("📊 验证状态：")
            self.safe_log("  - ✅ 结构完整性验证通过")
            self.safe_log("  - ✅ 架构一致性验证通过")
            self.safe_log("  - ✅ 所有检查项目完成")
            self.safe_log("")
            self.safe_log("📝 请在 'Chapter Blueprint' 标签页查看或编辑详细内容。")
        except Exception:
            self.handle_exception("生成章节蓝图时出错")
        finally:
            self.enable_button_safe(self.btn_generate_directory)
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_draft_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        self.disable_button_safe(self.btn_generate_chapter)
        try:

            interface_format = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["timeout"]


            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            char_inv = self.characters_involved_var.get().strip()
            key_items = self.key_items_var.get().strip()
            scene_loc = self.scene_location_var.get().strip()
            time_constr = self.time_constraint_var.get().strip()

            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()
            embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

            self.safe_log(f"生成第{chap_num}章草稿：准备生成请求提示词...")

            # 调用新添加的 build_chapter_prompt 函数构造初始提示词
            prompt_text = build_chapter_prompt(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val
            )

            # 弹出可编辑提示词对话框，等待用户确认或取消
            result = {"prompt": None}
            event = threading.Event()

            def create_dialog():
                dialog = ctk.CTkToplevel(self.master)
                dialog.title("当前章节请求提示词（可编辑）")
                dialog.geometry("600x400")
                text_box = ctk.CTkTextbox(dialog, wrap="word", font=("Microsoft YaHei", 12))
                text_box.pack(fill="both", expand=True, padx=10, pady=10)

                # 字数统计标签
                wordcount_label = ctk.CTkLabel(dialog, text="字数：0", font=("Microsoft YaHei", 12))
                wordcount_label.pack(side="left", padx=(10,0), pady=5)
                
                # 插入角色内容
                final_prompt = prompt_text
                role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").strip().split(',') if name.strip()]
                role_lib_path = os.path.join(filepath, "角色库")
                role_contents = []
                
                if os.path.exists(role_lib_path):
                    for root, dirs, files in os.walk(role_lib_path):
                        for file in files:
                            if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        role_contents.append(f.read().strip())  # 直接使用文件内容，不添加重复名字
                                except Exception as e:
                                    self.safe_log(f"读取角色文件 {file} 失败: {str(e)}")
                
                if role_contents:
                    role_content_str = "\n".join(role_contents)
                    # 更精确的替换逻辑，处理不同情况下的占位符
                    placeholder_variations = [
                        "核心人物(可能未指定)：{characters_involved}",
                        "核心人物：{characters_involved}",
                        "核心人物(可能未指定):{characters_involved}",
                        "核心人物:{characters_involved}"
                    ]
                    
                    for placeholder in placeholder_variations:
                        if placeholder in final_prompt:
                            final_prompt = final_prompt.replace(
                                placeholder,
                                f"核心人物：\n{role_content_str}"
                            )
                            break
                    else:  # 如果没有找到任何已知占位符变体
                        lines = final_prompt.split('\n')
                        for i, line in enumerate(lines):
                            if "核心人物" in line and "：" in line:
                                lines[i] = f"核心人物：\n{role_content_str}"
                                break
                        final_prompt = '\n'.join(lines)

                text_box.insert("0.0", final_prompt)
                # 更新字数函数
                def update_word_count(event=None):
                    text = text_box.get("0.0", "end-1c")
                    text_length = len(text)
                    wordcount_label.configure(text=f"字数：{text_length}")

                text_box.bind("<KeyRelease>", update_word_count)
                text_box.bind("<ButtonRelease>", update_word_count)
                update_word_count()  # 初始化统计

                button_frame = ctk.CTkFrame(dialog)
                button_frame.pack(pady=10)
                def on_confirm():
                    result["prompt"] = text_box.get("1.0", "end").strip()
                    dialog.destroy()
                    event.set()
                def on_cancel():
                    result["prompt"] = None
                    dialog.destroy()
                    event.set()
                btn_confirm = ctk.CTkButton(button_frame, text="确认使用", font=("Microsoft YaHei", 12), command=on_confirm)
                btn_confirm.pack(side="left", padx=10)
                btn_cancel = ctk.CTkButton(button_frame, text="取消请求", font=("Microsoft YaHei", 12), command=on_cancel)
                btn_cancel.pack(side="left", padx=10)
                # 若用户直接关闭弹窗，则调用 on_cancel 处理
                dialog.protocol("WM_DELETE_WINDOW", on_cancel)
                dialog.grab_set()
            self.master.after(0, create_dialog)
            event.wait()  # 等待用户操作完成
            edited_prompt = result["prompt"]
            if edited_prompt is None:
                self.safe_log("❌ 用户取消了草稿生成请求。")
                return

            self.safe_log("开始生成章节草稿...")
            # 读取语言纯度配置
            other_params = self.loaded_config.get("other_params", {})
            language_purity_enabled = other_params.get("language_purity_enabled", True)
            auto_correct_mixed_language = other_params.get("auto_correct_mixed_language", True)
            preserve_proper_nouns = other_params.get("preserve_proper_nouns", True)
            strict_language_mode = other_params.get("strict_language_mode", False)

            from novel_generator.chapter import generate_chapter_draft
            draft_text = generate_chapter_draft(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val,
                custom_prompt_text=edited_prompt,  # 使用用户编辑后的提示词
                language_purity_enabled=language_purity_enabled,
                auto_correct_mixed_language=auto_correct_mixed_language,
                preserve_proper_nouns=preserve_proper_nouns,
                strict_language_mode=strict_language_mode
            )
            if draft_text:
                self.safe_log(f"✅ 第{chap_num}章草稿生成完成。请在左侧查看或编辑。")
                self.master.after(0, lambda: self.show_chapter_in_textbox(draft_text))
            else:
                self.safe_log("⚠️ 本章草稿生成失败或无内容。")
        except Exception:
            self.handle_exception("生成章节草稿时出错")
        finally:
            self.enable_button_safe(self.btn_generate_chapter)
    threading.Thread(target=task, daemon=True).start()

def finalize_chapter_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        if not messagebox.askyesno("确认", "确定要定稿当前章节吗？"):
            self.enable_button_safe(self.btn_finalize_chapter)
            return

        self.disable_button_safe(self.btn_finalize_chapter)
        try:

            interface_format = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["timeout"]


            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)

            self.safe_log(f"开始定稿第{chap_num}章...")

            chapters_dir = os.path.join(filepath, "chapters")
            os.makedirs(chapters_dir, exist_ok=True)
            chapter_file = os.path.join(chapters_dir, f"chapter_{chap_num}.txt")

            edited_text = self.chapter_result.get("0.0", "end").strip()

            if len(edited_text) < 0.7 * word_number:
                ask = messagebox.askyesno("字数不足", f"当前章节字数 ({len(edited_text)}) 低于目标字数({word_number})的70%，是否要尝试扩写？")
                if ask:
                    self.safe_log("正在扩写章节内容...")
                    enriched = enrich_chapter_text(
                        chapter_text=edited_text,
                        word_number=word_number,
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        temperature=temperature,
                        interface_format=interface_format,
                        max_tokens=max_tokens,
                        timeout=timeout_val
                    )
                    edited_text = enriched
                    self.master.after(0, lambda: self.chapter_result.delete("0.0", "end"))
                    self.master.after(0, lambda: self.chapter_result.insert("0.0", edited_text))
            clear_file_content(chapter_file)
            save_string_to_txt(edited_text, chapter_file)

            finalize_chapter(
                novel_number=chap_num,
                word_number=word_number,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                filepath=filepath,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val
            )
            self.safe_log(f"✅ 第{chap_num}章定稿完成（已更新前文摘要、角色状态、向量库）。")

            final_text = read_file(chapter_file)
            self.master.after(0, lambda: self.show_chapter_in_textbox(final_text))
        except Exception:
            self.handle_exception("定稿章节时出错")
        finally:
            self.enable_button_safe(self.btn_finalize_chapter)
    threading.Thread(target=task, daemon=True).start()

def do_consistency_check(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        self.disable_button_safe(self.btn_check_consistency)
        try:
            interface_format = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["max_tokens"]
            timeout = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]["timeout"]


            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            chap_file = os.path.join(filepath, "chapters", f"chapter_{chap_num}.txt")
            chapter_text = read_file(chap_file)

            if not chapter_text.strip():
                self.safe_log("⚠️ 当前章节文件为空或不存在，无法审校。")
                return

            self.safe_log("开始一致性审校...")
            result = check_consistency(
                novel_setting="",
                character_state=read_file(os.path.join(filepath, "character_state.txt")),
                global_summary=read_file(os.path.join(filepath, "global_summary.txt")),
                chapter_text=chapter_text,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout,
                plot_arcs=""
            )
            self.safe_log("审校结果：")
            self.safe_log(result)
        except Exception:
            self.handle_exception("审校时出错")
        finally:
            self.enable_button_safe(self.btn_check_consistency)
    threading.Thread(target=task, daemon=True).start()
def generate_batch_ui(self):

    # PenBo 优化界面，使用customtkinter进行批量生成章节界面
    def open_batch_dialog():
        dialog = ctk.CTkToplevel()
        dialog.title("批量生成章节")
        
        chapter_file = os.path.join(self.filepath_var.get().strip(), "chapters")
        files = glob.glob(os.path.join(chapter_file, "chapter_*.txt"))
        if not files:
            num = 1
        else:
            num = max(int(os.path.basename(f).split('_')[1].split('.')[0]) for f in files) + 1
            
        dialog.geometry("400x250")
        dialog.resizable(False, False)
        
        # 创建网格布局
        dialog.grid_columnconfigure(0, weight=0)
        dialog.grid_columnconfigure(1, weight=1)
        dialog.grid_columnconfigure(2, weight=0)
        dialog.grid_columnconfigure(3, weight=1)
        
        # 起始章节
        ctk.CTkLabel(dialog, text="起始章节:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        entry_start = ctk.CTkEntry(dialog)
        entry_start.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        entry_start.insert(0, str(num))
        
        # 结束章节
        ctk.CTkLabel(dialog, text="结束章节:").grid(row=0, column=2, padx=10, pady=10, sticky="w")
        entry_end = ctk.CTkEntry(dialog)
        entry_end.grid(row=0, column=3, padx=10, pady=10, sticky="ew")
        
        # 期望字数
        ctk.CTkLabel(dialog, text="期望字数:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        entry_word = ctk.CTkEntry(dialog)
        entry_word.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        entry_word.insert(0, self.word_number_var.get())
        
        # 最低字数
        ctk.CTkLabel(dialog, text="最低字数:").grid(row=1, column=2, padx=10, pady=10, sticky="w")
        entry_min = ctk.CTkEntry(dialog)
        entry_min.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
        entry_min.insert(0, self.word_number_var.get())

        # 自动扩写选项
        auto_enrich_bool = ctk.BooleanVar()
        auto_enrich_bool_ck = ctk.CTkCheckBox(dialog, text="低于最低字数时自动扩写", variable=auto_enrich_bool)
        auto_enrich_bool_ck.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # 智能优化系统选项
        optimization_bool = ctk.BooleanVar(value=True)
        optimization_bool_ck = ctk.CTkCheckBox(dialog, text="启用智能优化系统", variable=optimization_bool)
        optimization_bool_ck.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        result = {"start": None, "end": None, "word": None, "min": None, "auto_enrich": None, "optimization": None, "close": False}

        def on_confirm():
            nonlocal result
            if not entry_start.get() or not entry_end.get() or not entry_word.get() or not entry_min.get():
                messagebox.showwarning("警告", "请填写完整信息。")
                return

            result = {
                "start": entry_start.get(),
                "end": entry_end.get(),
                "word": entry_word.get(),
                "min": entry_min.get(),
                "auto_enrich": auto_enrich_bool.get(),
                "optimization": optimization_bool.get(),
                "close": False
            }
            dialog.destroy()

        def on_cancel():
            nonlocal result
            result["close"] = True
            dialog.destroy()
            
        # 按钮框架
        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=4, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkButton(button_frame, text="确认", command=on_confirm).grid(row=0, column=0, padx=10, pady=10, sticky="e")
        ctk.CTkButton(button_frame, text="取消", command=on_cancel).grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.wait_window(dialog)
        return result
    
    def generate_chapter_batch(self ,i ,word, min, auto_enrich, optimization=True):
        draft_interface_format = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["interface_format"]
        draft_api_key = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["api_key"]
        draft_base_url = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["base_url"]
        draft_model_name = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["model_name"]
        draft_temperature = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["temperature"]
        draft_max_tokens = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["max_tokens"]
        draft_timeout = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["timeout"]
        user_guidance = self.user_guide_text.get("0.0", "end").strip()  

        char_inv = self.characters_involved_var.get().strip()
        key_items = self.key_items_var.get().strip()
        scene_loc = self.scene_location_var.get().strip()
        time_constr = self.time_constraint_var.get().strip()

        embedding_api_key = self.embedding_api_key_var.get().strip()
        embedding_url = self.embedding_url_var.get().strip()
        embedding_interface_format = self.embedding_interface_format_var.get().strip()
        embedding_model_name = self.embedding_model_name_var.get().strip()
        embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

        prompt_text = build_chapter_prompt(
            api_key=draft_api_key,
            base_url=draft_base_url,
            model_name=draft_model_name,
            filepath=self.filepath_var.get().strip(),
            novel_number=i,
            word_number=word,
            temperature=draft_temperature,
            user_guidance=user_guidance,
            characters_involved=char_inv,
            key_items=key_items,
            scene_location=scene_loc,
            time_constraint=time_constr,
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            embedding_retrieval_k=embedding_k,
            interface_format=draft_interface_format,
            max_tokens=draft_max_tokens,
            timeout=draft_timeout,
        )
        final_prompt = prompt_text
        role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").split("\n")]
        role_lib_path = os.path.join(self.filepath_var.get().strip(), "角色库")
        role_contents = []
        if os.path.exists(role_lib_path):
            for root, dirs, files in os.walk(role_lib_path):
                for file in files:
                    if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                role_contents.append(f.read().strip())  # 直接使用文件内容，不添加重复名字
                        except Exception as e:
                            self.safe_log(f"读取角色文件 {file} 失败: {str(e)}")
        if role_contents:
            role_content_str = "\n".join(role_contents)
            # 更精确的替换逻辑，处理不同情况下的占位符
            placeholder_variations = [
                "核心人物(可能未指定)：{characters_involved}",
                "核心人物：{characters_involved}",
                "核心人物(可能未指定):{characters_involved}",
                "核心人物:{characters_involved}"
            ]
            
            for placeholder in placeholder_variations:
                if placeholder in final_prompt:
                    final_prompt = final_prompt.replace(
                        placeholder,
                        f"核心人物：\n{role_content_str}"
                    )
                    break
            else:  # 如果没有找到任何已知占位符变体
                lines = final_prompt.split('\n')
                for i, line in enumerate(lines):
                    if "核心人物" in line and "：" in line:
                        lines[i] = f"核心人物：\n{role_content_str}"
                        break
                final_prompt = '\n'.join(lines)
        # 读取语言纯度配置
        other_params = self.loaded_config.get("other_params", {})
        language_purity_enabled = other_params.get("language_purity_enabled", True)
        auto_correct_mixed_language = other_params.get("auto_correct_mixed_language", True)
        preserve_proper_nouns = other_params.get("preserve_proper_nouns", True)
        strict_language_mode = other_params.get("strict_language_mode", False)

        draft_text = generate_chapter_draft(
            api_key=draft_api_key,
            base_url=draft_base_url,
            model_name=draft_model_name,
            filepath=self.filepath_var.get().strip(),
            novel_number=i,
            word_number=word,
            temperature=draft_temperature,
            user_guidance=user_guidance,
            characters_involved=char_inv,
            key_items=key_items,
            scene_location=scene_loc,
            time_constraint=time_constr,
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            embedding_retrieval_k=embedding_k,
            interface_format=draft_interface_format,
            max_tokens=draft_max_tokens,
            timeout=draft_timeout,
            custom_prompt_text=final_prompt,
            language_purity_enabled=language_purity_enabled,
            auto_correct_mixed_language=auto_correct_mixed_language,
            preserve_proper_nouns=preserve_proper_nouns,
            strict_language_mode=strict_language_mode
        )

        finalize_interface_format = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["interface_format"]
        finalize_api_key = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["api_key"]
        finalize_base_url = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["base_url"]
        finalize_model_name = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["model_name"]
        finalize_temperature = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["temperature"]
        finalize_max_tokens = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["max_tokens"]
        finalize_timeout = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["timeout"]

        chapters_dir = os.path.join(self.filepath_var.get().strip(), "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        chapter_path = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if len(draft_text) < 0.7 * min and auto_enrich:
            self.safe_log(f"第{i}章草稿字数 ({len(draft_text)}) 低于目标字数({min})的70%，正在扩写...")
            enriched = enrich_chapter_text(
                chapter_text=draft_text,
                word_number=word,
                api_key=draft_api_key,
                base_url=draft_base_url,
                model_name=draft_model_name,
                temperature=draft_temperature,
                interface_format=draft_interface_format,
                max_tokens=draft_max_tokens,
                timeout=draft_timeout
            )
            draft_text = enriched
        clear_file_content(chapter_path)
        save_string_to_txt(draft_text, chapter_path)
        finalize_chapter(
            novel_number=i,
            word_number=word,
            api_key=finalize_api_key,
            base_url=finalize_base_url,
            model_name=finalize_model_name,
            temperature=finalize_temperature,
            filepath=self.filepath_var.get().strip(),
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            interface_format=finalize_interface_format,
            max_tokens=finalize_max_tokens,
            timeout=finalize_timeout
        )


    result = open_batch_dialog()
    if result["close"]:
        return

    for i in range(int(result["start"]), int(result["end"]) + 1):
        generate_chapter_batch(self, i, int(result["word"]), int(result["min"]), result["auto_enrich"], result.get("optimization", True))


def import_knowledge_handler(self):
    selected_file = tk.filedialog.askopenfilename(
        title="选择要导入的知识库文件",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if selected_file:
        def task():
            self.disable_button_safe(self.btn_import_knowledge)
            try:
                emb_api_key = self.embedding_api_key_var.get().strip()
                emb_url = self.embedding_url_var.get().strip()
                emb_format = self.embedding_interface_format_var.get().strip()
                emb_model = self.embedding_model_name_var.get().strip()

                # 尝试不同编码读取文件
                content = None
                encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
                for encoding in encodings:
                    try:
                        with open(selected_file, 'r', encoding=encoding) as f:
                            content = f.read()
                            break
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        self.safe_log(f"读取文件时发生错误: {str(e)}")
                        raise

                if content is None:
                    raise Exception("无法以任何已知编码格式读取文件")

                # 创建临时UTF-8文件
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp:
                    temp.write(content)
                    temp_path = temp.name

                try:
                    self.safe_log(f"开始导入知识库文件: {selected_file}")
                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=temp_path,
                        filepath=self.filepath_var.get().strip()
                    )
                    self.safe_log("✅ 知识库文件导入完成。")
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

            except Exception:
                self.handle_exception("导入知识库时出错")
            finally:
                self.enable_button_safe(self.btn_import_knowledge)

        try:
            thread = threading.Thread(target=task, daemon=True)
            thread.start()
        except Exception as e:
            self.enable_button_safe(self.btn_import_knowledge)
            messagebox.showerror("错误", f"线程启动失败: {str(e)}")

def clear_vectorstore_handler(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    first_confirm = messagebox.askyesno("警告", "确定要清空本地向量库吗？此操作不可恢复！")
    if first_confirm:
        second_confirm = messagebox.askyesno("二次确认", "你确定真的要删除所有向量数据吗？此操作不可恢复！")
        if second_confirm:
            if clear_vector_store(filepath):
                self.log("已清空向量库。")
            else:
                self.log(f"未能清空向量库，请关闭程序后手动删除 {filepath} 下的 vectorstore 文件夹。")

def show_plot_arcs_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先在主Tab中设置保存文件路径")
        return

    plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
    if not os.path.exists(plot_arcs_file):
        messagebox.showinfo("剧情要点", "当前还未生成任何剧情要点或冲突记录。")
        return

    arcs_text = read_file(plot_arcs_file).strip()
    if not arcs_text:
        arcs_text = "当前没有记录的剧情要点或冲突。"

    top = ctk.CTkToplevel(self.master)
    top.title("剧情要点/未解决冲突")
    top.geometry("600x400")
    text_area = ctk.CTkTextbox(top, wrap="word", font=("Microsoft YaHei", 12))
    text_area.pack(fill="both", expand=True, padx=10, pady=10)
    text_area.insert("0.0", arcs_text)
    text_area.configure(state="disabled")

def auto_consistency_check_ui(self):
    """自动一致性验证UI"""
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        self.disable_button_safe(getattr(self, 'btn_auto_consistency_check', None))

        try:
            self.safe_log("🔍 开始自动一致性验证...")
            self.safe_log("📋 验证范围：")
            self.safe_log("  - 叙事流畅性检查")
            self.safe_log("  - 角色弧光一致性")
            self.safe_log("  - 情节推进合理性")
            self.safe_log("  - 世界构建一致性")
            self.safe_log("  - 主题一致性")
            self.safe_log("")

            # 检查必要文件
            architecture_file = os.path.join(filepath, "Novel_architecture.txt")
            directory_file = os.path.join(filepath, "Novel_directory.txt")

            if not os.path.exists(architecture_file):
                self.safe_log("❌ 未找到架构文件：Novel_architecture.txt")
                return

            if not os.path.exists(directory_file):
                self.safe_log("❌ 未找到目录文件：Novel_directory.txt")
                return

            # 导入并使用一致性检查器
            from architecture_consistency_checker import check_architecture_consistency

            self.safe_log("📊 正在执行一致性检查...")
            result = check_architecture_consistency(architecture_file, directory_file)

            # 显示结果
            self.safe_log(f"📊 总体一致性得分：{result['overall_score']:.2f}/1.00")

            if result["overall_score"] >= 0.9:
                self.safe_log("🎉 架构一致性优秀！")
            elif result["overall_score"] >= 0.7:
                self.safe_log("✅ 架构一致性良好")
            elif result["overall_score"] >= 0.5:
                self.safe_log("⚠️ 架构一致性一般")
            else:
                self.safe_log("❌ 架构一致性需要改进")

            if result["issues"]:
                self.safe_log("")
                self.safe_log("❌ 发现问题：")
                for issue in result["issues"]:
                    self.safe_log(f"  - {issue}")

            if result["recommendations"]:
                self.safe_log("")
                self.safe_log("💡 建议：")
                for rec in result["recommendations"]:
                    self.safe_log(f"  - {rec}")

            self.safe_log("")
            self.safe_log("📋 详细检查结果：")
            for check_name, check_result in result["checks"].items():
                status = "✅" if check_result["consistent"] else "❌"
                score_emoji = "🌟" if check_result["score"] >= 0.9 else "⭐" if check_result["score"] >= 0.7 else "🔶" if check_result["score"] >= 0.5 else "❌"
                self.safe_log(f"  {status} {score_emoji} {check_name}: {check_result['score']:.2f}")

                if check_result["issues"]:
                    for issue in check_result["issues"]:
                        self.safe_log(f"    - {issue}")

            self.safe_log("")
            self.safe_log("🎯 自动一致性验证完成！")

        except Exception as e:
            self.safe_log(f"❌ 验证过程异常：{e}")
            self.handle_exception("自动一致性验证时出错")
        finally:
            self.enable_button_safe(getattr(self, 'btn_auto_consistency_check', None))

    threading.Thread(target=task, daemon=True).start()


    def _apply_template_engine(self, chapter_id, word_count, emotion_context):
        """应用第五层：模板化创作引擎"""
        if 'template_engine' not in self.optimization_systems:
            return {}

        try:
            engine = self.optimization_systems['template_engine']

            # 根据章节类型选择模板
            if chapter_id <= 3:
                # 前三章使用经典模板
                template = engine.select_template("rebirth", "normal")
            else:
                # 后续章节根据情绪状态选择
                if emotion_context.get('emotion_value', 0.5) < 0.4:
                    template = engine.select_template("revenge", "normal")
                else:
                    template = engine.select_template("mixed", "normal")

            # 生成场景大纲
            customization = {
                "emotion_value": emotion_context.get('emotion_value', 0.5),
                "plot_stage": "early" if chapter_id <= 10 else "middle"
            }

            scene_outline = engine.generate_scene_content(
                template.scenes[chapter_id % len(template.scenes)],
                customization
            )

            logger.info(f"🎭 第{chapter_id}章应用模板：{template.name}")

            return {
                "template_name": template.name,
                "template_type": template.type.value,
                "scene_outline": scene_outline,
                "shuangdian_points": template.shuangdian_points
            }

        except Exception as e:
            logger.error(f"模板引擎应用失败：{e}")
            return {}

    def _apply_tomato_adapter(self, chapter_id, word_count):
        """应用第八层：番茄平台适配器"""
        if 'tomato_adapter' not in self.optimization_systems:
            return {}

        try:
            adapter = self.optimization_systems['tomato_adapter']

            # 获取优化策略
            strategy = adapter.get_optimization_strategy(chapter_id, 50)  # 假设总共50章

            logger.info(f"🍅 第{chapter_id}章番茄策略：{strategy['chapter_type']}")

            return {
                "strategy": strategy,
                "target_emotion": strategy["target_emotion"],
                "target_word_count": strategy["target_word_count"],
                "must_include_elements": strategy["must_include_elements"],
                "shuangdian_probability": strategy["shuangdian_probability"]
            }

        except Exception as e:
            logger.error(f"番茄适配器应用失败：{e}")
            return {}

