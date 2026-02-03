"""
向量存储管理
使用 LlamaIndex 的向量存储功能
"""
import os
import time
import logging

# 配置 HuggingFace 镜像
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# 增加下载超时时间
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"

from typing import List, Dict

# --- LlamaIndex 核心组件 ---
from llama_index.core import (
    VectorStoreIndex, 
    Document, 
    StorageContext, 
    load_index_from_storage, 
    Settings
)
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from backend.config import settings 

logger = logging.getLogger(__name__)


def load_embedding_model_with_retry(max_retries: int = 3, retry_delay: int = 5):
    """
    带重试机制加载 Embedding 模型
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    
    Returns:
        HuggingFaceEmbedding 实例，失败返回 None
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"[Embedding] 尝试加载模型 (第 {attempt + 1}/{max_retries} 次)...")
            embed_model = HuggingFaceEmbedding(
                model_name="BAAI/bge-small-zh-v1.5",
                trust_remote_code=True
            )
            logger.info("[Embedding] 模型加载成功!")
            return embed_model
        except Exception as e:
            logger.warning(f"[Embedding] 加载失败: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"[Embedding] {retry_delay}秒后重试...")
                time.sleep(retry_delay)
            else:
                logger.error("[Embedding] 所有重试均失败，向量检索功能将不可用")
    return None


class VectorStoreManager:
    """
    DeepStudy 向量知识库管理器
    """
    
    def __init__(self):
        # 使用配置文件中的路径
        self.persist_dir = settings.VECTOR_STORE_PATH
        self.initialized = False
        self.index = None
        
        # 确保目录存在
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir, exist_ok=True)
        
        # 1. 配置大脑 (LLM) -> 指向 ModelScope
        model_scope_llm = OpenAI(
            model=settings.CODER_MODEL_NAME,
            api_key=settings.MODELSCOPE_API_KEY,
            api_base=settings.MODELSCOPE_API_BASE,
            temperature=0.1,
            max_tokens=2048
        )
        Settings.llm = model_scope_llm
        
        # 2. 配置眼睛 (Embedding) -> 使用 BGE 中文模型（带重试）
        embed_model = load_embedding_model_with_retry(max_retries=3, retry_delay=10)
        if embed_model is None:
            logger.warning("[VectorStore] Embedding 模型加载失败，向量检索功能不可用")
            return
        
        Settings.embed_model = embed_model
        
        # 3. 初始化/加载索引 (记忆库)
        try:
            index_exists = os.path.exists(self.persist_dir) and os.listdir(self.persist_dir)
            if not index_exists:
                # 初始化新知识库
                self.index = VectorStoreIndex.from_documents([])
                self.index.storage_context.persist(persist_dir=self.persist_dir)
            else:
                # 加载已有索引
                storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
                self.index = load_index_from_storage(storage_context)
            self.initialized = True
            logger.info("[VectorStore] 向量存储初始化成功")
        except Exception as e:
            logger.error(f"[VectorStore] 索引初始化失败: {str(e)}")

    async def add_document(self, text: str, metadata: Dict = None):
        """存入知识：切片 -> 向量化 -> 存硬盘"""
        if not self.initialized or not text:
            return
        
        try:
            doc = Document(text=text, metadata=metadata or {})
            self.index.insert(doc)
            self.index.storage_context.persist(persist_dir=self.persist_dir)
        except Exception as e:
            logger.error(f"[VectorStore] 添加文档失败: {str(e)}")

    async def search_context(self, query: str, top_k: int = 3) -> List[Dict]:
        """检索知识：语义搜索 -> 返回片段"""
        if not self.initialized:
            return []
        
        try:
            retriever = self.index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query)
            
            results = []
            for node in nodes:
                results.append({
                    "text": node.text,
                    "score": node.score,
                    "source": node.metadata.get("source", "unknown")
                })
            return results
        except Exception as e:
            logger.error(f"[VectorStore] 检索失败: {str(e)}")
            return []

    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        搜索相似文档（兼容旧接口）
        
        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            
        Returns:
            相似文档列表
        """
        return await self.search_context(query, top_k)

# 全局单例（延迟初始化，避免模块加载时崩溃）
_vector_store_manager = None


def get_vector_store_manager() -> VectorStoreManager:
    """获取向量存储管理器实例（懒加载）"""
    global _vector_store_manager
    if _vector_store_manager is None:
        try:
            _vector_store_manager = VectorStoreManager()
        except Exception as e:
            logger.error(f"[VectorStore] 初始化失败: {str(e)}")
            # 返回一个空的管理器实例
            _vector_store_manager = VectorStoreManager.__new__(VectorStoreManager)
            _vector_store_manager.initialized = False
            _vector_store_manager.index = None
            _vector_store_manager.persist_dir = settings.VECTOR_STORE_PATH
    return _vector_store_manager


# 兼容旧代码的属性访问
class _VectorStoreProxy:
    """代理类，支持懒加载"""
    def __getattr__(self, name):
        return getattr(get_vector_store_manager(), name)

vector_store_manager = _VectorStoreProxy()
