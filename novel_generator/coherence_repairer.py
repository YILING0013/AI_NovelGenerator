#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
章节衔接问题修复器
修复 location_jump, unresolved_conflict, character_inconsistency 等衔接问题
v3.1: 增加修复效果回扫验证 (Fix 1.2)
"""

import logging
import time
import re
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

from llm_adapters import create_llm_adapter

logger = logging.getLogger(__name__)


class CoherenceRepairer:
    """章节衔接修复器"""
    
    def __init__(self, filepath: str, llm_config: Dict[str, Any]):
        self.filepath = filepath
        self.llm_config = llm_config
        self.llm_adapter = create_llm_adapter(
            interface_format=llm_config.get('interface_format', 'openai'),
            api_key=llm_config.get('api_key', ''),
            base_url=llm_config.get('base_url', ''),
            model_name=llm_config.get('model_name', ''),
            temperature=llm_config.get('temperature', 0.7),
            max_tokens=llm_config.get('max_tokens', 4000),
            timeout=llm_config.get('timeout', 60)
        )
        self.directory_path = Path(filepath) / "Novel_directory.txt"
    
    def repair_coherence_issues(self, issues: List[Dict], 
                                 progress_callback: Callable = None) -> Dict[str, Any]:
        """
        修复衔接问题
        
        Args:
            issues: 衔接问题列表，每项包含 issue_type, chapter_pair, description
            progress_callback: 进度回调 (current, total, message)
        
        Returns:
            修复结果报告
        """
        if not issues:
            return {'success': 0, 'failed': 0, 'repaired_pairs': []}
        
        # 加载章节内容
        chapters = self._load_chapters()
        if not chapters:
            logger.error("无法加载章节内容")
            return {'success': 0, 'failed': 0, 'error': '无法加载章节'}
        
        # 按章节对分组问题
        pair_issues = {}
        for issue in issues:
            pair = issue.get('chapter_pair', (0, 0))
            if pair not in pair_issues:
                pair_issues[pair] = []
            pair_issues[pair].append(issue)
        
        total = len(pair_issues)
        results = {
            'total': total,
            'success': 0,
            'failed': 0,
            'repaired_pairs': []
        }
        
        for idx, (pair, pair_issue_list) in enumerate(pair_issues.items()):
            prev_ch, curr_ch = pair
            
            if progress_callback:
                progress_callback(idx + 1, total, f"修复章节 {prev_ch}-{curr_ch} 的衔接问题...")
            
            # 获取章节内容
            prev_content = chapters.get(prev_ch, '')
            curr_content = chapters.get(curr_ch, '')
            
            if not prev_content or not curr_content:
                logger.warning(f"找不到章节 {prev_ch} 或 {curr_ch} 的内容")
                results['failed'] += 1
                continue
            
            # 生成修复
            repaired_curr = self._repair_pair(
                prev_ch, prev_content,
                curr_ch, curr_content,
                pair_issue_list
            )
            
            if repaired_curr and repaired_curr != curr_content:
                # 🆕 Fix 1.2: 修复效果回扫验证
                verification_passed = True
                try:
                    from novel_generator.coherence_checker import CoherenceChecker
                    checker = CoherenceChecker(self.filepath)
                    # 构建 ChapterState 用于验证
                    prev_state = checker.extract_chapter_state(prev_content, prev_ch)
                    curr_state = checker.extract_chapter_state(repaired_curr, curr_ch)
                    remaining_issues = checker.check_adjacent_coherence(prev_state, curr_state)
                    if remaining_issues:
                        logger.warning(
                            f"🔄 章节 {prev_ch}-{curr_ch} 修复后回扫发现 "
                            f"{len(remaining_issues)} 个残留问题, 重试一次..."
                        )
                        # 重试修复（带残留问题描述）
                        retry_issues = pair_issue_list + [
                            {'issue_type': ri.issue_type,
                             'description': f"[残留] {ri.description}",
                             'chapter_pair': (prev_ch, curr_ch)}
                            for ri in remaining_issues
                        ]
                        retry_content = self._repair_pair(
                            prev_ch, prev_content, curr_ch, repaired_curr, retry_issues
                        )
                        if retry_content and retry_content != repaired_curr:
                            repaired_curr = retry_content
                            logger.info(f"✅ 章节 {prev_ch}-{curr_ch} 二次修复完成")
                        else:
                            logger.warning(f"⚠️ 章节 {prev_ch}-{curr_ch} 二次修复未能改善, 保留首次修复结果")
                    else:
                        logger.info(f"✅ 章节 {prev_ch}-{curr_ch} 回扫验证通过, 无残留问题")
                except ImportError:
                    logger.debug("CoherenceChecker 不可用, 跳过回扫验证")
                except Exception as e:
                    logger.warning(f"回扫验证出错 (不影响修复结果): {e}")
                
                # 更新章节
                chapters[curr_ch] = repaired_curr
                results['success'] += 1
                results['repaired_pairs'].append({
                    'pair': (prev_ch, curr_ch),
                    'issues_fixed': len(pair_issue_list)
                })
                
                if progress_callback:
                    progress_callback(idx + 1, total, f"✅ 章节 {prev_ch}-{curr_ch} 衔接已修复")
            else:
                results['failed'] += 1
                if progress_callback:
                    progress_callback(idx + 1, total, f"❌ 章节 {prev_ch}-{curr_ch} 修复失败")
            
            time.sleep(1)  # 避免API限速
        
        # 保存修复后的章节
        if results['success'] > 0:
            self._save_chapters(chapters)
            logger.info(f"已保存 {results['success']} 对章节的衔接修复")
        
        return results
    
    def _repair_pair(self, prev_ch: int, prev_content: str,
                     curr_ch: int, curr_content: str,
                     issues: List[Dict]) -> Optional[str]:
        """修复一对章节的衔接问题"""
        
        # 分析问题类型
        issue_descriptions = []
        for issue in issues:
            issue_type = issue.get('issue_type', 'unknown')
            desc = issue.get('description', '')
            
            if issue_type == 'location_jump':
                issue_descriptions.append(f"【地点跳跃】{desc}（需添加过渡描写）")
            elif issue_type == 'unresolved_conflict':
                issue_descriptions.append(f"【冲突断裂】{desc}（需延续或收束冲突）")
            elif issue_type == 'character_inconsistency':
                issue_descriptions.append(f"【角色不一致】{desc}（需统一角色状态）")
            else:
                issue_descriptions.append(f"【{issue_type}】{desc}")
        
        issues_text = "\n".join([f"  - {d}" for d in issue_descriptions])
        
        # 提取章节末尾和开头的关键内容
        prev_ending = prev_content[-1500:] if len(prev_content) > 1500 else prev_content
        curr_opening = curr_content[:2000] if len(curr_content) > 2000 else curr_content
        
        prompt = f"""你是一位专业的小说编辑。请修复以下两章之间的衔接问题。

