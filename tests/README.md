# Tests Guide

当前包含的测试文件：

- [tests/test_volumes.py](tests/test_volumes.py)：卷相关 API 集成测试
- [tests/test_factions.py](tests/test_factions.py)：阵营相关 API 集成测试
- [tests/test_llm.py](tests/test_llm.py)：LLM 集成测试，仅默认跑 OpenAI 兼容接口
- [tests/conftest.py](tests/conftest.py)：pytest 公共 fixture

## 1. 前置条件

请在项目根目录执行测试。

建议先激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果本地还没有安装依赖：

```powershell
pip install -r requirements.txt
```

## 2. API 测试说明

[tests/test_volumes.py](tests/test_volumes.py) 和 [tests/test_factions.py](tests/test_factions.py) 使用 FastAPI TestClient 直接拉起应用进行测试。

这意味着：

- 不需要手动执行 `python main.py`
- 但需要 MongoDB 配置可用，并且数据库可连接
- 测试会自动创建临时小说数据，并在结束后尝试清理

### 运行 volumes 测试

```powershell
python -m pytest tests/test_volumes.py -q
```

### 运行 factions 测试

```powershell
python -m pytest tests/test_factions.py -q
```

### 一次运行两个 API 测试文件

```powershell
python -m pytest tests/test_volumes.py tests/test_factions.py -q
```

### 运行全部 API 测试

```powershell
python -m pytest tests -q -k "not llm"
```

## 3. LLM 测试说明

[tests/test_llm.py](tests/test_llm.py) 会真实调用外部模型接口。

这意味着：

- 需要可用的网络连接
- 需要设置环境变量
- 会消耗模型额度或产生费用

### PowerShell 设置环境变量

下面是 OpenAI 兼容接口的示例写法：

```powershell
$env:OPENAI_BASE_URL='https://api.chatanywhere.tech/v1'
$env:OPENAI_API_KEY='<your_api_key>'
$env:OPENAI_MODEL='gpt-5.4-mini'
```

### 运行 LLM 测试

```powershell
python -m pytest tests/test_llm.py -q
```

如果没有设置 `OPENAI_BASE_URL` 或 `OPENAI_API_KEY`，该测试文件会被自动跳过。

## 4. 运行全部测试

如果你已经完成 MongoDB 配置，并且也设置了 LLM 环境变量，可以直接运行：

```powershell
python -m pytest tests -q
```

## 5. 常用调试命令

### 显示更详细输出

```powershell
python -m pytest tests/test_factions.py -v
```

### 只运行名字里包含某个关键字的测试

```powershell
python -m pytest tests/test_factions.py -k create -q
```

### 遇到第一个失败就停止

```powershell
python -m pytest tests -x
```

## 6. 注意事项

- API 测试依赖当前应用配置中的 MongoDB 连接信息
- LLM 测试优先使用环境变量，不依赖 `application/config/config.yaml` 中的 provider 配置
- 小说硬删除现在会级联删除 factions 数据，避免 API 测试后留下阵营残留
- 如果测试失败，优先先看数据库连接、环境变量和外部接口连通性
