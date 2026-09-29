"""Reading bytes that are not text.

Two questions get asked of a binary blob here, and they are different
questions:

1. *What is it?* - answered from the leading bytes, which is the only part of
   a file format that is standardised enough to trust. An extension is a hint
   a user can change; a magic number is the file itself.
2. *Can anything be read out of it?* - for the OOXML/ODF family (docx, xlsx,
   pptx, odt) the answer is yes, because those are ZIP files full of XML. Text
   extraction is done with the standard library only: adding a PDF or
   spreadsheet dependency to read a dropped file is not a trade worth making
   yet, and these formats cover most of what people actually attach.

Everything else is reported by type and size, with a base64 prefix so a model
can still reason about the beginning of the data (or hand it to a decoder)
instead of being told the file does not exist.
"""

from __future__ import annotations

import base64
import io
import re
import zipfile
from html import unescape

# Longest signatures first, so a container test cannot shadow a specific one.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"BM", "BMP image"),
    (b"%PDF-", "PDF document"),
    (b"PK\x03\x04", "ZIP-based file"),
    (b"PK\x05\x06", "empty ZIP archive"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!\x1a\x07", "RAR archive"),
    (b"\x1f\x8b", "gzip stream"),
    (b"BZh", "bzip2 stream"),
    (b"\xfd7zXZ\x00", "XZ stream"),
    (b"\x28\xb5\x2f\xfd", "Zstandard stream"),
    (b"SQLite format 3\x00", "SQLite database"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "legacy Office document"),
    (b"\x7fELF", "ELF binary"),
    (b"MZ", "Windows executable"),
    (b"\xca\xfe\xba\xbe", "Java class or macOS universal binary"),
    (b"OggS", "Ogg stream"),
    (b"ID3", "MP3 audio"),
    (b"\xff\xfb", "MP3 audio"),
    (b"fLaC", "FLAC audio"),
    (b"RIFF", "RIFF container (WAV/AVI/WebP)"),
    (b"\x1aE\xdf\xa3", "Matroska/WebM video"),
    (b"\x00\x00\x01\x00", "ICO image"),
    (b"file format=", "Netpbm image"),
)

# Image types a vision-capable model can accept directly.
IMAGE_KINDS = frozenset({"PNG image", "JPEG image", "GIF image", "BMP image"})

# How much of a binary is handed over as base64 when nothing else can be read.
BASE64_PREFIX_BYTES = 24 * 1024

_ZIP_MEMBERS: tuple[tuple[str, str], ...] = (
    ("word/document.xml", "document text"),
    ("xl/sharedStrings.xml", "spreadsheet strings"),
    ("ppt/slides/slide1.xml", "first slide text"),
    ("content.xml", "document text"),
    ("META-INF/manifest.xml", ""),
)


def sniff(data: bytes) -> str:
    """Name the file type from its leading bytes, or "unknown binary"."""
    for signature, label in _SIGNATURES:
        if data.startswith(signature):
            return label
    return "unknown binary"


def looks_binary(data: bytes) -> bool:
    """Whether bytes are better treated as binary than as text.

    A NUL byte in the first block is the cheapest reliable signal: no text
    format in use today contains one, and UTF-16 - which does - is caught by
    the decode attempt in the caller instead.
    """
    return b"\x00" in data[:8192]


def decode_text(data: bytes) -> str | None:
    """Best-effort text decode, or None when the bytes are not text."""
    if looks_binary(data):
        return None
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def is_image(kind: str) -> bool:
    return kind in IMAGE_KINDS


def extract_zip_text(data: bytes, *, char_limit: int = 20_000) -> str | None:
    """Pull readable text out of an OOXML/ODF/zip container.

    Returns None when the archive holds nothing worth quoting - a .zip of
    photos, say - so the caller can fall back to describing the file.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError):
        return None

    chunks: list[str] = []
    with archive:
        names = set(archive.namelist())
        for member, label in _ZIP_MEMBERS:
            if member not in names or not label:
                continue
            try:
                raw = archive.read(member)
            except (KeyError, OSError, zipfile.BadZipFile):
                continue
            text = _strip_xml(raw)
            if text:
                chunks.append(f"[{label}]\n{text}")

        if not chunks:
            # Unknown layout: quote the names, which at least reveals the
            # structure of the archive rather than nothing at all.
            listing = ", ".join(sorted(names)[:40])
            return f"[archive contents] {listing}" if listing else None

    joined = "\n\n".join(chunks)
    if len(joined) > char_limit:
        joined = joined[:char_limit] + "\n... [text truncated]"
    return joined


def _strip_xml(raw: bytes) -> str:
    """Reduce an XML part to its text content."""
    try:
        text = raw.decode("utf-8", errors="replace")
    except AttributeError:  # pragma: no cover - defensive
        return ""
    # Paragraph and row boundaries become newlines so the result stays
    # readable instead of collapsing into one line.
    text = re.sub(r"</w:p>|</a:p>|</w:tr>|</text:p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def base64_prefix(data: bytes, *, byte_limit: int = BASE64_PREFIX_BYTES) -> tuple[str, bool]:
    """Base64 of the start of the payload, plus whether it was cut short."""
    cut = data[:byte_limit]
    return base64.b64encode(cut).decode("ascii"), len(cut) < len(data)


def describe_binary(data: bytes, *, byte_limit: int = BASE64_PREFIX_BYTES) -> str:
    """A textual account of a binary file for a model that cannot see bytes.

    The shape is: what it is, how big, then whatever text could be extracted,
    then the base64 prefix. Each part is labelled, because a model reading
    this needs to know which of the three it is looking at.
    """
    kind = sniff(data)
    lines = [f"[binary file: {kind}, {len(data)} bytes]"]

    extracted = extract_zip_text(data) if data.startswith(b"PK\x03\x04") else None
    if extracted:
        lines.append("")
        lines.append("[readable text extracted from the container]")
        lines.append(extracted)

    payload, truncated = base64_prefix(data, byte_limit=byte_limit)
    decoded_bytes = len(payload) // 4 * 3
    lines.append("")
    if truncated:
        lines.append(f"[base64 of the first ~{decoded_bytes} bytes; the file continues past this point]")
    else:
        lines.append("[base64 of the whole file]")
    lines.append(payload)
    return "\n".join(lines)


def image_data_uri(data: bytes, mime: str) -> str:
    """A data URI for a vision request."""
    actual = mime or "image/png"
    return f"data:{actual};base64,{base64.b64encode(data).decode('ascii')}"
