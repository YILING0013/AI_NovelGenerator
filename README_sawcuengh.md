# 📖 Gij Swnjgenh Siujsoz Swjdoengh Sengcwngz Doenghgiuj

[中文文档](./README_zh-CN.md) | [English](./README.md) | [日本語](./README_ja.md) | [Français](./README_fr-FR.md) | Sawcuengh

>- ~~Gyangneix mbouj miz geijlai lijlaeng guenj gij gohyenz neix, gij gohyenz neix mbouj miz gij sauhik maz, caeuq henz byaijdoeg, miz haujlai saehcingz yiet mbouj ndaej banh, hawj gou miz seizgan lai, doengh haujlaiz cungi gig yungh gij gijsuz coengzsin daeuj gaicig.——2025/9/24~~
>
>- ~~**(2026/03/09)：** Gij gohyenz neix gyaq bae gak ge cungj gaicig, doengh seizgan caenh caiq doengh gij gijsuz coengzsin caeuq sin'gyaehuj.~~
>
> **Cingqsin (2026/03/25)：** Gaicig banh lijdoengh caenh cauhgiet banh (caenh doengh daihdaeq dij fukgouz, gij gunghnangz lij mbouj ndaej yungh), gyaq bae doengh it aen sojceih ndaej doengh dev branch, haujlaiz gaicig cungj gyaq doengh branch doengh it lij.

<div align="center">
  
✨ **Gij Gunghnangz Cojyinh** ✨

| Gunghnangz Moegsiz          | Gij Nangzlig Guenhdoh                          |
|-----------------------------|------------------------------------------------|
| 🎨 Siujsoz Dinzsez Gunghfangh    | Seiqgaih gvanhgouz / Gohgyah dizcinz / Gij Gyangmujlwd |
| 📖 Canghgiet Sengcwngz Nangzlig    | Doengh gaidaij sengcwngz baujcwngz gij gyangmujlwd mbouj bienh |
| 🧠 Dungzciengj Doica Genjdungz    | Gohgyah fazcanj gveilwd / Genjdungz genjli gvanhgvenj dungzciengj |
| 🔍 Yiyi Gijca Genjdungz Yinzbingz    | Gij doengh veizciz genjca dauhcingh ndaej ndaej gvanhhoz |
| 📚 Cihswz Goj Cizbungz    | Hojyungh doengh gij banhfap caenhcuengh ndaej gvanhhoz |
| ✅ Swjdoengh Genjgauh Gveiciz    | Genjcat gij gyangmujlwd doenghcaeuq yijcoz doenghcaeuq |
| 🖥 Hagokdoengh Gunghcoz Dozdoz    | Doengh gij doenghlij gij GUI, beihci/sengcwngz/genjgauh doengh it |

</div>

> Gij gij swnjgenh siujsoz sengcwngz doenghgiuj gij gveilwd daih'yoz yiyi moediz gunghnangz, hoj mwngz ndaej sij ndaej hawjlwd cauhcoz ndaej gij doenghcaeuq doenghcaeuq gij doenghcaeuq gij doenghcaeuq

---

