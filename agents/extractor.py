"""
agents/extractor.py
DITA Converter Tool — Extractor Agent

Parses PDF and DOCX files into a normalised Content Tree (list of block dicts).
Each block is produced by make_block() and carries: type, text, metadata.

Font-size thresholds calibrated against Gilbarco Passport manuals:
  H1 = 18pt  |  H2 = 14pt  |  H3 = 12pt
  Note header = 15pt  |  Steps/Figures = 10pt
  Body = 11pt  |  Headers/Footers = 9pt or less

Session: S-02 | Reviewer-signed-off
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Block factory
# ---------------------------------------------------------------------------

VALID_TYPES = {
    "heading", "paragraph", "list_item", "table",
    "figure", "note_header", "note_inline", "code_block", "dropped",
}


def make_block(
    block_type: str,
    text: str,
    level: int = 0,
    is_header: bool = False,
    rows: list | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    if block_type not in VALID_TYPES:
        raise ValueError(f"Unknown block type: {block_type!r}")
    block: dict[str, Any] = {
        "type": block_type,
        "text": text.strip() if text else "",
        "level": level,
        "is_header": is_header,
        "rows": rows or [],
        "metadata": metadata or {},
        "dita_element": None,
    }
    return block


# ---------------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------------

class ExtractorError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Drop-pattern helpers
# ---------------------------------------------------------------------------

_DROP_PATTERNS = [
    re.compile(r"^Page \d+"),
    re.compile(r"MDE-\w+.+\d{4}$"),
    re.compile(r"^©\s*\d{4}"),
    re.compile(r"^Table of Contents"),
    re.compile(r"^Related Documents"),
]


def _parse_page_range(page_range: str, total_pages: int) -> set[int]:
    """
    Parse a page range string like "1-5, 8, 12-15" into a set of
    0-based page indices. Returns None if page_range is empty (= all pages).

    Examples:
        "1-5, 8"     → {0, 1, 2, 3, 4, 7}
        "3"          → {2}
        ""           → None (all pages)
    """
    if not page_range or not page_range.strip():
        return None
    indices = set()
    for part in page_range.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = max(1, int(start_s.strip()))
            end   = min(total_pages, int(end_s.strip()))
            for i in range(start, end + 1):
                indices.add(i - 1)  # convert to 0-based
        else:
            page_num = int(part)
            if 1 <= page_num <= total_pages:
                indices.add(page_num - 1)
    return indices if indices else None


_BLANK_PAGE_PATTERNS = [
    re.compile(r"^this\s+page\s+(is\s+)?intentionally\s+(left\s+)?blank", re.IGNORECASE),
    re.compile(r"^intentionally\s+(left\s+)?blank", re.IGNORECASE),
    re.compile(r"^this\s+page\s+left\s+blank", re.IGNORECASE),
    re.compile(r"^blank\s+page$", re.IGNORECASE),
]


def _should_drop(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if len(t) < 3:
        return True
    for pat in _DROP_PATTERNS:
        if pat.search(t):
            return True
    return False


def _is_blank_page(page_text: str) -> bool:
    """Return True if the page contains only a blank-page notice or nothing."""
    cleaned = page_text.strip()
    if not cleaned:
        return True
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    meaningful = [l for l in lines if not _should_drop(l)]
    if not meaningful:
        return True
    full = " ".join(meaningful)
    for pat in _BLANK_PAGE_PATTERNS:
        if pat.match(full):
            return True
    return False


# ---------------------------------------------------------------------------
# PDF Extractor
# ---------------------------------------------------------------------------

# Font-size → heading level mapping (calibrated on Gilbarco manuals)
_H1_SIZE   = 17.0   # ≥ 17 pt bold → H1
_H2_SIZE   = 13.5   # ≥ 13.5 pt bold → H2
_H3_SIZE   = 11.5   # ≥ 11.5 pt bold → H3
_NOTE_SIZE = 14.0   # ≥ 14 pt bold → potential note header
_STEP_SIZE =  9.5   # ≤ 9.5 pt → running header/footer (drop)
_DROP_SIZE =  9.5


def _classify_line(word_group: list[dict]) -> tuple[str, int]:
    """Return (block_type, level) for a group of words on one line."""
    if not word_group:
        return "paragraph", 0

    sizes = [w.get("size", 11) for w in word_group]
    avg_size = sum(sizes) / len(sizes)

    fonts = [w.get("fontname", "") for w in word_group]
    is_bold = any("Bold" in f or "BoldMT" in f for f in fonts)

    if avg_size <= _DROP_SIZE:
        return "dropped", 0

    if is_bold:
        if avg_size >= _H1_SIZE:
            return "heading", 1
        if avg_size >= _NOTE_SIZE:
            return "note_header", 0
        if avg_size >= _H2_SIZE:
            return "heading", 2
        if avg_size >= _H3_SIZE:
            return "heading", 3

    return "paragraph", 0


def extract_pdf(file_bytes: bytes, page_range: str = "") -> list[dict]:
    """Extract a content tree from a text-based PDF.

    Args:
        file_bytes:  Raw bytes of the PDF file.
        page_range:  Optional page range string e.g. "1-5, 8, 12-15".
                     Leave empty to extract all pages.
    """
    import pdfplumber  # type: ignore

    blocks: list[dict] = []
    dropped_count = 0
    blank_pages_skipped = 0

    with pdfplumber.open(file_bytes if hasattr(file_bytes, "read") else
                         __import__("io").BytesIO(file_bytes)) as pdf:

        total_pages = len(pdf.pages)
        total_chars = sum(len(p.extract_text() or "") for p in pdf.pages)
        if total_chars < 50:
            raise ExtractorError(
                "No extractable text found. This appears to be a scanned PDF. "
                "Please supply a text-based (digital) PDF."
            )

        # Resolve page range filter
        page_indices = _parse_page_range(page_range, total_pages)  # None = all pages

        for page_idx, page in enumerate(pdf.pages):

            # ---- Page range filter (B-001) ----
            if page_indices is not None and page_idx not in page_indices:
                continue

            # ---- Blank page detection (B-002) ----
            page_text = page.extract_text() or ""
            if _is_blank_page(page_text):
                blank_pages_skipped += 1
                continue

            # ---- Tables first ----
            tables = page.extract_tables()
            table_bboxes = [t.bbox for t in page.find_tables()] if tables else []

            for table_data in tables:
                if not table_data:
                    continue
                rows = []
                for row in table_data:
                    rows.append([cell or "" for cell in row])
                is_hdr = False
                if rows:
                    first = " ".join(rows[0]).upper()
                    _note_kw = {"WARNING", "CAUTION", "DANGER", "IMPORTANT INFORMATION"}
                    is_hdr = any(kw in first for kw in _note_kw) or True
                blocks.append(make_block("table", "", is_header=True, rows=rows))

            # ---- Words → lines ----
            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=True,
                extra_attrs=["fontname", "size"],
            )

            # Group words into lines by top-coordinate
            lines: dict[float, list] = {}
            for w in words:
                top = round(w["top"], 1)
                lines.setdefault(top, []).append(w)

            prev_para = None
            for top in sorted(lines):
                word_group = lines[top]
                text = " ".join(w["text"] for w in word_group).strip()

                if _should_drop(text):
                    dropped_count += 1
                    continue

                block_type, level = _classify_line(word_group)

                if block_type == "dropped":
                    dropped_count += 1
                    continue

                # Bullet detection
                if text.startswith(("•", "–", "-", "▪", "◆")) or \
                   re.match(r"^[●○■□▸▹►]", text):
                    text = re.sub(r"^[•–\-▪◆●○■□▸▹►]\s*", "", text)
                    block_type = "list_item"
                    meta = {"list_kind": "bullet"}
                    blocks.append(make_block(block_type, text, metadata=meta))
                    prev_para = None
                    continue

                # Numbered item detection
                num_match = re.match(r"^(\d{1,2})\s{1,4}(.+)", text)
                if num_match and block_type == "paragraph":
                    text = num_match.group(2)
                    block_type = "list_item"
                    meta = {"list_kind": "numbered", "num": int(num_match.group(1))}
                    blocks.append(make_block(block_type, text, metadata=meta))
                    prev_para = None
                    continue

                # Figure caption
                if re.match(r"^Figure\s+\d+\s*:", text, re.IGNORECASE):
                    blocks.append(make_block("figure", text))
                    prev_para = None
                    continue

                # Inline note
                if re.match(r"^Notes?:", text, re.IGNORECASE):
                    blocks.append(make_block("note_inline", text))
                    prev_para = None
                    continue

                # Code block signals
                code_signals = ("telnet ", "C:\\>", "$ ", "http://")
                if any(text.startswith(s) for s in code_signals):
                    blocks.append(make_block("code_block", text))
                    prev_para = None
                    continue

                # Paragraph merging (continuation lines at same style)
                if block_type == "paragraph" and prev_para is not None:
                    # Merge if previous was also a paragraph and ends mid-sentence
                    last = blocks[-1]
                    if last["type"] == "paragraph" and not last["text"].endswith((".", ":", "?")):
                        last["text"] = last["text"] + " " + text
                        continue

                blocks.append(make_block(block_type, text, level=level))
                prev_para = block_type if block_type == "paragraph" else None

    # Tag how many blocks were dropped
    for b in blocks:
        b.setdefault("metadata", {})
    if blocks:
        blocks[0]["metadata"]["dropped_count"]       = dropped_count
        blocks[0]["metadata"]["blank_pages_skipped"] = blank_pages_skipped

    return blocks


# ---------------------------------------------------------------------------
# DOCX Extractor
# ---------------------------------------------------------------------------

_DOCX_STYLE_MAP = {
    "Heading 1": ("heading", 1),
    "Heading 2": ("heading", 2),
    "Heading 3": ("heading", 3),
    "Heading 4": ("heading", 3),
    "Title":     ("heading", 1),
    "Subtitle":  ("heading", 2),
}

_DOCX_NOTE_STYLES = {"Caution", "Warning", "Note", "Important"}


def extract_docx(file_bytes: bytes, image_folder: str = "") -> list[dict]:
    """Extract a content tree from a DOCX file.

    Args:
        file_bytes: Raw bytes of the .docx file.
        image_folder: Optional path to the extracted media folder (from the
                      renamed .zip). When provided, image relationships are
                      resolved to absolute paths for DITA <image href>.
    """
    import io
    from docx import Document  # type: ignore
    from docx.oxml.ns import qn  # type: ignore

    doc = Document(io.BytesIO(file_bytes))
    blocks: list[dict] = []
    dropped_count = 0
    image_map: dict[str, str] = {}

    # Build image relationship map if folder provided
    if image_folder:
        img_dir = Path(image_folder)
        if img_dir.is_dir():
            # Map rId → absolute path by scanning rels
            for rel in doc.part.rels.values():
                if "image" in rel.reltype:
                    target = rel.target_ref  # e.g. "media/image1.png"
                    fname = Path(target).name
                    candidate = img_dir / fname
                    if candidate.exists():
                        image_map[rel.rId] = str(candidate)

    for para in doc.paragraphs:
        text = para.text.strip()
        style_name = para.style.name if para.style else ""

        if not text:
            continue

        if _should_drop(text):
            dropped_count += 1
            continue

        # Check for inline images in runs
        for run in para.runs:
            for drawing in run._element.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"):
                blip_fills = drawing.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/picture}blipFill")
                for bf in blip_fills:
                    blip = bf.find(
                        "{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
                    if blip is not None:
                        r_embed = blip.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                        img_path = image_map.get(r_embed, "")
                        caption = text or f"Image {r_embed}"
                        blocks.append(make_block(
                            "figure", caption,
                            metadata={"image_href": img_path, "r_id": r_embed}
                        ))

        # Style-driven classification
        if style_name in _DOCX_STYLE_MAP:
            btype, level = _DOCX_STYLE_MAP[style_name]
            blocks.append(make_block(btype, text, level=level))
            continue

        # Note styles
        if style_name in _DOCX_NOTE_STYLES:
            blocks.append(make_block("note_header", text))
            continue

        # List paragraph
        if "List" in style_name:
            list_kind = "numbered" if "Number" in style_name else "bullet"
            blocks.append(make_block("list_item", text, metadata={"list_kind": list_kind}))
            continue

        # Inline note prefix
        if re.match(r"^Notes?:", text, re.IGNORECASE):
            blocks.append(make_block("note_inline", text))
            continue

        # Figure caption
        if re.match(r"^Figure\s+\d+\s*:", text, re.IGNORECASE):
            blocks.append(make_block("figure", text))
            continue

        # Code style
        if "Code" in style_name or "Preformatted" in style_name:
            blocks.append(make_block("code_block", text))
            continue

        # Bullet by text prefix
        if text.startswith(("•", "–", "▪")):
            text = re.sub(r"^[•–▪]\s*", "", text)
            blocks.append(make_block("list_item", text, metadata={"list_kind": "bullet"}))
            continue

        # Numbered item
        num_match = re.match(r"^(\d{1,2})[.)]\s+(.+)", text)
        if num_match:
            blocks.append(make_block(
                "list_item", num_match.group(2),
                metadata={"list_kind": "numbered", "num": int(num_match.group(1))}
            ))
            continue

        blocks.append(make_block("paragraph", text))

    # Tables
    for table in doc.tables:
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        if rows:
            blocks.append(make_block("table", "", is_header=True, rows=rows))

    if blocks:
        blocks[0]["metadata"]["dropped_count"] = dropped_count

    return blocks
