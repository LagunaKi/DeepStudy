"""
学习画像数据与概念归一化
负责：
- 概念名称归一化（词法规范化 + 别名字典 + Embedding 相似度合并）
- 学习事件增量应用到概念画像 (U, R, A, times, last_practice)
- 画像统计查询（summary / weak）
"""

import json
import logging
import math
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.config import settings
from backend.data.sqlite_db import get_db_connection
from backend.data.vector_store import load_embedding_model_with_retry

logger = logging.getLogger(__name__)


# ==============================
# 配置与常量
# ==============================

ANONYMOUS_USER_ID = "anonymous"


@dataclass
class ActivityVector:
    """学习活动的三维增量向量 (U, R, A)"""

    u: float
    r: float
    a: float


@dataclass
class ConceptProfile:
    """概念画像统计"""

    concept_key: str
    u: float
    r: float
    a: float
    times: int
    last_practice: Optional[datetime]

    @property
    def score(self) -> float:
        """综合得分（简单取三维平均），用于排序展示"""
        return (self.u + self.r + self.a) / 3.0


class ProfileConfig:
    """
    画像配置读取
    - 活动类型 -> 三维增量向量
    - Embedding 相似度阈值
    - 时间衰减参数（当前未启用，只预留字段）
    """

    def __init__(self) -> None:
        base_dir = Path(__file__).parent
        self._config_path = base_dir / "profile_config.json"

        # 默认配置（可被 JSON 覆盖）
        self.activity_weights: Dict[str, ActivityVector] = {
            "explain": ActivityVector(0.08, 0.04, 0.02),
            "derive": ActivityVector(0.04, 0.09, 0.03),
            "practice": ActivityVector(0.04, 0.05, 0.08),
            "recall": ActivityVector(0.05, 0.02, 0.0),
        }
        self.embedding_similarity_threshold: float = 0.88
        self.decay_half_life_days: int = 0  # 0 表示暂不启用时间衰减

        self._load_from_file()

    def _load_from_file(self) -> None:
        if not self._config_path.exists():
            logger.info(
                "Profile 配置文件不存在，使用默认配置: %s",
                self._config_path,
            )
            return

        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:  # pragma: no cover - 防御性逻辑
            logger.warning("加载 profile 配置失败，使用默认配置: %s", exc)
            return

        activity_raw = raw.get("activity_weights") or {}
        for name, vec in activity_raw.items():
            if (
                isinstance(vec, list)
                and len(vec) == 3
                and all(isinstance(x, (int, float)) for x in vec)
            ):
                self.activity_weights[name] = ActivityVector(
                    float(vec[0]),
                    float(vec[1]),
                    float(vec[2]),
                )

        if "embedding_similarity_threshold" in raw:
            try:
                self.embedding_similarity_threshold = float(
                    raw["embedding_similarity_threshold"],
                )
            except (TypeError, ValueError):
                logger.warning("embedding_similarity_threshold 配置无效，使用默认值")

        if "decay_half_life_days" in raw:
            try:
                self.decay_half_life_days = int(raw["decay_half_life_days"])
            except (TypeError, ValueError):
                logger.warning("decay_half_life_days 配置无效，使用默认值")


profile_config = ProfileConfig()


