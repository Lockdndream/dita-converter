"""
ui/app.py
DITA Converter Tool — Streamlit UI

Updated in S-08:
  - DITA 2.0 output
  - Multi-topic splitting: separate .dita per H1 section, delivered as ZIP
  - Optional DOCX image folder input with usage instructions
  - Single-topic output still downloads as a plain .dita file

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

# Path resolution: works both from root and from ui/
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.extractor import extract_pdf, extract_docx, ExtractorError  # noqa: E402
from agents.mapper import Mapper  # noqa: E402
from agents.generator import Generator  # noqa: E402
from agents.validator import Validator  # noqa: E402

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DITA Converter",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📄 DITA Converter")
    st.caption("PDF & DOCX → DITA 2.0 XML")
    st.divider()

    st.subheader("⚙️ Configuration")
    st.markdown(f"""
- **Mapping profile:** Gilbarco Passport
- **DITA version:** 2.0
- **Multi-topic:** enabled
- **Images:** optional
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
st.markdown("Upload a text-based PDF or DOCX file to convert it to valid **DITA 2.0 XML**.")

left_col, right_col = st.columns([1, 1.6])

# ---------------------------------------------------------------------------
# LEFT: Upload + options
# ---------------------------------------------------------------------------

with left_col:
    st.subheader("1 · Upload")
    uploaded_file = st.file_uploader(
        "Select a PDF or DOCX file",
        type=["pdf", "docx"],
        help="Text-based PDFs only. Scanned (image) PDFs are not supported.",
    )

    # ---- DOCX image folder option ----
    st.subheader("2 · Image Folder (DOCX only, optional)")

    with st.expander("ℹ️ How to provide images from a DOCX file"):
        st.markdown("""
**Why this is needed:**  
Images inside a `.docx` file are embedded in the archive. To link them in DITA `<image>` elements, you need to extract them first.

**Steps:**
1. Make a copy of your `.docx` file
2. Rename the copy so its extension changes from `.docx` → `.zip`
3. Extract (unzip) the renamed file
4. Inside the extracted folder, open the `word/` subfolder
5. Inside `word/`, you will find a `media/` folder containing all images
6. Enter the **full path** to that `media/` folder below

**Example path:**  
`D:\\Projects\\ToDita - Claude\\extracted\\word\\media`
""")

    image_folder = st.text_input(
        "Media folder path",
        placeholder="D:\\path\\to\\extracted\\word\\media",
        help="Leave blank to skip image linking. Image placeholders will appear in the DITA output.",
    )

    if image_folder and not Path(image_folder).is_dir():
        st.warning("⚠️ That folder path does not exist on this machine. Images will be skipped.")
        image_folder = ""

    run_button = st.button(
        "▶  Convert to DITA 2.0",
        type="primary",
        disabled=uploaded_file is None,
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# RIGHT: Output
# ---------------------------------------------------------------------------

with right_col:
    if "results" not in st.session_state:
        st.session_state.results = None

    if run_button and uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_name = uploaded_file.name
        is_pdf = file_name.lower().endswith(".pdf")

        status_box = st.empty()

        def status(msg: str):
            status_box.info(msg)

        try:
            t0 = time.time()

            # ---- EXTRACTOR ----
            status("⏳ `[EXTRACTOR]` — Parsing document structure…")
            if is_pdf:
                blocks = extract_pdf(file_bytes)
            else:
                blocks = extract_docx(file_bytes, image_folder=image_folder)
            status(f"✅ `[EXTRACTOR]` — {len(blocks)} blocks extracted")

            # ---- MAPPER ----
            status("⏳ `[MAPPER]` — Applying YAML mapping rules…")
            mapper = Mapper()
            blocks = mapper.map(blocks)
            tt = blocks[0].get("metadata", {}).get("topic_type", "concept") if blocks else "concept"
            status(f"✅ `[MAPPER]` — Annotated as `{tt}` topic")

            # ---- GENERATOR ----
            status("⏳ `[GENERATOR]` — Generating DITA 2.0 XML…")
            gen = Generator(topic_type=tt)
            topic_files: list[tuple[str, str]] = gen.generate(blocks)
            n_topics = len(topic_files)
            status(f"✅ `[GENERATOR]` — {n_topics} topic file(s) generated")

            # ---- VALIDATOR ----
            status("⏳ `[VALIDATOR]` — Validating XML…")
            validator = Validator()
            validation_results = []
            for fname, xml_str in topic_files:
                vr = validator.validate(xml_str, blocks, filename=fname)
                validation_results.append((fname, xml_str, vr))

            total_errors = sum(len(vr.errors) for _, _, vr in validation_results)
            total_warnings = sum(len(vr.warnings) for _, _, vr in validation_results)
            elapsed = time.time() - t0

            if total_errors == 0:
                status(f"✅ `[VALIDATOR]` — {total_errors} errors · {total_warnings} warnings · {elapsed:.2f}s")
            else:
                status(f"⚠️ `[VALIDATOR]` — {total_errors} errors · {total_warnings} warnings · {elapsed:.2f}s")

            st.session_state.results = {
                "topic_files": validation_results,
                "n_topics": n_topics,
                "source_name": file_name,
                "elapsed": elapsed,
                "blocks": blocks,
            }

        except ExtractorError as exc:
            status_box.error(f"❌ Extraction failed: {exc}")
            st.info("💡 Tip: Only text-based (digital) PDFs are supported. Scanned documents require OCR preprocessing.")
            st.session_state.results = None

        except Exception as exc:
            status_box.error(f"❌ Unexpected error: {exc}")
            st.session_state.results = None

    # -----------------------------------------------------------------------
    # Display results
    # -----------------------------------------------------------------------

    if st.session_state.results:
        res = st.session_state.results
        topic_files: list[tuple[str, str, object]] = res["topic_files"]
        n_topics: int = res["n_topics"]
        source_name: str = res["source_name"]

        st.divider()

        # ---- Download button ----
        if n_topics == 1:
            fname, xml_str, vr = topic_files[0]
            st.download_button(
                label="⬇️ Download .dita",
                data=xml_str.encode("utf-8"),
                file_name=fname,
                mime="application/xml",
                type="primary",
                use_container_width=True,
            )
        else:
            # Multiple topics → ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname, xml_str, vr in topic_files:
                    zf.writestr(fname, xml_str.encode("utf-8"))
            zip_buffer.seek(0)
            zip_name = Path(source_name).stem + "_dita_topics.zip"
            st.success(f"✅ **{n_topics} topics** generated. Downloading as ZIP.")
            st.download_button(
                label=f"⬇️ Download {zip_name}",
                data=zip_buffer,
                file_name=zip_name,
                mime="application/zip",
                type="primary",
                use_container_width=True,
            )

        # ---- Tabs ----
        tabs = st.tabs(["📄 DITA XML", "✅ Validation", "📊 Stats"])

        with tabs[0]:
            if n_topics == 1:
                _, xml_str, _ = topic_files[0]
                display_xml = xml_str if len(xml_str) <= 50_000 else xml_str[:50_000] + "\n\n<!-- ... truncated for display. Download for full file. -->"
                st.code(display_xml, language="xml")
            else:
                topic_names = [fname for fname, _, _ in topic_files]
                selected = st.selectbox("Select topic to preview:", topic_names)
                for fname, xml_str, _ in topic_files:
                    if fname == selected:
                        display_xml = xml_str if len(xml_str) <= 50_000 else xml_str[:50_000] + "\n\n<!-- truncated -->"
                        st.code(display_xml, language="xml")
                        break

        with tabs[1]:
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

        with tabs[2]:
            all_stats = [vr.stats for _, _, vr in topic_files]

            # Aggregate
            total_words = sum(s.get("word_count", 0) for s in all_stats)
            total_sections = sum(s.get("sections", 0) for s in all_stats)
            total_notes = sum(s.get("notes", 0) for s in all_stats)
            total_steps = sum(s.get("steps", 0) for s in all_stats)
            total_tables = sum(s.get("tables", 0) for s in all_stats)
            total_figs = sum(s.get("figures", 0) for s in all_stats)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Topics", n_topics)
            m2.metric("Word Count", total_words)
            m3.metric("Sections", total_sections)
            m4.metric("Notes", total_notes)

            m5, m6, m7, m8 = st.columns(4)
            m5.metric("Steps", total_steps)
            m6.metric("Tables", total_tables)
            m7.metric("Figures", total_figs)
            m8.metric("Time (s)", f"{res['elapsed']:.2f}")

            if n_topics > 1:
                st.subheader("Topic breakdown")
                for fname, _, vr in topic_files:
                    s = vr.stats
                    st.markdown(
                        f"**{fname}** — {s.get('word_count',0)} words · "
                        f"{s.get('sections',0)} sections · "
                        f"{s.get('steps',0)} steps · "
                        f"{s.get('notes',0)} notes"
                    )

            if res["blocks"]:
                b0 = res["blocks"][0]
                fb = b0.get("metadata", {}).get("fallback_count", 0)
                if fb > 0:
                    st.warning(f"⚠️ {fb} block(s) used the fallback `<p>` element. "
                               "Review the validation report for details.")
