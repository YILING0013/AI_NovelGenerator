# 本地开发与快速运行（针对 Python 3.14）

此说明针对在 Windows 上使用 Python 3.14 创建的虚拟环境（`.venv`）运行本仓库的本地开发/测试流程。

快速步骤：

1. 创建并激活虚拟环境（若尚未创建）

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
```

2. 安装开发依赖（使用 `dev-requirements.txt`，这些版本已在本地验证可用于 cp314）

```powershell
python -m pip install -r dev-requirements.txt
```

3. 运行离线测试（使用 DummyAdapter 验证生成与写入流程）

```powershell
python tools_run_draft_test.py
```

4. 运行 GUI（如果已配置并希望启动）

```powershell
python main.py
```

注意：
- `dev-requirements.txt` 保存了本地用于调试/测试的 pins，目的是在 Python 3.14 环境中快速复现可运行状态。上游 `requirements.txt` 仍保留为主依赖清单。
- `test_output/` 已加入 `.gitignore`，测试产生的输出不会被提交。

如需我把 `dev` 分支推送到远端或另外制作一个可发布的 zip 打包，请告诉我。