class ConceptNormalizer:
    """
    概念名称归一化：
    1. 词法规范化
    2. 显式别名字典
    3. Embedding 相似度合并高相似别名
    """

    def __init__(self) -> None:
        base_dir = Path(__file__).parent
        self._alias_path = base_dir / "profile_aliases.json"
        self._aliases: Dict[str, str] = {}
        self._canonical_names: List[str] = []
        self._canonical_embeddings: Dict[str, List[float]] = {}
        self._embed_model = None

        self._load_aliases()

    def _load_aliases(self) -> None:
        if not self._alias_path.exists():
            logger.info(
                "Profile 别名字典不存在，将使用空字典: %s",
                self._alias_path,
            )
            self._aliases = {}
            self._canonical_names = []
            return

        try:
            with self._alias_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:  # pragma: no cover - 防御性逻辑
            logger.warning("加载 profile 别名字典失败，使用空字典: %s", exc)
            self._aliases = {}
            self._canonical_names = []
            return

        aliases = raw.get("aliases") or {}
        normalized_aliases: Dict[str, str] = {}
        for alias, canonical in aliases.items():
            if not isinstance(alias, str) or not isinstance(canonical, str):
                continue
            alias_norm = self._lexical_normalize(alias)
            canonical_norm = self._lexical_normalize(canonical)
            normalized_aliases[alias_norm] = canonical_norm
        self._aliases = normalized_aliases
        self._canonical_names = sorted(set(normalized_aliases.values()))

    def reload_aliases(self) -> None:
        """
        重新从 JSON 加载别名字典并清空已缓存的规范名向量，使后续 normalize 使用最新别名。
        """
        self._load_aliases()
        self._canonical_embeddings = {}

    def _ensure_embed_model(self) -> None:
        """懒加载 Embedding 模型，仅用于概念归一化，失败时优雅降级。"""
        if self._embed_model is not None:
            return
        try:
            self._embed_model = load_embedding_model_with_retry(
                max_retries=1,
                retry_delay=5,
            )
            if self._embed_model is None:
                logger.warning(
                    "[Profile] Embedding 模型加载失败，将跳过相似度归一化",
                )
        except Exception as exc:  # pragma: no cover - 防御性逻辑
            logger.warning(
                "[Profile] 初始化 Embedding 模型异常，将跳过相似度归一化: %s",
                exc,
            )
            self._embed_model = None

    def _ensure_canonical_embeddings(self) -> None:
        """为别名字典中的规范名预先计算向量。"""
        if self._canonical_embeddings or not self._canonical_names:
            return
        self._ensure_embed_model()
        if self._embed_model is None:
            return

        for name in self._canonical_names:
            try:
                emb = self._embed_model.get_text_embedding(name)
                self._canonical_embeddings[name] = emb
            except Exception as exc:  # pragma: no cover - 防御性逻辑
                logger.warning(
                    "[Profile] 计算规范概念向量失败 '%s': %s",
                    name,
                    exc,
                )

    @staticmethod
    def _lexical_normalize(raw: str) -> str:
        """
        轻量级词法规范化：
        - 去前后空格
        - 英文部分转小写
        - 去掉常见无信息后缀（如“的概念”、“概念”、“简介”）
        """
        text = (raw or "").strip()
        if not text:
            return ""

        # 英文部分小写
        text = "".join(ch.lower() if ch.isascii() else ch for ch in text)

        # 去掉常见后缀
        for suffix in ("的概念", "概念", "简介"):
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)].strip()

        return text

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0.0 or n2 == 0.0:
            return 0.0
        return dot / (n1 * n2)

    def normalize(self, raw: str) -> str:
        """
        概念名称归一化：
        1. 词法规范化
        2. 显式别名字典
        3. Embedding 相似度高于阈值时合并到已有规范名
        """
        norm = self._lexical_normalize(raw)
        if not norm:
            return ""

        # 2. 显式别名字典
        if norm in self._aliases:
            return self._aliases[norm]

        # 3. Embedding 相似度合并
        self._ensure_canonical_embeddings()
        if not self._canonical_embeddings:
            return norm

        self._ensure_embed_model()
        if self._embed_model is None:
            return norm

        try:
            emb = self._embed_model.get_text_embedding(norm)
        except Exception as exc:  # pragma: no cover - 防御性逻辑
            logger.warning(
                "[Profile] 计算概念向量失败 '%s': %s",
                norm,
                exc,
            )
            return norm

        best_name = None
        best_score = 0.0
        for name, c_emb in self._canonical_embeddings.items():
            if not c_emb:
                continue
            sim = self._cosine_similarity(emb, c_emb)
            if sim > best_score:
                best_score = sim
                best_name = name

        if best_name and best_score >= profile_config.embedding_similarity_threshold:
            return best_name

        return norm


concept_normalizer = ConceptNormalizer()

# 进程内锁，用于追加 alias 写文件时避免并发写乱
_aliases_file_lock = threading.Lock()


