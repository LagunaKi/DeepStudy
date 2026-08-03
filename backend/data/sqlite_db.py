"""
SQLite 数据库操作
管理用户数据和对话记录
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime

import aiosqlite

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

    # 可持久化学习会话。Agent checkpoint 将在阶段 1 后续复用 session_id。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            conversation_id TEXT,
            parent_id TEXT,
            status TEXT NOT NULL DEFAULT 'complete',
            agent_trace TEXT NOT NULL DEFAULT '[]',
            sources TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)

    # 兼容已有数据库：SQLite 的 CREATE TABLE IF NOT EXISTS 不会补充新列。
    columns_cursor = await db.execute("PRAGMA table_info(chat_messages)")
    columns = {row[1] for row in await columns_cursor.fetchall()}
    if "agent_trace" not in columns:
        await db.execute(
            "ALTER TABLE chat_messages ADD COLUMN agent_trace TEXT NOT NULL DEFAULT '[]'"
        )
    if "sources" not in columns:
        await db.execute(
            "ALTER TABLE chat_messages ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'"
        )

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
        ON chat_sessions(user_id, updated_at DESC)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
        ON chat_messages(session_id, created_at ASC)
    """)

    # 附件元数据先进入统一模型；阶段 2 接入文件存储、解析和多模态内容。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS message_attachments (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            message_id TEXT,
            document_id TEXT,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            storage_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE SET NULL
        )
    """)

    attachment_columns_cursor = await db.execute("PRAGMA table_info(message_attachments)")
    attachment_columns = {row[1] for row in await attachment_columns_cursor.fetchall()}
    for column, definition in {
        "document_id": "TEXT",
        "progress": "INTEGER NOT NULL DEFAULT 0",
        "error": "TEXT",
        "storage_path": "TEXT",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if column not in attachment_columns:
            await db.execute(
                f"ALTER TABLE message_attachments ADD COLUMN {column} {definition}"
            )

    await db.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            page_count INTEGER,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, session_id, filename, content_hash)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            page INTEGER,
            section TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            lexical_text TEXT NOT NULL,
            embedding TEXT,
            embedding_model TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES rag_documents(id) ON DELETE CASCADE,
            UNIQUE(document_id, chunk_index)
        )
    """)
    await db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            content,
            lexical_text,
            tokenize='unicode61'
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_rag_documents_session_status
        ON rag_documents(user_id, session_id, status, updated_at DESC)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_session_document
        ON rag_chunks(user_id, session_id, document_id, chunk_index)
    """)

    # Phase 3: 可审计、可编辑、可遗忘的跨会话长期记忆。
    # 短期对话仍由 chat_messages 管理，运行状态由 LangGraph checkpoint 管理。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            scope TEXT NOT NULL CHECK (scope IN ('semantic', 'episodic')),
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            normalized_content TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            source TEXT NOT NULL,
            source_session_id TEXT,
            source_conversation_id TEXT,
            confidence REAL NOT NULL DEFAULT 0.7,
            importance REAL NOT NULL DEFAULT 0.5,
            user_confirmed INTEGER NOT NULL DEFAULT 0,
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed_at TEXT,
            expires_at TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, dedupe_key)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_memories_user_scope_updated
        ON agent_memories(user_id, scope, updated_at DESC)
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory_audit (
            id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_memory_audit_user_created
        ON agent_memory_audit(user_id, created_at DESC)
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
) -> dict | None:
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
) -> dict | None:
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
