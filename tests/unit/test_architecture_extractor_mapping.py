from __future__ import annotations

from novel_generator.architecture_extractor import DynamicArchitectureExtractor


def test_find_relevant_volumes_uses_explicit_chapter_ranges():
    architecture = """
#=== 3) 角色总表 ===
### 角色一：林夜
#=== 4) 设定补充 ===
#=== 5) 情节架构 ===
第一卷：寒门起势
第1-20章：起势段
第二卷：宗门争锋
第21-40章：争锋段
第三卷：秘境风暴
第41-60章：秘境段
#=== 6) 终局 ===
"""
    extractor = DynamicArchitectureExtractor(architecture)
    volumes = extractor._find_relevant_volumes(23, 26)
    assert [int(vol["vol_num"]) for vol in volumes] == [2]


def test_find_relevant_volumes_falls_back_to_first_volume_when_no_mapping():
    architecture = """
#=== 3) 角色总表 ===
### 角色一：林夜
#=== 4) 设定补充 ===
#=== 5) 情节架构 ===
第一卷：寒门起势
这里没有明确章节号
第二卷：宗门争锋
这里也没有明确章节号
#=== 6) 终局 ===
"""
    extractor = DynamicArchitectureExtractor(architecture)
    volumes = extractor._find_relevant_volumes(200, 205)
    assert len(volumes) == 1
    assert int(volumes[0]["vol_num"]) == 1


def test_find_relevant_volumes_supports_markdown_detailed_plot_blocks():
    architecture = """
## 5. 角色系统
主角实名：秦昭野

## 15. 卷1-卷4详细情节点（80点，可直接拆章）
### 15.1 卷1《边荒断命》情节点（1-20）
1. 1-3章：古碑爆裂，主角前世身死。
2. 4-6章：重生于边荒废脉少年。

### 15.2 卷2《血火开脉》情节点（21-40）
21. 91-95章：主角逃入蛮荒，肉身濒碎。
22. 96-100章：巫寨祭师提出借命开脉交易。

## 16. 其他内容
"""
    extractor = DynamicArchitectureExtractor(architecture)
    volumes = extractor._find_relevant_volumes(92, 94)
    assert [int(vol["vol_num"]) for vol in volumes] == [2]


def test_last_markdown_volume_does_not_swallow_following_sections():
    architecture = """
## 15. 卷1-卷4详细情节点（80点，可直接拆章）
### 15.1 卷1《边荒断命》情节点（1-20）
1. 1-3章：起势。

## 38. 卷13-卷16详细情节点（241-320，可直接拆章）
### 38.4 卷16《裂书之夜》情节点（301-320）
301. 1491-1495章：外环崩塌。
302. 1496-1500章：终锚启动。

## 39. 卷13-卷16二十个高光场景（S61-S80）
### 39.1 卷13高光场景（S61-S65）
附录统计：1-100章节奏回顾（本段不是情节点）。
"""
    extractor = DynamicArchitectureExtractor(architecture)
    vol16 = next(vol for vol in extractor.structure["volumes"] if int(vol["vol_num"]) == 16)

    assert int(vol16["chapter_min"]) == 1491
    assert int(vol16["chapter_max"]) == 1500


def test_find_relevant_volumes_excludes_far_volume_when_range_not_overlapping():
    architecture = """
## 15. 卷1-卷4详细情节点（80点，可直接拆章）
### 15.1 卷1《边荒断命》情节点（1-20）
1. 1-3章：起势。

## 38. 卷13-卷16详细情节点（241-320，可直接拆章）
### 38.4 卷16《裂书之夜》情节点（301-320）
301. 1491-1495章：外环崩塌。
302. 1496-1500章：终锚启动。

## 39. 额外章节统计
### 39.1 统计说明
附录统计：1-100章节奏回顾（本段不是情节点）。
"""
    extractor = DynamicArchitectureExtractor(architecture)
    volumes = extractor._find_relevant_volumes(1, 1)

    assert [int(vol["vol_num"]) for vol in volumes] == [1]


def test_parse_structure_supports_plain_volume_lines_and_table_range_mapping():
    architecture = """
## 6. 四十卷展开
卷1《边荒断命》
- 起势卷
卷2《血火开脉》
- 进阶卷

## 88. 全书伏笔回收总表
| 编号 | 伏笔 | Setup章 | Echo章 | Resolve章 | 状态 |
|---|---|---|---|---|---|
| S01 | 前世死于古碑异变并非意外 | 1-3 | 1096-1110 | 3806-3835 | 文本落地 |
| S02 | 天书残页与执笔席位绑定 | 211-230 | 3231-3250 | 3821-3850 | 文本落地 |

## 94. 全书40卷章节配额基线
| 卷次 | 章节范围 | 目标字数 | 阶段 |
|---|---|---|---|
| 卷1 | 1-100 | 70万-80万 | 第一阶段 |
| 卷2 | 101-200 | 70万-80万 | 第一阶段 |
"""
    extractor = DynamicArchitectureExtractor(architecture)

    volumes = {int(vol["vol_num"]): vol for vol in extractor.structure["volumes"]}
    assert 1 in volumes
    assert 2 in volumes
    assert extractor.structure["chapter_to_volume"].get(1) == 1
    assert extractor.structure["chapter_to_volume"].get(150) == 2
    assert "古碑异变" in str(extractor.structure["chapters"].get(1, ""))
