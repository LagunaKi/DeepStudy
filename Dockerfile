FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

# 1. 禁用 GPG，配置源，禁用 apt 缓存（关键！）
RUN echo 'APT::Get::AllowUnauthenticated "true";' > /etc/apt/apt.conf.d/99allow-unauthenticated && \
    echo 'Acquire::AllowInsecureRepositories "true";' >> /etc/apt/apt.conf.d/99allow-unauthenticated && \
    echo 'Acquire::Check-Valid-Until "false";' >> /etc/apt/apt.conf.d/99allow-unauthenticated && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "false";' > /etc/apt/apt.conf.d/docker-clean && \
    echo 'APT::Keep-Downloaded-Packages "false";' >> /etc/apt/apt.conf.d/docker-clean && \
    echo "deb [trusted=yes] https://mirrors.aliyun.com/debian/ bookworm main" > /etc/apt/sources.list && \
    echo "deb [trusted=yes] https://mirrors.aliyun.com/debian/ bookworm-updates main" >> /etc/apt/sources.list && \
    echo "deb [trusted=yes] https://mirrors.aliyun.com/debian-security/ bookworm-security main" >> /etc/apt/sources.list && \
    rm -rf /etc/apt/sources.list.d/* /var/lib/apt/lists/* /var/cache/apt/*

# 2. 安装基础依赖（分步安装以节省空间）
RUN rm -rf /var/lib/apt/lists/* && \
    apt-get update --allow-insecure-repositories && \
    apt-get install -y --allow-unauthenticated --no-install-recommends \
    wget curl ca-certificates tar xz-utils && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# 2.1 安装 Nginx 和 Netcat（单独安装）
RUN rm -rf /var/lib/apt/lists/* && \
    apt-get update --allow-insecure-repositories && \
    apt-get install -y --allow-unauthenticated --no-install-recommends \
    nginx netcat-openbsd && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# 3. 安装 Node.js（直接下载官方二进制包，避免 apt 依赖）
RUN NODE_VERSION="20.11.0" && \
    wget -q "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -O /tmp/node.tar.xz && \
    tar -xJf /tmp/node.tar.xz -C /opt && \
    mv /opt/node-v${NODE_VERSION}-linux-x64 /opt/node && \
    ln -s /opt/node/bin/node /usr/local/bin/node && \
    ln -s /opt/node/bin/npm /usr/local/bin/npm && \
    ln -s /opt/node/bin/npx /usr/local/bin/npx && \
    rm /tmp/node.tar.xz

# 4. 安装 Neo4j（使用 tar 包，避免 apt 依赖）
RUN NEO4J_VERSION="5.15.0" && \
    wget -q "https://dist.neo4j.org/neo4j-community-${NEO4J_VERSION}-unix.tar.gz" -O /tmp/neo4j.tar.gz && \
    tar -xzf /tmp/neo4j.tar.gz -C /opt && \
    mv /opt/neo4j-community-${NEO4J_VERSION} /opt/neo4j && \
    rm /tmp/neo4j.tar.gz && \
    # 创建 neo4j 用户
    id -u neo4j >/dev/null 2>&1 || useradd -r -s /bin/bash neo4j && \
    chown -R neo4j:neo4j /opt/neo4j && \
    ln -s /opt/neo4j/bin/neo4j /usr/local/bin/neo4j && \
    # 基础配置
    mkdir -p /mnt/workspace/neo4j/data /mnt/workspace/neo4j/logs /mnt/workspace/neo4j/plugins && \
    chown -R neo4j:neo4j /mnt/workspace/neo4j && \
    sed -i 's|#dbms.directories.data=data|dbms.directories.data=/mnt/workspace/neo4j/data|g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's|#dbms.directories.logs=logs|dbms.directories.logs=/mnt/workspace/neo4j/logs|g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's/#dbms.default_listen_address=0.0.0.0/dbms.default_listen_address=0.0.0.0/g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's/#dbms.security.auth_enabled=true/dbms.security.auth_enabled=true/g' /opt/neo4j/conf/neo4j.conf && \
    echo "dbms.memory.heap.initial_size=512m" >> /opt/neo4j/conf/neo4j.conf && \
    echo "dbms.memory.heap.max_size=1g" >> /opt/neo4j/conf/neo4j.conf && \
    echo 'export JAVA_HOME=/opt/java-21' >> /opt/neo4j/conf/neo4j-env.sh && \
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> /opt/neo4j/conf/neo4j-env.sh

# 5. 安装 Java 21（直接下载，无依赖）
RUN wget -q "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.1%2B12/OpenJDK21U-jdk_x64_linux_hotspot_21.0.1_12.tar.gz" -O /tmp/jdk21.tar.gz && \
    mkdir -p /opt/java-21 && \
    tar -xzf /tmp/jdk21.tar.gz -C /opt/java-21 --strip-components=1 && \
    rm /tmp/jdk21.tar.gz && \
    echo 'export JAVA_HOME=/opt/java-21' >> /etc/profile && \
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> /etc/profile

# 设置环境变量，确保运行时生效
ENV JAVA_HOME=/opt/java-21
ENV PATH=$JAVA_HOME/bin:$PATH

# 设置工作目录
WORKDIR /home/user/app

# 复制后端代码和依赖
COPY backend/ ./backend/
COPY backend/requirements.txt ./requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制前端代码
COPY frontend/ ./frontend/

# 安装前端依赖并构建
WORKDIR /home/user/app/frontend
RUN npm install && npm run build

# 复制 Nginx 配置（直接覆盖主配置）
COPY nginx.conf /etc/nginx/nginx.conf
RUN rm -rf /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*

# 复制启动脚本
COPY start.sh /home/user/app/start.sh
RUN chmod +x /home/user/app/start.sh

# 暴露端口
EXPOSE 7860 7687

# 启动服务
ENTRYPOINT ["/home/user/app/start.sh"]
