# 📖 自動小説生成ツール

[中文文档](./README_zh-CN.md) | [English](./README.md) | 日本語 | [Français](./README_fr-FR.md) | [Sawcuengh](./README_sawcuengh.md)

> ~~現在このプロジェクトを維持する余裕があまりありません。プロジェクト自体に収益はなく、卒業も近づいているため、他にも忙しいことがたくさんあります。後で時間があれば、より新しい技術を使ってリファクタリングすることを検討するかもしれません。——2025/09/24~~
>
>- ~~**(2026/03/09):** 本プロジェクトは近日中にリファクタリングを開始し、より先進的な技術実装と新しい創造的なコンセプトを採用する予定です。~~
>
> **更新 (2026/03/25):** リファクタリング版は初期開発が完了しました（メインフレームワークのみで、機能はまだ利用できません）。1週間以内に dev ブランチへアップロードされ、以降の開発もブランチで同期されます。

<div align="center">

✨ **コア機能** ✨

| モジュール             | 主な機能                                       |
|------------------------|------------------------------------------------|
| 🎨 小説設定ワークショップ | 世界観構築 / キャラクター設計 / プロット設計図 |
| 📖 インテリジェント章生成 | 多段階生成によりプロットの一貫性を確保         |
| 🧠 状態追跡システム     | キャラクター成長軌跡 / 伏線管理                |
| 🔍 セマンティック検索   | ベクトルベースの長期コンテキスト整合性         |
| 📚 ナレッジベース統合   | ローカルドキュメント参照に対応                 |
| ✅ 自動校正機能         | プロットの矛盾と論理的衝突を検出               |
| 🖥 ビジュアルワークベンチ | 設定 / 生成 / 校正をカバーする全工程 GUI       |

</div>

> 大規模言語モデルを基盤とした多機能小説ジェネレーターです。設定が統一され、論理が緻密な長編ストーリーを効率的に創作することを支援します。

---

