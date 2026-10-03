"""Bank-guarantee document text loading for extraction."""

from __future__ import annotations

import io
from pathlib import Path


def load_document_text(path: Path) -> str:
    """Return plain text suitable for the BG extraction prompt.

    Supports .msg (Outlook) with .docx attachments, .docx, and plain text.
    PDF/image bytes are not converted here — callers should use a vision path.
    """

    suffix = path.suffix.lower()
    if suffix == ".msg":
        return _text_from_msg(path)
    if suffix == ".docx":
        return _text_from_docx_bytes(path.read_bytes())
    if suffix in {".txt", ".md", ".html", ".htm"}:
        return path.read_text(encoding="utf-8", errors="replace")
    # Fall back to best-effort UTF-8 for unknown text-like payloads.
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"unsupported document type for text extraction: {path.name}"
        ) from exc


def _text_from_msg(path: Path) -> str:
    import extract_msg  # type: ignore[import-untyped]

    msg = extract_msg.Message(str(path))
    parts: list[str] = []
    subject = (msg.subject or "").strip()
    if subject:
        parts.append(f"Subject: {subject}")
    body = (msg.body or "").strip()
    if body:
        parts.append(body)
    for attachment in msg.attachments:
        name = attachment.longFilename or attachment.shortFilename or "attachment"
        data = attachment.data
        if not data:
            continue
        lower = name.lower()
        if lower.endswith(".docx"):
            parts.append(f"--- attachment: {name} ---")
            parts.append(_text_from_docx_bytes(data))
        elif lower.endswith((".txt", ".md")):
            parts.append(f"--- attachment: {name} ---")
            parts.append(data.decode("utf-8", errors="replace"))
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError(f"no extractable text in {path.name}")
    return text


def _text_from_docx_bytes(data: bytes) -> str:
    from docx import Document  # type: ignore[import-untyped]

    document = Document(io.BytesIO(data))
    lines = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [
                c.text.strip().replace("\n", " ") for c in row.cells if c.text.strip()
            ]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)
