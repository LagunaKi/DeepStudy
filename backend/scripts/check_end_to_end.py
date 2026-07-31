import asyncio
import sys
import os
import uuid
from google import genai
from google.genai import types

# 确保能找到 backend 文件夹
sys.path.append(os.getcwd())
from backend.data.neo4j_client import neo4j_client

# ==========================================
# 1. 手工联调用的 Gemini 客户端
# ==========================================
class RealAgent:
    def __init__(self):
        # 仅从环境变量读取，禁止在测试或示例代码中写入真实 Token。
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = os.environ.get("LLM_MODEL", "gemini-3-flash-preview")

    def think_and_reply(self, current_user_input, history_messages):
        """
        调用真实的大模型 API
        args:
            current_user_input: 这次用户说了啥
            history_messages: 之前的对话历史 [{"role": "user", "content":...}, ...]
        """
        print(f"🤖 [Gemini] 收到消息: '{current_user_input}'，正在思考...")
        
        # 1. 构建完整的对话上下文 (Context)
        # 系统提示词：设定 AI 的人设
        messages = [
            types.Content(
                role="model" if item["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=item["content"])],
            )
            for item in history_messages
        ]
        messages.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=current_user_input)],
            )
        )

        try:
            # 2. 发起真实的 API 请求
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "你是一个乐于助人的学习助手，擅长数学和编程教学。"
                        "请用简洁的中文回答。"
                    ),
                    thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
                ),
            )
            
            # 3. 获取 AI 的回复
            reply_content = response.text or ""
            print(f"💡 [Gemini] 回复: {reply_content[:50]}...")
            
            # 简单判断一下意图 (在真实项目中，这里可以让 AI 返回 JSON 来判断)
            intent = "explanation" if len(reply_content) > 20 else "chit_chat"
            
            return reply_content, intent
            
        except Exception as e:
            print(f"❌ 调用 Gemini API 失败: {e}")
            return "AI 大脑掉线了，请检查 Token 或网络。", "error"

# ==========================================
# 2. 真实业务流程手工联调 (存库 + 调大模型)
# ==========================================
async def test_real_workflow():
    print("🎬 === 开始：DeepStudy 真实 AI 联调测试 ===\n")
    
    agent = RealAgent()
    
    # 检查有没有填 Token
    if not agent.api_key:
        print("❌ 错误：请先通过环境变量 GEMINI_API_KEY 配置密钥！")
        return

    user_id = "real_student_007"
    
    # ----------------------------------------------
    # 第一轮：用户提问
    # ----------------------------------------------
    print("\n--- [Round 1] 用户发起提问 ---")
    question_1 = "请问学习 Python 应该先学什么？"
    msg_id_1 = str(uuid.uuid4())
    
    # 1. 存用户消息
    await neo4j_client.save_dialogue_node(msg_id_1, user_id, "user", question_1, intent="query")
    
    # 2. 呼叫 AI (传入空历史)
    reply_1, intent_1 = agent.think_and_reply(question_1, [])
    
    # 3. 存 AI 回复
    msg_id_2 = str(uuid.uuid4())
    await neo4j_client.save_dialogue_node(msg_id_2, user_id, "assistant", reply_1, intent=intent_1)
    await neo4j_client.link_dialogue_nodes(msg_id_1, msg_id_2) # 关联
    print("✅ 第一轮对话已闭环 (Neo4j 保存成功)")

    
    # ----------------------------------------------
    # 第二轮：用户追问 (测试 AI 是否记得上下文)
    # ----------------------------------------------
    print("\n--- [Round 2] 用户根据上文追问 ---")
    question_2 = "那你推荐哪本书呢？"  # 注意：这里没有提 "Python"，AI 必须记得上一句是聊 Python
    msg_id_3 = str(uuid.uuid4())
    
    # 1. 存用户消息
    await neo4j_client.save_dialogue_node(msg_id_3, user_id, "user", question_2)
    await neo4j_client.link_dialogue_nodes(msg_id_2, msg_id_3) # 连到上一句 AI 回复后面
    
    # 2. 构造历史记录传给 AI
    history = [
        {"role": "user", "content": question_1},
        {"role": "assistant", "content": reply_1}
    ]
    
    # 3. 呼叫 AI (带记忆)
    reply_2, intent_2 = agent.think_and_reply(question_2, history)
    
    # 4. 存 AI 回复
    msg_id_4 = str(uuid.uuid4())
    await neo4j_client.save_dialogue_node(msg_id_4, user_id, "assistant", reply_2, intent=intent_2)
    await neo4j_client.link_dialogue_nodes(msg_id_3, msg_id_4)
    print("✅ 第二轮对话已闭环")

    # ==========================================
    # 最终查验：看看数据库里是不是真的存下来了
    # ==========================================
    print("\n🕵️‍♂️ [最终查验] 正在从 Neo4j 读取完整对话树...")
    tree = await neo4j_client.get_dialogue_tree(msg_id_1, user_id)
    
    if tree:
        print(f"\n[用户]: {tree['content']}")
        if tree.get('children'):
            ai_reply = tree['children'][0]
            print(f"[AI  ]: {ai_reply['content'][:50]}...")
            
            if ai_reply.get('children'):
                user_reply_2 = ai_reply['children'][0]
                print(f"[用户]: {user_reply_2['content']}")
                
                if user_reply_2.get('children'):
                    ai_reply_2 = user_reply_2['children'][0]
                    print(f"[AI  ]: {ai_reply_2['content'][:50]}...")
        print("\n🎉 测试成功！真实 AI 对话已成功存入图数据库！")
    else:
        print("❌ 数据库查询失败。")

    await neo4j_client.close()

if __name__ == "__main__":
    asyncio.run(test_real_workflow())
