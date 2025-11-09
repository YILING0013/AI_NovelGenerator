# 部署文档

本文档提供AI小说生成工具的完整部署指南，包括开发环境搭建、生产环境部署、打包分发和性能优化。

## 📋 目录

- [系统要求](#系统要求)
- [开发环境搭建](#开发环境搭建)
- [生产环境部署](#生产环境部署)
- [容器化部署](#容器化部署)
- [应用打包](#应用打包)
- [配置管理](#配置管理)
- [性能优化](#性能优化)
- [监控与日志](#监控与日志)
- [安全配置](#安全配置)
- [故障排除](#故障排除)

## 💻 系统要求

### 最低配置要求

#### 硬件要求
```
CPU: 双核 2.0GHz 或更高
内存: 8GB RAM (推荐 16GB+)
存储: 10GB 可用空间 (推荐 50GB+)
网络: 稳定的互联网连接
```

#### 软件要求
```
操作系统:
- Windows 10/11 (推荐)
- Ubuntu 18.04+ / CentOS 7+
- macOS 10.15+

运行时环境:
- Python 3.8+ (推荐 3.9-3.11)
- pip 21.0+
- Git 2.25+

可选依赖:
- Docker 20.10+ (容器部署)
- Node.js 16+ (前端开发)
- Redis 6.0+ (缓存服务)
```

### 推荐配置

#### 开发环境
```
CPU: 四核 3.0GHz+
内存: 16GB+ RAM
存储: SSD 50GB+
GPU: NVIDIA GTX 1060+ (可选，用于本地模型)
```

#### 生产环境
```
CPU: 八核 3.0GHz+
内存: 32GB+ RAM
存储: SSD 100GB+
网络: 1Gbps 带宽
负载均衡: Nginx/HAProxy
数据库: PostgreSQL 13+ (可选)
```

## 🛠️ 开发环境搭建

### 1. 环境准备

#### 安装Python环境
```bash
# Windows
# 下载Python安装包: https://python.org/downloads/
# 安装时勾选 "Add Python to PATH"

# Ubuntu/Debian
sudo apt update
sudo apt install python3.9 python3.9-pip python3.9-venv

# CentOS/RHEL
sudo yum install python39 python39-pip

# macOS
brew install python@3.9
```

#### 安装Git
```bash
# Windows
# 下载Git for Windows: https://git-scm.com/download/win

# Ubuntu/Debian
sudo apt install git

# CentOS/RHEL
sudo yum install git

# macOS
brew install git
```

### 2. 项目设置

#### 克隆项目
```bash
git clone https://github.com/your-username/AI_NovelGenerator.git
cd AI_NovelGenerator
```

#### 创建虚拟环境
```bash
# 创建虚拟环境
python -m venv venv

# Windows激活
venv\Scripts\activate

# Linux/macOS激活
source venv/bin/activate
```

#### 安装依赖
```bash
# 升级pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt  # 如果存在
```

### 3. 配置设置

#### 创建配置文件
```bash
# 复制配置模板
cp config.example.json config.json

# 创建环境变量文件
touch .env
```

#### 配置环境变量
```bash
# .env 文件内容
# API密钥 (不建议直接写入config.json)
OPENAI_API_KEY=your_openai_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
ZHIPUAI_API_KEY=your_zhipuai_api_key_here

# 数据库配置 (可选)
DATABASE_URL=postgresql://user:password@localhost:5432/ai_novel_generator

# Redis配置 (可选)
REDIS_URL=redis://localhost:6379/0

# 日志级别
LOG_LEVEL=INFO

# 开发模式
DEBUG=True
```

#### 编辑配置文件
```json
// config.json
{
  "development": {
    "last_interface_format": "OpenAI",
    "filepath": "./dev_data/",
    "vectorstore_path": "./dev_vectorstore/",
    "log_level": "DEBUG"
  },
  "llm_configs": {
    "OpenAI": {
      "model_name": "gpt-3.5-turbo",
      "temperature": 0.7,
      "max_tokens": 4000,
      "timeout": 300
    }
  }
}
```

### 4. 验证环境

#### 运行测试
```bash
# 运行基础测试
python test_basic_functionality.py

# 运行单元测试 (如果存在)
python -m pytest tests/ -v

# 测试API连接
python test_api_connection.py
```

#### 启动应用
```bash
# 开发模式启动
python main.py

# 或者使用调试模式
python -m debugpy --listen 5678 --wait-for-client main.py
```

## 🚀 生产环境部署

### 1. 服务器准备

#### 系统更新
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

#### 安装运行时依赖
```bash
# Ubuntu/Debian
sudo apt install -y python3.9 python3.9-pip python3.9-venv nginx supervisor

# CentOS/RHEL
sudo yum install -y python39 python39-pip nginx supervisor
```

#### 创建应用用户
```bash
# 创建专用用户
sudo useradd -m -s /bin/bash ai-novel-app
sudo usermod -aG sudo ai-novel-app

# 切换到应用用户
sudo su - ai-novel-app
```

### 2. 应用部署

#### 部署应用代码
```bash
# 克隆代码到生产目录
cd /opt
sudo git clone https://github.com/your-username/AI_NovelGenerator.git
sudo chown -R ai-novel-app:ai-novel-app AI_NovelGenerator
cd AI_NovelGenerator

# 创建生产环境配置
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 复制并编辑生产配置
cp config.example.json config.json
cp .env.example .env
```

#### 配置生产环境
```json
// config.json (生产环境)
{
  "production": {
    "last_interface_format": "OpenAI",
    "filepath": "/opt/ai-novel-data/",
    "vectorstore_path": "/opt/ai-novel-vectorstore/",
    "log_level": "WARNING",
    "auto_backup": true,
    "backup_interval": 3600
  }
}
```

```bash
# .env (生产环境)
DEBUG=False
LOG_LEVEL=WARNING
DATABASE_URL=postgresql://prod_user:secure_password@localhost:5432/ai_novel_prod
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your_very_secure_secret_key_here
```

### 3. 服务配置

#### 创建systemd服务
```bash
sudo tee /etc/systemd/system/ai-novel-generator.service > /dev/null <<EOF
[Unit]
Description=AI Novel Generator
After=network.target

[Service]
Type=simple
User=ai-novel-app
WorkingDirectory=/opt/AI_NovelGenerator
Environment=PATH=/opt/AI_NovelGenerator/venv/bin
ExecStart=/opt/AI_NovelGenerator/venv/bin/python main.py
Restart=always
RestartSec=10

# 安全设置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/ai-novel-data /opt/ai-novel-vectorstore

[Install]
WantedBy=multi-user.target
EOF
```

#### 启动和启用服务
```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start ai-novel-generator

# 设置开机自启
sudo systemctl enable ai-novel-generator

# 检查服务状态
sudo systemctl status ai-novel-generator
```

#### 配置Supervisor (可选)
```bash
sudo tee /etc/supervisor/conf.d/ai-novel-generator.conf > /dev/null <<EOF
[program:ai-novel-generator]
command=/opt/AI_NovelGenerator/venv/bin/python main.py
directory=/opt/AI_NovelGenerator
user=ai-novel-app
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/ai-novel-generator.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
EOF

# 更新Supervisor配置
sudo supervisorctl update
sudo supervisorctl start ai-novel-generator
```

### 4. 反向代理配置

#### Nginx配置 (Web界面)
```bash
sudo tee /etc/nginx/sites-available/ai-novel-generator > /dev/null <<EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # 静态文件服务
    location /static/ {
        alias /opt/AI_NovelGenerator/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 安全头部
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
EOF

# 启用站点
sudo ln -s /etc/nginx/sites-available/ai-novel-generator /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### SSL证书配置 (HTTPS)
```bash
# 安装Certbot
sudo apt install certbot python3-certbot-nginx

# 获取SSL证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo crontab -e
# 添加: 0 12 * * * /usr/bin/certbot renew --quiet
```

## 🐳 容器化部署

### 1. Docker部署

#### 创建Dockerfile
```dockerfile
# Dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "main.py"]
```

#### 构建镜像
```bash
# 构建镜像
docker build -t ai-novel-generator:latest .

# 或者使用多阶段构建优化大小
docker build -f Dockerfile.prod -t ai-novel-generator:prod .
```

#### 运行容器
```bash
# 基本运行
docker run -d \
  --name ai-novel-app \
  -p 8080:8080 \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/data:/app/data \
  ai-novel-generator:latest

# 生产环境运行 (包含环境变量)
docker run -d \
  --name ai-novel-app-prod \
  -p 8080:8080 \
  --restart unless-stopped \
  -e OPENAI_API_KEY="\$OPENAI_API_KEY" \
  -e LOG_LEVEL=WARNING \
  -v /opt/ai-novel-data:/app/data \
  -v /opt/ai-novel-config:/app/config \
  ai-novel-generator:prod
```

### 2. Docker Compose部署

#### 创建docker-compose.yml
```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - LOG_LEVEL=INFO
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - app_data:/app/data
      - app_config:/app/config
    depends_on:
      - redis
      - postgres
    restart: unless-stopped

  redis:
    image: redis:6-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  postgres:
    image: postgres:13-alpine
    environment:
      - POSTGRES_DB=ai_novel_generator
      - POSTGRES_USER=app_user
      - POSTGRES_PASSWORD=secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - app
    restart: unless-stopped

volumes:
  app_data:
  app_config:
  redis_data:
  postgres_data:
```

#### 创建环境文件
```bash
# .env
OPENAI_API_KEY=your_openai_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
COMPOSE_PROJECT_NAME=ai-novel-generator
```

#### 启动服务
```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down

# 完全清理
docker-compose down -v --remove-orphans
```

### 3. Kubernetes部署

#### 创建Kubernetes清单
```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ai-novel-generator

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: ai-novel-generator
data:
  config.json: |
    {
      "production": {
        "filepath": "/data/",
        "log_level": "INFO"
      }
    }

---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets
  namespace: ai-novel-generator
type: Opaque
data:
  OPENAI_API_KEY: <base64-encoded-key>
  DEEPSEEK_API_KEY: <base64-encoded-key>

---
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-novel-app
  namespace: ai-novel-generator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-novel-app
  template:
    metadata:
      labels:
        app: ai-novel-app
    spec:
      containers:
      - name: app
        image: ai-novel-generator:latest
        ports:
        - containerPort: 8080
        envFrom:
        - secretRef:
            name: api-secrets
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: data
          mountPath: /data
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: config
        configMap:
          name: app-config
      - name: data
        persistentVolumeClaim:
          claimName: app-data-pvc

---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: ai-novel-service
  namespace: ai-novel-generator
spec:
  selector:
    app: ai-novel-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: ClusterIP

---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-novel-ingress
  namespace: ai-novel-generator
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - your-domain.com
    secretName: ai-novel-tls
  rules:
  - host: your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ai-novel-service
            port:
              number: 80
```

#### 部署到Kubernetes
```bash
# 应用所有清单
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -n ai-novel-generator
kubectl get services -n ai-novel-generator
kubectl get ingress -n ai-novel-generator

# 查看日志
kubectl logs -f deployment/ai-novel-app -n ai-novel-generator

# 更新部署
kubectl set image deployment/ai-novel-app app=ai-novel-generator:v2 -n ai-novel-generator
```

## 📦 应用打包

### 1. PyInstaller打包

#### 安装PyInstaller
```bash
pip install pyinstaller
```

#### 创建规格文件
```python
# main.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui', 'ui'),
        ('novel_generator', 'novel_generator'),
        ('config.example.json', '.'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'tkinter',
        'PIL',
        'chromadb',
        'openai',
        'langchain',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI_NovelGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'  # 应用图标
)
```

#### 构建可执行文件
```bash
# Windows
pyinstaller main.spec

# Linux/macOS
python -m PyInstaller main.spec

# 优化构建 (更小的文件)
pyinstaller --onefile --windowed --clean main.py
```

#### 创建安装程序
```bash
# Windows (使用NSIS)
# 1. 下载NSIS: https://nsis.sourceforge.io/
# 2. 创建安装脚本 installer.nsi
# 3. 编译安装包

# macOS (使用create-dmg)
brew install create-dmg
create-dmg "AI_NovelGenerator.app"

# Linux (使用AppImage)
wget https://github.com/probonopd/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
chmod +x linuxdeploy-x86_64.AppImage
./linuxdeploy-x86_64.AppImage --appdir AppDir --executable dist/AI_NovelGenerator --create-desktop-file --output appimage
```

### 2. 跨平台构建

#### GitHub Actions配置
```yaml
# .github/workflows/build.yml
name: Build and Release

on:
  push:
    tags:
      - 'v*'
  pull_request:
    branches: [ main ]

jobs:
  build:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: [3.9]

    runs-on: ${{ matrix.os }}

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pyinstaller

    - name: Build executable
      run: |
        pyinstaller --onefile --windowed main.py

    - name: Upload artifacts
      uses: actions/upload-artifact@v3
      with:
        name: ai-novel-generator-${{ matrix.os }}
        path: dist/
```

## ⚙️ 配置管理

### 1. 环境配置

#### 开发环境配置
```json
// config.development.json
{
  "environment": "development",
  "debug": true,
  "log_level": "DEBUG",
  "filepath": "./dev_data/",
  "vectorstore_path": "./dev_vectorstore/",
  "auto_save_interval": 30,
  "max_concurrent_generations": 2,
  "api_timeout": 300,
  "retry_attempts": 3
}
```

#### 测试环境配置
```json
// config.testing.json
{
  "environment": "testing",
  "debug": true,
  "log_level": "INFO",
  "filepath": "./test_data/",
  "vectorstore_path": "./test_vectorstore/",
  "auto_save_interval": 60,
  "max_concurrent_generations": 3,
  "api_timeout": 180,
  "retry_attempts": 2,
  "mock_api_calls": true
}
```

#### 生产环境配置
```json
// config.production.json
{
  "environment": "production",
  "debug": false,
  "log_level": "WARNING",
  "filepath": "/opt/ai-novel-data/",
  "vectorstore_path": "/opt/ai-novel-vectorstore/",
  "auto_save_interval": 300,
  "max_concurrent_generations": 5,
  "api_timeout": 600,
  "retry_attempts": 5,
  "enable_monitoring": true,
  "backup_enabled": true,
  "security_mode": "strict"
}
```

### 2. 配置管理最佳实践

#### 配置加载策略
```python
# config_loader.py
import os
import json
from typing import Dict, Any

class ConfigLoader:
    def __init__(self):
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_file = f"config.{self.environment}.json"

        # 默认配置
        config = self._load_default_config()

        # 环境特定配置
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                env_config = json.load(f)
                config.update(env_config)

        # 环境变量覆盖
        config.update(self._load_env_config())

        return config

    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认配置"""
        with open('config.default.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_env_config(self) -> Dict[str, Any]:
        """从环境变量加载配置"""
        env_config = {}

        # API密钥
        if 'OPENAI_API_KEY' in os.environ:
            env_config['openai_api_key'] = os.environ['OPENAI_API_KEY']

        # 数据库配置
        if 'DATABASE_URL' in os.environ:
            env_config['database_url'] = os.environ['DATABASE_URL']

        return env_config
```

#### 配置验证
```python
# config_validator.py
from typing import Dict, Any, List

class ConfigValidator:
    def __init__(self):
        self.required_fields = {
            'development': ['last_interface_format'],
            'production': ['filepath', 'vectorstore_path']
        }

    def validate(self, config: Dict[str, Any], environment: str) -> List[str]:
        """验证配置"""
        errors = []

        # 检查必需字段
        if environment in self.required_fields:
            for field in self.required_fields[environment]:
                if field not in config:
                    errors.append(f"Missing required field: {field}")

        # 验证路径存在
        if 'filepath' in config:
            path = config['filepath']
            if not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create directory {path}: {e}")

        # 验证数值范围
        if 'max_concurrent_generations' in config:
            max_concurrent = config['max_concurrent_generations']
            if not isinstance(max_concurrent, int) or max_concurrent < 1:
                errors.append("max_concurrent_generations must be a positive integer")

        return errors
```

## 🚀 性能优化

### 1. 应用层优化

#### 异步处理优化
```python
# async_optimization.py
import asyncio
import aiohttp
from typing import List, Any

class OptimizedGenerator:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_batch(
        self,
        items: List[Any],
        processor_func: callable
    ) -> List[Any]:
        """批量处理任务"""
        tasks = []

        for item in items:
            task = self._process_with_semaphore(item, processor_func)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤异常结果
        valid_results = [
            result for result in results
            if not isinstance(result, Exception)
        ]

        return valid_results

    async def _process_with_semaphore(self, item: Any, processor_func: callable):
        """带信号量限制的处理"""
        async with self.semaphore:
            return await processor_func(item)
```

#### 缓存机制
```python
# cache_manager.py
import time
import hashlib
from functools import wraps
from typing import Any, Dict, Optional

class CacheManager:
    def __init__(self, ttl: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl

    def _generate_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存键"""
        key_data = f"{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            data = self.cache[key]
            if time.time() - data['timestamp'] < self.ttl:
                return data['value']
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        """设置缓存值"""
        self.cache[key] = {
            'value': value,
            'timestamp': time.time()
        }

def cached(ttl: int = 3600):
    """缓存装饰器"""
    cache = CacheManager(ttl)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = cache._generate_key(func.__name__, args, kwargs)

            # 尝试从缓存获取
            cached_result = cache.get(key)
            if cached_result is not None:
                return cached_result

            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            cache.set(key, result)

            return result
        return wrapper
    return decorator
```

### 2. 系统层优化

#### 数据库优化
```python
# database_optimization.py
import asyncio
import asyncpg
from typing import List, Dict, Any

class DatabaseOptimizer:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool = None

    async def initialize(self):
        """初始化连接池"""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20,
            command_timeout=60
        )

    async def batch_insert(
        self,
        table: str,
        data: List[Dict[str, Any]],
        batch_size: int = 1000
    ):
        """批量插入数据"""
        if not self.pool:
            await self.initialize()

        # 分批处理
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]

            async with self.pool.acquire() as conn:
                await conn.executemany(
                    f"""
                    INSERT INTO {table} ({','.join(batch[0].keys())})
                    VALUES ({','.join([f'${i+1}' for i in range(len(batch[0]))])})
                    """,
                    [tuple(item.values()) for item in batch]
                )

    async def create_indexes(self):
        """创建性能优化索引"""
        async with self.pool.acquire() as conn:
            # 章节内容索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapters_created_at
                ON chapters(created_at)
            """)

            # 向量搜索索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_chapter_id
                ON embeddings(chapter_id)
            """)
```

#### 内存优化
```python
# memory_optimizer.py
import gc
import psutil
from typing import Any

class MemoryOptimizer:
    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold

    def get_memory_usage(self) -> float:
        """获取当前内存使用率"""
        return psutil.virtual_memory().percent / 100

    def check_memory_pressure(self) -> bool:
        """检查内存压力"""
        return self.get_memory_usage() > self.threshold

    def force_garbage_collection(self):
        """强制垃圾回收"""
        gc.collect()

    def optimize_batch_size(self, base_batch_size: int) -> int:
        """根据内存使用情况优化批量大小"""
        memory_usage = self.get_memory_usage()

        if memory_usage > 0.9:
            return max(1, base_batch_size // 4)
        elif memory_usage > 0.8:
            return max(1, base_batch_size // 2)
        elif memory_usage > 0.6:
            return max(1, base_batch_size * 3 // 4)
        else:
            return base_batch_size

    def cleanup_large_objects(self, obj_list: list):
        """清理大对象列表"""
        # 清空列表
        obj_list.clear()

        # 强制垃圾回收
        self.force_garbage_collection()
```

### 3. 监控和调优

#### 性能监控
```python
# performance_monitor.py
import time
import asyncio
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class PerformanceMetrics:
    cpu_usage: float
    memory_usage: float
    disk_io: float
    network_io: float
    api_response_time: float
    generation_rate: float
    error_rate: float

class PerformanceMonitor:
    def __init__(self):
        self.metrics_history = []
        self.alerts = []

    async def collect_metrics(self) -> PerformanceMetrics:
        """收集性能指标"""
        import psutil

        # 系统指标
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        disk_io = psutil.disk_io_counters().read_bytes + psutil.disk_io_counters().write_bytes
        network_io = psutil.net_io_counters().bytes_sent + psutil.net_io_counters().bytes_recv

        # 应用指标
        api_response_time = await self._measure_api_response_time()
        generation_rate = await self._measure_generation_rate()
        error_rate = await self._measure_error_rate()

        metrics = PerformanceMetrics(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_io=disk_io,
            network_io=network_io,
            api_response_time=api_response_time,
            generation_rate=generation_rate,
            error_rate=error_rate
        )

        self.metrics_history.append(metrics)

        # 保持历史记录在合理范围内
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]

        return metrics

    async def _measure_api_response_time(self) -> float:
        """测量API响应时间"""
        # 实现API响应时间测量逻辑
        pass

    async def _measure_generation_rate(self) -> float:
        """测量生成速率"""
        # 实现生成速率测量逻辑
        pass

    async def _measure_error_rate(self) -> float:
        """测量错误率"""
        # 实现错误率测量逻辑
        pass

    def check_alerts(self, metrics: PerformanceMetrics) -> List[str]:
        """检查告警条件"""
        alerts = []

        if metrics.cpu_usage > 90:
            alerts.append("CPU使用率过高")

        if metrics.memory_usage > 85:
            alerts.append("内存使用率过高")

        if metrics.error_rate > 0.1:
            alerts.append("错误率过高")

        if metrics.api_response_time > 5.0:
            alerts.append("API响应时间过长")

        return alerts
```

## 📊 监控与日志

### 1. 日志系统

#### 结构化日志配置
```python
# logging_config.py
import logging
import json
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)

        return json.dumps(log_data, ensure_ascii=False)

def setup_logging(config: Dict[str, Any]):
    """设置日志系统"""
    level = getattr(logging, config.get('log_level', 'INFO'))

    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = StructuredFormatter()
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    if 'log_file' in config:
        file_handler = logging.FileHandler(
            config['log_file'],
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_formatter = StructuredFormatter()
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # 错误日志处理器
    if 'error_log_file' in config:
        error_handler = logging.FileHandler(
            config['error_log_file'],
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = StructuredFormatter()
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)
```

#### 应用日志记录
```python
# app_logger.py
import logging
from typing import Any, Dict

class AppLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def info(self, message: str, extra_data: Dict[str, Any] = None):
        """记录信息日志"""
        if extra_data:
            self.logger.info(message, extra={'extra_data': extra_data})
        else:
            self.logger.info(message)

    def error(self, message: str, exception: Exception = None, extra_data: Dict[str, Any] = None):
        """记录错误日志"""
        log_data = extra_data or {}

        if exception:
            log_data.update({
                'exception_type': type(exception).__name__,
                'exception_message': str(exception)
            })

        self.logger.error(message, extra={'extra_data': log_data})

    def performance(self, operation: str, duration: float, details: Dict[str, Any] = None):
        """记录性能日志"""
        log_data = {
            'operation': operation,
            'duration_seconds': duration,
            'type': 'performance'
        }

        if details:
            log_data.update(details)

        self.logger.info(f"Performance: {operation}", extra={'extra_data': log_data})

# 使用示例
logger = AppLogger(__name__)

# 记录普通日志
logger.info("应用启动成功")

# 记录错误日志
try:
    # 某些操作
    pass
except Exception as e:
    logger.error("操作失败", e, {"operation": "generate_chapter", "chapter_id": 123})

# 记录性能日志
import time
start_time = time.time()
# 执行操作
duration = time.time() - start_time
logger.performance("章节生成", duration, {"word_count": 4000, "model": "gpt-4"})
```

### 2. 监控系统

#### 健康检查端点
```python
# health_check.py
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
import psutil
import asyncio

app = FastAPI()

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查端点"""
    try:
        # 检查系统资源
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent

        # 检查应用状态
        app_status = await check_application_status()

        health_data = {
            "status": "healthy" if all([
                cpu_usage < 95,
                memory_usage < 95,
                disk_usage < 95,
                app_status["database_connected"],
                app_status["vectorstore_connected"]
            ]) else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "system": {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "disk_usage": disk_usage
            },
            "application": app_status
        }

        return health_data

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

@app.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """获取详细指标"""
    return {
        "system_metrics": await get_system_metrics(),
        "application_metrics": await get_application_metrics(),
        "performance_metrics": await get_performance_metrics()
    }

async def check_application_status() -> Dict[str, bool]:
    """检查应用状态"""
    # 检查数据库连接
    db_connected = await check_database_connection()

    # 检查向量存储连接
    vectorstore_connected = await check_vectorstore_connection()

    # 检查API服务状态
    api_services_status = await check_api_services()

    return {
        "database_connected": db_connected,
        "vectorstore_connected": vectorstore_connected,
        "api_services": api_services_status
    }
```

#### 告警系统
```python
# alert_system.py
import asyncio
import smtplib
from email.mime.text import MimeText
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class Alert:
    level: str  # info, warning, error, critical
    message: str
    source: str
    timestamp: str
    metadata: Dict[str, Any] = None

class AlertManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.alerts: List[Alert] = []
        self.notification_handlers = self._setup_handlers()

    def _setup_handlers(self):
        """设置通知处理器"""
        handlers = []

        if self.config.get('email_notifications', False):
            handlers.append(EmailNotificationHandler(self.config['email']))

        if self.config.get('webhook_notifications', False):
            handlers.append(WebhookNotificationHandler(self.config['webhook']))

        return handlers

    async def send_alert(self, alert: Alert):
        """发送告警"""
        self.alerts.append(alert)

        # 异步发送通知
        tasks = [
            handler.send_notification(alert)
            for handler in self.notification_handlers
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def check_system_health(self):
        """检查系统健康状态并发送告警"""
        metrics = await collect_system_metrics()

        # CPU使用率告警
        if metrics.cpu_usage > 90:
            await self.send_alert(Alert(
                level="critical",
                message=f"CPU使用率过高: {metrics.cpu_usage}%",
                source="system_monitor",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"cpu_usage": metrics.cpu_usage}
            ))

        # 内存使用率告警
        if metrics.memory_usage > 85:
            await self.send_alert(Alert(
                level="warning",
                message=f"内存使用率过高: {metrics.memory_usage}%",
                source="system_monitor",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"memory_usage": metrics.memory_usage}
            ))

class EmailNotificationHandler:
    def __init__(self, config: Dict[str, Any]):
        self.smtp_server = config['smtp_server']
        self.smtp_port = config['smtp_port']
        self.username = config['username']
        self.password = config['password']
        self.recipients = config['recipients']

    async def send_notification(self, alert: Alert):
        """发送邮件通知"""
        try:
            subject = f"[{alert.level.upper()}] AI小说生成器告警"

            body = f"""
            告警级别: {alert.level}
            告警消息: {alert.message}
            告警来源: {alert.source}
            告警时间: {alert.timestamp}
            """

            msg = MimeText(body)
            msg['Subject'] = subject
            msg['From'] = self.username
            msg['To'] = ', '.join(self.recipients)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

        except Exception as e:
            logging.error(f"发送邮件告警失败: {e}")
```

## 🔒 安全配置

### 1. API安全

#### API密钥管理
```python
# secure_config.py
import os
import json
from cryptography.fernet import Fernet

class SecureConfigManager:
    def __init__(self, key_file: str = ".encryption_key"):
        self.key_file = key_file
        self.cipher_suite = self._get_or_create_key()

    def _get_or_create_key(self):
        """获取或创建加密密钥"""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # 设置文件权限
            os.chmod(self.key_file, 0o600)

        return Fernet(key)

    def encrypt_api_key(self, api_key: str) -> str:
        """加密API密钥"""
        return self.cipher_suite.encrypt(api_key.encode()).decode()

    def decrypt_api_key(self, encrypted_key: str) -> str:
        """解密API密钥"""
        return self.cipher_suite.decrypt(encrypted_key.encode()).decode()

    def save_secure_config(self, config: Dict[str, Any], filename: str):
        """保存安全配置"""
        secure_config = {}

        # 加密敏感字段
        for key, value in config.items():
            if 'api_key' in key.lower() or 'password' in key.lower():
                secure_config[key] = self.encrypt_api_key(value)
            else:
                secure_config[key] = value

        with open(filename, 'w') as f:
            json.dump(secure_config, f, indent=2)

    def load_secure_config(self, filename: str) -> Dict[str, Any]:
        """加载安全配置"""
        with open(filename, 'r') as f:
            secure_config = json.load(f)

        config = {}

        # 解密敏感字段
        for key, value in secure_config.items():
            if 'api_key' in key.lower() or 'password' in key.lower():
                config[key] = self.decrypt_api_key(value)
            else:
                config[key] = value

        return config
```

#### 访问控制
```python
# access_control.py
import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class AccessController:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.rate_limits = {}
        self.session_tokens = {}

    def generate_token(self, user_id: str, permissions: list, expires_in: int = 3600) -> str:
        """生成JWT令牌"""
        payload = {
            'user_id': user_id,
            'permissions': permissions,
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow()
        }

        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证JWT令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def check_permission(self, token: str, required_permission: str) -> bool:
        """检查权限"""
        payload = self.verify_token(token)

        if not payload:
            return False

        return required_permission in payload.get('permissions', [])

    def check_rate_limit(self, client_id: str, limit: int, window: int = 3600) -> bool:
        """检查频率限制"""
        now = datetime.utcnow().timestamp()

        if client_id not in self.rate_limits:
            self.rate_limits[client_id] = []

        # 清理过期记录
        self.rate_limits[client_id] = [
            timestamp for timestamp in self.rate_limits[client_id]
            if now - timestamp < window
        ]

        # 检查是否超过限制
        if len(self.rate_limits[client_id]) >= limit:
            return False

        # 记录当前请求
        self.rate_limits[client_id].append(now)
        return True
```

### 2. 数据安全

#### 数据加密
```python
# data_encryption.py
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class DataEncryption:
    def __init__(self, password: str, salt: bytes = None):
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self.cipher_suite = Fernet(key)
        self.salt = salt

    def encrypt_data(self, data: str) -> bytes:
        """加密数据"""
        return self.cipher_suite.encrypt(data.encode())

    def decrypt_data(self, encrypted_data: bytes) -> str:
        """解密数据"""
        return self.cipher_suite.decrypt(encrypted_data).decode()

    def encrypt_file(self, input_file: str, output_file: str):
        """加密文件"""
        with open(input_file, 'rb') as f:
            data = f.read()

        encrypted_data = self.encrypt_data(data.decode())

        with open(output_file, 'wb') as f:
            f.write(encrypted_data)

    def decrypt_file(self, input_file: str, output_file: str):
        """解密文件"""
        with open(input_file, 'rb') as f:
            encrypted_data = f.read()

        decrypted_data = self.decrypt_data(encrypted_data)

        with open(output_file, 'w') as f:
            f.write(decrypted_data)
```

## 🔧 故障排除

### 1. 常见部署问题

#### API连接问题
```bash
# 检查网络连接
curl -I https://api.openai.com/v1/models

# 检查DNS解析
nslookup api.openai.com

# 检查防火墙设置
sudo ufw status

# 检查代理设置
echo $http_proxy
echo $https_proxy
```

#### 权限问题
```bash
# 检查文件权限
ls -la /opt/AI_NovelGenerator/

# 修复权限
sudo chown -R ai-novel-app:ai-novel-app /opt/AI_NovelGenerator/
sudo chmod -R 755 /opt/AI_NovelGenerator/

# 检查服务权限
sudo systemctl status ai-novel-generator
```

#### 内存不足问题
```bash
# 检查内存使用
free -h
ps aux --sort=-%mem | head

# 增加swap空间
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 调整应用内存限制
# 编辑systemd服务文件
# 添加 MemoryLimit=4G
```

### 2. 性能问题诊断

#### CPU使用率过高
```bash
# 查看CPU使用情况
top
htop

# 查看进程详情
ps aux --sort=-%cpu | head

# 分析Python进程
sudo strace -p <process_id>
```

#### 内存泄漏检测
```python
# memory_leak_detector.py
import tracemalloc
import gc
import time

class MemoryLeakDetector:
    def __init__(self):
        self.snapshots = []

    def start_tracking(self):
        """开始内存跟踪"""
        tracemalloc.start()

    def take_snapshot(self, label: str = ""):
        """拍摄内存快照"""
        snapshot = tracemalloc.take_snapshot()
        self.snapshots.append((label, snapshot, time.time()))

    def compare_snapshots(self, index1: int, index2: int):
        """比较两个快照"""
        if index1 >= len(self.snapshots) or index2 >= len(self.snapshots):
            return None

        label1, snapshot1, time1 = self.snapshots[index1]
        label2, snapshot2, time2 = self.snapshots[index2]

        stats = snapshot2.compare_to(snapshot1, 'lineno')

        print(f"\n内存对比: {label1} -> {label2}")
        print(f"时间间隔: {time2 - time1:.2f}秒")

        for stat in stats[:10]:  # 显示前10个最大的差异
            print(stat)

        return stats

# 使用示例
detector = MemoryLeakDetector()
detector.start_tracking()

# 在关键点拍摄快照
detector.take_snapshot("应用启动")
# ... 运行一段时间
detector.take_snapshot("生成100章后")

# 比较快照
detector.compare_snapshots(0, 1)
```

### 3. 日志分析

#### 日志分析脚本
```python
# log_analyzer.py
import json
import re
from collections import defaultdict, Counter
from datetime import datetime

class LogAnalyzer:
    def __init__(self, log_file: str):
        self.log_file = log_file

    def analyze_errors(self, hours: int = 24) -> Dict[str, Any]:
        """分析错误日志"""
        errors = []
        error_counts = Counter()

        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line)

                    if log_entry.get('level') == 'ERROR':
                        timestamp = datetime.fromisoformat(log_entry['timestamp'])
                        if (datetime.now() - timestamp).total_seconds() < hours * 3600:
                            errors.append(log_entry)
                            error_type = log_entry.get('extra_data', {}).get('exception_type', 'Unknown')
                            error_counts[error_type] += 1

                except (json.JSONDecodeError, KeyError):
                    continue

        return {
            'total_errors': len(errors),
            'error_types': dict(error_counts),
            'recent_errors': errors[-10:]  # 最近10个错误
        }

    def analyze_performance(self, hours: int = 24) -> Dict[str, Any]:
        """分析性能日志"""
        performance_data = []

        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line)

                    if log_entry.get('extra_data', {}).get('type') == 'performance':
                        timestamp = datetime.fromisoformat(log_entry['timestamp'])
                        if (datetime.now() - timestamp).total_seconds() < hours * 3600:
                            performance_data.append(log_entry['extra_data'])

                except (json.JSONDecodeError, KeyError):
                    continue

        if not performance_data:
            return {}

        operations = defaultdict(list)
        for data in performance_data:
            operations[data['operation']].append(data['duration_seconds'])

        performance_summary = {}
        for operation, durations in operations.items():
            performance_summary[operation] = {
                'count': len(durations),
                'avg_duration': sum(durations) / len(durations),
                'min_duration': min(durations),
                'max_duration': max(durations)
            }

        return performance_summary

    def generate_report(self) -> str:
        """生成分析报告"""
        error_analysis = self.analyze_errors()
        performance_analysis = self.analyze_performance()

        report = f"""
日志分析报告
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

错误分析:
- 总错误数: {error_analysis['total_errors']}
- 错误类型分布: {error_analysis['error_types']}

性能分析:
- 操作统计:
"""

        for operation, stats in performance_analysis.items():
            report += f"  {operation}: 平均耗时 {stats['avg_duration']:.2f}秒 (共{stats['count']}次)\n"

        return report
```

---

## 📞 部署支持

如果您在部署过程中遇到问题，可以通过以下方式获取帮助：

- 📧 **部署支持**: deploy-support@ai-novelgenerator.com
- 🐛 **部署问题**: [GitHub Deployment Issues](https://github.com/your-username/AI_NovelGenerator/issues)
- 💬 **运维讨论**: [GitHub Discussions](https://github.com/your-username/AI_NovelGenerator/discussions)
- 📖 **部署文档更新**: [在线部署文档](https://docs.ai-novelgenerator.com/deployment)

### 部署检查清单

- [ ] 系统要求满足
- [ ] 依赖环境安装完成
- [ ] 配置文件正确设置
- [ ] API密钥配置正确
- [ ] 防火墙规则配置
- [ ] 服务启动正常
- [ ] 日志记录正常
- [ ] 监控告警配置
- [ ] 备份策略制定
- [ ] 安全配置验证

---

本文档持续更新，请关注最新版本。