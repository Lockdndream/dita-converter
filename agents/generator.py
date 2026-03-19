"""
agents/generator.py
DITA Converter Tool — Generator Agent

Serialises the annotated Content Tree into valid DITA 2.0 XML using lxml.

NEW in S-08:
  - DITA 2.0 namespace and DOCTYPE
  - Multi-topic splitting: each H1 boundary (section_title) becomes a
    separate topic file. Returns list of (filename, xml_string) tuples.
  - Single-topic documents return a list of one tuple.

Session: S-04 | Updated S-08 (DITA 2.0 + multi-topic) | Reviewer-signed-off
"""

from __future__ import annotations

import re
from lxml import etree  # type: ignore
from typing import Any


# ---------------------------------------------------------------------------
# DITA 2.0 constants
# ---------------------------------------------------------------------------

# DITA 2.0 uses a real XML namespace
DITA2_NS = "https://docs.oasis-open.org/dita/ns/2.0"
DITA2_NS_MAP = {None: DITA2_NS}

_VALID_TOPIC_TYPES = {"concept", "task", "reference", "topic"}

# DOCTYPE for DITA 2.0
_DOCTYPE_MAP = {
    "concept":   '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA 2.0 Concept//EN" "concept.dtd">',
    "task":      '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA 2.0 Task//EN" "task.dtd">',
    "reference": '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA 2.0 Reference//EN" "reference.dtd">',
    "topic":     '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA 2.0 Topic//EN" "topic.dtd">',
}

