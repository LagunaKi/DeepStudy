import asyncio
import os
import sys

# 1. 确保能找到 backend 包
sys.path.append(os.getcwd())

from backend.agent.orchestrator import AgentOrchestrator

async def main():
    print("🚀 [测试开始] 正在启动编排器...")
    
    # 初始化编排器 (这里会初始化 LLM 和 Router)
    orchestrator = AgentOrchestrator()
    
    # --- 手工联调用例：问一个知识库里有的问题 ---
    # 你之前在 vector_store.py 里存过 "宫保鸡丁"
    query = "我想学做菜，有什么推荐？"
    
    print(f"\n❓ [用户提问] {query}")
    print("⏳ [处理中] 正在调度大脑和知识库...")
    
    try:
        # 调用 process_query (这就是我们在 orchestrator.py 里改的那个核心函数)
        response = await orchestrator.process_query(
            user_id="test_tester", 
            query=query
        )
        
        print("\n" + "="*50)
        print("🤖 [AI 回答]:")
        print(response.answer)
        print("="*50)
        
        # 验证点
        if "宫保鸡丁" in response.answer:
            print("\n✅ [测试成功] RAG 生效了！AI 成功读取了本地知识库！")
        else:
            print("\n⚠️ [测试存疑] AI 回答了，但好像没用到本地知识（没提宫保鸡丁）。")
            
    except Exception as e:
        print(f"\n❌ [测试失败] 报错信息: {e}")

if __name__ == "__main__":
    asyncio.run(main())