## 衔接问题

{issues_text}

## 第{prev_ch}章结尾

{prev_ending}

## 第{curr_ch}章开头（需要修复）

{curr_opening}

## 修复要求

1. **仅修改第{curr_ch}章的开头部分**，添加必要的过渡内容
2. 针对每个问题：
   - 地点跳跃：在开头添加1-2句过渡描写（如"翌日清晨..."、"一路疾行，数日后..."）
   - 冲突断裂：在开头1-2句中提及上章的冲突状态
   - 角色不一致：统一角色的状态/位置/情绪描述
3. **保持原有内容不变**，只在开头添加或修改过渡句
4. 过渡要自然，不要生硬

## 输出要求

直接输出修复后的完整第{curr_ch}章内容（保留所有原内容，只修改/添加开头过渡）。
不要输出任何解释。

请开始："""

        try:
            result = self.llm_adapter.invoke(prompt)
            # 清理输出
            result = result.strip()
            if result.startswith('```'):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)
            return result
        except Exception as e:
            logger.error(f"修复章节 {prev_ch}-{curr_ch} 衔接时出错: {e}")
            return None
    
    def _load_chapters(self) -> Dict[int, str]:
        """加载所有章节内容"""
        chapters = {}
        
        if not self.directory_path.exists():
            return chapters
        
        try:
            with open(self.directory_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析章节
            pattern = r'^(第\d+章\s*[-—]?\s*.*?)(?=^第\d+章|\Z)'
            matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
            
            for section in matches:
                section = section.strip()
                if not section:
                    continue
                match = re.search(r'第(\d+)章', section)
                if match:
                    chapter_number = int(match.group(1))
                    chapters[chapter_number] = section
            
            logger.info(f"加载了 {len(chapters)} 个章节")
        except Exception as e:
            logger.error(f"加载章节失败: {e}")
        
        return chapters
    
    def _save_chapters(self, chapters: Dict[int, str]) -> bool:
        """保存章节内容"""
        try:
            # 按章节号排序
            sorted_chapters = sorted(chapters.items(), key=lambda x: x[0])
            final_content = "\n\n".join([ch[1] for ch in sorted_chapters])
            
            with open(self.directory_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            logger.info(f"保存了 {len(chapters)} 个章节")
            return True
        except Exception as e:
            logger.error(f"保存章节失败: {e}")
            return False


def repair_coherence_issues(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    coherence_report: Dict[str, Any],
    progress_callback: Callable[[int, int, str], None] = None
) -> Dict[str, Any]:
    """
    修复衔接问题的便捷函数
    
    Args:
        coherence_report: 衔接检查报告，包含 issues 列表
    """
    llm_config = {
        'interface_format': interface_format,
        'api_key': api_key,
        'base_url': base_url,
        'model_name': llm_model,
        'temperature': 0.7,
        'max_tokens': 8000,
        'timeout': 120
    }
    
    repairer = CoherenceRepairer(filepath, llm_config)
    
    # 从报告中提取问题
    issues = coherence_report.get('issues', [])
    
    # 转换格式
    issue_list = []
    for issue in issues:
        if hasattr(issue, 'issue_type'):
            # CoherenceIssue 对象
            issue_list.append({
                'issue_type': issue.issue_type,
                'description': issue.description,
                'chapter_pair': issue.chapter_pair
            })
        elif isinstance(issue, dict):
            issue_list.append(issue)
    
    return repairer.repair_coherence_issues(issue_list, progress_callback)
