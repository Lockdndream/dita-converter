"""
DITA Converter Tool — Streamlit UI
====================================
Convert text-based PDF and DOCX files to valid DITA 1.3 XML.

Run with:
    streamlit run ui/app.py

Session: S-06
Author: Coder
"""

import io
import os
import sys
import tempfile
import time
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path when launched from ui/
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.extractor import Extractor, ExtractorError
from agents.mapper import Mapper
from agents.generator import Generator
from agents.validator import Validator, ValidationResult

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="DITA Converter Tool",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RULES_PATH      = ROOT / "config" / "mapping_rules.yaml"
ACCEPTED_TYPES  = ["pdf", "docx"]
ACCENT_COLOR    = "#2E75B6"
SUCCESS_COLOR   = "#375623"
WARNING_COLOR   = "#C55A11"
ERROR_COLOR     = "#C00000"

# ---------------------------------------------------------------------------
# CSS — minimal styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Tone down default Streamlit padding */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

    /* Status badge helpers */
    .badge-valid   { background:#E2EFDA; color:#375623; padding:2px 10px;
                     border-radius:12px; font-weight:600; font-size:0.85rem; }
    .badge-invalid { background:#FFE0E0; color:#C00000; padding:2px 10px;
                     border-radius:12px; font-weight:600; font-size:0.85rem; }
    .badge-info    { background:#D6E4F0; color:#1F3864; padding:2px 10px;
                     border-radius:12px; font-weight:600; font-size:0.85rem; }

    /* Stat card */
    .stat-card     { background:#F2F2F2; border-radius:8px; padding:12px 16px;
                     margin-bottom:8px; }
    .stat-label    { font-size:0.78rem; color:#666; text-transform:uppercase;
                     letter-spacing:0.05em; }
    .stat-value    { font-size:1.5rem; font-weight:700; color:#1F3864; }

    /* Pipeline step */
    .pipe-step     { display:flex; align-items:center; gap:10px;
                     padding:6px 0; font-size:0.9rem; }
    .pipe-icon     { width:24px; text-align:center; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        st.divider()

        st.markdown("**Mapping Profile**")
        st.code("gilbarco_passport_manuals", language=None)

        st.markdown("**DITA Output Version**")
        st.code("1.3", language=None)

        st.markdown("**DITA 2.0 Migration**")
        st.caption("Documented in `docs/01_Architecture.docx`")

        st.divider()
        st.markdown("**Pipeline Stages**")
        stages = [
            ("1", "Extractor",  "PDF/DOCX → Content Tree"),
            ("2", "Mapper",     "Apply YAML rules"),
            ("3", "Generator",  "Content Tree → DITA XML"),
            ("4", "Validator",  "Well-formedness + report"),
        ]
        for num, name, desc in stages:
            st.markdown(
                f'<div class="pipe-step">'
                f'<span class="pipe-icon">'
                f'<span class="badge-info">{num}</span></span>'
                f'<span><strong>{name}</strong> — {desc}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown("**Supported Input**")
        st.markdown("- Text-based PDF ✓")
        st.markdown("- DOCX ✓")
        st.markdown("- Scanned PDF ✗")

        st.divider()
        st.caption(
            "DITA Converter Tool v1.0 · Proof of Concept\n\n"
            "Open source — MIT License"
        )


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------
def run_pipeline(
    file_bytes: bytes,
    filename: str,
    suffix: str,
) -> tuple[str, ValidationResult, str]:
    """
    Run the full Extractor → Mapper → Generator → Validator pipeline.

    Args:
        file_bytes: Raw file content from uploader.
        filename:   Original filename (for display).
        suffix:     File extension (.pdf or .docx).

    Returns:
        Tuple of (xml_string, validation_result, topic_type).

    Raises:
        ExtractorError: If file is unsupported or image-only.
        Exception: On any other pipeline failure.
    """
    # Write to temp file — Extractor works on filesystem paths
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Stage 1 — Extract
        extractor = Extractor(tmp_path)
        content_tree = extractor.extract()

        # Stage 2 — Map
        mapper = Mapper(str(RULES_PATH))
        annotated_tree, topic_type = mapper.map(content_tree)

        # Stage 3 — Generate
        generator = Generator(topic_type)
        xml_string = generator.generate(annotated_tree)

        # Stage 4 — Validate
        validator = Validator()
        result = validator.validate(
            xml_string,
            dropped_blocks=extractor.dropped_count,
            unmapped_blocks=mapper.fallback_count,
            source_filename=filename,
        )

        return xml_string, result, topic_type

    finally:
        # Always clean up the temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Output panels
# ---------------------------------------------------------------------------
def render_stats_cards(result: ValidationResult, topic_type: str) -> None:
    """Render a row of stat cards from the validation result."""
    s = result.stats
    cols = st.columns(4)

    stat_items = [
        ("Topic Type",    topic_type.upper(),         "badge-info"),
        ("Sections",      str(s.get("sections", 0)),  None),
        ("Notes",         str(s.get("notes", 0)),     None),
        ("Steps",         str(s.get("steps", 0)),     None),
    ]
    for col, (label, value, badge) in zip(cols, stat_items):
        with col:
            if badge:
                st.markdown(
                    f'<div class="stat-card">'
                    f'<div class="stat-label">{label}</div>'
                    f'<span class="{badge}">{value}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="stat-card">'
                    f'<div class="stat-label">{label}</div>'
                    f'<div class="stat-value">{value}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    cols2 = st.columns(4)
    stat_items2 = [
        ("Tables",       str(s.get("tables", 0))),
        ("Figures",      str(s.get("figs", 0))),
        ("Bullet Items", str(s.get("ul_items", 0))),
        ("Word Count",   f"~{s.get('word_count', 0):,}"),
    ]
    for col, (label, value) in zip(cols2, stat_items2):
        with col:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="stat-label">{label}</div>'
                f'<div class="stat-value">{value}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_pipeline_summary(result: ValidationResult) -> None:
    """Render pipeline block counts."""
    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            label="Blocks dropped (headers/footers/pagination)",
            value=result.dropped_blocks,
            help="Lines removed during extraction: running headers, footers, "
                 "copyright lines, TOC entries.",
        )
    with c2:
        delta_color = "off" if result.unmapped_blocks == 0 else "inverse"
        st.metric(
            label="Blocks using fallback element",
            value=result.unmapped_blocks,
            delta=None if result.unmapped_blocks == 0 else "Review mapping_rules.yaml",
            delta_color=delta_color,
            help="Blocks where no YAML rule matched. "
                 "Add rules to mapping_rules.yaml to improve these.",
        )


def render_validity_badge(result: ValidationResult) -> None:
    """Show a coloured validity badge."""
    if result.is_valid:
        st.markdown(
            '<span class="badge-valid">✓ VALID DITA 1.3 XML</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="badge-invalid">✗ INVALID — See Errors Below</span>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Header ──────────────────────────────────────────────────────────
    st.markdown(
        "# 📄 DITA Converter Tool"
    )
    st.caption(
        "Convert text-based **PDF** and **DOCX** files to valid **DITA 1.3 XML** · "
        "Proof of Concept v1.0"
    )

    render_sidebar()

    # ── Layout ──────────────────────────────────────────────────────────
    left_col, right_col = st.columns([1, 2], gap="large")

    # ── Left column: upload + progress ──────────────────────────────────
    with left_col:
        st.markdown("### Upload Document")

        uploaded_file = st.file_uploader(
            label="Choose a PDF or DOCX file",
            type=ACCEPTED_TYPES,
            help="Text-based PDFs only. Scanned / image PDFs are not supported.",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            fname  = uploaded_file.name
            suffix = Path(fname).suffix.lower()
            size_kb = len(uploaded_file.getvalue()) / 1024

            st.markdown(f"**File:** `{fname}`")
            st.markdown(f"**Size:** {size_kb:.1f} KB")
            st.divider()

            # ── Run pipeline ─────────────────────────────────────────────
            st.markdown("**Pipeline**")

            stage_states = {
                "Extractor":  "⏳",
                "Mapper":     "⏸",
                "Generator":  "⏸",
                "Validator":  "⏸",
            }

            placeholders = {k: st.empty() for k in stage_states}

            def update_stage(name: str, icon: str, note: str = "") -> None:
                label = f"{icon} **{name}**"
                if note:
                    label += f" — {note}"
                placeholders[name].markdown(label)

            # Initial state
            for name in stage_states:
                update_stage(name, stage_states[name])

            update_stage("Extractor", "🔄", "extracting...")

            try:
                start = time.time()

                # Write to temp + extract
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name

                try:
                    extractor = Extractor(tmp_path)
                    content_tree = extractor.extract()
                finally:
                    os.unlink(tmp_path)

                block_count = len(content_tree)
                update_stage("Extractor", "✅", f"{block_count} blocks")
                update_stage("Mapper", "🔄", "applying rules...")

                mapper = Mapper(str(RULES_PATH))
                annotated_tree, topic_type = mapper.map(content_tree)

                update_stage("Mapper", "✅", f"topic type: {topic_type}")
                update_stage("Generator", "🔄", "building XML...")

                generator = Generator(topic_type)
                xml_string = generator.generate(annotated_tree)

                update_stage("Generator", "✅", f"{len(xml_string):,} chars")
                update_stage("Validator", "🔄", "validating...")

                validator = Validator()
                result = validator.validate(
                    xml_string,
                    dropped_blocks=extractor.dropped_count,
                    unmapped_blocks=mapper.fallback_count,
                    source_filename=fname,
                )

                elapsed = time.time() - start
                v_icon = "✅" if result.is_valid else "❌"
                update_stage(
                    "Validator", v_icon,
                    f"{'valid' if result.is_valid else 'invalid'} · "
                    f"{len(result.errors)} errors · "
                    f"{len(result.warnings)} warnings"
                )

                st.divider()
                st.success(f"Completed in {elapsed:.2f}s", icon="⚡")

                # ── Download button ───────────────────────────────────────
                dita_filename = Path(fname).stem + ".dita"
                st.download_button(
                    label="⬇️  Download .dita file",
                    data=xml_string.encode("utf-8"),
                    file_name=dita_filename,
                    mime="application/xml",
                    use_container_width=True,
                    type="primary",
                )

                # Store results in session state for right column
                st.session_state["result"]     = result
                st.session_state["xml_string"] = xml_string
                st.session_state["topic_type"] = topic_type
                st.session_state["filename"]   = fname

            except ExtractorError as exc:
                update_stage("Extractor", "❌", "failed")
                for name in ["Mapper", "Generator", "Validator"]:
                    update_stage(name, "⏸", "skipped")
                st.error(str(exc), icon="🚫")
                st.info(
                    "**Tip:** Only text-based PDFs are supported. "
                    "If your PDF is scanned, please use a text-extractable version.",
                    icon="💡",
                )
                st.session_state.pop("result", None)

            except Exception as exc:
                st.error(f"Pipeline error: {exc}", icon="❌")
                st.session_state.pop("result", None)

        else:
            # No file uploaded — show instructions
            st.info(
                "Upload a **text-based PDF** or **DOCX** file above to begin "
                "conversion to DITA 1.3 XML.",
                icon="📂",
            )
            st.markdown("**What you'll get:**")
            st.markdown("- Valid DITA 1.3 XML file")
            st.markdown("- XML preview with syntax highlighting")
            st.markdown("- Content inventory and validation report")
            st.markdown("- Downloadable `.dita` file")

    # ── Right column: output tabs ────────────────────────────────────────
    with right_col:
        if "result" not in st.session_state:
            st.markdown("### Output")
            st.markdown(
                '<div style="height:300px; display:flex; align-items:center; '
                'justify-content:center; color:#999; border:2px dashed #ddd; '
                'border-radius:12px; font-size:1.1rem;">'
                '⬅  Upload a document to see output here'
                '</div>',
                unsafe_allow_html=True,
            )
            return

        result     = st.session_state["result"]
        xml_string = st.session_state["xml_string"]
        topic_type = st.session_state["topic_type"]
        filename   = st.session_state["filename"]

        # Validity badge + filename
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown(f"### Output — `{filename}`")
        with col_b:
            st.markdown("<br>", unsafe_allow_html=True)
            render_validity_badge(result)

        # ── Tabs ────────────────────────────────────────────────────────
        tab_xml, tab_report, tab_stats = st.tabs([
            "📝 DITA XML",
            "🔍 Validation Report",
            "📊 Content Stats",
        ])

        with tab_xml:
            st.markdown(
                f"**DITA 1.3 XML** · `{len(xml_string):,}` characters · "
                f"`{len(xml_string.splitlines())}` lines"
            )
            # Display clean (pretty-printed) XML if valid, raw otherwise
            display_xml = result.xml_clean if result.xml_clean else xml_string
            # Trim very large outputs for display performance
            MAX_DISPLAY_CHARS = 50_000
            if len(display_xml) > MAX_DISPLAY_CHARS:
                st.code(
                    display_xml[:MAX_DISPLAY_CHARS] + "\n\n... [truncated for display]",
                    language="xml",
                )
                st.caption(
                    f"⚠ Display limited to {MAX_DISPLAY_CHARS:,} characters. "
                    "Download the full file using the button on the left."
                )
            else:
                st.code(display_xml, language="xml")

        with tab_report:
            st.markdown("**Validation Report**")

            # Errors
            if result.errors:
                for err in result.errors:
                    st.error(err, icon="❌")
            else:
                st.success("No errors found.", icon="✅")

            # Warnings
            if result.warnings:
                st.markdown(f"**Warnings ({len(result.warnings)})**")
                for warn in result.warnings:
                    st.warning(warn, icon="⚠")
            else:
                st.info("No warnings.", icon="ℹ")

            st.divider()
            st.markdown("**Pipeline Summary**")
            render_pipeline_summary(result)

            st.divider()
            st.markdown("**Full Plain-Text Report**")
            st.code(result.report, language=None)

        with tab_stats:
            st.markdown("**Content Inventory**")
            render_stats_cards(result, topic_type)

            st.divider()
            st.markdown("**Topic Details**")
            s = result.stats
            detail_cols = st.columns(2)
            with detail_cols[0]:
                st.markdown(f"**Topic type:** `{s.get('topic_type','')}`")
                st.markdown(f"**Topic ID:** `{s.get('topic_id','')}`")
                st.markdown(f"**Title:** {s.get('title','')}")
            with detail_cols[1]:
                st.markdown(f"**Ol items:** {s.get('ol_items', 0)}")
                st.markdown(f"**Code blocks:** {s.get('codeblocks', 0)}")
                st.markdown(
                    f"**Sectiondivs:** {s.get('sectiondivs', 0)}"
                )

            if result.unmapped_blocks > 0:
                st.divider()
                st.warning(
                    f"**{result.unmapped_blocks} block(s)** were mapped using the "
                    "fallback `<p>` element. To improve mapping quality, add "
                    "matching rules to `config/mapping_rules.yaml`.",
                    icon="⚠",
                )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
