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


def chunk_text(
    text: str,
    *,
    target_tokens: int = 450,
    max_tokens: int = 600,
    overlap_ratio: float = 0.1,
) -> list[ChunkDraft]:
    if target_tokens < 1 or max_tokens < target_tokens:
        raise ValueError("chunk token limits must satisfy 1 <= target_tokens <= max_tokens")
    if not 0 <= overlap_ratio < 1:
        raise ValueError("overlap_ratio must be between 0 (inclusive) and 1 (exclusive)")
    normalized = _normalize(text)
    if not normalized:
        raise AppError(
            status_code=400,
            code="document_empty",
            title="Document is empty",
            detail="The document does not contain usable text.",
        )
    overlap_tokens = max(1, round(target_tokens * overlap_ratio)) if overlap_ratio else 0
    blocks = [
        (part, headings)
        for block, headings in _merge_faq_blocks(_structural_blocks(normalized))
        for part in _split_long_block(block, max_tokens, overlap_tokens)
    ]
    chunks: list[ChunkDraft] = []
    current: list[str] = []
    current_heading: list[str] = []
    token_count = 0

    for block, headings in blocks:
        block_token_count = len(_tokens(block))
        if current and token_count + block_token_count > target_tokens:
            emitted = "\n\n".join(current)
            chunks.append(_draft(emitted, current_heading))
            overlap = _tail_by_tokens(emitted, overlap_tokens)
            if (
                headings == current_heading
                and overlap
                and len(_tokens(overlap)) + block_token_count <= max_tokens
            ):
                current = [overlap]
                token_count = len(_tokens(overlap))
            else:
                current = []
                token_count = 0
            current_heading = list(headings)
        if not current:
            current_heading = list(headings)
        current.append(block)
        token_count += block_token_count

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


def _merge_faq_blocks(
    blocks: list[tuple[str, list[str]]],
) -> list[tuple[str, list[str]]]:
    merged: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(blocks):
        block, headings = blocks[index]
        if index + 1 < len(blocks) and _is_question_block(block):
            answer, _answer_headings = blocks[index + 1]
            if _is_answer_block(answer):
                merged.append((f"{block}\n\n{answer}", headings))
                index += 2
                continue
        merged.append((block, headings))
        index += 1
    return merged


def _is_question_block(block: str) -> bool:
    first_line = re.sub(r"^#{1,6}\s+", "", block.splitlines()[0]).strip().casefold()
    return bool(re.match(r"^(?:q(?:uestion)?|问题|问)\s*[:：]", first_line))  # noqa: RUF001


def _is_answer_block(block: str) -> bool:
    first_line = re.sub(r"^#{1,6}\s+", "", block.splitlines()[0]).strip().casefold()
    return bool(re.match(r"^(?:a(?:nswer)?|答案|答)\s*[:：]", first_line))  # noqa: RUF001


def _split_long_block(block: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    if len(_tokens(block)) <= max_tokens:
        return [block]

    separator, segments = _logical_segments(block)
    expanded = [
        part for segment in segments for part in _token_windows(segment, max_tokens, overlap_tokens)
    ]
    parts: list[str] = []
    current: list[str] = []
    token_count = 0
    for segment in expanded:
        segment_tokens = len(_tokens(segment))
        if current and token_count + segment_tokens > max_tokens:
            emitted = separator.join(current).strip()
            parts.append(emitted)
            overlap = _tail_by_tokens(emitted, overlap_tokens)
            if overlap and len(_tokens(overlap)) + segment_tokens <= max_tokens:
                current = [overlap]
                token_count = len(_tokens(overlap))
            else:
                current = []
                token_count = 0
        current.append(segment)
        token_count += segment_tokens
    if current:
        parts.append(separator.join(current).strip())
    return parts


def _logical_segments(block: str) -> tuple[str, list[str]]:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) > 1:
        return "\n", lines
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?；;\.])\s*", block)  # noqa: RUF001
        if sentence.strip()
    ]
    return " ", sentences or [block]


def _token_windows(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    spans = [item for item in jieba.tokenize(text) if item[0].strip()]
    if len(spans) <= max_tokens:
        return [text.strip()]
    step = max(1, max_tokens - min(overlap_tokens, max_tokens - 1))
    windows: list[str] = []
    for start in range(0, len(spans), step):
        selected = spans[start : start + max_tokens]
        if not selected:
            break
        windows.append(text[selected[0][1] : selected[-1][2]].strip())
        if start + max_tokens >= len(spans):
            break
    return windows


def _tail_by_tokens(text: str, token_count: int) -> str:
    if token_count <= 0:
        return ""
    spans = [item for item in jieba.tokenize(text) if item[0].strip()]
    if not spans:
        return ""
    start = spans[max(0, len(spans) - token_count)][1]
    return text[start:].strip()


def _tokens(text: str) -> list[str]:
    return [token for token in jieba.lcut(text) if token.strip()]


def _draft(content: str, heading_path: list[str]) -> ChunkDraft:
    return ChunkDraft(
        content=content,
        heading_path=list(heading_path),
        lexical_text=lexicalize(content),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
