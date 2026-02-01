# Docker 部署指南（魔搭创空间）

本文档说明如何将 DeepStudy 项目部署到魔搭创空间的 Docker 环境。

## 前置要求

1. 完成魔搭账号实名认证
2. 创建 Docker 创空间
3. 获取访问令牌（Access Token）

## 部署步骤

### 1. 克隆项目到本地

```bash
git lfs install
git clone https://oauth2:YOUR-ACCESS-TOKEN@www.modelscope.cn/studios/YOUR_USERNAME/YOUR_STUDIO_NAME.git
cd YOUR_STUDIO_NAME
```

### 2. 复制项目文件

将以下文件复制到克隆的仓库目录：
- `backend/` - 后端代码
- `frontend/` - 前端代码
- `requirements.txt` - Python 依赖
- `Dockerfile` - Docker 构建文件
- `nginx.conf` - Nginx 配置
- `start.sh` - 启动脚本
- `.dockerignore` - Docker 忽略文件

### 3. 配置环境变量

在魔搭创空间的"设置"页面配置以下环境变量：

**必需的环境变量：**
- `MODELSCOPE_API_KEY`: 你的 ModelScope API Key
- `JWT_SECRET_KEY`: JWT 签名密钥（建议使用随机字符串）

**可选的环境变量：**
- `NEO4J_PASSWORD`: Neo4j 密码（默认：`neo4j123`）
- `MODEL_NAME`: 主模型名称（默认：`Qwen/Qwen2.5-72B-Instruct`）
- `CODER_MODEL_NAME`: 代码模型名称（默认：`Qwen/Qwen2.5-Coder-32B-Instruct`）

### 4. 提交代码

```bash
git add .
git commit -m "Add Docker deployment files"
git push
```

### 5. 上线部署

1. 前往创空间的"设置"页面
2. 点击"上线"按钮
3. 等待构建完成（首次构建可能需要 10-20 分钟）
4. 查看日志确认服务启动成功

## 服务架构

部署后的服务架构：

```
用户请求 (7860端口)
    ↓
Nginx (反向代理)
    ├─→ 前端静态文件 (/)
    └─→ 后端 API (/api)
        ├─→ FastAPI (8000端口)
        └─→ Neo4j (7687端口，内部)
```

## 数据持久化

以下数据会保存在 `/mnt/workspace/` 目录，重启后保留：
- SQLite 数据库：`/mnt/workspace/deepstudy.db`
- 向量存储：`/mnt/workspace/vector_store/`
- Neo4j 数据：`/mnt/workspace/neo4j/data/`

## 故障排查

### 查看日志

在创空间"设置"页面点击"查看日志"，可以查看：
- **构建日志**：Docker 镜像构建过程
- **运行日志**：容器运行时的日志

### 常见问题

1. **Neo4j 启动失败**
   - 检查日志中的 Neo4j 启动信息
   - 确认内存是否充足（Neo4j 需要至少 512MB）

2. **后端服务无法访问**
   - 检查 FastAPI 是否在 8000 端口启动
   - 查看运行日志中的错误信息

3. **前端页面无法加载**
   - 确认前端构建是否成功（检查 `frontend/dist/` 目录）
   - 检查 Nginx 配置是否正确

4. **环境变量未生效**
   - 确认环境变量在"设置"页面正确配置
   - 注意环境变量名称必须全大写

## 本地测试

在部署前，可以在本地测试 Docker 构建：

```bash
# 构建镜像
docker build -t deepstudy:test .

# 运行容器
docker run -p 7860:7860 \
  -e MODELSCOPE_API_KEY=your_key \
  -e JWT_SECRET_KEY=your_secret \
  deepstudy:test
```

## 注意事项

1. **首次启动时间**：Neo4j 首次启动需要较长时间（约 10-30 秒）
2. **内存限制**：确保容器有足够内存（建议至少 2GB）
3. **端口限制**：只能使用 7860 端口对外暴露服务
4. **数据备份**：定期备份 `/mnt/workspace/` 目录的数据

## 更新部署

更新代码后，重新提交并上线：

```bash
git add .
git commit -m "Update application"
git push
```

然后在创空间设置页面点击"上线"即可。
