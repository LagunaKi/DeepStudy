FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

# 安装系统依赖（包括 Java，Neo4j 需要）
RUN apt-get update && apt-get install -y \
    nginx \
    nodejs \
    npm \
    openjdk-17-jdk \
    wget \
    curl \
    gnupg \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# 安装 Neo4j
RUN wget -O /usr/share/keyrings/neo4j.gpg https://debian.neo4j.com/neotechnology.gpg.key && \
    echo 'deb [signed-by=/usr/share/keyrings/neo4j.gpg] https://debian.neo4j.com stable latest' > /etc/apt/sources.list.d/neo4j.list && \
    apt-get update && \
    apt-get install -y neo4j && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /home/user/app

# 复制后端代码和依赖
COPY backend/ ./backend/
COPY requirements.txt ./requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制前端代码
COPY frontend/ ./frontend/

# 安装前端依赖并构建
WORKDIR /home/user/app/frontend
RUN npm install && npm run build

# 配置 Neo4j（使用持久化目录）
RUN mkdir -p /mnt/workspace/neo4j/data && \
    mkdir -p /mnt/workspace/neo4j/logs && \
    mkdir -p /mnt/workspace/neo4j/plugins && \
    chown -R neo4j:neo4j /mnt/workspace/neo4j

# 修改 Neo4j 配置
RUN sed -i 's|#dbms.directories.data=data|dbms.directories.data=/mnt/workspace/neo4j/data|g' /etc/neo4j/neo4j.conf && \
    sed -i 's|#dbms.directories.logs=logs|dbms.directories.logs=/mnt/workspace/neo4j/logs|g' /etc/neo4j/neo4j.conf && \
    sed -i 's/#dbms.default_listen_address=0.0.0.0/dbms.default_listen_address=0.0.0.0/g' /etc/neo4j/neo4j.conf && \
    sed -i 's/#dbms.default_advertised_address=localhost/dbms.default_advertised_address=localhost/g' /etc/neo4j/neo4j.conf && \
    sed -i 's/#dbms.security.auth_enabled=true/dbms.security.auth_enabled=true/g' /etc/neo4j/neo4j.conf && \
    echo "dbms.memory.heap.initial_size=512m" >> /etc/neo4j/neo4j.conf && \
    echo "dbms.memory.heap.max_size=1g" >> /etc/neo4j/neo4j.conf

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/sites-available/default

# 复制启动脚本
COPY start.sh /home/user/app/start.sh
RUN chmod +x /home/user/app/start.sh

# 暴露端口（7860 是魔搭要求的，7687 是 Neo4j Bolt 端口）
EXPOSE 7860 7687

# 启动服务
ENTRYPOINT ["/home/user/app/start.sh"]
