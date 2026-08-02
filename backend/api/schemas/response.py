"""
API 响应模型定义
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ContentFragment(BaseModel):
    """片段模型：用于划词引用的核心单元"""
    id: str = Field(..., description="对应 HTML 中的 <span id='frag_xxx'>")
    type: str = Field(..., description="片段类型: text, formula, code, concept")
    content: str = Field(..., description="具体内容")


class KnowledgeTriple(BaseModel):
    """知识图谱三元组：支撑 Chat-to-Graph"""
    subject: str
    relation: str
    object: str


class MindMapGraph(BaseModel):
    """UI层状态协议：兼容 ReactFlow 的节点格式"""
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="节点列表，包含 id, data, position 等字段")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="边列表，包含 id, source, target, label 等字段")


class AgentResponse(BaseModel):
    """Agent 层输出协议"""
    answer: str = Field(..., description="包含 <span id='...'> 标签的 Markdown 回答")
    fragments: List[ContentFragment] = Field(default_factory=list, description="提取出的所有知识点")
    knowledge_triples: List[Dict[str, str]] = Field(
        default_factory=list,
        description="知识图谱三元组：支撑 Chat-to-Graph，格式: [{'subject': '...', 'relation': '...', 'object': '...'}]"
    )
    suggestion: Optional[str] = Field(None, description="诊断建议，例如：'建议复习特征值相关概念'")
    conversation_id: str = Field(..., description="对话 ID")
    parent_id: Optional[str] = Field(None, description="父对话 ID")


class AuthResponse(BaseModel):
    """认证响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class DialogueNodeBase(BaseModel):
    """对话节点模型：树状结构的基础"""
    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="全局唯一ID")
    parent_id: Optional[str] = Field(None, description="溯源关键：指向父节点 ID")
    user_id: str = Field(..., description="所属用户ID，确保数据隔离")
    role: str = Field(..., description="角色: 'user' 或 'assistant'")
    content: str = Field(..., description="原始 Markdown 文本")
    intent: Optional[str] = Field(None, description="意图识别: 'derivation', 'code', 'concept'")
    mastery_score: float = Field(0.0, description="掌握度评分 (0-1)")
    timestamp: datetime = Field(default_factory=datetime.now)
    children: List['DialogueNodeBase'] = Field(default_factory=list, description="子节点列表")
    
# 为了向后兼容，保留 ConversationNode 作为别名
ConversationNode = DialogueNodeBase


class ErrorResponse(BaseModel):
    """错误响应"""
    status: str = "error"
    code: int
    message: str
    detail: Optional[str] = None
