<<<<<<< HEAD
"""
向量存储管理
使用 LlamaIndex 的向量存储功能
"""
from typing import List, Dict
from llama_index.vector_stores import SimpleVectorStore
from llama_index import VectorStoreIndex, ServiceContext
from llama_index.llms.modelscope import ModelScopeLLM
from llama_index.embeddings import HuggingFaceEmbedding
from backend.config import settings
import os


class VectorStoreManager:
    """向量存储管理器"""
    
    def __init__(self):
        """初始化向量存储管理器"""
        self.store_path = settings.VECTOR_STORE_PATH
        os.makedirs(self.store_path, exist_ok=True)
        
        # 初始化 LLM
        self.llm = ModelScopeLLM(
            model_name=settings.MODEL_NAME,
            api_key=settings.MODELSCOPE_API_KEY,
            api_base=settings.MODELSCOPE_API_BASE
        )
        
        # 初始化嵌入模型
        # TODO: 使用 ModelScope 的嵌入模型
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # 初始化服务上下文
        self.service_context = ServiceContext.from_defaults(
            llm=self.llm,
            embed_model=self.embed_model
        )
        
        # 初始化向量存储
        self.vector_store = SimpleVectorStore()
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            service_context=self.service_context
        )
    
    async def add_document(self, text: str, metadata: Dict = None):
        """
        添加文档到向量存储
        
        Args:
            text: 文档文本
            metadata: 文档元数据
        """
        # TODO: 实现文档添加逻辑
        pass
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        搜索相似文档
        
        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            
        Returns:
            相似文档列表
        """
        # TODO: 实现搜索逻辑
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        results = await retriever.retrieve(query)
        return [
            {
                "text": result.text,
                "score": result.score,
                "metadata": result.metadata
            }
            for result in results
        ]


# 全局向量存储管理器实例
vector_store_manager = VectorStoreManager()
=======
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
    DeepFocus 向量知识库管理器
    """
    
    def __init__(self):
        # 使用配置文件中的路径
        self.persist_dir = settings.VECTOR_STORE_PATH
        # 确保目录存在
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir, exist_ok=True)
        
        # 1. 配置大脑 (LLM) -> 指向 ModelScope
        model_scope_llm = OpenAI(
            model="Qwen/Qwen2.5-Coder-32B-Instruct",
            api_key=settings.MODELSCOPE_API_KEY,  # 确保你的 .env 或 config.py 里填了 key
            api_base="https://api-inference.modelscope.cn/v1",
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
        #print(f"[存入成功] {text[:20]}...")

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

# 全局单例
vector_store_manager = VectorStoreManager()
>>>>>>> b719fdcda5e46ee55a08988e23b2acd7d6544c45
