# translation_mapping.py
# -*- coding: utf-8 -*-
"""
中英文词汇映射库
支持智能翻译和上下文感知的词汇替换
"""

# 常见副词映射
ADVERB_MAPPING = {
    'surprisingly': '意外地',
    'suddenly': '突然',
    'quickly': '迅速地',
    'slowly': '慢慢地',
    'carefully': '小心地',
    'quietly': '安静地',
    'loudly': '大声地',
    'softly': '轻柔地',
    'roughly': '粗糙地',
    'smoothly': '平滑地',
    'easily': '容易地',
    'difficultly': '困难地',
    'immediately': '立即',
    'eventually': '最终',
    'gradually': '逐渐地',
    'completely': '完全地',
    'partially': '部分地',
    'really': '真正地',
    'actually': '实际上',
    'obviously': '明显地',
    'clearly': '清楚地',
    'apparently': '显然地',
    'seemingly': '似乎',
    'supposedly': '据说',
    'hopefully': '希望地',
    'fortunately': '幸运地',
    'unfortunately': '不幸地',
    'interestingly': '有趣地',
    'strangely': '奇怪地',
    'normally': '正常地',
    'usually': '通常地',
    'always': '总是',
    'never': '从不',
    'sometimes': '有时',
    'often': '经常',
    'rarely': '很少地',
    'occasionally': '偶尔地',
    'frequently': '频繁地',
    'constantly': '不断地',
    'continuously': '持续地',
    'occasionally': '偶尔地',
    'seldom': '很少地',
    'merely': '仅仅',
    'simply': '简单地',
    'truly': '真正地',
    'genuinely': '真诚地',
    'honestly': '诚实地',
    'seriously': '严重地',
    'slightly': '轻微地',
    'heavily': '重重地',
    'deeply': '深深地',
    'highly': '高度地',
    'greatly': '大大地',
    'significantly': '显著地',
    'considerably': '相当大地',
    'substantially': '实质性地',
    'dramatically': '戏剧性地',
    'radically': '激进地',
    'fundamentally': '根本地',
    'essentially': '本质上',
    'basically': '基本上',
    'generally': '一般地',
    'typically': '典型地',
    'usually': '通常地',
    'normally': '正常地',
    'regularly': '定期地',
    'occasionally': '偶尔地',
    'rarely': '很少地',
    'scarcely': '几乎不',
    'hardly': '几乎不',
    'barely': '勉强地',
    'almost': '几乎',
    'nearly': '将近',
    'approximately': '大约地',
    'roughly': '大约地',
    'about': '大约地',
}

# 常见形容词映射
ADJECTIVE_MAPPING = {
    'soft': '柔软的',
    'hard': '坚硬的',
    'warm': '温暖的',
    'cold': '寒冷的',
    'hot': '炎热的',
    'cool': '凉爽的',
    'bright': '明亮的',
    'dark': '黑暗的',
    'light': '明亮的',
    'heavy': '沉重的',
    'big': '大的',
    'small': '小的',
    'large': '巨大的',
    'tiny': '微小的',
    'huge': '巨大的',
    'vast': '广阔的',
    'beautiful': '美丽的',
    'ugly': '丑陋的',
    'pretty': '漂亮的',
    'handsome': '英俊的',
    'cute': '可爱的',
    'lovely': '可爱的',
    'wonderful': '美妙的',
    'terrible': '可怕的',
    'horrible': '可怕的',
    'awful': '糟糕的',
    'good': '好的',
    'bad': '坏的',
    'nice': '好的',
    'great': '伟大的',
    'excellent': '优秀的',
    'perfect': '完美的',
    'imperfect': '不完美的',
    'strong': '强壮的',
    'weak': '虚弱的',
    'powerful': '强大的',
    'gentle': '温和的',
    'rough': '粗糙的',
    'smooth': '光滑的',
    'clean': '干净的',
    'dirty': '肮脏的',
    'fresh': '新鲜的',
    'stale': '陈旧的',
    'new': '新的',
    'old': '老的',
    'young': '年轻的',
    'mature': '成熟的',
    'green': '绿色的',
    'red': '红色的',
    'blue': '蓝色的',
    'yellow': '黄色的',
    'black': '黑色的',
    'white': '白色的',
    'gray': '灰色的',
    'brown': '棕色的',
    'pink': '粉红色的',
    'purple': '紫色的',
    'orange': '橙色的',
}

