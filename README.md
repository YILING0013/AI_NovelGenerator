# 📖 NovelForge: Intelligent AI Creative Writing Studio

**NovelForge** is a professional-grade, multi-stage novel generation tool designed to help authors create consistent, high-quality long-form stories using Large Language Models (LLMs). It automates the creative process from initial world-building to finalized chapters, maintaining a deep semantic memory of your story's progress.

<div align="center">
  
✨ **Core Capabilities** ✨

| Module                | Key Features                                           |
|-----------------------|--------------------------------------------------------|
| 🎨 **World Studio**   | Detailed Worldbuilding, Character Design, & Plot Arcs  |
| 📖 **Smart Blueprint**| Intelligent Chapter Directory & Rhythm Management      |
| 🧠 **Memory Engine**  | Vector-based Context Retrieval for Plot Consistency    |
| 🎭 **State Tracker**  | Real-time Character Development & Item Tracking        |
| ✅ **Logic Auditor**  | Automatic Proofreading & Contradiction Detection       |
| 🖥️ **Forge Console**  | Full-process Visual Workbench for Generation & Editing |

</div>

---

## 🚀 Quick Start

### Environment Preparation
- **Python 3.10+**
- **pip** package manager
- **API Keys**: OpenAI, DeepSeek, Google Gemini, or a local **Ollama** instance.

### Installation
1. **Clone the Studio**
   ```bash
   git clone https://github.com/your-repo/NovelForge
   cd NovelForge
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the Forge**
   ```bash
   python main.py
   ```

---

## 📘 Creating Your Masterpiece

1.  **Configure the Engine**: Go to the **Config Mapping** tab and select your preferred LLMs for different tasks (e.g., GPT-4o for Architecture, DeepSeek for Drafting).
2.  **Forge the Setting**: Use **Step 1** to generate your world, characters, and high-level plot structure.
3.  **Draft the Directory**: Use **Step 2** to create a chapter-by-chapter roadmap. You can edit every detail of the blueprint.
4.  **Generate Chapters**: Select a chapter number and use **Step 3** to generate a draft. NovelForge will use its **Memory Engine** to recall previous plot points and ensure continuity.
5.  **Finalize & Track**: Once you're happy with a draft, use **Step 4** to finalize it. This updates the **Global Summary**, **Character States**, and the **Semantic Memory**.

---

## ⚙️ Advanced Configuration

### Provider Support
NovelForge supports all OpenAI-compatible APIs, including:
- **Cloud**: OpenAI, DeepSeek, Google Gemini, Grok.
- **Local**: Ollama, LM Studio.
- **Ollama Cloud**: To use Ollama's cloud hosting, set the interface format to **Ollama Cloud**, use base URL `https://ollama.com/v1`, and provide your API key.

---

## 📑 Project Roadmap
- [ ] Multi-language prompt support (i18n).
- [ ] Export to Word/PDF/EPUB formats.
- [ ] Interactive character relationship graph.
- [ ] Multi-perspective chapter drafting.

---

## ❓ FAQ

**Q: The AI is forgetting details from early chapters.**
A: Ensure you are using **Step 4. Finalize Chapter**. This step adds the chapter content to the vector database, which NovelForge uses for long-term memory retrieval.

**Q: How do I change the chapter length?**
A: Adjust the **Words/Chap** parameter in the **Main Functions** tab before generating a draft.

---

*Transform your ideas into epic narratives with NovelForge.*
