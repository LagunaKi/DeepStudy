"""Deterministic document parsing and structure-aware chunking."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".scss",
    ".sh",
    ".bash",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | {".pdf"}


class DocumentParseError(ValueError):
    """Raised when a supported document cannot be decoded or parsed."""


@dataclass(frozen=True)
class Section:
    text: str
    section: str
    page: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    sections: list[Section]
    page_count: int | None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    chunk_index: int
    text: str
    section: str
    page: int | None
    content_hash: str


def safe_filename(filename: str) -> str:
    """Discard path components and control characters from an upload name."""
    name = Path(filename or "upload").name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:180] or "upload"


def file_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "unsupported"


def parse_document(filename: str, payload: bytes) -> ParsedDocument:
    """Parse supported bytes while retaining page and section provenance."""
    kind = file_kind(filename)
    if kind == "unsupported" or kind == "image":
        raise DocumentParseError(f"不支持将 {Path(filename).suffix or '该格式'} 解析为文档")
    if kind == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(payload))
            sections = []
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                if text:
                    sections.append(Section(text=text, section=f"第 {index} 页", page=index))
            if not sections:
                raise DocumentParseError("PDF 中没有可提取文本；扫描版 PDF 请先进行 OCR")
            return ParsedDocument(sections=sections, page_count=len(reader.pages))
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParseError(f"PDF 解析失败：{exc}") from exc

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("文本文件必须使用 UTF-8 编码") from exc
    if not text.strip():
        raise DocumentParseError("文件内容为空")
    if Path(filename).suffix.lower() in {".md", ".markdown"}:
        return ParsedDocument(sections=_markdown_sections(text), page_count=None)
    code_suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"}
    if Path(filename).suffix.lower() in code_suffixes:
        return ParsedDocument(sections=_code_sections(text), page_count=None)
    return ParsedDocument(sections=[Section(text=text.strip(), section="正文")], page_count=None)


def _markdown_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    heading_stack: list[tuple[int, str]] = []
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            title = " / ".join(title for _, title in heading_stack) or "正文"
            sections.append(Section(text=content, section=title))
        body.clear()

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        heading_stack[:] = [(n, title) for n, title in heading_stack if n < level]
        heading_stack.append((level, match.group(2).strip()))
    flush()
    return sections or [Section(text=text.strip(), section="正文")]


def _code_sections(text: str) -> list[Section]:
    pattern = re.compile(
        r"^(?:async\s+def|def|class|export\s+(?:async\s+)?function|function|interface|type|public\s+class)\s+([\w$]+)",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return [Section(text=text.strip(), section="代码")]
    sections: list[Section] = []
    if text[: matches[0].start()].strip():
        sections.append(Section(text=text[: matches[0].start()].strip(), section="模块说明"))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(Section(text=text[match.start() : end].strip(), section=match.group(1)))
    return sections


def chunk_document(
    document_id: str,
    version: int,
    parsed: ParsedDocument,
    *,
    target_chars: int = 900,
    overlap_chars: int = 140,
) -> list[DocumentChunk]:
    """Chunk on paragraph/line boundaries with bounded character overlap."""
    chunks: list[DocumentChunk] = []
    for section in parsed.sections:
        blocks = [item.strip() for item in re.split(r"\n\s*\n", section.text) if item.strip()]
        if not blocks:
            continue
        current = ""
        for block in blocks:
            if len(block) > target_chars:
                if current:
                    _append_chunk(chunks, document_id, version, current, section)
                    current = ""
                start = 0
                while start < len(block):
                    end = min(len(block), start + target_chars)
                    _append_chunk(chunks, document_id, version, block[start:end], section)
                    if end == len(block):
                        break
                    start = max(start + 1, end - overlap_chars)
                continue
            candidate = f"{current}\n\n{block}".strip() if current else block
            if current and len(candidate) > target_chars:
                _append_chunk(chunks, document_id, version, current, section)
                overlap = current[-overlap_chars:].lstrip()
                current = f"{overlap}\n\n{block}".strip()
            else:
                current = candidate
        if current:
            _append_chunk(chunks, document_id, version, current, section)
    return chunks


def _append_chunk(
    chunks: list[DocumentChunk],
    document_id: str,
    version: int,
    text: str,
    section: Section,
) -> None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    stable = hashlib.sha256(f"{document_id}:{version}:{len(chunks)}:{digest}".encode()).hexdigest()[
        :24
    ]
    chunks.append(
        DocumentChunk(
            chunk_id=f"chk_{stable}",
            chunk_index=len(chunks),
            text=text.strip(),
            section=section.section,
            page=section.page,
            content_hash=digest,
        )
    )


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
