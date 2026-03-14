"""
DITA Converter Tool — Agent 3: Generator
==========================================
Serialises an annotated Content Tree into valid DITA 1.3 XML using lxml.

Structural mapping:
  title           → <title> inside topic root
  section_title   → opens <section><title>...</title>  (closed at next section)
  sectiondiv_title→ opens <sectiondiv><title>...</title> (closed at next sectiondiv/section)
  p               → <p>
  ul_li           → <ul><li><p>  (items grouped into a single <ul>)
  ol_li           → <ol><li><p>  (items grouped into a single <ol>)
  step            → <steps><step><cmd>  (items grouped into <steps>)
  fig             → <fig><title>[IMAGE placeholder]</title></fig>
  codeblock       → <codeblock>
  menucascade     → <p><menucascade><uicontrol>…</uicontrol></menucascade></p>
  note:TYPE       → <note type="TYPE">
  table (CALS)    → <table><tgroup><thead><tbody>
  dl              → <dl><dlentry><dt><dd>
  row             → handled inside table serialisation

Session: S-04
Author: Coder
"""

from __future__ import annotations
import re
from pathlib import Path

from lxml import etree

# ---------------------------------------------------------------------------
# DOCTYPE declarations for DITA 1.3
# ---------------------------------------------------------------------------
DITA_DOCTYPE = {
    "concept": (
        '-//OASIS//DTD DITA Concept//EN',
        'concept.dtd',
    ),
    "task": (
        '-//OASIS//DTD DITA Task//EN',
        'task.dtd',
    ),
    "reference": (
        '-//OASIS//DTD DITA Reference//EN',
        'reference.dtd',
    ),
}

DITA_BODY_ELEMENT = {
    "concept":   "conbody",
    "task":      "taskbody",
    "reference": "refbody",
}

# DITA 1.3 @class attributes for common elements (aids DITA processors)
DITA_CLASS = {
    "concept":   "- topic/topic concept/concept ",
    "task":      "- topic/topic task/task ",
    "reference": "- topic/topic reference/reference ",
}

# UI path splitter — splits "A > B > C" into ["A","B","C"]
UI_SPLIT_RE = re.compile(r"\s*>\s*")

# Clean topic id: lowercase, replace non-alphanumeric with underscore
TOPIC_ID_RE = re.compile(r"[^a-z0-9]+")


class GeneratorError(Exception):
    """Raised when DITA XML generation fails."""
    pass


