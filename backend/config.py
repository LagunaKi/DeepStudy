"""
配置管理
使用 pydantic-settings 管理环境变量
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """应用配置"""
    
    # ModelScope API 配置
    MODELSCOPE_API_KEY: str = "ms-9b769e50-465c-4108-b47e-dc40e7bf22fd" 
    MODELSCOPE_API_BASE: str = "https://api-inference.modelscope.cn/v1"
    
    # 模型选择
    MODEL_NAME: str = "Qwen/Qwen2.5-72B-Instruct"
    CODER_MODEL_NAME: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    
    # Neo4j 配置
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str
    
    # JWT 配置
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # SQLite 数据库
    SQLITE_DB_PATH: str = "backend/storage/deepstudy.db"
    
    # 向量存储
    VECTOR_STORE_PATH: str = "backend/storage/vector_store"
    
    # CORS
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'  # JSON 字符串格式
    
    # 服务器配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    class Config:
        env_file = "backend/.env"
        case_sensitive = True


settings = Settings()
