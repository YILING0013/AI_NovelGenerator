# 📖 自动小说生成工具

>- ~~当前没有什么精力维护该项目，本身该项目并无任何收益，以及临近毕业，有很多内容要忙，如果后面有时间的话，再考虑基于更新的技术去重构吧。——2025/9/24~~
>
>- ~~**(2026/03/09)：** 本项目即将在近期开启重构，届时将采用更先进的技术实现与全新的创意。~~
>
> **更新 (2026/03/25)：** 重构版已完成初步开发（仅完成大体框架，功能还不可用），将在一周内上传到dev分支，后续开发也会在分支进行同步。

<div align="center">
  
✨ **核心功能** ✨

| 功能模块          | 关键能力                          |
|-------------------|----------------------------------|
| 🎨 小说设定工坊    | 世界观架构 / 角色设定 / 剧情蓝图   |
| 📖 智能章节生成    | 多阶段生成保障剧情连贯性           |
| 🧠 状态追踪系统    | 角色发展轨迹 / 伏笔管理系统         |
| 🔍 语义检索引擎    | 基于向量的长程上下文一致性维护      |
| 📚 知识库集成      | 支持本地文档参考         |
| ✅ 自动审校机制    | 检测剧情矛盾与逻辑冲突          |
| 🖥 可视化工作台    | 全流程GUI操作，配置/生成/审校一体化 |

</div>

> 一款基于大语言模型的多功能小说生成器，助您高效创作逻辑严谨、设定统一的长篇故事

---

