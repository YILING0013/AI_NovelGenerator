# enhanced_knowledge_retrieval.py
# -*- coding: utf-8 -*-
"""
增强型知识库检索系统
实现结构化信息提取、智能检索和重排序

功能:
1. 结构化信息提取(人物、事件、地点、时间)
2. 智能检索与重排序
3. 上下文感知的知识召回
4. 伏笔和悬念追踪

版本: 1.0
创建时间: 2025-12-07
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CharacterInfo:
    """角色信息"""
    name: str
    current_state: str = ""
    location: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)
    abilities: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    last_action: str = ""


@dataclass
class PlotEvent:
    """情节事件"""
    chapter_number: int
    event_description: str
    characters_involved: List[str]
    location: str = ""
    timestamp: str = ""
    consequences: List[str] = field(default_factory=list)
    importance: str = "normal"  # critical, major, normal, minor


@dataclass
class Foreshadowing:
    """伏笔信息"""
    chapter_set: int           # 设置伏笔的章节
    description: str           # 伏笔描述
    hint_type: str            # 类型:plot, character, item, mystery
    resolved: bool = False     # 是否已回收
    chapter_resolved: int = 0  # 回收伏笔的章节
    resolution: str = ""       # 回收方式


@dataclass
class ChapterKnowledge:
    """章节知识"""
    chapter_number: int
    characters: List[CharacterInfo]
    events: List[PlotEvent]
    locations: List[str]
    time_period: str
    foreshadowing_set: List[Foreshadowing]
    foreshadowing_resolved: List[str]
    key_items: List[str]
    mood: str  # 氛围: tense, peaceful, mysterious, etc.


@dataclass
class RetrievalResult:
    """检索结果"""
    content: str
    source: str
    relevance_score: float
    chapter_number: int = 0
    category: str = ""  # character, event, setting, foreshadowing


class StructuredKnowledgeExtractor:
    """结构化知识提取器"""
    
    def __init__(self, llm_adapter=None):
        """
        初始化知识提取器
        
        Args:
            llm_adapter: LLM适配器
        """
        self.llm_adapter = llm_adapter
        logger.info("结构化知识提取器初始化完成")
    
    def set_llm_adapter(self, llm_adapter):
        """设置LLM适配器"""
        self.llm_adapter = llm_adapter
    
    def extract_from_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
        existing_characters: Optional[List[str]] = None
    ) -> ChapterKnowledge:
        """
        从章节中提取结构化知识
        
        Args:
            chapter_content: 章节内容
            chapter_number: 章节编号
            existing_characters: 已知角色列表
            
        Returns:
            ChapterKnowledge: 提取的知识结构
        """
        if not self.llm_adapter:
            logger.warning("LLM适配器未设置,返回空知识结构")
            return self._create_empty_knowledge(chapter_number)
        
        prompt = self._build_extraction_prompt(
            chapter_content, 
            chapter_number,
            existing_characters
        )
        
        try:
            response = self.llm_adapter.invoke(prompt)
            return self._parse_extraction_response(response, chapter_number)
        except Exception as e:
            logger.error(f"知识提取失败: {e}")
            return self._create_empty_knowledge(chapter_number)
    
    def _build_extraction_prompt(
        self,
        content: str,
        chapter_number: int,
        existing_characters: Optional[List[str]]
    ) -> str:
        """构建提取提示词"""
        
        # 限制内容长度
        max_length = 6000
        if len(content) > max_length:
            content = content[:max_length] + "\n[内容已截断]"
        
        existing_chars = ", ".join(existing_characters) if existing_characters else "无已知角色"
        
        prompt = f"""从以下小说章节中提取关键信息。

【章节编号】第{chapter_number}章

【已知角色】{existing_chars}

【章节内容】
{content}

【提取要求】
请提取以下信息:

1. 角色信息:
   - 出场角色及其当前状态
   - 角色位置
   - 角色关系变化
   - 角色目标或动机

2. 情节事件:
   - 发生的关键事件
   - 事件的重要程度(critical/major/normal/minor)
   - 事件涉及的角色
   - 事件后果

