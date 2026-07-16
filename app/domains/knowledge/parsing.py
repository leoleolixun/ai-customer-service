import hashlib
import io
import re
from dataclasses import dataclass

import jieba
from pypdf import PdfReader

from app.core.errors import AppError

SUPPORTED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}

LEXICAL_QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "下单": ("订单",),
    "拿货": ("自提", "到店"),
}


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    content: str
    heading_path: list[str]
    lexical_text: str
    content_hash: str


def extract_text(content: bytes, mime_type: str) -> str:
    if mime_type in {"text/plain", "text/markdown"}:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(
                status_code=400,
                code="document_encoding_invalid",
                title="Invalid document encoding",
                detail="Text and Markdown documents must use UTF-8 encoding.",
            ) from exc
    if mime_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            if len(reader.pages) > 200:
                raise AppError(
                    status_code=400,
                    code="pdf_page_limit_exceeded",
                    title="PDF is too large",
                    detail="PDF documents may contain at most 200 pages in V1.0.",
                )
            pages = [page.extract_text() or "" for page in reader.pages]
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                status_code=400,
                code="pdf_parse_failed",
                title="PDF parsing failed",
                detail="The PDF does not contain extractable text or is invalid.",
            ) from exc
        text = "\n\n".join(pages)
        if not text.strip():
            raise AppError(
                status_code=400,
                code="pdf_text_missing",
                title="PDF text missing",
                detail="Scanned PDFs are not supported in V1.0.",
            )
        return text
    raise AppError(
        status_code=415,
        code="document_type_unsupported",
        title="Unsupported document type",
        detail="Only UTF-8 TXT, Markdown, and text-based PDF files are supported.",
    )


def chunk_text(text: str, *, target_tokens: int = 450, max_tokens: int = 600) -> list[ChunkDraft]:
    normalized = _normalize(text)
    if not normalized:
        raise AppError(
            status_code=400,
            code="document_empty",
            title="Document is empty",
            detail="The document does not contain usable text.",
        )
    blocks = _structural_blocks(normalized)
    chunks: list[ChunkDraft] = []
    current: list[str] = []
    heading_path: list[str] = []
    current_heading: list[str] = []
    token_count = 0

    for block, headings in blocks:
        block_tokens = _tokens(block)
        if len(block_tokens) > max_tokens:
            if current:
                chunks.append(_draft("\n\n".join(current), current_heading))
                current = []
                token_count = 0
            for part in _split_long_block(block, max_tokens):
                chunks.append(_draft(part, headings))
            continue
        if current and token_count + len(block_tokens) > target_tokens:
            chunks.append(_draft("\n\n".join(current), current_heading))
            overlap = current[-1:] if current else []
            current = overlap
            token_count = sum(len(_tokens(item)) for item in overlap)
        if headings:
            heading_path = headings
        current_heading = list(heading_path)
        current.append(block)
        token_count += len(block_tokens)

    if current:
        chunks.append(_draft("\n\n".join(current), current_heading))
    return chunks


def lexicalize(text: str) -> str:
    words = [token.strip().lower() for token in jieba.lcut(text) if token.strip()]
    normalized = text.casefold()
    for phrase, expansions in LEXICAL_QUERY_EXPANSIONS.items():
        if phrase in normalized:
            words.extend(expansions)
    return " ".join(words)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _structural_blocks(text: str) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    headings: list[str] = []
    for raw_block in re.split(r"\n\s*\n", text):
        block = raw_block.strip()
        if not block:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", block.splitlines()[0])
        if heading_match:
            level = len(heading_match.group(1))
            headings = [*headings[: level - 1], heading_match.group(2).strip()]
        blocks.append((block, list(headings)))
    return blocks


def _split_long_block(block: str, max_tokens: int) -> list[str]:
    approximate_chars = max_tokens * 2
    return [
        block[index : index + approximate_chars].strip()
        for index in range(0, len(block), approximate_chars)
        if block[index : index + approximate_chars].strip()
    ]


def _tokens(text: str) -> list[str]:
    return [token for token in jieba.lcut(text) if token.strip()]


def _draft(content: str, heading_path: list[str]) -> ChunkDraft:
    return ChunkDraft(
        content=content,
        heading_path=list(heading_path),
        lexical_text=lexicalize(content),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