## 📑 目录导航
1. [环境准备](#-环境准备)  
2. [项目架构](#-项目架构)  
3. [配置指南](#⚙️-配置指南)  
4. [运行说明](#🚀-运行说明)  
5. [使用教程](#📘-使用教程)  
6. [疑难解答](#❓-疑难解答)  

---

## 🛠 环境准备
确保满足以下运行条件：
- **Python 3.9+** 运行环境（推荐3.10-3.12之间）
- **pip** 包管理工具
- 有效API密钥：
  - 云端服务：OpenAI / DeepSeek 等
  - 本地服务：Ollama 等兼容 OpenAI 的接口

---


## 📥 安装说明
1. **下载项目**  
   - 通过 [GitHub](https://github.com) 下载项目 ZIP 文件，或使用以下命令克隆本项目：
     ```bash
     git clone https://github.com/YILING0013/AI_NovelGenerator
     ```

2. **安装编译工具（可选）**  
   - 如果对某些包无法正常安装，访问 [Visual Studio Build Tools](https://visualstudio.microsoft.com/zh-hans/visual-cpp-build-tools/) 下载并安装C++编译工具，用于构建部分模块包；
   - 安装时，默认只包含 MSBuild 工具，需手动勾选左上角列表栏中的 **C++ 桌面开发** 选项。

3. **安装依赖并运行**  
   - 打开终端，进入项目源文件目录：
     ```bash
     cd AI_NovelGenerator
     ```
   - 安装项目依赖：
     ```bash
     pip install -r requirements.txt
     ```
   - 安装完成后，运行主程序：
     ```bash
     python main.py
     ```

>如果缺失部分依赖，后续**手动执行**
>```bash
>pip install XXX
>```
>进行安装即可

## 🗂 项目架构
```
novel-generator/
├── main.py                      # 入口文件, 运行 GUI
├── consistency_checker.py       # 一致性检查, 防止剧情冲突
|—— chapter_directory_parser.py  # 目录解析
|—— embedding_adapters.py        # Embedding 接口封装
|—— llm_adapters.py              # LLM 接口封装
├── prompt_definitions.py        # 定义 AI 提示词
├── utils.py                     # 常用工具函数, 文件操作
├── config_manager.py            # 管理配置 (API Key, Base URL)
├── config.json                  # 用户配置文件 (可选)
├── novel_generator/             # 章节生成核心逻辑
├── ui/                          # 图形界面
└── vectorstore/                 # (可选) 本地向量数据库存储
```

---

## ⚙️ 配置指南
### 📌 基础配置（config.json）
```json
{
    "api_key": "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "base_url": "https://api.openai.com/v1",
    "interface_format": "OpenAI",
    "model_name": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "embedding_api_key": "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "embedding_interface_format": "OpenAI",
    "embedding_url": "https://api.openai.com/v1",
    "embedding_model_name": "text-embedding-ada-002",
    "embedding_retrieval_k": 4,
    "topic": "星穹铁道主角星穿越到原神提瓦特大陆，拯救提瓦特大陆，并与其中的角色展开爱恨情仇的小说",
    "genre": "玄幻",
    "num_chapters": 120,
    "word_number": 4000,
    "filepath": "D:/AI_NovelGenerator/filepath"
}
```

### 🔧 配置说明
1. **生成模型配置**
   - `api_key`: 大模型服务的API密钥
   - `base_url`: API终端地址（本地服务填Ollama等地址）
   - `interface_format`: 接口模式
   - `model_name`: 主生成模型名称（如gpt-4, claude-3等）
   - `temperature`: 创意度参数（0-1，越高越有创造性）
   - `max_tokens`: 模型最大回复长度

2. **Embedding模型配置**
   - `embedding_model_name`: 模型名称（如Ollama的nomic-embed-text）
   - `embedding_url`: 服务地址
   - `embedding_retrieval_k`: 

3. **小说参数配置**
   - `topic`: 核心故事主题
   - `genre`: 作品类型
   - `num_chapters`: 总章节数
   - `word_number`: 单章目标字数
   - `filepath`: 生成文件存储路径

---

## 🚀 运行说明
### **方式 1：使用 Python 解释器**
```bash
python main.py
```
执行后，GUI 将会启动，你可以在图形界面中进行各项操作。

### **方式 2：打包为可执行文件**
如果你想在无 Python 环境的机器上使用本工具，可以使用 **PyInstaller** 进行打包：

```bash
pip install pyinstaller
pyinstaller main.spec
```
打包完成后，会在 `dist/` 目录下生成可执行文件（如 Windows 下的 `main.exe`）。

---

## 📘 使用教程
1. **启动后，先完成基本参数设置：**  
   - **API Key & Base URL**（如 `https://api.openai.com/v1`）  
   - **模型名称**（如 `gpt-3.5-turbo`、`gpt-4o` 等）  
   - **Temperature** (0~1，决定文字创意程度)  
   - **主题(Topic)**（如 “废土世界的 AI 叛乱”）  
   - **类型(Genre)**（如 “科幻”/“魔幻”/“都市幻想”）  
   - **章节数**、**每章字数**（如 10 章，每章约 3000 字）  
   - **保存路径**（建议创建一个新的输出文件夹）

2. **点击「Step1. 生成设定」**  
   - 系统将基于主题、类型、章节数等信息，生成：  
     - `Novel_setting.txt`：包含世界观、角色信息、雷点暗线等。  
   - 可以在生成后的 `Novel_setting.txt` 中查看或修改设定内容。

3. **点击「Step2. 生成目录」**  
   - 系统会根据已完成的 `Novel_setting.txt` 内容，为全部章节生成：  
     - `Novel_directory.txt`：包括每章标题和简要提示。  
   - 可以在生成后的文件中查看、修改或补充章节标题和描述。

4. **点击「Step3. 生成章节草稿」**  
   - 在生成章节之前，你可以：  
     - **设置章节号**（如写第 1 章，就填 `1`）  
     - **在“本章指导”输入框**中提供对本章剧情的任何期望或提示  
   - 点击按钮后，系统将：  
     - 自动读取前文设定、`Novel_directory.txt`、以及已定稿章节  
     - 调用向量检索回顾剧情，保证上下文连贯  
     - 生成本章大纲 (`outline_X.txt`) 及正文 (`chapter_X.txt`)  
   - 生成完成后，你可在左侧的文本框查看、编辑本章草稿内容。

5. **点击「Step4. 定稿当前章节」**  
   - 系统将：  
     - **更新全局摘要**（写入 `global_summary.txt`）  
     - **更新角色状态**（写入 `character_state.txt`）  
     - **更新向量检索库**（保证后续章节可以调用最新信息）  
     - **更新剧情要点**（如 `plot_arcs.txt`）  
   - 定稿完成后，你可以在 `chapter_X.txt` 中看到定稿后的文本。

6. **一致性检查（可选）**  
   - 点击「[可选] 一致性审校」按钮，对最新章节进行冲突检测，如角色逻辑、剧情前后矛盾等。  
   - 若有冲突，会在日志区输出详细提示。

7. **重复第 4-6 步** 直到所有章节生成并定稿！

> **向量检索配置提示**  
> 1. embedding模型需要显示指定接口和模型名称；
> 2. 使用**本地Ollama**的**Embedding**时需提前启动Ollama服务：  
>    ```bash
>    ollama serve  # 启动服务
>    ollama pull nomic-embed-text  # 下载/启用模型
>    ```
> 3. 切换不同Embedding模型后建议清空vectorstore目录
> 4. 云端Embedding需确保对应API权限已开通

---

## ❓ 疑难解答
### Q1: Expecting value: line 1 column 1 (char 0)

该问题大概率由于API未正确响应造成，也许响应了一个html？其它内容，导致出现该报错；


### Q2: HTTP/1.1 504 Gateway Timeout？
确认接口是否稳定；

### Q3: 如何切换不同的Embedding提供商？
在GUI界面中对应输入即可。

---

如有更多问题或需求，欢迎在**项目 Issues** 中提出。