# 常见动词映射
VERB_MAPPING = {
    'walk': '行走',
    'run': '奔跑',
    'jump': '跳跃',
    'sit': '坐着',
    'stand': '站着',
    'lie': '躺着',
    'sleep': '睡觉',
    'wake': '醒来',
    'eat': '吃',
    'drink': '喝',
    'see': '看见',
    'look': '看',
    'watch': '观看',
    'listen': '听',
    'hear': '听到',
    'feel': '感觉',
    'touch': '触摸',
    'smell': '闻',
    'taste': '品尝',
    'think': '思考',
    'know': '知道',
    'understand': '理解',
    'learn': '学习',
    'teach': '教导',
    'speak': '说话',
    'talk': '交谈',
    'say': '说',
    'tell': '告诉',
    'ask': '询问',
    'answer': '回答',
    'read': '阅读',
    'write': '写作',
    'draw': '绘画',
    'sing': '唱歌',
    'dance': '跳舞',
    'play': '玩耍',
    'work': '工作',
    'rest': '休息',
    'fight': '战斗',
    'help': '帮助',
    'give': '给予',
    'take': '拿取',
    'bring': '带来',
    'carry': '携带',
    'push': '推',
    'pull': '拉',
    'open': '打开',
    'close': '关闭',
    'start': '开始',
    'stop': '停止',
    'continue': '继续',
    'finish': '完成',
    'begin': '开始',
    'end': '结束',
    'create': '创造',
    'destroy': '摧毁',
    'build': '建造',
    'break': '打破',
    'make': '制作',
    'do': '做',
    'have': '拥有',
    'get': '获得',
    'become': '变成',
    'seem': '似乎',
    'appear': '出现',
    'disappear': '消失',
    'change': '改变',
    'move': '移动',
    'turn': '转动',
    'fall': '落下',
    'rise': '升起',
    'grow': '成长',
    'live': '生活',
    'die': '死亡',
    'love': '爱',
    'hate': '恨',
    'like': '喜欢',
    'want': '想要',
    'need': '需要',
    'hope': '希望',
    'wish': '愿望',
    'dream': '梦想',
    'believe': '相信',
    'doubt': '怀疑',
    'remember': '记住',
    'forget': '忘记',
    'agree': '同意',
    'disagree': '不同意',
    'accept': '接受',
    'refuse': '拒绝',
    'invite': '邀请',
    'visit': '拜访',
    'travel': '旅行',
    'explore': '探索',
    'discover': '发现',
    'search': '搜索',
    'find': '找到',
    'lose': '失去',
    'save': '拯救',
    'protect': '保护',
    'attack': '攻击',
    'defend': '防御',
    'escape': '逃跑',
    'follow': '跟随',
    'lead': '领导',
    'join': '加入',
    'leave': '离开',
    'arrive': '到达',
    'depart': '离开',
    'return': '返回',
}

# 常见连词和介词映射
CONJUNCTION_MAPPING = {
    'and': '和',
    'or': '或者',
    'but': '但是',
    'because': '因为',
    'so': '所以',
    'if': '如果',
    'then': '那么',
    'when': '当',
    'where': '哪里',
    'why': '为什么',
    'how': '如何',
    'what': '什么',
    'who': '谁',
    'which': '哪个',
    'that': '那个',
    'this': '这个',
    'these': '这些',
    'those': '那些',
    'here': '这里',
    'there': '那里',
    'now': '现在',
    'then': '那时',
    'today': '今天',
    'tomorrow': '明天',
    'yesterday': '昨天',
    'always': '总是',
    'never': '从不',
    'sometimes': '有时',
    'often': '经常',
    'rarely': '很少地',
    'usually': '通常地',
    'maybe': '也许',
    'perhaps': '或许',
    'possibly': '可能地',
    'probably': '可能地',
    'certainly': '确定地',
    'definitely': '明确地',
    'obviously': '明显地',
    'clearly': '清楚地',
    'actually': '实际上',
    'really': '真正地',
    'indeed': '确实地',
    'in fact': '事实上',
    'of course': '当然',
    'at least': '至少',
    'at most': '最多',
    'more or less': '或多或少',
    'sooner or later': '迟早',
    'so to speak': '可以说',
    'as it were': '可以说',
}

