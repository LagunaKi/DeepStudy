import asyncio
import sys
import os

# 这一步是为了确保 Python 能找到 backend 文件夹
sys.path.append(os.getcwd())

from backend.data.neo4j_client import neo4j_client

async def main():
    print("🚀 === 开始 Neo4jClient 手工联调 ===\n")

    # ---------------------------
    # 1. 测试基础连接
    # ---------------------------
    print("📡 [步骤 1] 测试数据库连接...")
    try:
        await neo4j_client.verify_connectivity()
        print("✅ 连接成功！数据库是通的。\n")
    except Exception as e:
        print(f"❌ 连接失败！请检查 backend/config.py 里的账号密码。报错信息: {e}")
        return

    # ---------------------------
    # 2. 测试 DeepStudy (你的功能: 学习路径)
    # ---------------------------
    print("📚 [步骤 2] 测试学习路径 (DeepStudy)...")
    try:
        # 造一点假数据用于测试：测试导数 -> 依赖 -> 测试极限
        print("   -> 正在创建测试概念节点...")
        node_limit = await neo4j_client.create_node("Concept", {"name": "Test_Limit"})
        node_derivative = await neo4j_client.create_node("Concept", {"name": "Test_Derivative"})
        
        if node_limit and node_derivative:
            # 创建关系: 导数 (source) -> REQUIRES -> 极限 (target)
            await neo4j_client.create_relationship(node_derivative, node_limit, "REQUIRES")
            
            # 尝试调用你的核心函数
            print("   -> 正在查询学习路径...")
            path = await neo4j_client.get_learning_path("Test_Derivative")
            
            if "Test_Limit" in path:
                print(f"✅ 成功！查询到的路径: {path}")
            else:
                print(f"⚠️ 查询结果为空或不正确: {path}")
        else:
            print("⚠️ 节点创建失败，无法进行路径测试。")
            
    except Exception as e:
        print(f"❌ 学习路径测试出错: {e}")
    print("")

    # ---------------------------
    # 3. 测试 DeepFocus (学长的功能: 对话记忆)
    # ---------------------------
    print("💬 [步骤 3] 测试对话功能 (DeepFocus)...")
    try:
        user_id = "test_user_luke"
        msg_id_1 = "msg_001"
        msg_id_2 = "msg_002"

        # 模拟用户发一句话
        await neo4j_client.save_dialogue_node(
            node_id=msg_id_1, user_id=user_id, role="user", 
            content="你好，我要学高数", intent="start"
        )
        print("   -> 用户消息已保存")

        # 模拟 AI 回一句话
        await neo4j_client.save_dialogue_node(
            node_id=msg_id_2, user_id=user_id, role="assistant", 
            content="好的，请问你想学哪一章？", intent="reply"
        )
        print("   -> AI 回复已保存")

        # 把这两句话连起来
        await neo4j_client.link_dialogue_nodes(msg_id_1, msg_id_2)
        print("   -> 对话上下文已关联")

        # 尝试把整个对话树拉出来
        tree = await neo4j_client.get_dialogue_tree(msg_id_1, user_id)
        if tree and len(tree.get("children", [])) > 0:
            print(f"✅ 成功！查找到的对话内容: {tree['content']} -> 回复: {tree['children'][0]['content']}")
        else:
            print(f"⚠️ 对话树查询失败: {tree}")

    except Exception as e:
        print(f"❌ 对话功能测试出错: {e}")

    # ---------------------------
    # 4. 收尾
    # ---------------------------
    await neo4j_client.close()
    print("\n🏁 === 测试结束 ===")

if __name__ == "__main__":
    asyncio.run(main())