def append_aliases_and_reload(
    alias_suggestions: List[Dict[str, str]],
) -> None:
    """
    将 LLM 建议的别名追加到 profile_aliases.json 并重载 ConceptNormalizer。
    alias_suggestions 每项需含 "alias" 与 "canonical" 键；已存在的 alias 不覆盖。
    """
    if not alias_suggestions:
        return
    base_dir = Path(__file__).parent
    alias_path = base_dir / "profile_aliases.json"
    with _aliases_file_lock:
        try:
            raw: Dict = {}
            if alias_path.exists():
                with alias_path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
            aliases = dict(raw.get("aliases") or {})
            for item in alias_suggestions:
                if not isinstance(item, dict):
                    continue
                alias = item.get("alias") or ""
                canonical = item.get("canonical") or ""
                if alias and canonical and alias != canonical:
                    aliases[alias] = canonical
            raw["aliases"] = aliases
            with alias_path.open("w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            concept_normalizer.reload_aliases()
            logger.info("[Profile] 已追加 %d 个别名并重载", len(alias_suggestions))
        except Exception as exc:
            logger.warning("[Profile] 追加别名失败: %s", exc)


# ==============================
# 活动类型与增量向量
# ==============================

def get_activity_vector(activity: str) -> ActivityVector:
    """
    根据学习活动类型获取三维增量向量。
    若未配置该类型，则使用 explain 的权重作为兜底。
    """
    if activity in profile_config.activity_weights:
        return profile_config.activity_weights[activity]
    return profile_config.activity_weights.get("explain", ActivityVector(0.05, 0.03, 0.02))


def _clamp01(value: float) -> float:
    """将数值裁剪到 [0, 1] 区间。"""
    return max(0.0, min(1.0, value))


# ==============================
# SQLite 画像存储与聚合
# ==============================

async def upsert_concept_profile(
    concept_key: str,
    delta_u: float,
    delta_r: float,
    delta_a: float,
    user_id: str = ANONYMOUS_USER_ID,
) -> None:
    """
    将一次学习事件的增量累加到某个概念的画像上。

    Args:
        concept_key: 规范化后的概念名
        delta_u: 理解维度增量
        delta_r: 推理维度增量
        delta_a: 应用维度增量
        user_id: 用户 ID（当前单用户，默认 anonymous）
    """
    if not concept_key:
        return

    now = datetime.utcnow().isoformat()

    async with get_db_connection() as db:
        # 读取已有画像
        cursor = await db.execute(
            """
            SELECT u, r, a, times, last_practice
            FROM concept_profiles
            WHERE concept_key = ? AND user_id = ?
            """,
            (concept_key, user_id),
        )
        row = await cursor.fetchone()

        if row:
            old_u = float(row["u"])
            old_r = float(row["r"])
            old_a = float(row["a"])
            old_times = int(row["times"])

            new_u = _clamp01(old_u + delta_u)
            new_r = _clamp01(old_r + delta_r)
            new_a = _clamp01(old_a + delta_a)
            new_times = old_times + 1

            await db.execute(
                """
                UPDATE concept_profiles
                SET u = ?, r = ?, a = ?, times = ?, last_practice = ?
                WHERE concept_key = ? AND user_id = ?
                """,
                (new_u, new_r, new_a, new_times, now, concept_key, user_id),
            )
        else:
            await db.execute(
                """
                INSERT INTO concept_profiles
                    (concept_key, user_id, u, r, a, times, last_practice)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    concept_key,
                    user_id,
                    _clamp01(delta_u),
                    _clamp01(delta_r),
                    _clamp01(delta_a),
                    1,
                    now,
                ),
            )

        await db.commit()


async def delete_concept_profile(
    concept_key: str,
    user_id: str = ANONYMOUS_USER_ID,
) -> None:
    """
    从概念画像中删除该概念（仅删 concept_profiles 行，不删 conversation_concepts）。
    """
    if not concept_key:
        return
    async with get_db_connection() as db:
        await db.execute(
            "DELETE FROM concept_profiles WHERE concept_key = ? AND user_id = ?",
            (concept_key, user_id),
        )
        await db.commit()


async def get_all_profiles(
    user_id: str = ANONYMOUS_USER_ID,
) -> List[ConceptProfile]:
    """
    获取用户的所有概念画像。
    按综合得分从高到低排序。
    """
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT concept_key, u, r, a, times, last_practice
            FROM concept_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    profiles: List[ConceptProfile] = []
    for row in rows:
        last_practice_raw = row["last_practice"]
        last_dt: Optional[datetime] = None
        if last_practice_raw:
            try:
                last_dt = datetime.fromisoformat(last_practice_raw)
            except ValueError:
                last_dt = None

        profiles.append(
            ConceptProfile(
                concept_key=row["concept_key"],
                u=float(row["u"]),
                r=float(row["r"]),
                a=float(row["a"]),
                times=int(row["times"]),
                last_practice=last_dt,
            ),
        )

    profiles.sort(key=lambda p: p.score, reverse=True)
    return profiles


async def get_weak_profiles(
    user_id: str = ANONYMOUS_USER_ID,
    limit: int = 10,
) -> List[ConceptProfile]:
    """
    获取用户的薄弱概念列表。
    按理解维度 U 从低到高排序，返回前 N 个。
    """
    profiles = await get_all_profiles(user_id=user_id)
    if not profiles:
        return []
    profiles_sorted = sorted(profiles, key=lambda p: p.u)
    return profiles_sorted[: max(1, limit)]


async def record_conversation_concepts(
    conversation_id: str,
    concept_keys: List[str],
    user_id: str = ANONYMOUS_USER_ID,
) -> None:
    """
    记录某轮对话涉及的概念，用于按对话 id 检索父/祖先节点的画像概念。
    重复 (conversation_id, concept_key, user_id) 会忽略。
    """
    if not conversation_id or not concept_keys:
        return
    async with get_db_connection() as db:
        for key in concept_keys:
            if not key:
                continue
            await db.execute(
                """
                INSERT OR IGNORE INTO conversation_concepts
                    (conversation_id, concept_key, user_id)
                VALUES (?, ?, ?)
                """,
                (conversation_id, key, user_id),
            )
        await db.commit()


async def get_concepts_by_conversation_ids(
    conversation_ids: List[str],
    user_id: str = ANONYMOUS_USER_ID,
) -> List[str]:
    """
    按对话 id 列表查询出现过的 concept_key，去重返回。
    供递归追问时作为「祖先概念」传入 LLM。
    """
    if not conversation_ids:
        return []
    async with get_db_connection() as db:
        placeholders = ",".join("?" * len(conversation_ids))
        cursor = await db.execute(
            f"""
            SELECT DISTINCT concept_key
            FROM conversation_concepts
            WHERE conversation_id IN ({placeholders}) AND user_id = ?
            """,
            (*conversation_ids, user_id),
        )
        rows = await cursor.fetchall()
    return [row["concept_key"] for row in rows]


async def get_learning_plan(user_id: str = ANONYMOUS_USER_ID) -> List[str]:
    """
    获取用户学习计划中的概念列表（concept_key 顺序按插入顺序）。
    """
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            SELECT concept_key FROM learning_plan
            WHERE user_id = ?
            ORDER BY rowid
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [row["concept_key"] for row in rows]


async def add_to_learning_plan(
    concept_key: str,
    user_id: str = ANONYMOUS_USER_ID,
) -> None:
    """将概念加入用户学习计划；已存在则忽略。"""
    if not concept_key:
        return
    async with get_db_connection() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO learning_plan (user_id, concept_key)
            VALUES (?, ?)
            """,
            (user_id, concept_key),
        )
        await db.commit()


async def remove_from_learning_plan(
    concept_key: str,
    user_id: str = ANONYMOUS_USER_ID,
) -> None:
    """从用户学习计划中移除概念。"""
    if not concept_key:
        return
    async with get_db_connection() as db:
        await db.execute(
            "DELETE FROM learning_plan WHERE user_id = ? AND concept_key = ?",
            (user_id, concept_key),
        )
        await db.commit()


async def apply_learning_event_to_concepts(
    raw_concepts: List[str],
    activity: Optional[str],
    user_id: str = ANONYMOUS_USER_ID,
    conversation_id: Optional[str] = None,
) -> ActivityVector:
    """
    将一次学习事件应用到一组概念：
    - 对每个原始概念做归一化，得到规范名
    - 根据活动类型查找三维增量，累加到每个概念的画像上
    - 若传入 conversation_id，将该轮涉及的概念写入 conversation_concepts

    Returns:
        本次事件的增量向量（用于在节点上计算简单的 mastery_score）
    """
    if not raw_concepts:
        return ActivityVector(0.0, 0.0, 0.0)

    effective = (activity or "").strip().lower() or "explain"
    vec = get_activity_vector(effective)

    normalized_names: List[str] = []
    for raw in raw_concepts:
        norm = concept_normalizer.normalize(raw)
        if norm:
            normalized_names.append(norm)

    if not normalized_names:
        return ActivityVector(0.0, 0.0, 0.0)

    # 对每个规范概念应用同样的增量
    for name in normalized_names:
        await upsert_concept_profile(
            concept_key=name,
            delta_u=vec.u,
            delta_r=vec.r,
            delta_a=vec.a,
            user_id=user_id,
        )

    if conversation_id:
        await record_conversation_concepts(
            conversation_id=conversation_id,
            concept_keys=normalized_names,
            user_id=user_id,
        )

    return vec