# 专有名词列表（这些不会被翻译）
PROPER_NOUNS = [
    # 品牌名称
    'Apple', 'Google', 'Microsoft', 'Amazon', 'Facebook', 'Twitter', 'Instagram',
    'YouTube', 'Netflix', 'Tesla', 'Toyota', 'Honda', 'BMW', 'Mercedes', 'Audi',
    'Coca-Cola', 'Pepsi', 'McDonald', 'KFC', 'Starbucks', 'Nike', 'Adidas',

    # 常见人名
    'John', 'Mary', 'David', 'Sarah', 'Michael', 'Emma', 'James', 'Lisa',
    'Robert', 'Jennifer', 'William', 'Linda', 'Richard', 'Patricia', 'Joseph', 'Barbara',

    # 地名
    'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia',
    'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'London', 'Paris', 'Tokyo',
    'Beijing', 'Shanghai', 'Hong Kong', 'Singapore', 'Seoul', 'Bangkok',

    # 科技术语
    'AI', 'CPU', 'GPU', 'RAM', 'ROM', 'USB', 'WiFi', 'Bluetooth', 'GPS',
    'HTML', 'CSS', 'JavaScript', 'Python', 'Java', 'C++', 'SQL', 'API',
    'URL', 'HTTP', 'HTTPS', 'FTP', 'IP', 'LAN', 'WAN', 'VPN', 'CDN',

    # 组织和机构
    'NASA', 'FBI', 'CIA', 'UN', 'WHO', 'CDC', 'FDA', 'EPA', 'NATO',
    'Oxford', 'Cambridge', 'Harvard', 'Yale', 'MIT', 'Stanford',

    # 常见缩写
    'CEO', 'CTO', 'CFO', 'COO', 'CIO', 'CMO', 'CSO', 'CPO',
    'DIY', 'DIY', 'DIY', 'DIY', 'DIY', 'DIY', 'DIY', 'DIY',

    # 常见软件和平台
    'Windows', 'Mac', 'Linux', 'Android', 'iOS', 'Office', 'Photoshop',
    'Chrome', 'Firefox', 'Safari', 'Edge', 'Zoom', 'Slack', 'Discord',

    # 时间相关
    'AM', 'PM', 'BC', 'AD', 'CE', 'BCE', 'UTC', 'GMT', 'EST', 'PST',
    'CST', 'JST', 'KST', 'IST', 'AEST', 'NZST', 'HST', 'AKST', 'MST',
    'CET', 'EET', 'WET', 'AST', 'NST', 'YST', 'PST', 'MST', 'CST',
]

# 主映射表，按优先级排序
TRANSLATION_MAPPING = {
    # 首先添加副词（优先级最高）
    **ADVERB_MAPPING,

    # 然后添加形容词
    **ADJECTIVE_MAPPING,

    # 然后添加动词
    **VERB_MAPPING,

    # 最后添加连词和介词
    **CONJUNCTION_MAPPING,
}