3. 场景信息:
   - 出现的地点/场景
   - 时间节点

4. 伏笔悬念:
   - 新设置的伏笔
   - 回收的伏笔
   - 悬念或谜题

5. 重要物品:
   - 出现的关键道具/物品

6. 整体氛围:
   - 本章的情感氛围

【输出格式】
返回JSON:
```json
{{
  "characters": [
    {{
      "name": "角色名",
      "current_state": "当前状态描述",
      "location": "所在位置",
      "relationships": {{"角色B": "关系描述"}},
      "abilities": ["能力1"],
      "goals": ["目标1"],
      "last_action": "最后行动"
    }}
  ],
  "events": [
    {{
      "event_description": "事件描述",
      "characters_involved": ["角色1", "角色2"],
      "location": "地点",
      "timestamp": "时间",
      "consequences": ["后果1"],
      "importance": "major"
    }}
  ],
  "locations": ["地点1", "地点2"],
  "time_period": "时间段描述",
  "foreshadowing_set": [
    {{
      "description": "伏笔描述",
      "hint_type": "plot"
    }}
  ],
  "foreshadowing_resolved": ["回收的伏笔描述"],
  "key_items": ["物品1"],
  "mood": "氛围描述"
}}
```"""
        
        return prompt
    
    def _parse_extraction_response(
        self,
        response: str,
        chapter_number: int
    ) -> ChapterKnowledge:
        """解析提取响应"""
        
        try:
            # 提取JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()
            
            data = json.loads(json_str)
            
            # 解析角色
            characters = []
            for char_data in data.get('characters', []):
                char = CharacterInfo(
                    name=char_data.get('name', '未知'),
                    current_state=char_data.get('current_state', ''),
                    location=char_data.get('location', ''),
                    relationships=char_data.get('relationships', {}),
                    abilities=char_data.get('abilities', []),
                    goals=char_data.get('goals', []),
                    last_action=char_data.get('last_action', '')
                )
                characters.append(char)
            
            # 解析事件
            events = []
            for event_data in data.get('events', []):
                event = PlotEvent(
                    chapter_number=chapter_number,
                    event_description=event_data.get('event_description', ''),
                    characters_involved=event_data.get('characters_involved', []),
                    location=event_data.get('location', ''),
                    timestamp=event_data.get('timestamp', ''),
                    consequences=event_data.get('consequences', []),
                    importance=event_data.get('importance', 'normal')
                )
                events.append(event)
            
            # 解析伏笔
            foreshadowing = []
            for fs_data in data.get('foreshadowing_set', []):
                fs = Foreshadowing(
                    chapter_set=chapter_number,
                    description=fs_data.get('description', ''),
                    hint_type=fs_data.get('hint_type', 'plot')
                )
                foreshadowing.append(fs)
            
            return ChapterKnowledge(
                chapter_number=chapter_number,
                characters=characters,
                events=events,
                locations=data.get('locations', []),
                time_period=data.get('time_period', ''),
                foreshadowing_set=foreshadowing,
                foreshadowing_resolved=data.get('foreshadowing_resolved', []),
                key_items=data.get('key_items', []),
                mood=data.get('mood', '')
            )
            
        except Exception as e:
            logger.error(f"解析知识提取响应失败: {e}")
            return self._create_empty_knowledge(chapter_number)
    
    def _create_empty_knowledge(self, chapter_number: int) -> ChapterKnowledge:
        """创建空知识结构"""
        return ChapterKnowledge(
            chapter_number=chapter_number,
            characters=[],
            events=[],
            locations=[],
            time_period="",
            foreshadowing_set=[],
            foreshadowing_resolved=[],
            key_items=[],
            mood=""
        )


class EnhancedRetrieval:
    """增强型检索系统"""
    
    def __init__(self, llm_adapter=None, vector_store=None):
        """
        初始化增强检索系统
        
        Args:
            llm_adapter: LLM适配器(用于重排序)
            vector_store: 向量存储实例
        """
        self.llm_adapter = llm_adapter
        self.vector_store = vector_store
        self.knowledge_cache: Dict[int, ChapterKnowledge] = {}
        logger.info("增强型检索系统初始化完成")
    
    def set_llm_adapter(self, llm_adapter):
        """设置LLM适配器"""
        self.llm_adapter = llm_adapter
    
    def set_vector_store(self, vector_store):
        """设置向量存储"""
        self.vector_store = vector_store
    
    def add_chapter_knowledge(self, knowledge: ChapterKnowledge):
        """
        添加章节知识到缓存
        
        Args:
            knowledge: 章节知识结构
        """
        self.knowledge_cache[knowledge.chapter_number] = knowledge
        logger.info(f"添加第{knowledge.chapter_number}章知识到缓存")
    
    def retrieve_relevant_context(
        self,
        query: str,
        current_chapter: int,
        k: int = 5,
        categories: Optional[List[str]] = None
    ) -> List[RetrievalResult]:
        """
        检索相关上下文
        
        Args:
            query: 查询内容
            current_chapter: 当前章节编号
            k: 返回结果数量
            categories: 限定检索类别
            
        Returns:
            List[RetrievalResult]: 检索结果列表
        """
        results = []
        
        # 1. 从知识缓存中检索
        cache_results = self._search_knowledge_cache(
            query, current_chapter, categories
        )
        results.extend(cache_results)
        
        # 2. 从向量库检索
        if self.vector_store:
            vector_results = self._search_vector_store(query, k * 2)
            results.extend(vector_results)
        
        # 3. 如果有LLM,进行重排序
        if self.llm_adapter and len(results) > k:
            results = self._rerank_results(query, results, k)
        else:
            # 简单排序
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            results = results[:k]
        
        return results
    
    def _search_knowledge_cache(
        self,
        query: str,
        current_chapter: int,
        categories: Optional[List[str]]
    ) -> List[RetrievalResult]:
        """从知识缓存搜索"""
        results = []
        query_lower = query.lower()
        
        # 搜索最近N章的知识
        search_range = range(max(1, current_chapter - 10), current_chapter)
        
        for chap_num in search_range:
            if chap_num not in self.knowledge_cache:
                continue
            
            knowledge = self.knowledge_cache[chap_num]
            
            # 搜索角色信息
            if not categories or 'character' in categories:
                for char in knowledge.characters:
                    if query_lower in char.name.lower() or \
                       query_lower in char.current_state.lower():
                        results.append(RetrievalResult(
                            content=f"角色:{char.name}, 状态:{char.current_state}, 位置:{char.location}",
                            source=f"第{chap_num}章-角色信息",
                            relevance_score=0.8,
                            chapter_number=chap_num,
                            category='character'
                        ))
            
            # 搜索事件
            if not categories or 'event' in categories:
                for event in knowledge.events:
                    if query_lower in event.event_description.lower():
                        results.append(RetrievalResult(
                            content=event.event_description,
                            source=f"第{chap_num}章-事件",
                            relevance_score=0.7 if event.importance == 'major' else 0.5,
                            chapter_number=chap_num,
                            category='event'
                        ))
            
            # 搜索伏笔
            if not categories or 'foreshadowing' in categories:
                for fs in knowledge.foreshadowing_set:
                    if not fs.resolved and query_lower in fs.description.lower():
                        results.append(RetrievalResult(
                            content=f"伏笔:{fs.description}",
                            source=f"第{chap_num}章-伏笔",
                            relevance_score=0.9,  # 伏笔优先级高
                            chapter_number=chap_num,
                            category='foreshadowing'
                        ))
        
        return results
    
    def _search_vector_store(self, query: str, k: int) -> List[RetrievalResult]:
        """从向量库搜索"""
        results = []
        
        try:
            if hasattr(self.vector_store, 'similarity_search'):
                docs = self.vector_store.similarity_search(query, k=k)
                for doc in docs:
                    results.append(RetrievalResult(
                        content=doc.page_content,
                        source="向量库",
                        relevance_score=0.6,
                        category='general'
                    ))
        except Exception as e:
            logger.warning(f"向量库搜索失败: {e}")
        
        return results
    
    def _rerank_results(
        self,
        query: str,
        results: List[RetrievalResult],
        k: int
    ) -> List[RetrievalResult]:
        """使用LLM重排序结果"""
        
        if not results:
            return []
        
        # 格式化候选结果
        candidates_text = ""
        for i, result in enumerate(results[:20], 1):  # 最多处理20个
            candidates_text += f"{i}. [{result.category}] {result.content[:200]}...\n"
        
        prompt = f"""请根据查询相关性对以下检索结果进行排序。

