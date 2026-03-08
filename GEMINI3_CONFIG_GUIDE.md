# Gemini 3 Pro Preview 配置指南

## 配置概述

已成功为AI小说生成工具添加了新的LLM模型配置：

- **配置名称**: `Gemini 3 Pro Preview`
- **API Key**: `sk-XcmpQPk3Bj3mu2UISYWHygK8q4FnaGr2DaSPzpN2RwROENR0`
- **Base URL**: `https://nvewvip.preview.tencent-zeabur.cn/v1`
- **模型名称**: `gemini-3-pro-preview`
- **接口格式**: `OpenAI`

## 配置详情

### 基本信息
- **接口类型**: OpenAI兼容接口
- **最大Token**: 32768
- **Temperature**: 0.7
- **超时时间**: 600秒

### 默认任务配置
新配置已设置为以下任务的默认LLM：
- ✅ **生成草稿所用大模型** (`prompt_draft_llm`)
- ✅ **生成大目录所用大模型** (`chapter_outline_llm`)
- ✅ **生成架构所用大模型** (`architecture_llm`)
- ✅ **定稿章节所用大模型** (`final_chapter_llm`)
- ✅ **一致性审校所用大模型** (`consistency_review_llm`)

## 使用方法

### 1. 启动应用程序
```bash
python main.py
```

### 2. 配置界面访问
1. 启动应用程序后，点击 **"LLM Model settings"** 标签页
2. 在配置选择下拉菜单中找到并选择 **"Gemini 3 Pro Preview"**
3. 配置信息会自动加载显示

### 3. 配置验证
1. 点击 **"测试配置"** 按钮验证连接
2. 确认API连接正常后，配置即可使用

### 4. 任务配置选择
在 **"Config choose"** 标签页中，可以为不同的小说生成任务选择LLM：
- 所有任务已默认设置为使用 `Gemini 3 Pro Preview`
- 如需切换，可在相应下拉菜单中选择其他配置

## 配置文件位置

- **示例配置**: `config.example.json`
- **实际配置**: `config.json`
- **已自动更新**: 两个文件都已添加新配置

## 配置验证

应用程序已通过以下测试：
- ✅ 配置文件JSON格式验证
- ✅ 新配置添加成功验证
- ✅ 默认设置应用验证
- ✅ UI界面加载测试
- ✅ 配置选择功能测试

## 注意事项

1. **API Key安全**: API密钥已包含在配置中，请妥善保管
2. **网络连接**: 确保可以访问 `https://nvewvip.preview.tencent-zeabur.cn`
3. **接口兼容**: 该配置使用OpenAI兼容接口格式
4. **权限要求**: 使用前请确认API密钥具有足够的权限

## 技术支持

如遇到问题，请检查：
1. 网络连接是否正常
2. API密钥是否有效
3. 配置文件是否完整
4. 应用程序日志输出

---
*配置添加时间: 2025-11-22*
*配置状态: ✅ 就绪*