"""
DITA Converter Tool — Agent 2: Mapper
=======================================
Applies YAML mapping rules to an extracted Content Tree, annotating every
block with its target DITA 1.3 element type.

Key responsibilities:
  - Detect document topic type (concept | task | reference)
  - Merge split heading lines (PDF artefact)
  - Reclassify 1-col callout "tables" as note blocks
  - Map first H1 → title; subsequent H1 → section
  - Apply task-context detection: numbered items after task signal → step
  - Map Term/Description 2-col tables → dl; all others → CALS table
  - Count fallback-mapped blocks for the Validator report

Session: S-03
Author: Coder
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Union

import yaml


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------
STEP_NUM_PARA = re.compile(r"^(\d+)\s+(.+)", re.DOTALL)   # "1 Connect the..."
NOTE_KEYWORDS = {"IMPORTANT INFORMATION", "WARNING", "CAUTION", "DANGER", "IMPORTANT"}
UI_PATH_RE    = re.compile(r".+\s*>\s*.+")


class MapperError(Exception):
    """Raised when mapping rules cannot be loaded or applied."""
    pass


class Mapper:
    """
    Applies YAML mapping rules to a Content Tree.

    Usage:
        mapper = Mapper("config/mapping_rules.yaml")
        annotated_tree, topic_type = mapper.map(content_tree)
    """

    def __init__(self, rules_path: Union[str, Path]) -> None:
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()
        self._fallback_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def fallback_count(self) -> int:
        """Number of blocks that fell back to the default element in last map()."""
        return self._fallback_count

    def map(self, content_tree: list[dict]) -> tuple[list[dict], str]:
        """
        Annotate every block in the Content Tree with its DITA element.

        Args:
            content_tree: List of block dicts from the Extractor.

        Returns:
            Tuple of (annotated_tree, topic_type).
            topic_type is 'concept' | 'task' | 'reference'.
        """
        self._fallback_count = 0

        # Pass 1 — pre-processing
        tree = self._merge_split_headings(content_tree)
        tree = self._reclassify_callout_tables(tree)
        tree = self._detect_numbered_steps(tree)

        # Detect topic type from full tree
        topic_type = self.detect_topic_type(tree)

        # Pass 2 — annotate each block
        h1_seen = False
        for block in tree:
            dita_el, h1_seen = self._map_block(block, h1_seen, topic_type)
            block["dita_element"] = dita_el

        return tree, topic_type

    def detect_topic_type(self, content_tree: list[dict]) -> str:
        """
        Detect the appropriate DITA topic type for this document.

        Scans all paragraph and heading text for signal phrases from
        topic_type_signals in the rules file.

        Returns:
            'task' | 'reference' | 'concept'
        """
        signals = self.rules.get("topic_type_signals", {})
        all_text = " ".join(
            b["text"].lower() for b in content_tree
            if b["type"] in ("paragraph", "heading", "list_item")
        )

        # Task signals take priority
        for phrase in signals.get("task", []):
            if phrase.lower() in all_text:
                return "task"

        for phrase in signals.get("reference", []):
            if phrase.lower() in all_text:
                return "reference"

        return self.rules.get("topic_type", "concept")

    # ------------------------------------------------------------------
    # Pre-processing passes
    # ------------------------------------------------------------------

    def _merge_split_headings(self, tree: list[dict]) -> list[dict]:
        """
        Merge consecutive heading blocks at the same level that are
        PDF line-break artefacts (e.g. a long H1 split across two lines).

        Heuristic: two adjacent headings at the same level where the first
        does not end with punctuation and the second starts with a lowercase
        letter or closing punctuation → merge.
        """
        if not tree:
            return tree

        merged: list[dict] = []
        for block in tree:
            prev = merged[-1] if merged else None
            if (
                block["type"] == "heading"
                and prev
                and prev["type"] == "heading"
                and prev["level"] == block["level"]
                and not prev["text"].endswith((".", ":", "?", "!"))
                and (
                    block["text"] and (
                        block["text"][0].islower()
                        or block["text"][0] in (")", "]", "-")
                        or block["text"][:2].lower() in ("an", "or", "to")
                    )
                )
            ):
                prev["text"] = prev["text"].rstrip() + " " + block["text"].strip()
            else:
                merged.append(block)
        return merged

    def _reclassify_callout_tables(self, tree: list[dict]) -> list[dict]:
        """
        PDF renders callout boxes (IMPORTANT INFORMATION, WARNING, CAUTION)
        as 1-column tables. Reclassify these as note blocks.

        A table is a callout if:
          - It has exactly 1 column, OR
          - Its first cell text matches a known note keyword
        """
        result: list[dict] = []
        for block in tree:
            if block["type"] != "table":
                result.append(block)
                continue

            children = block.get("children") or []
            if not children:
                result.append(block)
                continue

            first_row = children[0]
            cells = first_row.get("attributes", {}).get("cells", [])
            col_count = block.get("attributes", {}).get("col_count", 0)

            # Check if the first cell content matches a note keyword
            first_cell = cells[0].strip().upper() if cells else ""
            # Strip warning symbols (!, ▲) from start
            first_cell_clean = re.sub(r"^[!▲\s]+", "", first_cell).strip()

            is_callout = (
                col_count == 1
                and first_cell_clean in NOTE_KEYWORDS
            )

            if is_callout:
                # Determine note type from keyword
                note_type = "important"
                if "WARNING" in first_cell_clean:
                    note_type = "warning"
                elif "CAUTION" in first_cell_clean:
                    note_type = "caution"
                elif "DANGER" in first_cell_clean:
                    note_type = "danger"

                # Collect body text from remaining rows
                body_parts = []
                for row in children[1:]:
                    row_cells = row.get("attributes", {}).get("cells", [])
                    for cell in row_cells:
                        if cell.strip():
                            body_parts.append(cell.strip())
                body_text = " ".join(body_parts)

                result.append({
                    "type": "note_header",
                    "level": None,
                    "text": body_text or first_cell.title(),
                    "style_name": None,
                    "children": None,
                    "attributes": {"note_type": note_type, "reclassified": True},
                    "dita_element": None,
                })
            else:
                result.append(block)

        return result

    def _detect_numbered_steps(self, tree: list[dict]) -> list[dict]:
        """
        Detect numbered paragraphs that are task steps.

        In PDFs, numbered steps are sometimes extracted as plain paragraphs
        (e.g. "1 Connect the power cable...") rather than list_items.
        After a task-signal paragraph, convert these to list_items with
        list_type=numbered so the Mapper treats them as steps.
        """
        task_signals = self.rules.get("topic_type_signals", {}).get("task", [])
        in_task_context = False
        result: list[dict] = []

        for block in tree:
            # Toggle task context on signal paragraphs
            if block["type"] == "paragraph":
                text_lower = block["text"].lower()
                if any(sig.lower() in text_lower for sig in task_signals):
                    in_task_context = True

            # New H1 section resets task context
            if block["type"] == "heading" and block.get("level") == 1:
                in_task_context = False

            # Detect "N text..." paragraphs in task context
            if in_task_context and block["type"] == "paragraph":
                m = STEP_NUM_PARA.match(block["text"])
                if m:
                    num = m.group(1)
                    text = m.group(2).strip()
                    block = dict(block)   # copy — don't mutate original
                    block["type"] = "list_item"
                    block["text"] = text
                    block["attributes"] = {
                        **block.get("attributes", {}),
                        "list_type": "numbered",
                        "number": num,
                    }

            result.append(block)

        return result

    # ------------------------------------------------------------------
    # Block-level mapping
    # ------------------------------------------------------------------

    def _map_block(
        self, block: dict, h1_seen: bool, topic_type: str
    ) -> tuple[str, bool]:
        """
        Return the DITA element string for a single block.

        Args:
            block:      Content block dict.
            h1_seen:    Whether the first H1 (topic title) has been seen.
            topic_type: Detected topic type ('concept'|'task'|'reference').

        Returns:
            Tuple of (dita_element_string, updated_h1_seen).
        """
        btype = block["type"]
        attrs = block.get("attributes", {})

        # --- Headings ---
        if btype == "heading":
            level = block.get("level", 1)
            if level == 1:
                if not h1_seen:
                    return "title", True         # First H1 → topic title
                return "section_title", h1_seen  # Subsequent H1 → section
            if level == 2:
                return "sectiondiv_title", h1_seen
            return "sectiondiv_title", h1_seen   # H3+

        # --- Notes (header blocks) ---
        if btype == "note_header":
            note_type = attrs.get("note_type", "important")
            return f"note:{note_type}", h1_seen

        # --- Notes (inline prefix) ---
        if btype == "note_inline":
            note_type = attrs.get("note_type", "note")
            return f"note:{note_type}", h1_seen

        # --- Figures ---
        if btype == "figure":
            return "fig", h1_seen

        # --- Code blocks ---
        if btype == "code_block":
            return "codeblock", h1_seen

        # --- Tables ---
        if btype == "table":
            return self._map_table(block), h1_seen

        # --- Table rows (children of tables — mapped separately) ---
        if btype == "table_row":
            return "row", h1_seen

        # --- List items ---
        if btype == "list_item":
            list_type = attrs.get("list_type", "bullet")
            in_task = attrs.get("in_task_context", False)

            if list_type == "numbered" and topic_type == "task":
                return "step", h1_seen
            if list_type == "numbered":
                return "ol_li", h1_seen
            return "ul_li", h1_seen

        # --- Paragraphs ---
        if btype == "paragraph":
            # Menu/UI path detection: "MWS > Set Up > ..."
            if UI_PATH_RE.search(block.get("text", "")):
                return "menucascade", h1_seen
            return "p", h1_seen

        # --- Fallback ---
        self._fallback_count += 1
        return self.rules.get("fallback_element", "p"), h1_seen

    def _map_table(self, block: dict) -> str:
        """
        Determine the DITA element for a table block.

        Rules (from D-009):
          - Term/Description 2-col tables → 'dl'
          - All other tables → 'table' (CALS)
        """
        children = block.get("children") or []
        if not children:
            return "table"

        first_row = children[0]
        cells = first_row.get("attributes", {}).get("cells", [])
        col_count = block.get("attributes", {}).get("col_count", 0)

        # Abbreviation / definition list detection
        abbrev_signals = (
            self.rules.get("table_map", {})
            .get("abbreviation_signals", ["Term", "Abbreviation", "Acronym"])
        )
        if col_count == 2 and cells:
            first_header = cells[0].strip()
            if any(sig.lower() in first_header.lower() for sig in abbrev_signals):
                return "dl"

        return "table"

    # ------------------------------------------------------------------
    # Rules loader
    # ------------------------------------------------------------------

    def _load_rules(self) -> dict:
        """Load and parse the YAML mapping rules file."""
        if not self.rules_path.exists():
            raise MapperError(f"Rules file not found: {self.rules_path}")
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise MapperError(f"Failed to parse rules file: {exc}") from exc
