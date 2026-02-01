"""
配置管理
使用 pydantic-settings 管理环境变量
支持本地开发和 Docker 容器部署
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List
import os


# 检测是否在容器环境中运行
def is_docker_env() -> bool:
    """检测是否在 Docker 容器中运行"""
    return os.path.exists("/.dockerenv") or os.path.exists("/mnt/workspace")


# 获取存储路径（容器环境使用持久化目录）
def get_storage_path(relative_path: str) -> str:
    """获取存储路径，容器环境使用 /mnt/workspace，本地使用相对路径"""
    if is_docker_env():
        # 容器环境：使用持久化目录
        base_path = Path("/mnt/workspace")
    else:
        # 本地环境：使用项目相对路径
        base_path = Path(__file__).parent.resolve()
    
    return str(base_path / relative_path)


class Settings(BaseSettings):
    """应用配置"""
    
    # ModelScope API 配置
    MODELSCOPE_API_KEY: str = "ms-9b769e50-465c-4108-b47e-dc40e7bf22fd" 
    MODELSCOPE_API_BASE: str = "https://api-inference.modelscope.cn/v1"
    
    # 模型选择
    MODEL_NAME: str = "Qwen/Qwen2.5-72B-Instruct"
    CODER_MODEL_NAME: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    
    # Neo4j 配置（容器内使用 localhost）
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123"  # 默认密码，可通过环境变量覆盖
    
    # JWT 配置（提供默认值，生产环境必须通过环境变量覆盖）
    JWT_SECRET_KEY: str = "default-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # SQLite 数据库（根据环境自动选择路径）
    SQLITE_DB_PATH: str = ""
    
    # 向量存储（根据环境自动选择路径）
    VECTOR_STORE_PATH: str = ""
    
    # CORS（容器环境允许所有来源，本地开发使用特定来源）
    CORS_ORIGINS: str = ""
    
    # 服务器配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # 如果未设置 SQLITE_DB_PATH，根据环境自动设置
        if not self.SQLITE_DB_PATH:
            if is_docker_env():
                self.SQLITE_DB_PATH = get_storage_path("deepstudy.db")
            else:
                self.SQLITE_DB_PATH = get_storage_path("storage/deepstudy.db")
        
        # 如果未设置 VECTOR_STORE_PATH，根据环境自动设置
        if not self.VECTOR_STORE_PATH:
            if is_docker_env():
                self.VECTOR_STORE_PATH = get_storage_path("vector_store")
            else:
                self.VECTOR_STORE_PATH = get_storage_path("storage/vector_store")
        
        # 如果未设置 CORS_ORIGINS，根据环境自动设置
        if not self.CORS_ORIGINS:
            if is_docker_env():
                # 容器环境：允许所有来源（通过 Nginx 代理）
                self.CORS_ORIGINS = '["*"]'
            else:
                # 本地开发：允许特定来源
                self.CORS_ORIGINS = '["http://localhost:5173","http://localhost:3000"]'
    
    class Config:
        env_file = "backend/.env"
        case_sensitive = True
        # 允许通过环境变量覆盖字段
        extra = "allow"


settings = Settings()
