"""运行时 Skills 目录：先扫描元数据，选中后才加载完整指令。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    intents: tuple[str, ...]
    triggers: tuple[str, ...]
    path: Path


class SkillCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "skills"
        self._metadata = self._discover()

    @property
    def metadata(self) -> tuple[SkillMetadata, ...]:
        return tuple(self._metadata)

    def _discover(self) -> list[SkillMetadata]:
        found: list[SkillMetadata] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            header: list[str] = []
            with path.open("r", encoding="utf-8") as handle:
                if handle.readline().strip() != "---":
                    continue
                for line in handle:
                    if line.strip() == "---":
                        break
                    header.append(line.rstrip())
            values: dict[str, str] = {}
            for line in header:
                key, separator, value = line.partition(":")
                if separator:
                    values[key.strip()] = value.strip()
            name = values.get("name", path.parent.name)
            found.append(
                SkillMetadata(
                    name=name,
                    description=values.get("description", ""),
                    intents=tuple(filter(None, re.split(r"\s*,\s*", values.get("intents", "")))),
                    triggers=tuple(filter(None, re.split(r"\s*,\s*", values.get("triggers", "")))),
                    path=path,
                )
            )
        return found

    def select(self, query: str, intent: str) -> SkillMetadata | None:
        normalized = query.casefold()
        scored: list[tuple[int, SkillMetadata]] = []
        for skill in self._metadata:
            score = (2 if intent in skill.intents else 0) + sum(
                4 for trigger in skill.triggers if trigger.casefold() in normalized
            )
            scored.append((score, skill))
        if not scored:
            return None
        score, selected = max(scored, key=lambda item: (item[0], item[1].name == "explain-concept"))
        return selected if score > 0 else next(
            (item for item in self._metadata if item.name == "explain-concept"), selected
        )

    @staticmethod
    def load_instructions(skill: SkillMetadata) -> str:
        """只为已经选中的 skill 加载正文，实现渐进式披露。"""
        text = skill.path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        return (parts[2] if len(parts) == 3 else text).strip()


skill_catalog = SkillCatalog()
