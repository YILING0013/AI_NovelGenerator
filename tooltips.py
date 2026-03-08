# tooltips.py
# -*- coding: utf-8 -*-

tooltips = {
    "api_key": "在这里填写你的API Key。如果使用OpenAI官方接口，请在 https://platform.openai.com/account/api-keys 获取。",
    "base_url": "模型的接口地址。若使用OpenAI官方：https://api.openai.com/v1。若使用Ollama本地部署，则类似 http://localhost:11434/v1。调用Gemini模型则无需填写。\n"+
                     "智谱AI请使用：https://open.bigmodel.cn/api/paas/v4 (不要包含/chat/completions)\n"+
                     "智谱AI API Key格式: 通常以'.'分隔，如: xxx.xxx.xxx\n"+
                     "注意：智谱AI有速率限制，如遇429错误请稍后重试",
    "interface_format": "指定LLM接口兼容格式，可选DeepSeek、OpenAI、Ollama、ML Studio、Gemini、智谱AI等。\n\n注意："+
                        "OpenAI 兼容是指的可以通过该标准请求的任何接口，不是只允许使用api.openai.com接口\n"+
                        "例如Ollama接口格式也兼容OpenAI，可以无需修改直接使用\n"+
                        "ML Studio接口格式与OpenAI接口格式也一致。",
    "model_name": "要使用的模型名称，例如deepseek-reasoner、gpt-4o等。如果是Ollama等，请填写你下载好的本地模型名。",
    "temperature": "生成文本的随机度。数值越大越具有发散性，越小越严谨。",
    "max_tokens": "限制单次生成的最大Token数。范围1~100000，请根据模型上下文及需求填写合适值。\n"+
                  "以下是一些常见模型的最大值：\n"+
                  "o1：100,000\n"+
                  "o1-mini：65,536\n"+
                  "gpt-4o：16384\n"+
                  "gpt-4o-mini：16384\n"+
                  "deepseek-reasoner：8192\n"+
                  "deepseek-chat：4096\n",
    "embedding_api_key": "调用Embedding模型时所需的API Key。",
    "embedding_interface_format": "Embedding模型接口风格，比如OpenAI或Ollama。",
    "embedding_url": "Embedding模型接口地址。",
    "embedding_model_name": "Embedding模型名称，如text-embedding-ada-002。",
    "embedding_retrieval_k": "向量检索时返回的Top-K结果数量。",
    "topic": "小说的大致主题或主要故事背景描述。",
    "genre": "小说的题材类型，如玄幻、都市、科幻等。",
    "num_chapters": "小说期望的章节总数。",
    "word_number": "每章的目标字数。",
    "filepath": "生成文件存储的根目录路径。所有txt文件、向量库等放在该目录下。",
    "chapter_num": "当前正在处理的章节号，用于生成草稿或定稿操作。",
    "user_guidance": "为本章提供的一些额外指令或写作引导。",
    "characters_involved": "本章需要重点描写或影响剧情的角色名单。",
    "key_items": "在本章中出现的重要道具、线索或物品。",
    "scene_location": "本章主要发生的地点或场景描述。",
    "time_constraint": "本章剧情中涉及的时间压力或时限设置。",
    "webdav_target_dir": "WebDAV 远端目录名。用于存放/恢复配置文件（config.json）。留空时默认使用 AI_Novel_Generator。",
    "interface_config": "选择你要使用的AI接口配置。"
}
