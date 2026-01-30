"""
测试知识三元组提取功能
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.extractors import knowledge_extractor

def test_extraction():
    """
    测试知识三元组提取功能
    """
    print("开始测试知识三元组提取功能...")
    
    # 测试文本1: 简单概念
    test_text1 = "人工智能是研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统的一门新的技术科学。人工智能的研究领域包括机器学习、计算机视觉、自然语言处理等。"
    print("\n测试文本1:")
    print(test_text1)
    
    triples1 = knowledge_extractor.extract_triples(test_text1)
    print(f"\n提取的三元组数量: {len(triples1)}")
    for i, triple in enumerate(triples1, 1):
        print(f"{i}. {triple['subject']} - {triple['relation']} - {triple['object']}")
    
    # 测试文本2: 数学概念
    test_text2 = "勾股定理是一个基本的几何定理，指直角三角形的两条直角边的平方和等于斜边的平方。勾股定理在中国古代称为商高定理。"
    print("\n测试文本2:")
    print(test_text2)
    
    triples2 = knowledge_extractor.extract_triples(test_text2)
    print(f"\n提取的三元组数量: {len(triples2)}")
    for i, triple in enumerate(triples2, 1):
        print(f"{i}. {triple['subject']} - {triple['relation']} - {triple['object']}")
    
    # 测试文本3: 科学知识
    test_text3 = "水的化学式是H2O。水在标准大气压下的沸点是100摄氏度。水由氢元素和氧元素组成。"
    print("\n测试文本3:")
    print(test_text3)
    
    triples3 = knowledge_extractor.extract_triples(test_text3)
    print(f"\n提取的三元组数量: {len(triples3)}")
    for i, triple in enumerate(triples3, 1):
        print(f"{i}. {triple['subject']} - {triple['relation']} - {triple['object']}")
    
    print("\n测试完成！")

if __name__ == "__main__":
    test_extraction()
