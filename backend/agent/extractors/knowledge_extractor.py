"""
知识提取器模块
负责从文本中提取知识图谱三元组
"""
import logging
from typing import List, Dict, Tuple

# 配置日志
logger = logging.getLogger(__name__)


class KnowledgeExtractor:
    """
    知识提取器
    负责从文本中提取知识图谱三元组
    """

    def __init__(self):
        """
        初始化知识提取器
        """
        pass

    def extract_triples(self, text: str) -> List[Dict[str, str]]:
        """
        从文本中提取知识三元组

        Args:
            text: 要提取三元组的文本

        Returns:
            提取的知识三元组列表，格式: [{'subject': '...', 'relation': '...', 'object': '...'}]
        """
        logger.info(f"开始提取知识三元组，文本长度: {len(text)}")
        
        # 1. 基于规则的简单提取
        rule_based_triples = self._rule_based_extraction(text)
        logger.info(f"基于规则提取的三元组数量: {len(rule_based_triples)}")
        
        # 2. 去重处理
        unique_triples = self._deduplicate_triples(rule_based_triples)
        logger.info(f"去重后三元组数量: {len(unique_triples)}")
        
        return unique_triples

    def _rule_based_extraction(self, text: str) -> List[Dict[str, str]]:
        """
        基于规则的简单三元组提取

        Args:
            text: 要提取三元组的文本

        Returns:
            提取的知识三元组列表
        """
        triples = []
        
        # 分割句子
        sentences = self._split_into_sentences(text)
        
        for sentence in sentences:
            # 提取主谓宾结构
            sentence_triples = self._extract_from_sentence(sentence)
            triples.extend(sentence_triples)
        
        return triples

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        将文本分割成句子

        Args:
            text: 要分割的文本

        Returns:
            句子列表
        """
        import re
        # 简单的句子分割，基于句号、问号、感叹号
        sentences = re.split(r'[。！？.!?]', text)
        # 过滤空句子
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences

    def _extract_from_sentence(self, sentence: str) -> List[Dict[str, str]]:
        """
        从单个句子中提取三元组

        Args:
            sentence: 要提取三元组的句子

        Returns:
            提取的知识三元组列表
        """
        triples = []
        
        # 简单的主谓宾模式匹配
        patterns = [
            # 模式1: A是B
            (r'(.+?)是(.+)', '是'),
            # 模式2: A属于B
            (r'(.+?)属于(.+)', '属于'),
            # 模式3: A有B
            (r'(.+?)有(.+)', '有'),
            # 模式4: A包括B
            (r'(.+?)包括(.+)', '包括'),
            # 模式5: A等于B
            (r'(.+?)等于(.+)', '等于'),
            # 模式6: A大于B
            (r'(.+?)大于(.+)', '大于'),
            # 模式7: A小于B
            (r'(.+?)小于(.+)', '小于'),
            # 模式8: A导致B
            (r'(.+?)导致(.+)', '导致'),
            # 模式9: A产生B
            (r'(.+?)产生(.+)', '产生'),
            # 模式10: A由B组成
            (r'(.+?)由(.+)组成', '由...组成'),
        ]
        
        import re
        for pattern, relation in patterns:
            matches = re.finditer(pattern, sentence)
            for match in matches:
                if len(match.groups()) >= 2:
                    subject = match.group(1).strip()
                    object_ = match.group(2).strip()
                    
                    # 过滤太短的主语和宾语
                    if len(subject) > 1 and len(object_) > 1:
                        triple = {
                            'subject': subject,
                            'relation': relation,
                            'object': object_
                        }
                        triples.append(triple)
        
        return triples

    def _deduplicate_triples(self, triples: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        对三元组进行去重

        Args:
            triples: 要去重的三元组列表

        Returns:
            去重后的三元组列表
        """
        seen = set()
        unique_triples = []
        
        for triple in triples:
            # 创建一个唯一键
            key = (triple['subject'], triple['relation'], triple['object'])
            if key not in seen:
                seen.add(key)
                unique_triples.append(triple)
        
        return unique_triples

    def extract_triples_with_llm(self, text: str, llm) -> List[Dict[str, str]]:
        """
        使用大语言模型提取知识三元组

        Args:
            text: 要提取三元组的文本
            llm: 大语言模型实例

        Returns:
            提取的知识三元组列表
        """
        logger.info("使用LLM提取知识三元组")
        
        prompt = f"""请从以下文本中提取知识图谱三元组，格式为JSON数组：

文本：{text}

请提取其中的主谓宾结构，格式为：
[{"subject": "主语", "relation": "关系", "object": "宾语"}]

只返回JSON数组，不要包含其他内容。"""
        
        try:
            response_text = llm.acomplete(prompt)
            answer = response_text.text if hasattr(response_text, "text") else str(response_text)
            
            # 解析JSON响应
            import json
            triples = json.loads(answer)
            
            # 验证格式
            if isinstance(triples, list):
                valid_triples = []
                for triple in triples:
                    if isinstance(triple, dict) and all(k in triple for k in ['subject', 'relation', 'object']):
                        valid_triples.append(triple)
                return valid_triples
        except Exception as e:
            logger.error(f"使用LLM提取三元组失败: {e}")
            # 失败时回退到规则提取
            return self.extract_triples(text)
        
        return []


# 全局知识提取器实例
knowledge_extractor = KnowledgeExtractor()
