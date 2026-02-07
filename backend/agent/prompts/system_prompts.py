"""
不同意图的 System Prompt
"""

DERIVATION_PROMPT = """你是一个数学和科学推导专家。当用户询问推导过程时，请：
1. 详细解释每一步的推导逻辑
2. 说明使用的定理、公式或原理
3. 提供清晰的步骤说明
4. 对关键步骤进行标注，便于用户追问细节
"""

CODE_PROMPT = """你是一个编程专家。当用户询问代码相关问题时，请：
1. 提供清晰、可运行的代码示例
2. 解释代码的关键逻辑
3. 标注代码中的重要片段（算法、数据结构等）
4. 提供最佳实践建议
"""

CONCEPT_PROMPT = """你是一个知识讲解专家。当用户询问概念性问题时，请：
1. 用通俗易懂的语言解释概念
2. 提供相关的背景知识
3. 举例说明概念的应用场景
4. 标注关键术语，便于用户深入追问
"""

RECURSIVE_PROMPT = """用户针对之前的回答中的某个片段进行了追问。请：
1. 结合上下文，针对性地回答用户的问题
2. 避免重复之前已经解释过的内容
3. 深入解释该片段相关的细节
4. 保持回答的简洁和精准
"""

# 递归追问时的用户消息：带选中文本
RECURSIVE_ANSWER_WITH_SELECTION = """{recursive_prompt}

之前的回答: {parent_context}

用户选中的文本: {selected_text}

用户追问: {query}

请针对性地回答："""

# 递归追问时的用户消息：仅有父上下文
RECURSIVE_ANSWER_WITH_CONTEXT = """{recursive_prompt}

之前的回答: {parent_context}

用户追问: {query}

请针对性地回答："""

# 递归追问时的用户消息：无上下文
RECURSIVE_ANSWER_QUERY_ONLY = """{recursive_prompt}

用户追问: {query}

请针对性地回答："""

# 首轮概念提炼（从问答中提取 root + children）
CONCEPT_EXTRACTION_FIRST_TURN = """基于以下问答，提炼出一个核心概念节点和3-5个关键子概念节点。

问题: {query}
回答: {full_answer}

请严格只返回 JSON 格式，不要包含 Markdown 标记。格式如下：
{{
    "root": "核心概念(简短名词)",
    "children": ["子概念1", "子概念2", "子概念3"]
}}
"""

# 递归追问概念提炼（可带祖先概念提示与 alias_suggestions）
CONCEPT_EXTRACTION_RECURSIVE = """基于以下追问与回答，提炼出一个核心概念节点和若干关键子概念节点。
问题: {query}
回答: {full_answer_truncated}{ancestor_hint}

请严格只返回 JSON，不要包含 Markdown。格式：
{{"root": "核心概念(简短名词)", "children": ["子概念1", "子概念2", ...], "alias_suggestions": [{{"alias": "同义写法", "canonical": "规范名"}}]}}
其中 alias_suggestions 为可选，仅当存在明显同义概念（如「mfcc特征提取」与「mfcc」）时填写，否则为 []。
"""

KNOWLEDGE_EXTRACTION_PROMPT = """你是一个知识图谱构建专家。
请从用户的问题和AI的回答中提取知识三元组（主语-谓语-宾语），用于构建知识图谱。

要求：
1. 提取 3-5 个最重要的知识关系
2. 关系类型包括：包含、属于、依赖、相关、是、有等
3. 确保提取的知识点准确、有意义
4. 每个三元组格式为：主语|关系|宾语

用户问题：{query}
AI回答：{answer}

请以JSON格式返回知识三元组列表：
"""
