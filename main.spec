# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, get_package_paths

datas = []
binaries = []
hiddenimports = ['typing_extensions', 
                 'langchain-openai',
                 'langgraph', 
                 'openai', 
                 'nltk',
                 'sentence_transformers',
                 'scikit-learn',
                 'langchain-community',
                 'pydantic',
                 'pydantic.deprecated.decorator',
                 'tiktoken_ext.openai_public',
                 'tiktoken_ext'
                 ]

tmp_ret = collect_all('chromadb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# customtkinter_dir = r'c:/Users/xieli/Desktop/AI_NovelGenerator/.venv/Lib/site-packages/customtkinter'
# datas.append((customtkinter_dir, 'customtkinter'))

package_dir = get_package_paths('customtkinter')[1]
customtkinter_data = (package_dir, 'customtkinter')
datas.append(customtkinter_data)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI_NovelGenerator_V1.3.0',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico']
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI_NovelGenerator_V1.3.0'
)
