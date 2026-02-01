FROM modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/python:3.10

# 配置 Debian 镜像源（使用 trusted=yes + 完全禁用 GPG 验证）
RUN echo "deb [trusted=yes] https://mirrors.aliyun.com/debian/ bookworm main" > /etc/apt/sources.list && \
    echo "deb [trusted=yes] https://mirrors.aliyun.com/debian/ bookworm-updates main" >> /etc/apt/sources.list && \
    echo "deb [trusted=yes] https://mirrors.aliyun.com/debian-security/ bookworm-security main" >> /etc/apt/sources.list && \
    # 清理所有旧的源配置
    rm -rf /etc/apt/sources.list.d/* 2>/dev/null || true && \
    # 配置 APT 选项：完全禁用 GPG 验证
    echo 'APT::Get::AllowUnauthenticated "true";' > /etc/apt/apt.conf.d/99allow-unauthenticated && \
    echo 'Acquire::AllowInsecureRepositories "true";' >> /etc/apt/apt.conf.d/99allow-unauthenticated && \
    echo 'Acquire::Check-Valid-Until "false";' >> /etc/apt/apt.conf.d/99allow-unauthenticated

# 安装系统依赖（使用 --allow-unauthenticated 确保安装成功）
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* && \
    apt-get update --allow-insecure-repositories && \
    apt-get install -y --allow-unauthenticated --no-install-recommends --fix-missing \
    wget \
    curl \
    gnupg \
    ca-certificates \
    tar \
    nginx \
    nodejs \
    npm \
    netcat-openbsd \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# 安装 Java 21
RUN apt-get update && \
    apt-get install -y wget tar && \
    # 注意：URL 中的 + 需要编码为 %2B
    wget "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.1%2B12/OpenJDK21U-jdk_x64_linux_hotspot_21.0.1_12.tar.gz" -O /tmp/jdk21.tar.gz && \
    mkdir -p /opt/java-21 && \
    tar -xzf /tmp/jdk21.tar.gz -C /opt/java-21 --strip-components=1 && \
    rm /tmp/jdk21.tar.gz && \
    update-alternatives --install /usr/bin/java java /opt/java-21/bin/java 2100 && \
    update-alternatives --install /usr/bin/javac javac /opt/java-21/bin/javac 2100 && \
    echo 'export JAVA_HOME=/opt/java-21' >> /etc/profile && \
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> /etc/profile && \
    rm -rf /var/lib/apt/lists/*

# 安装 Neo4j（使用 tar 包，避免 apt 依赖问题）
RUN NEO4J_VERSION="5.15.0" && \
    apt-get update && \
    apt-get install -y wget tar && \
    # 下载 Neo4j Community Edition
    wget "https://dist.neo4j.org/neo4j-community-${NEO4J_VERSION}-unix.tar.gz" -O /tmp/neo4j.tar.gz && \
    # 解压到 /opt
    tar -xzf /tmp/neo4j.tar.gz -C /opt && \
    mv /opt/neo4j-community-${NEO4J_VERSION} /opt/neo4j && \
    rm /tmp/neo4j.tar.gz && \
    # 创建 neo4j 用户（如果不存在）
    id -u neo4j >/dev/null 2>&1 || useradd -r -s /bin/bash neo4j && \
    # 设置权限
    chown -R neo4j:neo4j /opt/neo4j && \
    # 创建符号链接，使 neo4j 命令可用
    ln -s /opt/neo4j/bin/neo4j /usr/local/bin/neo4j && \
    # 配置数据目录（使用持久化目录）
    mkdir -p /mnt/workspace/neo4j/data && \
    mkdir -p /mnt/workspace/neo4j/logs && \
    mkdir -p /mnt/workspace/neo4j/plugins && \
    chown -R neo4j:neo4j /mnt/workspace/neo4j && \
    # 修改配置文件（注意：tar 包的配置文件在 /opt/neo4j/conf/）
    sed -i 's|#dbms.directories.data=data|dbms.directories.data=/mnt/workspace/neo4j/data|g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's|#dbms.directories.logs=logs|dbms.directories.logs=/mnt/workspace/neo4j/logs|g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's/#dbms.default_listen_address=0.0.0.0/dbms.default_listen_address=0.0.0.0/g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's/#dbms.default_advertised_address=localhost/dbms.default_advertised_address=localhost/g' /opt/neo4j/conf/neo4j.conf && \
    sed -i 's/#dbms.security.auth_enabled=true/dbms.security.auth_enabled=true/g' /opt/neo4j/conf/neo4j.conf && \
    # 设置内存限制
    echo "dbms.memory.heap.initial_size=512m" >> /opt/neo4j/conf/neo4j.conf && \
    echo "dbms.memory.heap.max_size=1g" >> /opt/neo4j/conf/neo4j.conf && \
    # 设置 JAVA_HOME（Neo4j 会读取环境变量）
    echo 'export JAVA_HOME=/opt/java-21' >> /opt/neo4j/conf/neo4j-env.sh && \
    echo 'export PATH=$JAVA_HOME/bin:$PATH' >> /opt/neo4j/conf/neo4j-env.sh && \
    rm -rf /var/lib/apt/lists/*

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

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/sites-available/default

# 复制启动脚本
COPY start.sh /home/user/app/start.sh
RUN chmod +x /home/user/app/start.sh

# 暴露端口
EXPOSE 7860 7687

# 启动服务
ENTRYPOINT ["/home/user/app/start.sh"]