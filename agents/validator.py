"""
DITA Converter Tool — Agent 4: Validator
==========================================
Validates generated DITA 1.3 XML and produces a human-readable report.

Checks performed:
  1. XML well-formedness (lxml parse)
  2. Required structure: root element, topic id, <title>
  3. Content inventory: sections, notes, steps, tables, figures
  4. Structural warnings: empty sections, empty steps groups, empty notes
  5. Unmapped block count (from mapper fallback_count)
  6. Dropped block count (from extractor dropped_count)
  7. Approximate word count

Session: S-05
Author: Coder
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from lxml import etree


# ---------------------------------------------------------------------------
# Allowed DITA 1.3 root tags
# ---------------------------------------------------------------------------
VALID_ROOT_TAGS = {"concept", "task", "reference", "topic"}

# Strip XML declaration + DOCTYPE to get the root element for parsing
ROOT_START_RE = re.compile(r"<(?:concept|task|reference|topic)\b")


@dataclass
class ValidationResult:
    """
    Result of a DITA XML validation run.

    Attributes:
        is_valid:        True if XML is well-formed with no critical errors.
        xml_clean:       Pretty-printed XML string (empty string if invalid).
        errors:          Critical errors that make the output unusable.
        warnings:        Non-critical issues worth reviewing.
        unmapped_blocks: Blocks that fell back to default element in Mapper.
        dropped_blocks:  Blocks silently dropped during Extraction.
        stats:           Dict of content counts (sections, notes, etc.)
        report:          Human-readable plain-text validation summary.
    """
    is_valid:        bool       = False
    xml_clean:       str        = ""
    errors:          list[str]  = field(default_factory=list)
    warnings:        list[str]  = field(default_factory=list)
    unmapped_blocks: int        = 0
    dropped_blocks:  int        = 0
    stats:           dict       = field(default_factory=dict)
    report:          str        = ""


class ValidatorError(Exception):
    """Raised when the validator itself encounters an unexpected error."""
    pass


class Validator:
    """
    Validates DITA 1.3 XML and produces a human-readable report.

    Usage:
        validator = Validator()
        result = validator.validate(
            xml_string,
            dropped_blocks=extractor.dropped_count,
            unmapped_blocks=mapper.fallback_count,
            source_filename="MDE-5570A.pdf",
        )
        print(result.report)
    """

    def validate(
        self,
        xml_string: str,
        dropped_blocks: int = 0,
        unmapped_blocks: int = 0,
        source_filename: str = "",
    ) -> ValidationResult:
        """
        Validate a DITA XML string.

        Args:
            xml_string:      The complete DITA XML string (incl. declaration).
            dropped_blocks:  Count of blocks dropped during extraction.
            unmapped_blocks: Count of blocks that fell to fallback element.
            source_filename: Source file name for report header.

        Returns:
            ValidationResult with full details and human-readable report.
        """
        result = ValidationResult(
            dropped_blocks=dropped_blocks,
            unmapped_blocks=unmapped_blocks,
        )

        try:
            doc = self._parse(xml_string, result)
            if doc is not None:
                self._check_structure(doc, result)
                self._collect_stats(doc, result)
                result.xml_clean = self._pretty_print(doc)
                result.is_valid = len(result.errors) == 0
        except Exception as exc:
            result.errors.append(f"Validator internal error: {exc}")
            result.is_valid = False

        result.report = self._build_report(result, source_filename)
        return result

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------

    def _parse(
        self, xml_string: str, result: ValidationResult
    ) -> etree._Element | None:
        """
        Parse the XML string with lxml.

        Strips the XML declaration and DOCTYPE before parsing (lxml does
        not validate against external DTDs in this mode — well-formedness only).

        Returns the root Element, or None if parsing fails.
        """
        # Find root element start
        match = ROOT_START_RE.search(xml_string)
        if not match:
            result.errors.append(
                "Could not locate DITA root element "
                "(expected <concept>, <task>, or <reference>)."
            )
            return None

        xml_body = xml_string[match.start():]

        try:
            doc = etree.fromstring(xml_body.encode("utf-8"))
            return doc
        except etree.XMLSyntaxError as exc:
            result.errors.append(
                f"XML is not well-formed: {exc.msg} "
                f"(line {exc.lineno}, column {exc.offset})"
            )
            return None

    # ------------------------------------------------------------------
    # Structure checks
    # ------------------------------------------------------------------

    def _check_structure(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Run all structural checks against the parsed document."""
        self._check_root(doc, result)
        self._check_title(doc, result)
        self._check_sections(doc, result)
        self._check_steps(doc, result)
        self._check_notes(doc, result)
        self._check_tables(doc, result)
        self._check_figs(doc, result)

    def _check_root(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Validate root element tag and required id attribute."""
        if doc.tag not in VALID_ROOT_TAGS:
            result.errors.append(
                f"Invalid root element <{doc.tag}>. "
                f"Expected one of: {sorted(VALID_ROOT_TAGS)}."
            )
        topic_id = doc.get("id")
        if not topic_id:
            result.errors.append("Root element is missing required 'id' attribute.")
        elif not re.match(r"^[a-z][a-z0-9_]*$", topic_id):
            result.warnings.append(
                f"Topic id '{topic_id}' contains unexpected characters. "
                "DITA ids should be lowercase alphanumeric with underscores."
            )

    def _check_title(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Verify exactly one <title> as a direct child of root."""
        titles = doc.findall("title")
        if len(titles) == 0:
            result.errors.append(
                "Document is missing required <title> element."
            )
        elif len(titles) > 1:
            result.warnings.append(
                f"Found {len(titles)} <title> elements as root children. "
                "DITA topics should have exactly one."
            )
        else:
            title_text = titles[0].text or ""
            if not title_text.strip():
                result.warnings.append("<title> element is present but empty.")

    def _check_sections(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Warn on sections that have a title but no content children."""
        sections = doc.findall(".//section")
        empty = []
        for sec in sections:
            children = list(sec)
            non_title = [c for c in children if c.tag != "title"]
            if not non_title:
                title_el = sec.find("title")
                label = title_el.text if title_el is not None else "(untitled)"
                empty.append(label)
        if empty:
            result.warnings.append(
                f"{len(empty)} section(s) contain only a title and no body content: "
                + ", ".join(f"'{s}'" for s in empty[:5])
                + (" ..." if len(empty) > 5 else "")
            )

    def _check_steps(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Warn on <steps> groups with no <step> children."""
        steps_groups = doc.findall(".//steps")
        empty = [s for s in steps_groups if not s.findall("step")]
        if empty:
            result.warnings.append(
                f"{len(empty)} <steps> element(s) contain no <step> children."
            )

        # Warn on steps missing <cmd>
        all_steps = doc.findall(".//step")
        no_cmd = [s for s in all_steps if s.find("cmd") is None]
        if no_cmd:
            result.warnings.append(
                f"{len(no_cmd)} <step> element(s) are missing required <cmd> child."
            )

    def _check_notes(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Warn on notes missing type attribute or with no content."""
        notes = doc.findall(".//note")
        no_type  = [n for n in notes if not n.get("type")]
        no_content = [
            n for n in notes
            if not list(n) and not (n.text or "").strip()
        ]
        if no_type:
            result.warnings.append(
                f"{len(no_type)} <note> element(s) are missing the 'type' attribute."
            )
        if no_content:
            result.warnings.append(
                f"{len(no_content)} <note> element(s) appear to be empty."
            )

    def _check_tables(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Warn on tables missing thead or tbody."""
        tables = doc.findall(".//table")
        for i, table in enumerate(tables, 1):
            tgroup = table.find("tgroup")
            if tgroup is None:
                result.warnings.append(f"Table {i} is missing <tgroup>.")
                continue
            if tgroup.find("thead") is None:
                result.warnings.append(f"Table {i} is missing <thead>.")
            if tgroup.find("tbody") is None:
                result.errors.append(f"Table {i} is missing required <tbody>.")

    def _check_figs(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Warn on figures missing title."""
        figs = doc.findall(".//fig")
        no_title = [f for f in figs if f.find("title") is None]
        if no_title:
            result.warnings.append(
                f"{len(no_title)} <fig> element(s) are missing a <title>."
            )

    # ------------------------------------------------------------------
    # Stats collection
    # ------------------------------------------------------------------

    def _collect_stats(
        self, doc: etree._Element, result: ValidationResult
    ) -> None:
        """Collect content inventory statistics."""
        all_text  = " ".join(doc.itertext())
        word_count = len(all_text.split())

        result.stats = {
            "topic_type":  doc.tag,
            "topic_id":    doc.get("id", ""),
            "title":       (doc.findtext("title") or "").strip(),
            "sections":    len(doc.findall(".//section")),
            "sectiondivs": len(doc.findall(".//sectiondiv")),
            "notes":       len(doc.findall(".//note")),
            "steps":       len(doc.findall(".//step")),
            "ul_items":    len(doc.findall(".//ul/li")),
            "ol_items":    len(doc.findall(".//ol/li")),
            "tables":      len(doc.findall(".//table")),
            "figs":        len(doc.findall(".//fig")),
            "codeblocks":  len(doc.findall(".//codeblock")),
            "word_count":  word_count,
        }

    # ------------------------------------------------------------------
    # Pretty-print
    # ------------------------------------------------------------------

    def _pretty_print(self, doc: etree._Element) -> str:
        """Return consistently indented XML string from parsed document."""
        etree.indent(doc, space="  ")
        return etree.tostring(
            doc,
            pretty_print=True,
            encoding="unicode",
            xml_declaration=False,
        )

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def _build_report(
        self, result: ValidationResult, source_filename: str
    ) -> str:
        """Build a human-readable plain-text validation report."""
        lines: list[str] = []
        SEP  = "─" * 60
        SEP2 = "═" * 60

        lines.append(SEP2)
        lines.append("  DITA Converter Tool — Validation Report")
        lines.append(SEP2)

        if source_filename:
            lines.append(f"  Source  : {source_filename}")

        status = "✓  VALID" if result.is_valid else "✗  INVALID"
        lines.append(f"  Status  : {status}")
        lines.append(SEP)

        # --- Pipeline summary ---
        lines.append("  PIPELINE SUMMARY")
        lines.append(f"    Blocks dropped during extraction : {result.dropped_blocks}")
        lines.append(f"    Blocks using fallback element   : {result.unmapped_blocks}")
        lines.append("")

        # --- Content inventory ---
        if result.stats:
            s = result.stats
            lines.append("  CONTENT INVENTORY")
            lines.append(f"    Topic type    : {s.get('topic_type','')}")
            lines.append(f"    Topic id      : {s.get('topic_id','')}")
            lines.append(f"    Title         : {s.get('title','')}")
            lines.append(f"    Sections      : {s.get('sections', 0)}")
            lines.append(f"    Notes         : {s.get('notes', 0)}")
            lines.append(f"    Steps         : {s.get('steps', 0)}")
            lines.append(f"    Bullet items  : {s.get('ul_items', 0)}")
            lines.append(f"    Tables        : {s.get('tables', 0)}")
            lines.append(f"    Figures       : {s.get('figs', 0)}")
            lines.append(f"    Code blocks   : {s.get('codeblocks', 0)}")
            lines.append(f"    Word count    : ~{s.get('word_count', 0):,}")
            lines.append("")

        # --- Errors ---
        if result.errors:
            lines.append(f"  ERRORS  ({len(result.errors)})")
            for err in result.errors:
                lines.append(f"    ✗  {err}")
            lines.append("")
        else:
            lines.append("  ERRORS  : none")
            lines.append("")

        # --- Warnings ---
        if result.warnings:
            lines.append(f"  WARNINGS  ({len(result.warnings)})")
            for warn in result.warnings:
                lines.append(f"    ⚠  {warn}")
            lines.append("")
        else:
            lines.append("  WARNINGS  : none")
            lines.append("")

        # --- Guidance ---
        if result.unmapped_blocks > 0:
            lines.append("  NOTE")
            lines.append(
                f"    {result.unmapped_blocks} block(s) were mapped using the fallback element."
            )
            lines.append(
                "    Review mapping_rules.yaml and add rules for these patterns"
            )
            lines.append("    to improve conversion quality.")
            lines.append("")

        if not result.is_valid:
            lines.append("  NEXT STEPS")
            lines.append("    1. Review errors above.")
            lines.append("    2. Check that the source file is text-based (not scanned).")
            lines.append("    3. Verify mapping_rules.yaml is correctly configured.")
            lines.append("")

        lines.append(SEP2)
        return "\n".join(lines)