# 多义词映射（根据上下文选择不同翻译）
POLYSEMOUS_MAPPING = {
    'like': [
        {'word': '喜欢', 'context': ['我', '你', '他', '她', '它', '我们', '你们', '他们', '她们', '它们', '喜欢']},
        {'word': '像', 'context': ['像', '如同', '仿佛', '好似', '犹如']},
        {'word': '例如', 'context': ['例如', '比如', '譬如', '诸如']},
    ],
    'set': [
        {'word': '设置', 'context': ['设置', '设定', '配置']},
        {'word': '放置', 'context': ['放置', '摆放', '安放']},
        {'word': '套', 'context': ['套', '组', '系列']},
        {'word': '落山', 'context': ['太阳', '月亮', '落山', '下沉']},
    ],
    'right': [
        {'word': '正确的', 'context': ['正确的', '对的', '准确的']},
        {'word': '右边', 'context': ['右边', '右侧', '右面']},
        {'word': '权利', 'context': ['权利', '权力', '权益']},
        {'word': '立即', 'context': ['立即', '马上', '即刻']},
    ],
    'light': [
        {'word': '光', 'context': ['光', '光线', '光芒']},
        {'word': '轻的', 'context': ['轻的', '轻便的', '轻松的']},
        {'word': '点燃', 'context': ['点燃', '点燃', '点火']},
        {'word': '浅色的', 'context': ['浅色', '淡色', '浅']},
    ],
    'well': [
        {'word': '好', 'context': ['好', '良好', '优秀']},
        {'word': '井', 'context': ['井', '水井', '井口']},
        {'word': '涌出', 'context': ['涌出', '涌出', '冒出']},
    ],
    'mean': [
        {'word': '意味着', 'context': ['意味着', '表示', '意思是']},
        {'word': '刻薄的', 'context': ['刻薄', '小气', '吝啬']},
        {'word': '平均的', 'context': ['平均', '中等', '一般']},
    ],
    'just': [
        {'word': '刚刚', 'context': ['刚刚', '刚才', '方才']},
        {'word': '仅仅', 'context': ['仅仅', '只是', '只不过']},
        {'word': '公正的', 'context': ['公正', '公平', '正义']},
        {'word': '合理的', 'context': ['合理', '正当', '应该']},
    ],
    'can': [
        {'word': '能够', 'context': ['能够', '可以', '能']},
        {'word': '罐头', 'context': ['罐头', '罐子', '金属罐']},
        {'word': '垃圾桶', 'context': ['垃圾', '垃圾桶', '废纸篓']},
    ],
}

def get_translation_by_context(word: str, context: str = "") -> str:
    """
    根据上下文获取最合适的翻译

    Args:
        word: 英文单词
        context: 上下文文本

    Returns:
        str: 最合适的中文翻译
    """
    word_lower = word.lower()

    # 检查多义词映射
    if word_lower in POLYSEMOUS_MAPPING:
        translations = POLYSEMOUS_MAPPING[word_lower]

        # 根据上下文选择最合适的翻译
        for trans_info in translations:
            for context_word in trans_info['context']:
                if context_word in context.lower():
                    return trans_info['word']

        # 如果没有匹配的上下文，返回第一个翻译
        return translations[0]['word']

    # 检查主映射表
    if word_lower in TRANSLATION_MAPPING:
        return TRANSLATION_MAPPING[word_lower]

    # 如果没有找到映射，返回原词
    return word

def add_custom_translation(english_word: str, chinese_translation: str, category: str = "custom"):
    """
    添加自定义翻译映射

    Args:
        english_word: 英文单词
        chinese_translation: 中文翻译
        category: 分类（adverb/adjective/verb/conjunction/custom）
    """
    global TRANSLATION_MAPPING

    TRANSLATION_MAPPING[english_word.lower()] = chinese_translation

    # 可选：根据分类添加到相应的映射表中
    if category == "adverb":
        ADVERB_MAPPING[english_word.lower()] = chinese_translation
    elif category == "adjective":
        ADJECTIVE_MAPPING[english_word.lower()] = chinese_translation
    elif category == "verb":
        VERB_MAPPING[english_word.lower()] = chinese_translation
    elif category == "conjunction":
        CONJUNCTION_MAPPING[english_word.lower()] = chinese_translation

def add_proper_noun(noun: str):
    """
    添加专有名词到保护列表

    Args:
        noun: 专有名词
    """
    global PROPER_NOUNS
    if noun not in PROPER_NOUNS:
        PROPER_NOUNS.append(noun)

def is_proper_noun(word: str) -> bool:
    """
    检查单词是否为专有名词

    Args:
        word: 待检查的单词

    Returns:
        bool: 是否为专有名词
    """
    word_lower = word.lower()
    return any(noun.lower() == word_lower for noun in PROPER_NOUNS)