## 📑 目次
1. [環境準備](#-環境準備)
2. [プロジェクト構成](#-プロジェクト構成)
3. [設定ガイド](#-設定ガイド)
4. [実行方法](#-実行方法)
5. [使い方](#-使い方)
6. [FAQ](#-faq)

---

## 🛠 環境準備
以下の要件を満たす環境を用意してください:
- **Python 3.9+**（推奨: 3.10–3.12）
- **pip** パッケージマネージャー
- 有効な API キー:
   - クラウドサービス: OpenAI / DeepSeek など
   - ローカルサービス: Ollama などの OpenAI 互換インターフェース

---

## 📥 インストール
1. **プロジェクトを取得**
    - [GitHub](https://github.com) から ZIP をダウンロードするか、リポジトリをクローンします:
       ```bash
       git clone https://github.com/YILING0013/AI_NovelGenerator
       ```

2. **ビルドツールのインストール（任意）**
    - 一部のパッケージがインストールに失敗する場合は、[Visual Studio Build Tools](https://visualstudio.microsoft.com/ja/visual-cpp-build-tools/) から C++ ビルドツールをダウンロード・インストールしてください。
    - デフォルトではインストーラーに MSBuild のみが含まれます。ワークロードから **C++ によるデスクトップ開発** を必ず選択してください。

3. **依存関係をインストールして実行**
    - ターミナルを開き、プロジェクトディレクトリに移動します:
       ```bash
       cd AI_NovelGenerator
       ```
    - （任意）仮想環境を作成して有効化します:
       ```bash
       python -m venv .venv
       # 動作しない場合は次を試してください:
       # python3 -m venv .venv
       ```
       ```
       # Windows の場合:
       .venv/Scripts/activate
       ```
       ```
       # Linux / Mac の場合:
       source .venv/bin/activate
       ```
    - プロジェクトの依存関係をインストールします:
       ```bash
       pip install -r requirements.txt
       ```
    - インストール完了後、メインプログラムを実行します:
       ```bash
       python main.py
       ```

依存関係が不足している場合は、手動でインストールしてください:
```bash
pip install <パッケージ名>
```

## 🗂 プロジェクト構成
```
novel-generator/
├── main.py                      # エントリーポイント、GUI を起動
├── consistency_checker.py       # 一致性チェック、プロット矛盾を防止
|—— chapter_directory_parser.py  # ディレクトリ解析
|—— embedding_adapters.py        # Embedding インターフェースラッパー
|—— llm_adapters.py              # LLM インターフェースラッパー
├── prompt_definitions.py        # AI プロンプトテンプレート
├── utils.py                     # ユーティリティ関数とファイル操作
├── config_manager.py            # 設定マネージャー (API キー、Base URL)
├── config.json                  # ユーザー設定 (任意)
├── novel_generator/             # 章生成のコアロジック
├── ui/                          # グラフィカルユーザーインターフェース
└── vectorstore/                 # (任意) ローカルベクトル DB ストレージ
```

---

## ⚙️ 設定ガイド
### 📌 基本設定 (`config.json`)
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
   "topic": "崩壊スターレイルの主人公が原神のテイワット大陸へ転移し、世界を救いながらキャラクターたちと複雑な関係を築いていく物語。",
   "genre": "ファンタジー",
   "num_chapters": 120,
   "word_number": 4000,
   "filepath": "D:/AI_NovelGenerator/filepath"
}
```

### 🔧 各項目の説明
1. **生成モデル設定**
   - `api_key`: LLM サービスの API キー
   - `base_url`: API エンドポイント（ローカルサービスでは Ollama のアドレスを指定）
   - `interface_format`: インターフェース形式
   - `model_name`: メイン生成モデル名（例: gpt-4、claude-3）
   - `temperature`: 創造性パラメータ（0–1、高いほど創造的）
   - `max_tokens`: モデル応答の最大長

2. **Embedding モデル設定**
   - `embedding_model_name`: Embedding モデル名（例: Ollama の nomic-embed-text）
   - `embedding_url`: サービスのエンドポイント
   - `embedding_retrieval_k`: 取得する近傍数

3. **小説パラメータ**
   - `topic`: メインストーリーのテーマ
   - `genre`: ジャンル
   - `num_chapters`: 全体の章数
   - `word_number`: 1章あたりの目標文字数
   - `filepath`: 生成ファイルの保存先パス

---

## 🚀 実行方法
### 方法 1 — Python で実行
```bash
python main.py
```
GUI が起動し、対話的に操作できます。

### 方法 2 — 実行ファイルへパッケージング
Python のない環境で実行したい場合は **PyInstaller** でパッケージングします:
```bash
pip install pyinstaller
pyinstaller main.spec
```
パッケージング後、`dist/` フォルダに実行ファイル（Windows の場合 `main.exe` など）が生成されます。

---

## 📘 使い方
1. **アプリ起動後、基本パラメータを入力します:**
   - **API Key & Base URL**（例: `https://api.openai.com/v1`）
   - **モデル名**（例: `gpt-3.5-turbo`、`gpt-4o`）
   - **Temperature**（0–1、創造性のばらつきを制御）
   - **トピック**（例: 「終末世界での AI 蜂起」）
   - **ジャンル**（例: 「SF」/「ファンタジー」/「アーバンファンタジー」）
   - **章数** と **1章あたりの文字数**（例: 10 章 × 約 3000 文字）
   - **保存先**（出力用フォルダを新規作成することを推奨）

2. **「Step1. 設定生成」をクリック**
   - トピック・ジャンル・章数を基に以下を生成します:
     - `Novel_setting.txt`: 世界観、キャラクター、伏線などの設定。
   - 生成後の設定は閲覧・編集できます。

3. **「Step2. ディレクトリ生成」をクリック**
   - `Novel_setting.txt` を基に以下を生成します:
     - `Novel_directory.txt`: 章タイトルと短いプロンプト。
   - 章タイトルと説明は確認・修正できます。

4. **「Step3. 章ドラフト生成」をクリック**
   - 章を生成する前に以下を設定できます:
     - 章番号（例: `1`）
     - 「本章ガイダンス」欄に各章固有の指示を入力
   - 章生成時、システムは以下を行います:
     - 既存の設定、`Novel_directory.txt`、確定済みの章を読み込み
     - 一貫性のためにベクトル検索で関連コンテキストを呼び出し
     - 章のアウトライン (`outline_X.txt`) と本文 (`chapter_X.txt`) を生成
   - エディタペインでドラフトを確認・編集できます。

5. **「Step4. 現在の章を確定」をクリック**
   - システムは以下を更新します:
     - グローバルサマリー (`global_summary.txt`)
     - キャラクター状態 (`character_state.txt`)
     - ベクトルストア（以降の章で最新情報を利用できるように）
     - 主要なプロットポイント（例: `plot_arcs.txt`）
   - 確定後、確定版テキストが `chapter_X.txt` に保存されます。

6. **一致性チェック（任意）**
   - 「[任意] 一致性校正」ボタンをクリックすると、最新章をスキャンしてキャラクターのロジックやプロットの矛盾を検出します。
   - 衝突が見つかった場合は、ログ領域に詳細メッセージが表示されます。

7. **手順 4–6 を繰り返し**、すべての章を生成・確定します。

> ベクトル検索のヒント:
> 1. Embedding のインターフェースとモデル名を明示的に指定してください。
> 2. ローカル Ollama の Embedding を使用する場合は、先に Ollama サービスを起動してください:
>    ```bash
>    ollama serve  # サービス起動
>    ollama pull nomic-embed-text  # モデルのダウンロード / 有効化
>    ```
> 3. Embedding モデルを切り替えた後は `vectorstore` ディレクトリをクリアしてください。
> 4. クラウド Embedding を使用する場合は、API の権限が有効になっていることを確認してください。

---

## ❓ FAQ
### Q1: Expecting value: line 1 column 1 (char 0)

このエラーは通常、API が有効な JSON を返さなかったことを示しています。HTML のエラーページや予期しない内容が返されている可能性があります。

### Q2: HTTP/1.1 504 Gateway Timeout?

API エンドポイントの安定性とネットワーク接続を確認してください。

### Q3: Embedding プロバイダーを切り替えるには?

GUI の Embedding 設定欄に新しいプロバイダーの情報を入力してください。

---

その他の質問や機能リクエストがあれば、プロジェクトリポジトリの Issue で報告してください。