## 📑 Muhloeg Dozdoz
1. [Gij Doenghbouh Hoengzgvanh](#-gij-doenghbouh-hoengzgvanh)  
2. [Gij Gveilwd Gouzdiz](#-gij-gveilwd-gouzdiz)  
3. [Beihci Dozdoz](#⚙️-beihci-dozdoz)  
4. [Yinzhangz Dozdoz](#🚀-yinzhangz-dozdoz)  
5. [Sijyungh Dozdoz](#📘-sijyungh-dozdoz)  
6. [Doenghcaeuq Gijca](#❓-doenghcaeuq-gijca)  

---

## 🛠 Gij Doenghbouh Hoengzgvanh
Baujcwngz doenghbouh hoengzgvanh neix:
- **Python 3.9+** Yinzhangz doenghbouh (doenzdoih 3.10-3.12 doengh gij)
- **pip** Goj Genjli Gunghgiuj
- Gij API Mijcaz ndaej ndaej:
  - Yinzdoengh fukvuz: OpenAI / DeepSeek doengh
  - Doenghbouh fukvuz: Ollama doengh doenghcaeuq OpenAI doengh gij giekou

---


## 📥 Ancangh Dozdoz
1. **Dauqloh Gij Gohyenz**  
   - Doengh [GitHub](https://github.com) dauqloh gij gohyenz ZIP banhfap, doengh yungh gij mingzing neix dauqloh:
     ```bash
     git clone https://github.com/YILING0013/AI_NovelGenerator
     ```

2. **Ancangh Biendoengh Gunghgiuj (hojyungh)**  
   - Hawj miz gij goj mbouj ndaej ancaenh ancangh, dozdoz [Visual Studio Build Tools](https://visualstudio.microsoft.com/zh-hans/visual-cpp-build-tools/) dauqloh caeuq ancangh C++ biendoengh gunghgiuj, yungh gij gienjgouz gij goj;
   - Ancangh seiz, doenghbouh caenh miz MSBuild gunghgiuj, mwngz ndaej sijyungh gij doenghlij doengh **C++ Dozdoengh Gienjgouz** doenghcaeuq.

3. **Ancangh Doenghcaeuq Yinzhangz**  
   - Doengh gij doenghlij, doengh gij gohyenz doenghbouh:
     ```bash
     cd AI_NovelGenerator
     ```
   - (Hojyungh) Gienjgouz caeuq hoengzgvanh doenghbouh:
     ```bash
     python -m venv .venv
     # Hawj mbouj ndaej doengh, doengh:
     # python3 -m venv .venv
     ```
     ```bash
     # Windows:
     .venv/Scripts/activate
     ```
     ```bash
     # Linux/Mac:
     source .venv/bin/activate
     ```
   - Ancangh gohyenz doenghcaeuq:
     ```bash
     pip install -r requirements.txt
     ```
   - Ancangh doengh, yinzhangz doenghlij:
     ```bash
     python main.py
     ```

>Hawj miz gij doenghcaeuq doengh, haujlaiz **sijyungh yinzhangz**
>```bash
>pip install XXX
>```
>Hawj ndaej ancaenh

## 🗂 Gij Gveilwd Gouzdiz
```
novel-generator/
├── main.py                      # Doenghlij, yinzhangz GUI
├── consistency_checker.py       # Doenghcaeuq genjcat, doengh gij gyangmujlwd doenghcaeuq
|—— chapter_directory_parser.py  # Muhloeg gijgaeg
|—— embedding_adapters.py        # Embedding giekou gienjgouz
|—— llm_adapters.py              # LLM giekou gienjgouz
├── prompt_definitions.py        |—— AI Dinzcizdoz
├── utils.py                     |—— Sijyungh gunghgiuj hanhsou, doenghfaenh doengh
├── config_manager.py            |—— Genjli beihci (API Key, Base URL)
├── config.json                  |—— Yinzdoengh beihci doenghfaenh (hojyungh)
├── novel_generator/             |—— Canghgiet sengcwngz doenghlij yijcoz
├── ui/                          |—— Hagokdoengh doenghlij dozdoz
└── vectorstore/                 |—— (Hojyungh) Doenghbouh veizciz swhkoj cunghcwz
```

---

## ⚙️ Beihci Dozdoz
### 📌 Gij Beihci Giekjiz (config.json)
```json
{
    "api_key": "***",
    "base_url": "https://api.openai.com/v1",
    "interface_format": "OpenAI",
    "model_name": "gpt-4o-mini",
    "temperature": 0.7,
    "max_tokens": 4096,
    "embedding_api_key": "sk-XXX...XXXX",
    "embedding_interface_format": "OpenAI",
    "embedding_url": "https://api.openai.com/v1",
    "embedding_model_name": "text-embedding-ada-002",
    "embedding_retrieval_k": 4,
    "topic": "Singfunghdijdaeuq doenghcaeuq doenghcaeuq doenghcaeuq",
    "genre": "Yenzgenj",
    "num_chapters": 120,
    "word_number": 4000,
    "filepath": "D:/AI_NovelGenerator/filepath"
}
```

### 🔧 Beihci Dozdoz
1. **Gij Sengcwngz Moediz Beihci**
   - `api_key`: Daih'yoz moediz fukvuz API mijcaz
   - `base_url`: Gij giekou doenghlij (doenghbouh fukvuz gienjgouz Ollama doengh)
   - `interface_format`: Giekou moediz
   - `model_name`: Doengh sengcwngz moediz (doengh gpt-4, claude-3 doengh)
   - `temperature`: Doengh gij yiyi (0-1, doengh ndaej miz gij yiyi)
   - `max_tokens`: Moediz doengh dauhcingh coengz

2. **Embedding Moediz Beihci**
   - `embedding_model_name`: Moediz (doengh Ollama nomic-embed-text)
   - `embedding_url`: Fukvuz doenghlij
   - `embedding_retrieval_k`: 

3. **Siujsoz Gij Beihci**
   - `topic`: Doengh gij gyangmujlwd doenghcaeuq
   - `genre`: Gij gveilwd
   - `num_chapters`: Doengh canghgiet souj
   - `word_number`: Doengh canghgiet doengh dauhcingh
   - `filepath`: Sengcwngz doenghfaenh doenghbouh

---

## 🚀 Yinzhangz Dozdoz
### **Moediz 1：Yungh Python Gijgaeg**
```bash
python main.py
```
Yinzhangz doengh, GUI gyaq doengh, mwngz ndaej doengh gij doenghlij doengh doengh doengh.

### **Moediz 2：Gienjgouz doengh ndaej yungh doenghfaenh**
Hawj mwngz mbouj miz Python doenghbouh ndaej yungh gij doenghgiuj neix, ndaej yungh **PyInstaller** daeuj gienjgouz:

```bash
pip install pyinstaller
pyinstaller main.spec
```
Gienjgouz doengh, gyaq doengh `dist/` doenghbouh sengcwngz doengh ndaej yungh doenghfaenh (doengh Windows `main.exe`).

---

## 📘 Sijyungh Dozdoz
1. **Doengh doengh, caenh doengh gij giekjiz doengh beihci:**  
   - **API Key & Base URL** (doengh `https://api.openai.com/v1`)  
   - **Moediz** (doengh `gpt-3.5-turbo`, `gpt-4o` doengh)  
   - **Temperature** (0~1, gij doengh dauhcingh yiyi)  
   - **Doenghcaeuq (Topic)** (doengh "doengh gij doenghcaeuq AI doengh")  
   - **Gveilwd (Genre)** (doengh "yenzsoij"/"doengh"/"doengh doengh")  
   - **Canghgiet souj**, **doengh canghgiet dauhcingh** (doengh 10 canghgiet, doengh caenh 3000 saw)  
   - **Doenghbouh doenghlij** (doengh gij sin doengh doengh doengh doengh doengh)

2. **Doengh「Step1. Sengcwngz Dinzsez」**  
   - Dungzciengj gyaq doenghcaeuq, gveilwd, canghgiet souj doengh, sengcwngz:  
     - `Novel_setting.txt`：Seiqgaih gvanhgouz, gij doengh gij, gij doengh doengh doengh doengh doengh.  
   - Ndaej doengh sengcwngz doengh `Novel_setting.txt` doengh doengh doengh doengh doengh.

3. **Doengh「Step2. Sengcwngz Muhloeg」**  
   - Dungzciengj gyaq doengh `Novel_setting.txt` doengh, doengh doengh canghgiet sengcwngz:  
     - `Novel_directory.txt`：Cizbwz doengh canghgiet caeuq doengh doengh doengh doengh.  
   - Ndaej doengh sengcwngz doengh doenghfaenh doengh, doengh doengh doengh canghgiet caeuq doengh doengh.

4. **Doengh「Step3. Sengcwngz Canghgiet Caugouj」**  
   - Sengcwngz canghgiet doengh, mwngz ndaej:  
     - **Dinzcinz canghgiet** (doengh 1 canghgiet, gienjgouz `1`)  
     - **Doengh "doengh canghgiet doengh" doengh doengh doengh** doengh doengh doengh doengh doengh  
   - Doengh doengh doengh, dungzciengj gyaq:  
     - Swjdoengh doengh gij doengh doengh, `Novel_directory.txt`, caeuq doengh doengh doengh canghgiet  
     - Doengh veizciz genjca doenghcaeuq gij gyangmujlwd, baujcwngz gij doenghcaeuq doenghcaeuq  
     - Sengcwngz doengh canghgiet daihdaeq (`outline_X.txt`) caeuq doenghlij (`chapter_X.txt`)  
   - Sengcwngz doengh, mwngz ndaej doengh doengh doengh doengh doengh doengh doengh doengh.

5. **Doengh「Step4. Dinzgouj Danghciengz Canghgiet」**  
   - Dungzciengj gyaq:  
     - **Cingqsin doengh gij doengh doengh** (doengh `global_summary.txt`)  
     - **Cingqsin doengh gij doengh doengh** (doengh `character_state.txt`)  
     - **Cingqsin veizciz genjca doengh** (baujcwngz haujlaiz canghgiet ndaej doengh sin doengh)  
     - **Cingqsin gij gyangmujlwd doengh** (doengh `plot_arcs.txt`)  
   - Dinzgouj doengh, mwngz ndaej doengh `chapter_X.txt` doengh doengh doengh doengh doengh.

6. **Doenghcaeuq genjcat (hojyungh)**  
   - Doengh「[Hojyungh] Doenghcaeuq genjgauh」doengh, doengh sin canghgiet doengh doengh doengh, doengh doengh gij doengh doengh, doengh doenghcaeuq doengh doengh doengh doengh doengh.  
   - Hawj miz doenghcaeuq, gyaq doengh doengh doengh doengh doengh doengh doengh.

7. **Doengh doengh 4-6 doengh** doengh doengh canghgiet sengcwngz caeuq dinzgouj!

> **Veizciz genjca beihci doengh**  
> 1. Embedding moediz ndaej doengh doengh doengh giekou caeuq moediz;
> 2. Yungh **doenghbouh Ollama** doengh **Embedding** seiz ndaej doengh Ollama fukvuz:  
>    ```bash
>    ollama serve  # Doengh fukvuz
>    ollama pull nomic-embed-text  # Dauqloh/doengh moediz
>    ```
> 3. Doengh doengh doengh Embedding moediz doengh doengh doengh vectorstore doenghbouh
> 4. Yinzdoengh Embedding ndaej baujcwngz doengh API gvanhgvenj ndaej doengh

---

## ❓ Doenghcaeuq Gijca
### Q1: Expecting value: line 1 column 1 (char 0)

Gij menhdiz neix daihgaibin dwg API mbouj doengh dauhcingh, doengh dauhcingh doengh html? Doengh doengh, doengh gij doengh doengh;

### Q2: HTTP/1.1 504 Gateway Timeout？
Baujcwngz giekou ndaej ndaej;

### Q3: Doengh doengh doengh doengh Embedding fukvuz gij?
Doengh GUI doenghlij doengh doengh doengh doengh.

---

Hawj miz gij doenghcaeuq doengh, doengh doengh **gohyenz Issues** doengh doengh.