# DITA 2.0 body element per topic type
_BODY_ELEM = {
    "concept":   "conbody",
    "task":      "taskbody",
    "reference": "refbody",
    "topic":     "body",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topic_id(title: str) -> str:
    if not title:
        return "untitled_topic"
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "topic"


def _safe_text(element: etree._Element, text: str) -> None:
    if text:
        element.text = text


def _tag(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


# ---------------------------------------------------------------------------
# Generator class
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self, topic_type: str = "concept"):
        if topic_type not in _VALID_TOPIC_TYPES:
            raise ValueError(
                f"Invalid topic_type {topic_type!r}. "
                f"Choose from {sorted(_VALID_TOPIC_TYPES)}"
            )
        self.topic_type = topic_type

    # -----------------------------------------------------------------------
    # Public: generate one or more topics
    # -----------------------------------------------------------------------

    def generate(self, blocks: list[dict]) -> list[tuple[str, str]]:
        """
        Split blocks at every section_title boundary and generate one DITA
        2.0 XML string per topic.

        Returns:
            List of (filename, xml_string) tuples.
            Single-topic documents return a list of exactly one tuple.
        """
        # Detect topic type from mapper metadata
        topic_type = self.topic_type
        if blocks:
            tt = blocks[0].get("metadata", {}).get("topic_type")
            if tt in _VALID_TOPIC_TYPES:
                topic_type = tt

        # Split at section boundaries
        topic_chunks = self._split_into_topics(blocks)

        results: list[tuple[str, str]] = []
        for chunk in topic_chunks:
            xml_str = self._render_topic(chunk, topic_type)
            # Derive filename from title block
            title_text = ""
            for b in chunk:
                if b.get("dita_element") in ("title", "section_title"):
                    title_text = b.get("text", "")
                    break
            filename = _make_topic_id(title_text) + ".dita"
            results.append((filename, xml_str))

        return results

    # -----------------------------------------------------------------------
    # Split blocks at section_title boundaries
    # -----------------------------------------------------------------------

    def _split_into_topics(self, blocks: list[dict]) -> list[list[dict]]:
        """
        Split the block list at every `section_title` element.
        The first chunk contains everything up to the first section_title.
        Each subsequent chunk starts with the section_title block (re-typed
        as `title` for its own topic).
        """
        if not blocks:
            return [[]]

        chunks: list[list[dict]] = []
        current: list[dict] = []

        for block in blocks:
            if block.get("dita_element") == "section_title" and current:
                # Close current chunk, start new one
                chunks.append(current)
                # Promote section_title → title for the new topic
                new_block = dict(block)
                new_block["dita_element"] = "title"
                current = [new_block]
            else:
                current.append(block)

        if current:
            chunks.append(current)

        # Filter out empty/title-only chunks
        return [c for c in chunks if any(
            b.get("dita_element") not in (None, "dropped") for b in c
        )]

    # -----------------------------------------------------------------------
    # Render a single topic to XML string
    # -----------------------------------------------------------------------

    def _render_topic(self, blocks: list[dict], topic_type: str) -> str:
        # Find title
        title_text = "Untitled Topic"
        for b in blocks:
            if b.get("dita_element") == "title":
                title_text = b.get("text", "Untitled Topic")
                break

        topic_id = _make_topic_id(title_text)
        ns = DITA2_NS

        # Root element
        root = etree.Element(
            _tag(ns, topic_type),
            nsmap=DITA2_NS_MAP,
        )
        root.set("id", topic_id)
        root.set("{http://www.w3.org/XML/1998/namespace}lang", "en-US")

        # <title>
        title_el = etree.SubElement(root, _tag(ns, "title"))
        _safe_text(title_el, title_text)

        # <shortdesc> from first paragraph after title
        first_para = None
        past_title = False
        for b in blocks:
            de = b.get("dita_element")
            if de == "title":
                past_title = True
                continue
            if past_title and de == "p" and not first_para:
                first_para = b.get("text", "")
                break

        if first_para:
            sd = etree.SubElement(root, _tag(ns, "shortdesc"))
            _safe_text(sd, first_para)

        # Body element
        body_tag = _BODY_ELEM.get(topic_type, "body")
        body = etree.SubElement(root, _tag(ns, body_tag))

        # Render remaining blocks
        self._render_blocks(blocks, body, ns, title_text, first_para)

        # Serialise
        xml_bytes = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
        xml_str = xml_bytes.decode("utf-8")

        # Prepend DOCTYPE
        doctype = _DOCTYPE_MAP.get(topic_type, _DOCTYPE_MAP["topic"])
        decl_end = xml_str.index("?>") + 2
        xml_str = xml_str[:decl_end] + "\n" + doctype + xml_str[decl_end:]

        return xml_str

    # -----------------------------------------------------------------------
    # Block rendering
    # -----------------------------------------------------------------------

    def _render_blocks(
        self,
        blocks: list[dict],
        body: etree._Element,
        ns: str,
        title_text: str,
        first_para_text: str | None,
    ) -> None:

        current_section: etree._Element | None = None
        current_sectiondiv: etree._Element | None = None
        step_buffer: list[dict] = []
        ul_buffer: list[dict] = []
        ol_buffer: list[dict] = []
        skip_first_para = first_para_text  # used as shortdesc already

        def flush_steps():
            nonlocal step_buffer
            if not step_buffer:
                return
            parent = current_sectiondiv or current_section or body
            steps_el = etree.SubElement(parent, _tag(ns, "steps"))
            for sb in step_buffer:
                step_el = etree.SubElement(steps_el, _tag(ns, "step"))
                cmd_el = etree.SubElement(step_el, _tag(ns, "cmd"))
                _safe_text(cmd_el, sb.get("text", ""))
            step_buffer = []

        def flush_ul():
            nonlocal ul_buffer
            if not ul_buffer:
                return
            parent = current_sectiondiv or current_section or body
            ul_el = etree.SubElement(parent, _tag(ns, "ul"))
            for ub in ul_buffer:
                li_el = etree.SubElement(ul_el, _tag(ns, "li"))
                p_el = etree.SubElement(li_el, _tag(ns, "p"))
                _safe_text(p_el, ub.get("text", ""))
            ul_buffer = []

        def flush_ol():
            nonlocal ol_buffer
            if not ol_buffer:
                return
            parent = current_sectiondiv or current_section or body
            ol_el = etree.SubElement(parent, _tag(ns, "ol"))
            for ob in ol_buffer:
                li_el = etree.SubElement(ol_el, _tag(ns, "li"))
                p_el = etree.SubElement(li_el, _tag(ns, "p"))
                _safe_text(p_el, ob.get("text", ""))
            ol_buffer = []

        def flush_all():
            flush_steps()
            flush_ul()
            flush_ol()

        past_title = False
        first_para_done = False

        for block in blocks:
            de = block.get("dita_element")
            text = block.get("text", "")
            meta = block.get("metadata", {})

            if de == "title":
                past_title = True
                continue  # already rendered as root <title>

            if not past_title:
                continue

            # Skip first paragraph (already used as shortdesc)
            if de == "p" and not first_para_done and skip_first_para:
                if text == skip_first_para:
                    first_para_done = True
                    continue

            # ---- section_title: open new <section> ----
            if de == "section_title":
                flush_all()
                current_sectiondiv = None
                current_section = etree.SubElement(body, _tag(ns, "section"))
                sec_title = etree.SubElement(current_section, _tag(ns, "title"))
                _safe_text(sec_title, text)
                continue

            # ---- sectiondiv_title: open new <div> inside section ----
            if de == "sectiondiv_title":
                flush_all()
                parent = current_section or body
                current_sectiondiv = etree.SubElement(parent, _tag(ns, "div"))
                div_title = etree.SubElement(current_sectiondiv, _tag(ns, "title"))
                _safe_text(div_title, text)
                continue

            parent = current_sectiondiv or current_section or body

            # ---- Paragraph ----
            if de == "p":
                flush_all()
                p_el = etree.SubElement(parent, _tag(ns, "p"))
                _safe_text(p_el, text)
                continue

            # ---- Menucascade ----
            if de == "menucascade":
                flush_all()
                mc = etree.SubElement(parent, _tag(ns, "menucascade"))
                for segment in re.split(r"\s*>\s*", text):
                    seg = segment.strip()
                    if seg:
                        uc = etree.SubElement(mc, _tag(ns, "uicontrol"))
                        _safe_text(uc, seg)
                continue

            # ---- List items (buffered) ----
            if de == "step":
                flush_ul()
                flush_ol()
                step_buffer.append(block)
                continue

            if de == "ul_li":
                flush_steps()
                flush_ol()
                ul_buffer.append(block)
                continue

            if de == "ol_li":
                flush_steps()
                flush_ul()
                ol_buffer.append(block)
                continue

            # ---- Note ----
            if de and de.startswith("note:"):
                flush_all()
                note_type = de.split(":", 1)[1]
                note_el = etree.SubElement(parent, _tag(ns, "note"))
                note_el.set("type", note_type)
                _safe_text(note_el, text)
                continue

            # ---- Figure ----
            if de == "fig":
                flush_all()
                caption = meta.get("caption", text)
                image_href = meta.get("image_href", "")
                fig_el = etree.SubElement(parent, _tag(ns, "fig"))
                fig_title = etree.SubElement(fig_el, _tag(ns, "title"))
                _safe_text(fig_title, caption)
                img_el = etree.SubElement(fig_el, _tag(ns, "image"))
                if image_href:
                    img_el.set("href", image_href)
                else:
                    img_el.set("href", "")
                    img_el.set("placement", "inline")
                    alt = etree.SubElement(img_el, _tag(ns, "alt"))
                    _safe_text(alt, f"[IMAGE — {caption}]")
                continue

            # ---- Codeblock ----
            if de == "codeblock":
                flush_all()
                cb_el = etree.SubElement(parent, _tag(ns, "codeblock"))
                _safe_text(cb_el, text)
                continue

            # ---- Table (CALS) ----
            if de == "table":
                flush_all()
                rows = block.get("rows", [])
                if not rows:
                    continue
                ncols = max(len(r) for r in rows)
                tbl = etree.SubElement(parent, _tag(ns, "table"))
                tbl.set("frame", "all")
                tgroup = etree.SubElement(tbl, _tag(ns, "tgroup"))
                tgroup.set("cols", str(ncols))
                for ci in range(1, ncols + 1):
                    cs = etree.SubElement(tgroup, _tag(ns, "colspec"))
                    cs.set("colname", f"col{ci}")
                    cs.set("colnum", str(ci))
                # Header row
                thead_el = etree.SubElement(tgroup, _tag(ns, "thead"))
                hrow = etree.SubElement(thead_el, _tag(ns, "row"))
                for cell in rows[0]:
                    entry = etree.SubElement(hrow, _tag(ns, "entry"))
                    _safe_text(entry, str(cell))
                # Body rows
                if len(rows) > 1:
                    tbody_el = etree.SubElement(tgroup, _tag(ns, "tbody"))
                    for row_data in rows[1:]:
                        row_el = etree.SubElement(tbody_el, _tag(ns, "row"))
                        for ci, cell in enumerate(row_data):
                            entry = etree.SubElement(row_el, _tag(ns, "entry"))
                            _safe_text(entry, str(cell))
                        # Pad missing cells
                        for _ in range(ncols - len(row_data)):
                            etree.SubElement(row_el, _tag(ns, "entry"))
                continue

            # ---- Definition list ----
            if de == "dl":
                flush_all()
                rows = block.get("rows", [])
                if not rows:
                    continue
                dl_el = etree.SubElement(parent, _tag(ns, "dl"))
                for row_data in rows[1:]:  # skip header row
                    if len(row_data) >= 2:
                        dle = etree.SubElement(dl_el, _tag(ns, "dlentry"))
                        dt = etree.SubElement(dle, _tag(ns, "dt"))
                        _safe_text(dt, str(row_data[0]))
                        dd = etree.SubElement(dle, _tag(ns, "dd"))
                        _safe_text(dd, str(row_data[1]))
                continue

            # ---- Dropped / None ----
            if de in ("dropped", None):
                continue

            # ---- Generic fallback ----
            flush_all()
            fb = etree.SubElement(parent, _tag(ns, "p"))
            _safe_text(fb, text)

        flush_all()
