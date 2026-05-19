# 📖 Outil de Génération Automatique de Romans

[中文文档](./README_zh-CN.md) | [English](./README%20%281%29.md) | Français

> ~~Actuellement, je n'ai pas beaucoup d'énergie pour maintenir ce projet. Le projet ne génère aucun revenu et, avec l'approche de la remise des diplômes, j'ai beaucoup d'autres priorités. Si le temps le permet à l'avenir, je pourrais envisager une refonte avec des technologies plus récentes. — 24/09/2025~~
>
>- ~~**(09/03/2026) :** Ce projet sera bientôt refondu, avec des implémentations modernes et de nouveaux concepts créatifs.~~
>
> **Mise à jour (25/03/2026) :** La version refondue a terminé son développement initial (seul le cadre principal est terminé, les fonctionnalités ne sont pas encore disponibles) et sera téléchargée sur la branche dev d'ici une semaine. Le développement ultérieur sera également synchronisé sur cette branche.

<div align="center">
  
✨ **Fonctionnalités Principales** ✨

| Module                | Capacités Clés                          |
|-----------------------|-----------------------------------------|
| 🎨 Atelier de Configuration | Création d'univers / Conception de personnages / Plan d'intrigue |
| 📖 Génération Intelligente de Chapitres | Génération multi-étapes pour assurer la cohérence de l'intrigue |
| 🧠 Système de Suivi d'État | Trajectoire de développement des personnages / Gestion des présages |
| 🔍 Moteur de Recherche Sémantique | Cohérence du contexte à long terme basée sur les vecteurs |
| 📚 Intégration de Base de Connaissances | Prise en charge des références de documents locaux |
| ✅ Relecture Automatique | Détecte les contradictions d'intrigue et les conflits logiques |
| 🖥 Plan de Travail Visuel | Interface graphique complète pour la configuration / génération / relecture |

</div>

> Un générateur de romans polyvalent basé sur de grands modèles de langage. Il vous aide à créer efficacement des histoires longues avec des paramètres cohérents et une logique rigoureuse.

---

