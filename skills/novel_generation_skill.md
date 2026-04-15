**Novel Generation Skill**

- 描述：最小化的小说生成工作流说明，包含架构、章节蓝图、章节草稿、定稿的顺序和所需输入。
- 使用说明：
  1. 生成小说架构（调用 `novel_generator.Novel_architecture_generate`）
  2. 生成章节蓝图（调用 `novel_generator.Chapter_blueprint_generate`）
  3. 生成章节草稿（调用 `novel_generator.generate_chapter_draft`）
  4. 定稿（调用 `novel_generator.finalize_chapter`）

- 输入/输出：
  - 所有函数使用的主要参数请参考 `novel_generator/chapter.py` 中的函数签名。
  - 提示词模板位于 `prompt_definitions.py`，调试时可使用 `prompts/first_chapter_request.txt` 中的模板填充后调用。 

- 快速测试：
  - 在项目根目录运行：

    .\.venv\Scripts\python.exe tools_test_generate.py

  - 该脚本会打印基于模板生成的第一章提示词，用于确认本地逻辑和模板填充。

