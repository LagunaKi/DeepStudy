"""
向量存储管理
使用 LlamaIndex 的向量存储功能
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
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

class VectorStoreManager:
    """
    DeepStudy 向量知识库管理器
    """
    
    def __init__(self):
        # 使用配置文件中的路径
        self.persist_dir = settings.VECTOR_STORE_PATH
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
        
        # 2. 配置眼睛 (Embedding) -> 使用 BGE 中文模型
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="BAAI/bge-small-zh-v1.5"
        )
        
        # 3. 初始化/加载索引 (记忆库)
        # 检查是否已有索引文件（通过检查目录中是否有特定文件来判断）
        index_exists = os.path.exists(self.persist_dir) and os.listdir(self.persist_dir)
        if not index_exists:
            # 初始化新知识库
            self.index = VectorStoreIndex.from_documents([])
            self.index.storage_context.persist(persist_dir=self.persist_dir)
        else:
            # 加载已有索引
            storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
            self.index = load_index_from_storage(storage_context)

    async def add_document(self, text: str, metadata: Dict = None):
        """存入知识：切片 -> 向量化 -> 存硬盘"""
        if not text: return
        
        doc = Document(text=text, metadata=metadata or {})
        self.index.insert(doc)
        self.index.storage_context.persist(persist_dir=self.persist_dir)

    async def search_context(self, query: str, top_k: int = 3) -> List[Dict]:
        """检索知识：语义搜索 -> 返回片段"""
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

# 全局单例
vector_store_manager = VectorStoreManager()
