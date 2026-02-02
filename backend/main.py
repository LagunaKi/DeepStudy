"""
FastAPI 应用入口
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.api.routes import auth, chat, mindmap, knowledge
from backend.data.sqlite_db import init_db
import asyncio
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 创建 FastAPI 应用
app = FastAPI(
    title="DeepStudy API",
    description="基于 ModelScope 的递归学习 Agent",
    version="0.1.0"
)

# [调试] 全局中间件：记录请求头，用于排查 403 问题
from fastapi import Request
@app.middleware("http")
async def log_request_headers(request: Request, call_next):
    # 打印关键 Header 信息
    auth_header = request.headers.get("authorization")
    x_auth_token = request.headers.get("x-auth-token")
    
    logger.info(f"Incoming Request: {request.method} {request.url.path}")
    
    if auth_header:
        logger.info(f"Authorization Header: Present (Starts with {auth_header[:10]}...)")
    else:
        logger.warning("Authorization Header: MISSING")
        
    if x_auth_token:
        logger.info(f"X-Auth-Token Header: Present (Starts with {x_auth_token[:10]}...)")
    else:
        logger.warning("X-Auth-Token Header: MISSING")
    
    response = await call_next(request)
    return response

# 注册知识库路由（在 CORS 之前）
app.include_router(knowledge.router)

# 配置 CORS
import json
cors_origins = json.loads(settings.CORS_ORIGINS) if isinstance(settings.CORS_ORIGINS, str) else settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(mindmap.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    logger.info("应用启动，初始化数据库...")
    
    # 打印关键配置信息（用于验证环境变量是否正确读取）
    logger.info(f"[配置] MODELSCOPE_API_KEY: {settings.MODELSCOPE_API_KEY[:10]}...{settings.MODELSCOPE_API_KEY[-4:]}")
    logger.info(f"[配置] JWT_SECRET_KEY: {settings.JWT_SECRET_KEY[:10]}...{settings.JWT_SECRET_KEY[-4:]}")
    logger.info(f"[配置] MODEL_NAME: {settings.MODEL_NAME}")
    logger.info(f"[配置] NEO4J_URI: {settings.NEO4J_URI}")
    logger.info(f"[配置] SQLITE_DB_PATH: {settings.SQLITE_DB_PATH}")
    logger.info(f"[配置] CORS_ORIGINS: {settings.CORS_ORIGINS}")
    
    await init_db()
    logger.info("数据库初始化完成")


@app.get("/")
async def root():
    """根路径"""
    return {"message": "DeepStudy API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )
