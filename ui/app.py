"""
ui/app.py
DITA Converter Tool — Streamlit UI

S-09 updates:
  - Dark mode default; light mode toggle in sidebar
  - .ditamap generated and shown as primary map view
  - Checkbox multi-select per topic → selective ZIP or single .dita download
  - @id removed from topics (per-chunk type detection in generator)

Run:
    streamlit run ui/app.py
"""

from __future__ import annotations

import io
import sys
import zipfile
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.extractor import extract_pdf, extract_docx, ExtractorError  # noqa
from agents.mapper import Mapper                                          # noqa
from agents.generator import Generator                                    # noqa
from agents.validator import Validator                                    # noqa

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DITA Converter",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme state
# ---------------------------------------------------------------------------

if "light_mode" not in st.session_state:
    st.session_state.light_mode = False

_DARK_CSS = """
<style>
  /* ── Material dark theme ──────────────────────────────────────────────
     Background:  #121212  (base surface — not pure black)
     Surface dp1: #1E1E1E  (cards, sidebar)
     Surface dp4: #252525  (inputs, code blocks)
     Surface dp8: #2C2C2C  (elevated panels)
     Primary text:    rgba(255,255,255,0.87)  — #DEDEDE
     Secondary text:  rgba(255,255,255,0.60)  — #9E9E9E
     Disabled text:   rgba(255,255,255,0.38)
     Accent (blue):   #82B1FF  (desaturated, not vibrant)
     Border:          #2C2C2C → #333333
  ─────────────────────────────────────────────────────────────────────── */

  /* App shell */
  .stApp {
    background-color: #121212;
    color: rgba(255,255,255,0.87);
  }

  /* Sidebar — dp1 surface */
  section[data-testid="stSidebar"] {
    background-color: #1E1E1E;
    border-right: 1px solid #2C2C2C;
  }
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] li,
  section[data-testid="stSidebar"] span,
  section[data-testid="stSidebar"] label {
    color: rgba(255,255,255,0.87) !important;
  }
  section[data-testid="stSidebar"] .stCaption {
    color: rgba(255,255,255,0.60) !important;
  }

  /* Main content text */
  p, li, span, label, .stMarkdown {
    color: rgba(255,255,255,0.87);
  }
  .stCaption, small, .stCaption p {
    color: rgba(255,255,255,0.60) !important;
  }

  /* Tabs — dp1 surface */
  .stTabs [data-baseweb="tab-list"] {
    background-color: #1E1E1E;
    border-radius: 8px;
    border: 1px solid #2C2C2C;
    gap: 4px;
    padding: 4px;
  }
  .stTabs [data-baseweb="tab"] {
    color: rgba(255,255,255,0.60);
    border-radius: 6px;
  }
  .stTabs [aria-selected="true"] {
    color: rgba(255,255,255,0.87) !important;
    background-color: #252525 !important;
    border-bottom: 2px solid #82B1FF !important;
  }
  .stTabs [data-baseweb="tab"]:hover {
    color: rgba(255,255,255,0.87) !important;
    background-color: #252525 !important;
  }

  /* Code blocks — dp4 surface */
  .stCodeBlock, pre, code {
    background-color: #1E1E1E !important;
    color: rgba(255,255,255,0.87) !important;
    border: 1px solid #2C2C2C !important;
    border-radius: 6px !important;
  }

  /* Metrics — dp1 surface */
  [data-testid="metric-container"] {
    background-color: #1E1E1E;
    border: 1px solid #2C2C2C;
    border-radius: 8px;
    padding: 14px;
  }
  [data-testid="metric-container"] label {
    color: rgba(255,255,255,0.60) !important;
    font-size: 0.8em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  [data-testid="metric-container"] [data-testid="metric-value"] {
    color: rgba(255,255,255,0.87) !important;
  }

  /* Expanders — dp1 surface */
  details, [data-testid="stExpander"] {
    background-color: #1E1E1E !important;
    border: 1px solid #2C2C2C !important;
    border-radius: 8px !important;
  }
  [data-testid="stExpander"] summary {
    color: rgba(255,255,255,0.87) !important;
  }

  /* Inputs — dp4 surface */
  input, textarea, [data-baseweb="input"], [data-baseweb="textarea"] {
    background-color: #252525 !important;
    color: rgba(255,255,255,0.87) !important;
    border: 1px solid #333333 !important;
    border-radius: 6px !important;
  }
  input::placeholder, textarea::placeholder {
    color: rgba(255,255,255,0.38) !important;
  }
  input:focus, textarea:focus {
    border-color: #82B1FF !important;
    box-shadow: 0 0 0 2px rgba(130,177,255,0.15) !important;
  }

  /* Select box */
  [data-baseweb="select"] {
    background-color: #252525 !important;
    border: 1px solid #333333 !important;
    border-radius: 6px !important;
  }
  [data-baseweb="select"] span {
    color: rgba(255,255,255,0.87) !important;
  }

  /* File uploader */
  [data-testid="stFileUploader"] {
    background-color: #1E1E1E;
    border: 1px dashed #333333;
    border-radius: 8px;
  }

  /* Buttons */
  .stButton button {
    background-color: #252525;
    color: rgba(255,255,255,0.87);
    border: 1px solid #333333;
    border-radius: 6px;
  }
  .stButton button:hover {
    background-color: #2C2C2C;
    border-color: #82B1FF;
    color: #82B1FF;
  }

  /* Divider */
  hr { border-color: #2C2C2C; }

  /* Alert / info boxes */
  [data-testid="stAlert"] {
    background-color: #1E1E1E !important;
    border-radius: 8px !important;
    border-left-width: 3px !important;
  }

  /* Topic cards — dp1 surface, subtle border */
  .topic-card {
    background: #1E1E1E;
    border: 1px solid #2C2C2C;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 6px;
    transition: border-color 0.15s ease;
  }
  .topic-card:hover {
    border-color: #82B1FF;
  }
  .topic-card strong {
    color: rgba(255,255,255,0.87);
  }

  /* Type badges — desaturated colours per Material dark spec */
  .badge-task {
    background: rgba(129,199,132,0.15);
    color: #81C784;
    border-radius: 4px; padding: 2px 8px; font-size: 0.75em;
    font-weight: 600; letter-spacing: 0.03em;
  }
  .badge-concept {
    background: rgba(130,177,255,0.15);
    color: #82B1FF;
    border-radius: 4px; padding: 2px 8px; font-size: 0.75em;
    font-weight: 600; letter-spacing: 0.03em;
  }
  .badge-reference {
    background: rgba(255,204,128,0.15);
    color: #FFCC80;
    border-radius: 4px; padding: 2px 8px; font-size: 0.75em;
    font-weight: 600; letter-spacing: 0.03em;
  }
  .badge-topic {
    background: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.60);
    border-radius: 4px; padding: 2px 8px; font-size: 0.75em;
    font-weight: 600; letter-spacing: 0.03em;
  }
</style>
"""

_LIGHT_CSS = """
<style>
  /* Material light theme */
  .stApp { background-color: #FAFAFA; color: rgba(0,0,0,0.87); }

  section[data-testid="stSidebar"] {
    background-color: #F5F5F5;
    border-right: 1px solid #E0E0E0;
  }

  .stTabs [data-baseweb="tab-list"] {
    background-color: #F5F5F5;
    border-radius: 8px;
    border: 1px solid #E0E0E0;
    gap: 4px; padding: 4px;
  }
  .stTabs [data-baseweb="tab"] { color: rgba(0,0,0,0.60); border-radius: 6px; }
  .stTabs [aria-selected="true"] {
    color: rgba(0,0,0,0.87) !important;
    background-color: #FFFFFF !important;
    border-bottom: 2px solid #1565C0 !important;
  }

  [data-testid="metric-container"] {
    background-color: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px; padding: 14px;
  }
  [data-testid="metric-container"] label {
    color: rgba(0,0,0,0.60) !important;
    font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em;
  }

  details, [data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E0E0E0 !important;
    border-radius: 8px !important;
  }

  .topic-card {
    background: #FFFFFF;
    border: 1px solid #E0E0E0;
    border-radius: 8px; padding: 12px 16px; margin-bottom: 6px;
    transition: border-color 0.15s ease;
  }
  .topic-card:hover { border-color: #1565C0; }

  .badge-task      { background:#E8F5E9; color:#2E7D32; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; }
  .badge-concept   { background:#E3F2FD; color:#1565C0; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; }
  .badge-reference { background:#FFF8E1; color:#E65100; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; }
  .badge-topic     { background:#F5F5F5; color:rgba(0,0,0,0.60); border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; }
</style>
"""

st.markdown(_LIGHT_CSS if st.session_state.light_mode else _DARK_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_type_from_xml(xml_str: str) -> str:
    """Extract the topic type from the root element of a DITA XML string."""
    _VALID = {"concept", "task", "reference", "topic"}
    try:
        from lxml import etree as _et
        clean = "\n".join(
            l for l in xml_str.splitlines()
            if not l.strip().startswith("<?")
            and not l.strip().startswith("<!DOCTYPE")
        )
        root = _et.fromstring(clean.encode())
        local = _et.QName(root.tag).localname
        return local if local in _VALID else "topic"
    except Exception:
        return "topic"


def _badge(ttype: str) -> str:
    return f'<span class="badge-{ttype}">{ttype}</span>'


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📄 DITA Converter")
    st.caption("PDF & DOCX → DITA 2.0 XML")

    mode_label = "☀️ Light Mode" if not st.session_state.light_mode else "🌙 Dark Mode"
    if st.button(mode_label, use_container_width=True):
        st.session_state.light_mode = not st.session_state.light_mode
        st.rerun()

    st.divider()
    st.subheader("⚙️ Configuration")
    st.markdown("""
- **Mapping profile:** Gilbarco Passport
- **DITA version:** 2.0
- **Multi-topic:** enabled
- **Map:** .ditamap generated
""")
    st.divider()
    st.subheader("🔁 Pipeline")
    st.markdown("""
`[EXTRACTOR]` → Parse structure
`[MAPPER]` → Apply YAML rules
`[GENERATOR]` → Build DITA 2.0 XML
`[VALIDATOR]` → Check & report
""")
    st.divider()
    st.caption("Supported: `.pdf`, `.docx`")

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("DITA 2.0 Converter Tool")
st.markdown("Upload a text-based PDF or DOCX to convert to **DITA 2.0 XML** with a `.ditamap`.")

left_col, right_col = st.columns([1, 1.7])

# ---------------------------------------------------------------------------
# LEFT — Upload + options
# ---------------------------------------------------------------------------

with left_col:
    st.subheader("1 · Upload")
    uploaded_file = st.file_uploader(
        "Select a PDF or DOCX file",
        type=["pdf", "docx"],
        help="Text-based PDFs only. Scanned PDFs are not supported.",
    )

    st.subheader("2 · Image Folder (DOCX only, optional)")
    with st.expander("ℹ️ How to provide DOCX images"):
        st.markdown("""
**Steps:**
1. Copy your `.docx` file
2. Rename the copy: `.docx` → `.zip`
3. Extract the `.zip`
4. Navigate to: extracted folder → `word/` → `media/`
5. Paste the full path to `media/` below

**Example:**
`D:\\Projects\\ToDita - Claude\\extracted\\word\\media`
""")

    image_folder = st.text_input(
        "Media folder path",
        placeholder="D:\\path\\to\\extracted\\word\\media",
    )
    if image_folder and not Path(image_folder).is_dir():
        st.warning("⚠️ Folder not found — images will be skipped.")
        image_folder = ""

    st.divider()
    run_button = st.button(
        "▶  Convert to DITA 2.0",
        type="primary",
        disabled=uploaded_file is None,
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# RIGHT — Output
# ---------------------------------------------------------------------------

with right_col:
    if "results" not in st.session_state:
        st.session_state.results = None

    if run_button and uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_name  = uploaded_file.name
        is_pdf     = file_name.lower().endswith(".pdf")
        status_box = st.empty()

        def _status(msg: str):
            status_box.info(msg)

        try:
            t0 = time.time()

            _status("⏳ `[EXTRACTOR]` — Parsing document structure…")
            blocks = (extract_pdf(file_bytes) if is_pdf
                      else extract_docx(file_bytes, image_folder=image_folder))
            _status(f"✅ `[EXTRACTOR]` — {len(blocks)} blocks extracted")

            _status("⏳ `[MAPPER]` — Applying YAML mapping rules…")
            blocks = Mapper().map(blocks)
            _status("✅ `[MAPPER]` — Blocks annotated")

            _status("⏳ `[GENERATOR]` — Generating DITA 2.0 topics…")
            gen         = Generator()
            topic_files = gen.generate(blocks)
            map_title   = (Path(file_name).stem
                           .replace("_", " ").replace("-", " ").title())
            ditamap_str  = gen.generate_ditamap(topic_files, map_title=map_title)
            ditamap_name = Path(file_name).stem + ".ditamap"
            n_topics     = len(topic_files)
            _status(f"✅ `[GENERATOR]` — {n_topics} topic(s) + .ditamap")

            _status("⏳ `[VALIDATOR]` — Validating XML…")
            validator = Validator()
            validation_results = [
                (fname, xml_str, validator.validate(xml_str, blocks, filename=fname))
                for fname, xml_str in topic_files
            ]
            total_errors   = sum(len(vr.errors)   for _, _, vr in validation_results)
            total_warnings = sum(len(vr.warnings)  for _, _, vr in validation_results)
            elapsed = time.time() - t0

            _status(
                f"{'✅' if total_errors == 0 else '⚠️'} `[VALIDATOR]` — "
                f"{total_errors} errors · {total_warnings} warnings · {elapsed:.2f}s"
            )

            st.session_state.results = {
                "topic_files":  validation_results,
                "ditamap_str":  ditamap_str,
                "ditamap_name": ditamap_name,
                "n_topics":     n_topics,
                "source_name":  file_name,
                "map_title":    map_title,
                "elapsed":      elapsed,
                "blocks":       blocks,
            }

        except ExtractorError as exc:
            status_box.error(f"❌ Extraction failed: {exc}")
            st.info("💡 Only text-based (digital) PDFs are supported.")
            st.session_state.results = None
        except Exception as exc:
            status_box.error(f"❌ Unexpected error: {exc}")
            st.session_state.results = None

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------

    if st.session_state.results:
        res          = st.session_state.results
        topic_files  = res["topic_files"]
        ditamap_str  = res["ditamap_str"]
        ditamap_name = res["ditamap_name"]
        n_topics     = res["n_topics"]
        map_title    = res["map_title"]

        st.divider()
        tabs = st.tabs(["🗺️ DITA Map", "📄 Topic XML", "✅ Validation", "📊 Stats"])

        # ── TAB 1: DITA Map ──────────────────────────────────────────────
        with tabs[0]:
            st.subheader(f"📋 {map_title}")
            st.caption(f"{n_topics} topic(s) — check boxes to select, then export")

            selected_indices: list[int] = []
            for i, (fname, xml_str, vr) in enumerate(topic_files):
                ttype       = _topic_type_from_xml(xml_str)
                title       = vr.stats.get("title", fname.replace(".dita", ""))
                words       = vr.stats.get("word_count", 0)
                secs        = vr.stats.get("sections", 0)
                errs        = len(vr.errors)
                warns       = len(vr.warnings)
                status_icon = "🔴" if errs else ("🟡" if warns else "🟢")

                col_chk, col_info = st.columns([0.07, 0.93])
                with col_chk:
                    checked = st.checkbox(
                        label="select", key=f"chk_{i}",
                        value=False, label_visibility="collapsed"
                    )
                with col_info:
                    st.markdown(
                        f'<div class="topic-card">'
                        f'{status_icon}&nbsp; {_badge(ttype)}&nbsp; '
                        f'<strong>{title}</strong><br/>'
                        f'<small style="opacity:0.6">'
                        f'{fname} &nbsp;·&nbsp; {words} words'
                        f'{f" &nbsp;·&nbsp; {secs} sections" if secs else ""}'
                        f'</small></div>',
                        unsafe_allow_html=True,
                    )
                if checked:
                    selected_indices.append(i)

            st.divider()

            # Download row
            col_map, col_sel, col_all = st.columns(3)

            with col_map:
                st.download_button(
                    "⬇️ .ditamap",
                    data=ditamap_str.encode("utf-8"),
                    file_name=ditamap_name,
                    mime="application/xml",
                    use_container_width=True,
                    help="Download the DITA map referencing all topics",
                )

            with col_sel:
                n_sel = len(selected_indices)
                if n_sel == 1:
                    i = selected_indices[0]
                    fname, xml_str, _ = topic_files[i]
                    st.download_button(
                        f"⬇️ Export {n_sel} topic",
                        data=xml_str.encode("utf-8"),
                        file_name=fname,
                        mime="application/xml",
                        use_container_width=True,
                        type="primary",
                        help="Download the selected topic as a .dita file",
                    )
                elif n_sel > 1:
                    sel_files  = [topic_files[i] for i in selected_indices]
                    sel_tuples = [(f, x) for f, x, _ in sel_files]
                    scoped_map = Generator().generate_ditamap(
                        sel_tuples,
                        map_title=f"{map_title} (selection)",
                    )
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for fname, xml_str, _ in sel_files:
                            zf.writestr(fname, xml_str.encode("utf-8"))
                        zf.writestr(
                            ditamap_name.replace(".ditamap", "_selection.ditamap"),
                            scoped_map.encode("utf-8"),
                        )
                    buf.seek(0)
                    st.download_button(
                        f"⬇️ Export {n_sel} topics",
                        data=buf,
                        file_name=ditamap_name.replace(".ditamap", f"_selection_{n_sel}.zip"),
                        mime="application/zip",
                        use_container_width=True,
                        type="primary",
                        help="Download selected topics + scoped .ditamap as ZIP",
                    )
                else:
                    st.button(
                        "⬇️ Export selected",
                        disabled=True,
                        use_container_width=True,
                        help="Check one or more topics above to enable",
                    )

            with col_all:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fname, xml_str, _ in topic_files:
                        zf.writestr(fname, xml_str.encode("utf-8"))
                    zf.writestr(ditamap_name, ditamap_str.encode("utf-8"))
                buf.seek(0)
                zip_name = Path(res["source_name"]).stem + "_dita.zip"
                st.download_button(
                    "⬇️ Export all (ZIP)",
                    data=buf,
                    file_name=zip_name,
                    mime="application/zip",
                    use_container_width=True,
                    help="Download all topics + .ditamap as ZIP",
                )

            with st.expander("📄 View .ditamap XML"):
                st.code(ditamap_str, language="xml")

        # ── TAB 2: Topic XML ──────────────────────────────────────────────
        with tabs[1]:
            if n_topics == 1:
                _, xml_str, _ = topic_files[0]
                display = (xml_str if len(xml_str) <= 50_000
                           else xml_str[:50_000] + "\n<!-- truncated — download for full file -->")
                st.code(display, language="xml")
            else:
                names = [fname for fname, _, _ in topic_files]
                sel   = st.selectbox("Select topic to preview:", names)
                for fname, xml_str, _ in topic_files:
                    if fname == sel:
                        display = (xml_str if len(xml_str) <= 50_000
                                   else xml_str[:50_000] + "\n<!-- truncated -->")
                        st.code(display, language="xml")
                        break

        # ── TAB 3: Validation ─────────────────────────────────────────────
        with tabs[2]:
            for fname, _, vr in topic_files:
                with st.expander(f"📄 {fname}", expanded=(n_topics == 1)):
                    if vr.errors:
                        for e in vr.errors:
                            st.error(e)
                    if vr.warnings:
                        for w in vr.warnings:
                            st.warning(w)
                    if not vr.errors and not vr.warnings:
                        st.success("Clean — no errors or warnings.")
                    st.code(vr.report, language="text")

        # ── TAB 4: Stats ──────────────────────────────────────────────────
        with tabs[3]:
            all_stats      = [vr.stats for _, _, vr in topic_files]
            total_words    = sum(s.get("word_count", 0) for s in all_stats)
            total_sections = sum(s.get("sections",   0) for s in all_stats)
            total_notes    = sum(s.get("notes",       0) for s in all_stats)
            total_steps    = sum(s.get("steps",       0) for s in all_stats)
            total_tables   = sum(s.get("tables",      0) for s in all_stats)
            total_figs     = sum(s.get("figures",     0) for s in all_stats)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Topics",   n_topics)
            m2.metric("Words",    total_words)
            m3.metric("Sections", total_sections)
            m4.metric("Notes",    total_notes)

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Steps",    total_steps)
            m6.metric("Tables",   total_tables)
            m7.metric("Figures",  total_figs)
            m8.metric("Time (s)", f"{res['elapsed']:.2f}")

            if n_topics > 1:
                st.subheader("Per-topic breakdown")
                for fname, xml_str, vr in topic_files:
                    ttype = _topic_type_from_xml(xml_str)
                    s = vr.stats
                    st.markdown(
                        f"**{fname}** `{ttype}` — "
                        f"{s.get('word_count',0)} words · "
                        f"{s.get('sections',0)} sections · "
                        f"{s.get('steps',0)} steps · "
                        f"{s.get('notes',0)} notes"
                    )

            if res["blocks"]:
                fb = res["blocks"][0].get("metadata", {}).get("fallback_count", 0)
                if fb > 0:
                    st.warning(
                        f"⚠️ {fb} block(s) used fallback `<p>`. "
                        "Review the Validation tab for details."
                    )
