"""
DITA Converter Tool — Agent 1: Extractor
=========================================
Converts PDF and DOCX source files into a normalised Content Tree.

Font size → element map (calibrated from Gilbarco Passport manuals):
    ≥ 17pt  Arial-Bold  → H1  (chapter headings: "Feature Activation")
    ≥ 13pt  Arial-Bold  → H2  (section headings: "Before You Begin")
    ≥ 11.5pt Arial-Bold → H3  (sub-section headings)
    ≥ 14.5pt Arial-Bold → NOTE_HEADER (IMPORTANT INFORMATION callouts)
    ~10pt   Arial-Bold  → numbered step or figure caption
    ~11pt   Times       → body paragraph
    ≤ 9.4pt italic      → DROP (running headers/footers)

Session: S-02
Author: Coder
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Union

import pdfplumber
from docx import Document as DocxDocument


# ---------------------------------------------------------------------------
# Font-size thresholds (calibrated against MDE-5570A, MDE-3839Q)
# ---------------------------------------------------------------------------
PDF_H1_SIZE       = 17.0
PDF_H2_SIZE       = 13.0
PDF_H3_SIZE       = 11.5
PDF_NOTE_HDR_SIZE = 14.5
PDF_BODY_MIN_SIZE = 9.5

BULLET_CHARS = {"•", "–", "◦", "▪", "‐", "\uf020", "·"}

DROP_TEXT_PATTERNS = [
    re.compile(r"^Page\s+\d+\s+MDE-"),
    re.compile(r"^MDE-\w+\s+.+\d{4}"),
    re.compile(r"^©\s*\d{4}"),
    re.compile(r"^Table of Contents$"),
    re.compile(r"^GOLD(SM)?\s*Library$", re.IGNORECASE),
    re.compile(r"^\s*$"),
]

FIGURE_PATTERN   = re.compile(r"^Figure\s+\d+\s*:", re.IGNORECASE)
STEP_PATTERN     = re.compile(r"^(\d+)\s*[.)]\s+(.+)", re.DOTALL)
NOTE_PREFIX      = re.compile(r"^Notes?\s*:", re.IGNORECASE)
IMPORTANT_PREFIX = re.compile(r"^IMPORTANT\s*:", re.IGNORECASE)

DOCX_HEADING_STYLES = {
    "Heading 1": 1, "heading 1": 1,
    "Heading 2": 2, "heading 2": 2,
    "Heading 3": 3, "heading 3": 3,
    "Heading 4": 4, "heading 4": 4,
    "Title":     1,
}


class ExtractorError(Exception):
    """Raised when a file cannot be extracted."""
    pass


class Extractor:
    """
    Extracts structured content from PDF or DOCX files into a Content Tree.

    Usage:
        extractor = Extractor("path/to/file.pdf")
        content_tree = extractor.extract()
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

    def __init__(self, file_path: Union[str, Path]) -> None:
        self.file_path = Path(file_path)
        self._dropped_count = 0
        self._validate_file()

    def _validate_file(self) -> None:
        if not self.file_path.exists():
            raise ExtractorError(f"File not found: {self.file_path}")
        if self.file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ExtractorError(
                f"Unsupported file type: {self.file_path.suffix}. "
                f"Supported: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def extract(self) -> list[dict]:
        """
        Extract content from the source file into a Content Tree.

        Returns:
            List of content block dicts.

        Raises:
            ExtractorError: If extraction fails or PDF is image-only.
        """
        self._dropped_count = 0
        suffix = self.file_path.suffix.lower()
        try:
            if suffix == ".pdf":
                return self._extract_pdf()
            return self._extract_docx()
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(
                f"Extraction failed for {self.file_path.name}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # PDF EXTRACTION
    # ------------------------------------------------------------------

    def _extract_pdf(self) -> list[dict]:
        blocks: list[dict] = []

        with pdfplumber.open(self.file_path) as pdf:
            # Scanned PDF guard
            sample = "".join(
                (p.extract_text() or "") for p in pdf.pages[:3]
            )
            if not sample.strip():
                raise ExtractorError(
                    f"No text found in '{self.file_path.name}'. "
                    "This appears to be a scanned/image PDF. "
                    "Only text-based PDFs are supported in v1."
                )

            for page in pdf.pages:
                blocks.extend(self._extract_pdf_page(page))

        return self._merge_paragraphs(blocks)

    def _extract_pdf_page(self, page) -> list[dict]:
        page_blocks: list[dict] = []

        # Tables first
        try:
            for table_data in page.extract_tables():
                blk = self._pdf_table_to_block(table_data)
                if blk:
                    page_blocks.append(blk)
        except Exception:
            pass

        # Line-level text
        try:
            lines = page.extract_text_lines(extra_attrs=["size", "fontname"])
        except Exception:
            lines = []

        for line in lines:
            blk = self._pdf_line_to_block(line)
            if blk is None:
                self._dropped_count += 1
            else:
                page_blocks.append(blk)

        return page_blocks

    def _pdf_line_to_block(self, line: dict) -> dict | None:
        text = line.get("text", "").strip()
        if not text:
            return None

        chars = line.get("chars", [])
        if not chars:
            return None

        dominant = chars[0]
        size     = round(dominant.get("size", 11.0), 1)
        fontname = dominant.get("fontname", "")
        is_bold  = any(k in fontname for k in ("Bold", "BoldMT"))
        is_italic = any(k in fontname for k in ("Italic", "ItalicMT"))

        # Drop running headers/footers (small italic Times lines)
        if is_italic and size <= 9.5:
            return None

        # Drop by text pattern
        for pat in DROP_TEXT_PATTERNS:
            if pat.search(text):
                return None

        # IMPORTANT INFORMATION note header
        if size >= PDF_NOTE_HDR_SIZE and is_bold and "IMPORTANT" in text.upper():
            return self.make_block("note_header", text=text,
                                   attributes={"note_type": "important"})

        # WARNING / CAUTION / DANGER
        for ntype in ("WARNING", "CAUTION", "DANGER"):
            if text.strip().upper().startswith(ntype) and is_bold:
                return self.make_block("note_header", text=text,
                                       attributes={"note_type": ntype.lower()})

        # H1
        if size >= PDF_H1_SIZE and is_bold:
            return self.make_block("heading", text=text, level=1,
                                   attributes={"font_size": size})

        # H2
        if size >= PDF_H2_SIZE and is_bold:
            return self.make_block("heading", text=text, level=2,
                                   attributes={"font_size": size})

        # H3
        if size >= PDF_H3_SIZE and is_bold:
            return self.make_block("heading", text=text, level=3,
                                   attributes={"font_size": size})

        # Figure caption
        if FIGURE_PATTERN.match(text):
            caption = re.sub(r"^Figure\s+\d+\s*:\s*", "", text).strip()
            return self.make_block("figure", text=caption,
                                   attributes={"raw_label": text})

        # Note inline prefix
        if NOTE_PREFIX.match(text) or IMPORTANT_PREFIX.match(text):
            ntype = "important" if IMPORTANT_PREFIX.match(text) else "note"
            return self.make_block("note_inline", text=text,
                                   attributes={"note_type": ntype})

        # Bullet list item
        if text[0] in BULLET_CHARS or text.startswith("- "):
            content = re.sub(r"^[•–\-◦▪·\uf020]\s*", "", text).strip()
            return self.make_block("list_item", text=content,
                                   attributes={"list_type": "bullet"})

        # Numbered step (10pt bold)
        step_m = STEP_PATTERN.match(text)
        if step_m and is_bold and size <= 10.5:
            return self.make_block("list_item",
                                   text=step_m.group(2).strip(),
                                   attributes={"list_type": "numbered",
                                               "number": step_m.group(1)})

        # Drop very small text
        if size < PDF_BODY_MIN_SIZE:
            return None

        # Code block
        for sig in ("telnet ", "C:\\>", "C:/", "$ ", "http://", "https://"):
            if text.startswith(sig):
                return self.make_block("code_block", text=text)

        # Default paragraph
        attrs: dict = {}
        if is_bold:
            attrs["is_bold"] = True
        if is_italic:
            attrs["is_italic"] = True
        return self.make_block("paragraph", text=text, attributes=attrs)

    def _pdf_table_to_block(self, table_data: list[list]) -> dict | None:
        if not table_data:
            return None
        cleaned_rows = []
        for row in table_data:
            if row is None:
                continue
            cleaned = [(c.strip() if isinstance(c, str) else "") for c in row]
            if any(cleaned):
                cleaned_rows.append(cleaned)
        if not cleaned_rows:
            return None

        children = [
            self.make_block("table_row", text="",
                            attributes={"is_header": i == 0, "cells": row})
            for i, row in enumerate(cleaned_rows)
        ]
        return self.make_block("table", text="", children=children,
                               attributes={"col_count": len(cleaned_rows[0])})

    def _merge_paragraphs(self, blocks: list[dict]) -> list[dict]:
        """
        Join wrapped paragraph lines back into single blocks.
        pdfplumber often splits one long paragraph across multiple line objects.
        """
        if not blocks:
            return blocks
        merged: list[dict] = []
        for blk in blocks:
            prev = merged[-1] if merged else None
            if (
                blk["type"] == "paragraph"
                and prev
                and prev["type"] == "paragraph"
                and not prev["text"].endswith((".", ":", "?", "!"))
                and blk["text"]
                and not blk["text"][0].isupper()
            ):
                prev["text"] = prev["text"].rstrip() + " " + blk["text"].strip()
            else:
                merged.append(blk)
        return merged

    # ------------------------------------------------------------------
    # DOCX EXTRACTION
    # ------------------------------------------------------------------

    def _extract_docx(self) -> list[dict]:
        doc = DocxDocument(str(self.file_path))
        blocks: list[dict] = []

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                blk = self._docx_para_to_block(element, doc)
                if blk is None:
                    self._dropped_count += 1
                else:
                    blocks.append(blk)

            elif tag == "tbl":
                blk = self._docx_table_to_block(element, doc)
                if blk:
                    blocks.append(blk)

        return blocks

    def _docx_para_to_block(self, para_el, doc) -> dict | None:
        from docx.text.paragraph import Paragraph
        para = Paragraph(para_el, doc)
        text = para.text.strip()
        style_name = para.style.name if para.style else "Normal"

        if not text:
            return None
        for pat in DROP_TEXT_PATTERNS:
            if pat.search(text):
                return None

        # Heading styles
        if style_name in DOCX_HEADING_STYLES:
            return self.make_block("heading", text=text,
                                   level=DOCX_HEADING_STYLES[style_name],
                                   style_name=style_name)

        # Note inline prefix
        if NOTE_PREFIX.match(text) or IMPORTANT_PREFIX.match(text):
            ntype = "important" if IMPORTANT_PREFIX.match(text) else "note"
            return self.make_block("note_inline", text=text,
                                   style_name=style_name,
                                   attributes={"note_type": ntype})

        # IMPORTANT INFORMATION header
        if text.upper() == "IMPORTANT INFORMATION":
            return self.make_block("note_header", text=text,
                                   style_name=style_name,
                                   attributes={"note_type": "important"})

        # WARNING / CAUTION / DANGER
        for ntype in ("WARNING", "CAUTION", "DANGER"):
            if text.strip().upper().startswith(ntype):
                return self.make_block("note_header", text=text,
                                       style_name=style_name,
                                       attributes={"note_type": ntype.lower()})

        # Figure caption
        if FIGURE_PATTERN.match(text):
            caption = re.sub(r"^Figure\s+\d+\s*:\s*", "", text).strip()
            return self.make_block("figure", text=caption,
                                   style_name=style_name,
                                   attributes={"raw_label": text})

        # List styles
        if any(k in style_name for k in ("List", "Bullet")):
            return self.make_block("list_item", text=text,
                                   style_name=style_name,
                                   attributes={"list_type": "bullet"})
        if "Number" in style_name:
            m = STEP_PATTERN.match(text)
            return self.make_block("list_item",
                                   text=m.group(2).strip() if m else text,
                                   style_name=style_name,
                                   attributes={"list_type": "numbered",
                                               "number": m.group(1) if m else "?"})

        # Bullet character in body text
        if text[0] in BULLET_CHARS:
            content = re.sub(r"^[•–\-◦▪·\uf020]\s*", "", text).strip()
            return self.make_block("list_item", text=content,
                                   style_name=style_name,
                                   attributes={"list_type": "bullet"})

        # Code block
        for sig in ("telnet ", "C:\\>", "C:/", "$ ", "http://", "https://"):
            if text.startswith(sig):
                return self.make_block("code_block", text=text,
                                       style_name=style_name)

        # Default paragraph
        attrs: dict = {}
        if all(r.bold for r in para.runs if r.text.strip()):
            attrs["is_bold"] = True
        if all(r.italic for r in para.runs if r.text.strip()):
            attrs["is_italic"] = True
        return self.make_block("paragraph", text=text,
                               style_name=style_name, attributes=attrs)

    def _docx_table_to_block(self, tbl_el, doc) -> dict | None:
        from docx.table import Table
        table = Table(tbl_el, doc)
        if not table.rows:
            return None

        children = []
        for i, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                children.append(self.make_block(
                    "table_row", text="",
                    attributes={"is_header": i == 0, "cells": cells}
                ))

        if not children:
            return None

        col_count = len(table.columns) if table.columns else 0
        return self.make_block("table", text="", children=children,
                               attributes={"col_count": col_count})

    # ------------------------------------------------------------------
    # FACTORY
    # ------------------------------------------------------------------

    @staticmethod
    def make_block(
        block_type: str,
        text: str = "",
        level: int | None = None,
        style_name: str | None = None,
        children: list | None = None,
        attributes: dict | None = None,
    ) -> dict:
        """
        Create a normalised content block.

        Block types: heading | paragraph | list_item | table | table_row |
                     figure | code_block | note_header | note_inline
        """
        return {
            "type":         block_type,
            "level":        level,
            "text":         text,
            "style_name":   style_name,
            "children":     children,
            "attributes":   attributes or {},
            "dita_element": None,
        }
