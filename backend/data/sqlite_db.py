"""
SQLite 数据库操作
管理用户数据和对话记录
"""
import aiosqlite
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, List
from backend.config import settings


async def get_db():
    """
    获取数据库连接
    
    Returns:
        数据库连接对象
    """
    # 确保数据目录存在
    db_path = settings.SQLITE_DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    return db


@asynccontextmanager
async def get_db_connection():
    """
    数据库连接上下文管理器
    自动管理连接的打开和关闭
    
    Usage:
        async with get_db_connection() as db:
            # 使用 db 进行数据库操作
            user = await get_user_by_username(db, "username")
    """
    db = await get_db()
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    """初始化数据库表结构"""
    db = await get_db()
    
    # 创建用户表（当前保留结构，登录已移除，仅作为示例与预留）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 创建概念画像表（单用户场景下，以 concept_key + user_id 作为主键）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS concept_profiles (
            concept_key TEXT NOT NULL,
            user_id TEXT NOT NULL,
            u REAL NOT NULL,
            r REAL NOT NULL,
            a REAL NOT NULL,
            times INTEGER NOT NULL,
            last_practice TEXT,
            PRIMARY KEY (concept_key, user_id)
        )
    """)

    # 对话 id → 该轮涉及的概念（用于检索父/祖先节点画像概念）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS conversation_concepts (
            conversation_id TEXT NOT NULL,
            concept_key TEXT NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY (conversation_id, concept_key, user_id)
        )
    """)

    # 用户学习计划（手动维护的概念列表，用于多设备同步与图谱高亮）
    await db.execute("""
        CREATE TABLE IF NOT EXISTS learning_plan (
            user_id TEXT NOT NULL,
            concept_key TEXT NOT NULL,
            PRIMARY KEY (user_id, concept_key)
        )
    """)

    await db.commit()
    await db.close()


async def create_user(
    db: aiosqlite.Connection,
    username: str,
    email: str,
    hashed_password: str
) -> int:
    """
    创建用户
    
    Args:
        db: 数据库连接
        username: 用户名
        email: 邮箱
        hashed_password: 密码哈希
        
    Returns:
        用户 ID
    """
    created_at = datetime.utcnow().isoformat()
    cursor = await db.execute(
        "INSERT INTO users (username, email, hashed_password, created_at) VALUES (?, ?, ?, ?)",
        (username, email, hashed_password, created_at)
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_by_username(
    db: aiosqlite.Connection,
    username: str
) -> Optional[Dict]:
    """
    根据用户名获取用户
    
    Args:
        db: 数据库连接
        username: 用户名
        
    Returns:
        用户信息字典，如果不存在则返回 None
    """
    cursor = await db.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def get_user_by_email(
    db: aiosqlite.Connection,
    email: str
) -> Optional[Dict]:
    """
    根据邮箱获取用户
    
    Args:
        db: 数据库连接
        email: 邮箱
        
    Returns:
        用户信息字典，如果不存在则返回 None
    """
    cursor = await db.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