## 📑 Table des Matières
1. [Préparation de l'Environnement](#-préparation-de-lenvironnement)  
2. [Structure du Projet](#-structure-du-projet)  
3. [Guide de Configuration](#️-guide-de-configuration)  
4. [Instructions d'Exécution](#-instructions-dexécution)  
5. [Guide de l'Utilisateur](#-guide-de-lutilisateur)  
6. [FAQ](#-faq)  

---

## 🛠 Préparation de l'Environnement
Assurez-vous que l'environnement répond aux exigences suivantes :
- **Python 3.9+** (3.10–3.12 recommandé)
- Gestionnaire de paquets **pip**
- Clés API valides :
   - Services cloud : OpenAI / DeepSeek, etc.
   - Services locaux : Ollama ou autres interfaces compatibles OpenAI

---

## 📥 Installation
1. **Télécharger le projet**  
    - Téléchargez le ZIP du projet depuis [GitHub](https://github.com) ou clonez le dépôt :
       ```bash
       git clone https://github.com/YILING0013/AI_NovelGenerator
       ```


2. **Installer les outils de compilation (facultatif)**  
    - Si certains paquets ne s'installent pas, visitez [Visual Studio Build Tools](https://visualstudio.microsoft.com/zh-hans/visual-cpp-build-tools/) pour télécharger et installer les outils de compilation C++ requis par certains modules.
    - Par défaut, l'installateur n'inclut que MSBuild ; assurez-vous de sélectionner **Développement Desktop C++** dans la liste des charges de travail.

3. **Installer les dépendances et exécuter**  
    - Ouvrez un terminal et placez-vous dans le répertoire du projet :
       ```bash
       cd AI_NovelGenerator
       ```
    - (Facultatif) Créer et activer un environnement virtuel :
       ```bash
       python -m venv .venv
       # si cela ne fonctionne pas, essayez :
       # python3 -m venv .venv
       ```
       ```
       # Sous Windows :
       .venv/Scripts/activate
       ```
       ```
       # Sous Linux/Mac :
       source .venv/bin/activate
       ```
    - Installer les dépendances du projet :
       ```bash
       pip install -r requirements.txt
       ```
    - Après l'installation, exécutez le programme principal :
       ```bash
       python main.py
       ```

Si certaines dépendances manquent encore, exécutez manuellement :
```bash
pip install <nom-du-paquet>
```
pour les installer.


## 🗂 Structure du Projet
```
novel-generator/
├── main.py                      # Fichier d'entrée, exécute l'interface graphique
├── consistency_checker.py       # Vérifications de cohérence pour éviter les conflits d'intrigue
|—— chapter_directory_parser.py  # Analyse du répertoire
|—— embedding_adapters.py        # Wrappers d'interface d'embedding
|—— llm_adapters.py              # Wrappers d'interface LLM
├── prompt_definitions.py        # Modèles de prompts IA
├── utils.py                     # Fonctions utilitaires et opérations sur fichiers
├── config_manager.py            # Gestionnaire de configuration (clés API, URL de base)
├── config.json                  # Configuration utilisateur (facultatif)
├── novel_generator/             # Logique principale de génération de chapitres
├── ui/                          # Interface graphique
└── vectorstore/                 # (Facultatif) Stockage de la base de données vectorielle locale
```

---

## ⚙️ Guide de Configuration
### 📌 Configuration de base (`config.json`)
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
   "topic": "Le protagoniste de Star Rail voyage sur le continent de Teyvat de Genshin Impact, le sauve et développe des relations complexes avec ses personnages.",
   "genre": "Fantasy",
   "num_chapters": 120,
   "word_number": 4000,
   "filepath": "D:/AI_NovelGenerator/filepath"
}
```

### 🔧 Explication
1. **Configuration du modèle de génération**
   - `api_key` : Clé API pour le service LLM
   - `base_url` : Point de terminaison API (pour les services locaux, utilisez l'adresse Ollama)
   - `interface_format` : Mode d'interface
   - `model_name` : Modèle de génération principal (par exemple, gpt-4, claude-3)
   - `temperature` : Paramètre de créativité (0–1, plus élevé = plus créatif)
   - `max_tokens` : Longueur maximale de la réponse du modèle

2. **Configuration du modèle d'embedding**
   - `embedding_model_name` : Nom du modèle d'embedding (par exemple, nomic-embed-text d'Ollama)
   - `embedding_url` : Point de terminaison du service
   - `embedding_retrieval_k` : Nombre de plus proches voisins à récupérer

3. **Paramètres du roman**
   - `topic` : Thème principal de l'histoire
   - `genre` : Genre
   - `num_chapters` : Nombre total de chapitres
   - `word_number` : Nombre de mots cible par chapitre
   - `filepath` : Chemin pour sauvegarder les fichiers générés

---

## 🚀 Instructions d'Exécution
### Méthode 1 — Exécuter avec Python
```bash
python main.py
```
Cela lance l'interface graphique pour une utilisation interactive.

### Méthode 2 — Créer un exécutable
Si vous souhaitez exécuter l'outil sur des machines sans Python, empaquetez-le avec **PyInstaller** :
```bash
pip install pyinstaller
pyinstaller main.spec
```
Après l'empaquetage, un exécutable (par exemple, `main.exe` sous Windows) apparaîtra dans le dossier `dist/`.

---

## 📘 Guide de l'Utilisateur
1. **Après le lancement de l'application, remplissez les paramètres de base :**  
   - **Clé API & URL de base** (par exemple, `https://api.openai.com/v1`)  
   - **Nom du modèle** (par exemple, `gpt-3.5-turbo`, `gpt-4o`)  
   - **Température** (0–1, contrôle la variance créative)  
   - **Sujet** (par exemple, « Soulèvement de l'IA dans un monde post-apocalyptique »)  
   - **Genre** (par exemple, « Science-fiction » / « Fantasy » / « Fantasy urbaine »)  
   - **Nombre de chapitres** et **mots par chapitre** (par exemple, 10 chapitres × ~3000 mots)  
   - **Chemin d'enregistrement** (créez un nouveau dossier de sortie pour les résultats)

2. **Cliquez sur « Étape 1. Générer les Paramètres »**  
   - Le système générera, en fonction du sujet/genre/nombre de chapitres :  
     - `Novel_setting.txt` : Création d'univers, personnages, points déclencheurs et présages.  
   - Vous pouvez consulter ou modifier ces paramètres après la génération.

3. **Cliquez sur « Étape 2. Générer le Répertoire »**  
   - Le système utilisera `Novel_setting.txt` pour produire :  
     - `Novel_directory.txt` : Titres de chapitres et courts prompts.  
   - Vous pouvez réviser et modifier les titres et descriptions des chapitres.

4. **Cliquez sur « Étape 3. Générer le Brouillon du Chapitre »**  
   - Avant de générer un chapitre, vous pouvez :  
     - Définir le numéro du chapitre (par exemple, `1`)  
     - Fournir des directives spécifiques au chapitre dans la case « Directives de ce chapitre »  
   - Lors de la génération d'un chapitre, le système :  
     - Lira les paramètres précédents, `Novel_directory.txt` et les chapitres finalisés  
     - Utilisera la récupération vectorielle pour rappeler le contexte pertinent et assurer la cohérence  
     - Produira un plan (`outline_X.txt`) et le texte du chapitre (`chapter_X.txt`)  
   - Vous pouvez visualiser et modifier le brouillon dans le panneau d'édition.

5. **Cliquez sur « Étape 4. Finaliser le Chapitre Actuel »**  
   - Le système :  
     - Mettra à jour le résumé global (`global_summary.txt`)  
     - Mettra à jour les états des personnages (`character_state.txt`)  
     - Mettra à jour le magasin de vecteurs (afin que les futurs chapitres puissent utiliser les dernières informations)  
     - Mettra à jour les points d'intrigue majeurs (par exemple, `plot_arcs.txt`)  
   - Après finalisation, vous verrez le texte finalisé dans `chapter_X.txt`.

6. **Vérification de cohérence (facultatif)**  
   - Cliquez sur le bouton « [Facultatif] Relecture de Cohérence » pour scanner le dernier chapitre à la recherche de conflits (logique des personnages, contradictions d'intrigue, etc.).  
   - Si des conflits sont détectés, des messages détaillés apparaîtront dans la zone de journal.

7. **Répétez les étapes 4 à 6** jusqu'à ce que tous les chapitres soient générés et finalisés.

> Conseils de récupération vectorielle :
> 1. Définissez explicitement l'interface d'embedding et le nom du modèle.
> 2. Pour les embeddings locaux Ollama, démarrez d'abord le service Ollama :
>    ```bash
>    ollama serve  # Démarrer le service
>    ollama pull nomic-embed-text  # Télécharger/activer le modèle
>    ```
> 3. Videz le répertoire `vectorstore` après avoir changé de modèle d'embedding.
> 4. Pour les embeddings cloud, assurez-vous que les permissions API sont activées.

---

## ❓ FAQ
### Q1 : Expecting value: line 1 column 1 (char 0)

Cette erreur indique généralement que l'API n'a pas renvoyé de JSON valide — parfois une page d'erreur HTML ou un autre contenu inattendu a été renvoyé.

### Q2 : HTTP/1.1 504 Gateway Timeout ?

Vérifiez la stabilité du point de terminaison API et la connectivité réseau.

### Q3 : Comment changer de fournisseur d'Embedding ?

Saisissez les paramètres du nouveau fournisseur dans les champs de l'interface graphique pour la configuration des embeddings.

---

Si vous avez d'autres questions ou demandes de fonctionnalités, veuillez ouvrir un ticket sur le dépôt du projet.