class Generator:
    """
    Generates DITA 1.3 XML from an annotated Content Tree.

    Usage:
        gen = Generator(topic_type="task")
        xml_string = gen.generate(annotated_tree)
    """

    def __init__(self, topic_type: str = "concept") -> None:
        if topic_type not in DITA_DOCTYPE:
            raise GeneratorError(
                f"Unknown topic type: '{topic_type}'. "
                f"Must be one of: {list(DITA_DOCTYPE.keys())}"
            )
        self.topic_type = topic_type

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, annotated_tree: list[dict]) -> str:
        """
        Serialise the annotated Content Tree to a DITA 1.3 XML string.

        Args:
            annotated_tree: Fully annotated Content Tree from Mapper.

        Returns:
            DITA 1.3 XML string with XML declaration and DOCTYPE.

        Raises:
            GeneratorError: If serialisation fails.
        """
        try:
            return self._build_xml(annotated_tree)
        except GeneratorError:
            raise
        except Exception as exc:
            raise GeneratorError(f"XML generation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # XML construction
    # ------------------------------------------------------------------

    def _build_xml(self, tree: list[dict]) -> str:
        """Build the complete DITA XML document."""
        # Derive topic id and title
        title_block = next(
            (b for b in tree if b.get("dita_element") == "title"), None
        )
        title_text = title_block["text"] if title_block else "Untitled Topic"
        topic_id   = self._build_topic_id(title_text)

        # Root element
        root_tag = self.topic_type   # concept | task | reference
        XML_NS = "http://www.w3.org/XML/1998/namespace"
        root = etree.Element(root_tag)
        root.set("id", topic_id)
        root.set(f"{{{XML_NS}}}lang", "en-US")

        # <title>
        title_el = etree.SubElement(root, "title")
        title_el.text = title_text

        # <shortdesc> — DITA 1.3 best practice: first paragraph after title
        first_para = next(
            (b for b in tree if b.get("dita_element") == "p"), None
        )
        if first_para:
            sd = etree.SubElement(root, "shortdesc")
            sd.text = first_para["text"]

        # Body element  (<conbody> / <taskbody> / <refbody>)
        body_tag = DITA_BODY_ELEMENT[self.topic_type]
        body = etree.SubElement(root, body_tag)

        # Feed remaining blocks into the body builder
        remaining = [b for b in tree if b.get("dita_element") != "title"]
        self._populate_body(body, remaining)

        # Serialise
        return self._serialise(root, topic_id, title_text)

    def _populate_body(self, body: etree._Element, tree: list[dict]) -> None:
        """
        Walk the annotated tree and append DITA elements to body.

        Uses a cursor-based approach:
          - current_section tracks the open <section> element
          - current_sectiondiv tracks the open <sectiondiv>
          - list buffers accumulate consecutive list/step items
        """
        current_section:    etree._Element | None = None
        current_sectiondiv: etree._Element | None = None

        # Buffer for consecutive list items
        list_buffer:  list[dict] = []   # ul_li | ol_li blocks
        step_buffer:  list[dict] = []   # step blocks

        def flush_lists(parent: etree._Element) -> None:
            """Flush any buffered list/step items into parent."""
            nonlocal list_buffer, step_buffer
            if list_buffer:
                self._append_list(parent, list_buffer)
                list_buffer = []
            if step_buffer:
                self._append_steps(parent, step_buffer)
                step_buffer = []

        def current_parent() -> etree._Element:
            """Return the deepest currently open container."""
            if current_sectiondiv is not None:
                return current_sectiondiv
            if current_section is not None:
                return current_section
            return body

        for block in tree:
            el = block.get("dita_element", "p")

            # --- Section boundary ---
            if el == "section_title":
                flush_lists(current_parent())
                current_sectiondiv = None          # close any open sectiondiv
                sec = etree.SubElement(body, "section")
                t   = etree.SubElement(sec, "title")
                t.text = block["text"]
                current_section = sec
                continue

            # --- Sectiondiv boundary ---
            if el == "sectiondiv_title":
                flush_lists(current_parent())
                parent = current_section if current_section is not None else body
                sdiv = etree.SubElement(parent, "sectiondiv")
                t    = etree.SubElement(sdiv, "title")
                t.text = block["text"]
                current_sectiondiv = sdiv
                continue

            parent = current_parent()

            # --- Flush list buffers when hitting non-list content ---
            if el not in ("ul_li", "ol_li", "step"):
                flush_lists(parent)

            # --- Dispatch ---
            if el == "p":
                self._append_p(parent, block)

            elif el == "ul_li":
                list_buffer.append(block)

            elif el == "ol_li":
                list_buffer.append(block)

            elif el == "step":
                step_buffer.append(block)

            elif el and el.startswith("note:"):
                self._append_note(parent, block, el)

            elif el == "fig":
                self._append_fig(parent, block)

            elif el == "codeblock":
                self._append_codeblock(parent, block)

            elif el == "menucascade":
                self._append_menucascade(parent, block)

            elif el == "table":
                self._append_table(parent, block)

            elif el == "dl":
                self._append_dl(parent, block)

            # shortdesc, title already handled — skip silently
            # row, table_row handled inside table — skip at top level

        # Flush any remaining list items
        flush_lists(current_parent())

    # ------------------------------------------------------------------
    # Element serialisers
    # ------------------------------------------------------------------

    def _append_p(self, parent: etree._Element, block: dict) -> None:
        """Append a <p> element."""
        p = etree.SubElement(parent, "p")
        p.text = block["text"]

    def _append_list(self, parent: etree._Element, items: list[dict]) -> None:
        """
        Append a <ul> or <ol> from buffered list_item blocks.
        Mixed lists (both ul and ol) are split into separate elements.
        """
        ul_items = [b for b in items if b["dita_element"] == "ul_li"]
        ol_items = [b for b in items if b["dita_element"] == "ol_li"]

        if ul_items:
            ul = etree.SubElement(parent, "ul")
            for item in ul_items:
                li = etree.SubElement(ul, "li")
                p  = etree.SubElement(li, "p")
                p.text = item["text"]

        if ol_items:
            ol = etree.SubElement(parent, "ol")
            for item in ol_items:
                li = etree.SubElement(ol, "li")
                p  = etree.SubElement(li, "p")
                p.text = item["text"]

    def _append_steps(self, parent: etree._Element, steps: list[dict]) -> None:
        """
        Append a <steps> block from buffered step blocks.
        Each step → <step><cmd>text</cmd></step>.
        Sub-bullets inside the step go into <info><ul><li>.
        """
        steps_el = etree.SubElement(parent, "steps")
        for step in steps:
            step_el = etree.SubElement(steps_el, "step")
            cmd     = etree.SubElement(step_el, "cmd")
            cmd.text = step["text"]

            # Sub-bullets stored in children (future enhancement)
            sub_items = step.get("children") or []
            if sub_items:
                info = etree.SubElement(step_el, "info")
                ul   = etree.SubElement(info, "ul")
                for sub in sub_items:
                    li = etree.SubElement(ul, "li")
                    p  = etree.SubElement(li, "p")
                    p.text = sub.get("text", "")

    def _append_note(
        self, parent: etree._Element, block: dict, el_tag: str
    ) -> None:
        """
        Append a <note type="TYPE"> element.
        el_tag format: "note:important" | "note:warning" | "note:caution" etc.
        """
        note_type = el_tag.split(":", 1)[1] if ":" in el_tag else "note"
        note = etree.SubElement(parent, "note")
        note.set("type", note_type)
        p = etree.SubElement(note, "p")
        p.text = block["text"]

    def _append_fig(self, parent: etree._Element, block: dict) -> None:
        """
        Append a <fig> element with a placeholder for the image.
        Images are not extractable from text-based PDFs in v1.
        """
        fig   = etree.SubElement(parent, "fig")
        title = etree.SubElement(fig, "title")
        title.text = block["text"]
        # Image placeholder — actual href populated when image files available
        img = etree.SubElement(fig, "image")
        img.set("href", "")
        img.set("placement", "inline")
        alt = etree.SubElement(img, "alt")
        alt.text = f"[IMAGE — {block['text']}]"

    def _append_codeblock(
        self, parent: etree._Element, block: dict
    ) -> None:
        """Append a <codeblock> element."""
        cb = etree.SubElement(parent, "codeblock")
        cb.text = block["text"]

    def _append_menucascade(
        self, parent: etree._Element, block: dict
    ) -> None:
        """
        Detect and wrap UI path strings in <menucascade><uicontrol>.
        E.g. "MWS > Set Up > Network Menu" →
          <p><menucascade>
            <uicontrol>MWS</uicontrol>
            <uicontrol>Set Up</uicontrol>
            <uicontrol>Network Menu</uicontrol>
          </menucascade></p>
        """
        text = block["text"]
        p    = etree.SubElement(parent, "p")

        if ">" in text:
            parts_before = UI_SPLIT_RE.split(text, maxsplit=1)
            # Find the first ">" segment and split the whole string
            segments = UI_SPLIT_RE.split(text)
            mc = etree.SubElement(p, "menucascade")
            for seg in segments:
                seg = seg.strip()
                if seg:
                    uc = etree.SubElement(mc, "uicontrol")
                    uc.text = seg
        else:
            p.text = text

    def _append_table(
        self, parent: etree._Element, block: dict
    ) -> None:
        """
        Append a full CALS table:
          <table frame="all">
            <tgroup cols="N">
              <colspec colname="col1" ... />
              <thead><row><entry>...</entry></row></thead>
              <tbody><row><entry>...</entry></row></tbody>
            </tgroup>
          </table>
        """
        children = block.get("children") or []
        if not children:
            return

        col_count = block.get("attributes", {}).get("col_count", 1)
        # Determine col count from first row if attribute missing
        if col_count == 0 and children:
            col_count = len(children[0]["attributes"].get("cells", []))

        table  = etree.SubElement(parent, "table")
        table.set("frame", "all")
        tgroup = etree.SubElement(table, "tgroup")
        tgroup.set("cols", str(col_count))

        # colspec elements
        for i in range(1, col_count + 1):
            cs = etree.SubElement(tgroup, "colspec")
            cs.set("colname", f"col{i}")
            cs.set("colnum",  str(i))

        # Split header vs body rows
        header_rows = [r for r in children if r["attributes"].get("is_header")]
        body_rows   = [r for r in children if not r["attributes"].get("is_header")]

        if header_rows:
            thead = etree.SubElement(tgroup, "thead")
            for row_block in header_rows:
                self._append_table_row(thead, row_block, col_count)

        tbody = etree.SubElement(tgroup, "tbody")
        if body_rows:
            for row_block in body_rows:
                self._append_table_row(tbody, row_block, col_count)
        else:
            # DITA requires at least one tbody row
            row = etree.SubElement(tbody, "row")
            entry = etree.SubElement(row, "entry")
            entry.text = ""

    def _append_table_row(
        self,
        parent: etree._Element,
        row_block: dict,
        col_count: int,
    ) -> None:
        """Append a <row> with <entry> children to thead or tbody."""
        cells = row_block["attributes"].get("cells", [])
        row   = etree.SubElement(parent, "row")
        for i in range(col_count):
            entry = etree.SubElement(row, "entry")
            entry.set("colname", f"col{i + 1}")
            text = cells[i].strip() if i < len(cells) else ""
            # Clean embedded newlines
            entry.text = text.replace("\n", " ").strip()

    def _append_dl(self, parent: etree._Element, block: dict) -> None:
        """
        Append a <dl> (definition list) for Term/Description tables.
        Each row → <dlentry><dt>term</dt><dd>description</dd></dlentry>
        """
        children = block.get("children") or []
        if not children:
            return

        dl = etree.SubElement(parent, "dl")
        # Skip header row (index 0) — it contains column labels, not data
        data_rows = [r for r in children if not r["attributes"].get("is_header")]
        for row_block in data_rows:
            cells = row_block["attributes"].get("cells", [])
            if len(cells) < 2:
                continue
            dlentry = etree.SubElement(dl, "dlentry")
            dt = etree.SubElement(dlentry, "dt")
            dt.text = cells[0].strip()
            dd = etree.SubElement(dlentry, "dd")
            dd.text = cells[1].strip()

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _serialise(
        self, root: etree._Element, topic_id: str, title_text: str
    ) -> str:
        """
        Convert the lxml element tree to a UTF-8 XML string with
        XML declaration and DITA 1.3 DOCTYPE.
        """
        public_id, system_id = DITA_DOCTYPE[self.topic_type]

        # Build DOCTYPE string manually (lxml doesn't support PUBLIC doctype
        # via tostring directly)
        xml_decl = '<?xml version="1.0" encoding="UTF-8"?>'
        doctype  = (
            f'<!DOCTYPE {self.topic_type} '
            f'PUBLIC "{public_id}"\n'
            f'       "{system_id}">'
        )

        # Serialise tree (no xml_declaration — we prepend it manually)
        body_bytes = etree.tostring(
            root,
            pretty_print=True,
            encoding="unicode",
        )

        return f"{xml_decl}\n{doctype}\n{body_bytes}"

    def _build_topic_id(self, title_text: str) -> str:
        """
        Derive a valid XML id attribute from the document title.

        Converts to lowercase, collapses runs of non-alphanumeric chars
        to underscores, strips leading/trailing underscores.

        Args:
            title_text: Raw title string.

        Returns:
            Valid XML id (e.g. "introduction", "feature_activation").
        """
        lowered  = title_text.lower()
        cleaned  = TOPIC_ID_RE.sub("_", lowered)
        stripped = cleaned.strip("_")
        return stripped or "topic"
