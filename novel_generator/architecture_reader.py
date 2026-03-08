import re
import logging
from typing import Dict, List, Optional

class ArchitectureReader:
    """
    动态架构文件阅读器
    用于从 Novel_architecture.txt 中动态提取特定章节或指导原则，
    避免将特定小说的设定（如程序员思维、暧昧技法）硬编码到程序中。
    """
    
    def __init__(self, content: str):
        self.content = content
        self.sections = self._parse_sections(content)
        
    def _parse_sections(self, content: str) -> Dict[str, str]:
        """
        粗粒度解析Markdown章节
        返回 {标题: 内容} 的字典
        """
        sections = {}
        # 匹配 #, ##, ### 等标题
        # 格式： ^#+ 标题文本
        # 为了简化，我们按行处理
        lines = content.split('\n')
        current_title = "preamble"
        current_content = []
        
        for line in lines:
            line_strip = line.strip()
            # 检测标题行，例如 "#=== 1) 核心种子 ===" 或 "## 程序员思维"
            if line_strip.startswith('#'):
                # 保存前一个章节
                if current_content:
                    sections[current_title] = '\n'.join(current_content).strip()
                
                # 开始新章节
                # 清理标题中的 # 和 === 等装饰符
                clean_title = re.sub(r'^[#=]+\s*', '', line_strip) # 去除开头的 # 和 =
                clean_title = re.sub(r'\s*[=]+$', '', clean_title) # 去除结尾的 =
                clean_title = re.sub(r'^\d+\)\s*', '', clean_title) # 去除序号如 "1) "
                
                current_title = clean_title.strip()
                current_content = []  # 不包含标题行本身
            else:
                current_content.append(line)
        
        # 保存最后一个章节
        if current_content:
            sections[current_title] = '\n'.join(current_content).strip()
            
        return sections

    def get_section(self, keyword: str) -> Optional[str]:
        """
        根据关键词获取章节内容（模糊匹配）
        例如：get_section("程序员思维") 可以匹配 "5) 程序员思维→奇幻能力转化体系"
        """
        for title, content in self.sections.items():
            if keyword in title:
                logging.info(f"ArchitectureReader: Found section '{title}' matching keyword '{keyword}'")
                return f"## {title}\n{content}"
        return None

    def get_dynamic_guidelines(self) -> str:
        """
        自动提取所有"指导性"的章节
        这些章节通常包含对生成过程的具体要求
        """
        guidelines = []
        
        # 定义需要关注的关键词列表
        # 这些词出现时，意味着该章节包含具体的写作指引
        target_keywords = [
            "程序员思维",
            "暧昧",
            "香艳",
            "创作技法",
            "合规",
            "写作指导",
            "场景设计原则",
            "伏笔植入体系",
            "反转节点",
            "血脉",
            "五脉",
            "五大血脉"
        ]
        
        for title, content in self.sections.items():
            for kw in target_keywords:
                if kw in title:
                    guidelines.append(f"### 指导原则：{title}\n{content}\n")
                    break # 避免重复添加
        
        if not guidelines:
            return ""
            
        return "\n".join(guidelines)
