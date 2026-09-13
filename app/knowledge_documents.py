"""Deterministic, local-only parsing for knowledge-base text documents."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath


MAX_DOCUMENT_BYTES = 512 * 1024
MAX_SECTION_CHARACTERS = 800
MAX_DOCUMENT_SECTIONS = 1000


class KnowledgeDocumentError(ValueError):
    def __init__(self, error_code: str, message: str, *, status_code: int = 422):
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class ParsedSection:
    ordinal: int
    heading_path: str
    anchor: str
    content: str
    content_sha256: str


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    media_type: str
    byte_size: int
    content_sha256: str
    sections: tuple[ParsedSection, ...]


class KnowledgeDocumentParser:
    """Parse bytes without file-system, network, browser, or model access."""

    @staticmethod
    def safe_filename(filename: str) -> str:
        value = str(filename or "").replace("\\", "/").split("/")[-1]
        value = "".join(ch for ch in value if ch >= " " and ch != "\x7f").strip()
        if not value or len(value) > 180:
            raise KnowledgeDocumentError("knowledge_document_invalid", "文件名无效")
        return value

    @classmethod
    def parse_bytes(cls, filename: str, content: bytes) -> ParsedDocument:
        safe_name = cls.safe_filename(filename)
        suffix = PurePath(safe_name).suffix.casefold()
        if suffix not in {".md", ".markdown", ".txt"}:
            raise KnowledgeDocumentError(
                "knowledge_document_type", "仅支持 Markdown 和 TXT 文档", status_code=415
            )
        if not isinstance(content, bytes):
            raise KnowledgeDocumentError("knowledge_document_invalid", "文档内容无效")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise KnowledgeDocumentError(
                "knowledge_document_too_large", "文档不能超过 512 KiB", status_code=413
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KnowledgeDocumentError("knowledge_document_encoding", "文档必须使用 UTF-8 编码") from exc
        if "\x00" in text:
            raise KnowledgeDocumentError("knowledge_document_invalid", "文档包含不支持的 NUL 字符")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise KnowledgeDocumentError("knowledge_document_empty", "文档不能为空")
        media_type = "text/plain" if suffix == ".txt" else "text/markdown"
        chunks = cls._text_chunks(safe_name, text) if media_type == "text/plain" else cls._markdown_chunks(safe_name, text)
        sections = []
        ordinal = 0
        for heading, body in chunks:
            for piece in cls._split_body(body):
                ordinal += 1
                if ordinal > MAX_DOCUMENT_SECTIONS:
                    raise KnowledgeDocumentError(
                        "knowledge_document_too_many_sections",
                        "文档分段过多，请合并过短段落后重试",
                    )
                normalized = unicodedata.normalize("NFKC", piece).strip()
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                anchor_base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKC", heading).casefold()).strip("-")
                sections.append(ParsedSection(ordinal, heading, f"{anchor_base or 'section'}-{ordinal}", piece.strip(), digest))
        if not sections:
            raise KnowledgeDocumentError("knowledge_document_empty", "文档没有可导入内容")
        return ParsedDocument(
            filename=safe_name,
            media_type=media_type,
            byte_size=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
            sections=tuple(sections),
        )

    @staticmethod
    def _text_chunks(filename: str, text: str) -> list[tuple[str, str]]:
        heading = PurePath(filename).stem or "文档"
        return [(heading, block) for block in re.split(r"\n\s*\n", text) if block.strip()]

    @staticmethod
    def _markdown_chunks(filename: str, text: str) -> list[tuple[str, str]]:
        heading_stack: list[str] = []
        current_heading = PurePath(filename).stem or "文档"
        body: list[str] = []
        result: list[tuple[str, str]] = []
        fenced = False
        fence_marker = ""
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                marker = stripped[:3]
                if not fenced:
                    fenced, fence_marker = True, marker
                elif marker == fence_marker:
                    fenced = False
                body.append(line)
                continue
            match = None if fenced else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if match:
                if "\n".join(body).strip():
                    result.append((current_heading, "\n".join(body)))
                level, title = len(match.group(1)), match.group(2).strip()
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_heading = " / ".join(heading_stack)
                body = []
            else:
                body.append(line)
        if "\n".join(body).strip():
            result.append((current_heading, "\n".join(body)))
        return result

    @staticmethod
    def _split_body(body: str) -> list[str]:
        result: list[str] = []
        for paragraph in (part.strip() for part in re.split(r"\n\s*\n", body)):
            while len(paragraph) > MAX_SECTION_CHARACTERS:
                window = paragraph[:MAX_SECTION_CHARACTERS]
                cut = max(window.rfind(mark) + 1 for mark in ("。", "！", "？", ".", "!", "?", "\n"))
                if cut < MAX_SECTION_CHARACTERS // 2:
                    cut = MAX_SECTION_CHARACTERS
                result.append(paragraph[:cut].strip())
                paragraph = paragraph[cut:].strip()
            if paragraph:
                result.append(paragraph)
        return result


__all__ = [
    "KnowledgeDocumentError",
    "KnowledgeDocumentParser",
    "MAX_DOCUMENT_SECTIONS",
    "ParsedDocument",
    "ParsedSection",
]
