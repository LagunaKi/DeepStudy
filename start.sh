#!/bin/bash

echo "=== Starting DeepStudy Application ==="

# 1. 启动 Neo4j
echo "[1/3] Starting Neo4j..."
# 显式设置 JAVA_HOME，确保 Neo4j 能找到 Java 21
export JAVA_HOME=/opt/java-21
export PATH=$JAVA_HOME/bin:$PATH

neo4j start || {
    echo "Warning: Failed to start Neo4j, but continuing..."
}

# 等待 Neo4j 启动完成
echo "Waiting for Neo4j to start..."
sleep 10

# 检查 Neo4j 是否启动成功（通过 Bolt 端口 7687）
max_attempts=30
attempt=0
neo4j_ready=false
while [ $attempt -lt $max_attempts ]; do
    if nc -z localhost 7687 2>/dev/null; then
        echo "Neo4j started successfully!"
        neo4j_ready=true
        break
    fi
    echo "Waiting for Neo4j... (attempt $((attempt + 1))/$max_attempts)"
    sleep 2
    attempt=$((attempt + 1))
done

if [ "$neo4j_ready" = false ]; then
    echo "Warning: Neo4j may not have started properly, but continuing..."
fi

# 2. 启动后端服务
echo "[2/3] Starting FastAPI backend..."
cd /home/user/app
# 添加 --proxy-headers 以正确处理代理头
python -u -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' &

# 等待后端启动（加载 embedding 模型需要较长时间）
sleep 10

# 检查后端是否启动成功（增加等待时间到60秒）
max_attempts=30
attempt=0
backend_ready=false
while [ $attempt -lt $max_attempts ]; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "Backend started successfully!"
        backend_ready=true
        break
    fi
    echo "Waiting for backend... (attempt $((attempt + 1))/$max_attempts)"
    sleep 2
    attempt=$((attempt + 1))
done

if [ "$backend_ready" = false ]; then
    echo "Warning: Backend may not have started properly, but continuing..."
fi

# 3. 启动 Nginx（前台运行，保持容器运行）
echo "[3/3] Starting Nginx..."
echo "=== All services started! ==="
nginx -g "daemon off;"
