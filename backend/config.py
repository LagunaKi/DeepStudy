"""
配置管理
使用 pydantic-settings 管理环境变量
支持本地开发和 Docker 容器部署
"""
import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    # Gemini Developer API 免费层。密钥必须来自环境变量。
    GEMINI_API_KEY: str = ""

    # Gemini 3 Flash 提供免费 API 层；preview 模型可能被 Google 后续替换。
    LLM_MODEL: str = "gemini-3-flash-preview"
    LLM_CODER_MODEL: str = "gemini-3-flash-preview"
    GEMINI_THINKING_LEVEL: Literal["minimal", "low", "medium", "high"] = "medium"
    # 免费层按项目与模型共享请求额度；统一限制短时间内的请求启动频率。
    GEMINI_MIN_REQUEST_INTERVAL_SECONDS: float = 4.0
    
    # Neo4j 配置（容器内使用 localhost）
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "deepstudy-dev-only"
    
    # JWT 尚未进入主流程；启用认证前必须通过环境变量设置密钥。
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # SQLite 数据库（根据环境自动选择路径）
    SQLITE_DB_PATH: str = ""
    LANGGRAPH_CHECKPOINT_DB_PATH: str = ""
    
    # 向量存储（根据环境自动选择路径）
    VECTOR_STORE_PATH: str = ""
    UPLOAD_STORAGE_PATH: str = ""
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    RAG_MAX_FILE_BYTES: int = 20 * 1024 * 1024
    RAG_MAX_IMAGE_BYTES: int = 8 * 1024 * 1024
    
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

        if not self.LANGGRAPH_CHECKPOINT_DB_PATH:
            if is_docker_env():
                self.LANGGRAPH_CHECKPOINT_DB_PATH = get_storage_path("checkpoints.db")
            else:
                self.LANGGRAPH_CHECKPOINT_DB_PATH = get_storage_path("storage/checkpoints.db")
        
        # 如果未设置 VECTOR_STORE_PATH，根据环境自动设置
        if not self.VECTOR_STORE_PATH:
            if is_docker_env():
                self.VECTOR_STORE_PATH = get_storage_path("vector_store")
            else:
                self.VECTOR_STORE_PATH = get_storage_path("storage/vector_store")

        if not self.UPLOAD_STORAGE_PATH:
            if is_docker_env():
                self.UPLOAD_STORAGE_PATH = get_storage_path("uploads")
            else:
                self.UPLOAD_STORAGE_PATH = get_storage_path("storage/uploads")
        
        # 如果未设置 CORS_ORIGINS，根据环境自动设置
        if not self.CORS_ORIGINS:
            if is_docker_env():
                # 容器环境：允许所有来源（通过 Nginx 代理）
                self.CORS_ORIGINS = '["*"]'
            else:
                # 本地开发：允许特定来源
                self.CORS_ORIGINS = '["http://localhost:5173","http://localhost:3000"]'
    
settings = Settings()