【查询】
{query}

【候选结果】
{candidates_text}

【要求】
返回按相关性从高到低排序的结果编号列表(只返回最相关的{k}个)。
格式: [1, 5, 3, 8, 2]

只输出编号列表,不要其他内容。"""
        
        try:
            response = self.llm_adapter.invoke(prompt)
            
            # 解析排序结果
            numbers = re.findall(r'\d+', response)
            ranked_indices = [int(n) - 1 for n in numbers if 0 <= int(n) - 1 < len(results)]
            
            # 根据排序返回结果
            ranked_results = []
            for idx in ranked_indices[:k]:
                result = results[idx]
                result.relevance_score = 1.0 - (len(ranked_results) * 0.1)  # 更新分数
                ranked_results.append(result)
            
            return ranked_results
            
        except Exception as e:
            logger.warning(f"重排序失败: {e}, 使用原始排序")
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            return results[:k]
    
    def get_character_context(
        self,
        character_name: str,
        current_chapter: int
    ) -> str:
        """
        获取角色相关上下文
        
        Args:
            character_name: 角色名称
            current_chapter: 当前章节
            
        Returns:
            角色上下文描述
        """
        context_parts = []
        
        for chap_num in range(max(1, current_chapter - 5), current_chapter):
            if chap_num not in self.knowledge_cache:
                continue
            
            knowledge = self.knowledge_cache[chap_num]
            for char in knowledge.characters:
                if character_name.lower() in char.name.lower():
                    context_parts.append(
                        f"第{chap_num}章: {char.current_state}, 位置:{char.location}"
                    )
        
        return "\n".join(context_parts) if context_parts else "无相关记录"
    
    def get_unresolved_foreshadowing(self, current_chapter: int) -> List[Foreshadowing]:
        """
        获取未回收的伏笔
        
        Args:
            current_chapter: 当前章节
            
        Returns:
            未回收伏笔列表
        """
        unresolved = []
        
        for chap_num, knowledge in self.knowledge_cache.items():
            if chap_num >= current_chapter:
                continue
            for fs in knowledge.foreshadowing_set:
                if not fs.resolved:
                    unresolved.append(fs)
        
        return unresolved
    
    def format_context_for_generation(
        self,
        results: List[RetrievalResult],
        max_length: int = 2000
    ) -> str:
        """
        格式化检索结果用于生成
        
        Args:
            results: 检索结果列表
            max_length: 最大长度
            
        Returns:
            格式化的上下文文本
        """
        context_parts = []
        current_length = 0
        
        for result in results:
            entry = f"[{result.category}] {result.content}"
            if current_length + len(entry) > max_length:
                break
            context_parts.append(entry)
            current_length += len(entry)
        
        return "\n".join(context_parts)


def create_knowledge_extractor(llm_adapter=None) -> StructuredKnowledgeExtractor:
    """创建知识提取器实例"""
    return StructuredKnowledgeExtractor(llm_adapter)


def create_enhanced_retrieval(llm_adapter=None, vector_store=None) -> EnhancedRetrieval:
    """创建增强检索系统实例"""
    return EnhancedRetrieval(llm_adapter, vector_store)


if __name__ == "__main__":
    # 测试代码
    extractor = create_knowledge_extractor()
    retrieval = create_enhanced_retrieval()
    print("增强型知识检索系统测试完成")
