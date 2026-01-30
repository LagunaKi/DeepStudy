"""
API 请求模型定义
"""
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr = Field(...)
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class ChatRequest(BaseModel):
    """前端请求格式：划词追问时发送的数据"""
    query: str = Field(..., min_length=1, description="用户输入的问题")
    parent_id: Optional[str] = Field(None, description="当前所在节点的 ID，首次提问可为空")
    ref_fragment_id: Optional[str] = Field(None, description="如果是划词追问，需带上片段 ID")
    session_id: str = Field(..., description="会话 ID，区分不同学习主题")
