"""API 路由包。

不在包导入时急切加载所有路由，避免聊天主链路被可选的 RAG Embedding
依赖阻断。`backend.main` 会显式导入并注册需要的子模块。
"""
