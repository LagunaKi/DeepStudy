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
        self.persist_dir = "./local_storage"
        
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
        if not os.path.exists(self.persist_dir):
            #print("VectorStore] 本地为空，正在初始化新知识库...")
            self.index = VectorStoreIndex.from_documents([])
            self.index.storage_context.persist(persist_dir=self.persist_dir)
        else:
            #print("[VectorStore] 发现本地记忆，正在加载...")
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