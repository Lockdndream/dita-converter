"""
ui/app.py
DITA Converter Tool — Streamlit UI
"""

from __future__ import annotations

import io
import sys
import zipfile
import time
from pathlib import Path

import streamlit as st

VERSION = "v2.3"

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
# Particle animation + UI polish injected into the Streamlit shell
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CSS for topic cards and badges (safe — no JS needed here)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  /* Frosted glass panel behind the left (controls) column */
  [data-testid="column"]:first-child > div:first-child {
    background: rgba(255, 255, 255, 0.55) !important;
    backdrop-filter: blur(10px) !important;
    -webkit-backdrop-filter: blur(10px) !important;
    border-radius: 14px !important;
    padding: 18px 20px !important;
    border: 1px solid rgba(180, 195, 240, 0.35) !important;
    box-shadow: 0 4px 24px rgba(100, 120, 200, 0.08) !important;
  }
  .topic-card {
    border: 1px solid rgba(99,130,237,0.25);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 6px;
    background: rgba(255,255,255,0.55);
    transition: border-color 0.2s ease, background 0.2s ease;
  }
  .topic-card:hover {
    border-color: rgba(99,130,237,0.55);
    background: rgba(255,255,255,0.8);
  }
  .badge-task      { background:rgba(46,125,50,0.12);  color:#276749; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; font-family:monospace; }
  .badge-concept   { background:rgba(49,130,206,0.12); color:#2b6cb0; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; font-family:monospace; }
  .badge-reference { background:rgba(192,86,33,0.12);  color:#c05621; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; font-family:monospace; }
  .badge-topic     { background:rgba(113,128,150,0.12);color:#4a5568; border-radius:4px; padding:2px 8px; font-size:0.75em; font-weight:600; font-family:monospace; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Particle animation — injected into the parent page via components.v1.html
# Uses window.parent to escape the iframe sandbox
# ---------------------------------------------------------------------------
import streamlit.components.v1 as _components

_components.html("""
<script>
(function() {
  var doc = window.parent.document;

  if (!doc.getElementById('dita-particles-style')) {
    var style = doc.createElement('style');
    style.id = 'dita-particles-style';
    style.textContent = `
      #dita-particle-canvas {
        position: fixed !important;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: 0;
        pointer-events: none !important;
      }
      body {
        background: linear-gradient(160deg,#f0f4ff 0%,#e8f0fe 50%,#f5f0ff 100%) !important;
        background-attachment: fixed !important;
      }
      .stApp { background: transparent !important; }
      .main .block-container { position: relative; z-index: 1; }
      section[data-testid="stSidebar"] { position: relative !important; }
      section[data-testid="stSidebar"] > div:first-child {
        background: rgba(248,250,255,0.88) !important;
      }
    `;
    doc.head.appendChild(style);
  }

  if (doc.getElementById('dita-particle-canvas')) return;
  var canvas = doc.createElement('canvas');
  canvas.id = 'dita-particle-canvas';
  doc.body.appendChild(canvas);
  var ctx = canvas.getContext('2d');

  var W, H;
  var mouse = { x: -9999, y: -9999, active: false };

  function resize() {
    W = canvas.width  = window.parent.innerWidth;
    H = canvas.height = window.parent.innerHeight;
    initFilings();
  }
  window.parent.addEventListener('resize', resize);
  window.parent.document.addEventListener('mousemove', function(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.active = true;
  });

  // ── Field: pure mouse dipole + slow time-varying background field ──────
  // No fixed poles. The background field rotates slowly so filings drift.
  // Mouse acts as a strong pole that dominates locally.

  var tick = 0;

  function fieldAt(x, y) {
    var fx = 0, fy = 0;

    // Slow rotating uniform background — gives the whole canvas a consistent
    // field direction that rotates over ~2 min, keeping filings alive everywhere
    var angle = tick * 0.0004;
    fx += Math.cos(angle) * 0.06;
    fy += Math.sin(angle) * 0.06;

    // Gentle standing waves — two overlapping sine fields that create
    // a spatially varying pattern across the canvas
    var wave1 = Math.sin(x * 0.007 + tick * 0.0012) * 0.04;
    var wave2 = Math.cos(y * 0.009 - tick * 0.0008) * 0.04;
    fx += wave1;
    fy += wave2;

    // Mouse pole — dominant field, visible across large radius
    if (mouse.active) {
      var mdx = x - mouse.x;
      var mdy = y - mouse.y;
      var md2 = mdx*mdx + mdy*mdy + 100;
      var md  = Math.sqrt(md2);
      // Use 1/d falloff (not 1/d2) so influence reaches much further
      fx += (18.0 / (md + 1)) * mdx / md;
      fy += (18.0 / (md + 1)) * mdy / md;
    }

    return { x: fx, y: fy };
  }

  // ── Filings ───────────────────────────────────────────────────────────
  var FILINGS = 2200;
  var filings = [];

  function initFilings() {
    filings = [];
    for (var i = 0; i < FILINGS; i++) {
      filings.push({
        x:   Math.random() * W,
        y:   Math.random() * H,
        len: 4 + Math.random() * 6,
        age: Math.floor(Math.random() * 260),
      });
    }
  }

  function frame() {
    // Slow fade — lets trail show field movement without smearing
    ctx.fillStyle = 'rgba(240,244,255,0.10)';
    ctx.fillRect(0, 0, W, H);
    tick++;

    for (var i = 0; i < FILINGS; i++) {
      var f = filings[i];
      f.age++;

      // Drift slowly along field line
      var fv = fieldAt(f.x, f.y);
      var fm = Math.sqrt(fv.x*fv.x + fv.y*fv.y);
      if (fm > 0.00001) {
        f.x += (fv.x / fm) * 0.18;
        f.y += (fv.y / fm) * 0.18;
      }

      // Respawn when out of bounds or too old
      if (f.x < -10 || f.x > W+10 || f.y < -10 || f.y > H+10 || f.age > 280) {
        f.x   = Math.random() * W;
        f.y   = Math.random() * H;
        f.age = 0;
        continue;
      }

      // Direction from field
      var v  = fieldAt(f.x, f.y);
      var m  = Math.sqrt(v.x*v.x + v.y*v.y);
      if (m < 0.00001) continue;
      var nx = v.x / m, ny = v.y / m;

      var halfLen = f.len * 0.5;

      // Age fade in/out
      var ageFade = Math.min(f.age / 25, 1) * Math.min((280 - f.age) / 25, 1);

      // Strength-based alpha — floor keeps everything visible
      var strength = Math.min(m * 80, 1);
      var alpha    = (0.30 + strength * 0.38) * ageFade;

      // Colour varies by position — gentle spatial hue shift
      var hue = 215 + Math.sin(f.x * 0.005 + f.y * 0.004) * 30;
      var sat = 45 + strength * 20;
      var lig = 32 + (1 - strength) * 18;

      ctx.beginPath();
      ctx.moveTo(f.x - nx * halfLen, f.y - ny * halfLen);
      ctx.lineTo(f.x + nx * halfLen, f.y + ny * halfLen);
      ctx.strokeStyle = 'hsla(' + hue + ',' + sat + '%,' + lig + '%,' + alpha + ')';
      ctx.lineWidth   = 0.05 + strength * 0.05;
      ctx.stroke();
    }

    // Mouse ripple
    if (mouse.active) {
      var rp = (tick % 180) / 180;
      ctx.beginPath();
      ctx.arc(mouse.x, mouse.y, 50 * rp, 0, 6.2832);
      ctx.strokeStyle = 'hsla(230,60%,50%,' + (1-rp)*0.25 + ')';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    requestAnimationFrame(frame);
  }

  W = window.parent.innerWidth;
  H = window.parent.innerHeight;
  canvas.width = W; canvas.height = H;
  initFilings();
  frame();
})();
</script>
""", height=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_type_from_xml(xml_str: str) -> str:
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
    st.caption(f"PDF & DOCX → DITA 2.0 XML  ·  {VERSION}")

    st.divider()
    st.subheader("⚙️ Configuration")
    st.markdown("""
- **Mapping profile:** Gilbarco
- **DITA version:** 2.0
- **Multi-topic:** enabled
- **Map types:** `.ditamap` · `.bookmap`
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

st.title("DITA 2.0 Converter")
st.markdown("Upload a text-based PDF or DOCX to convert to **DITA 2.0 XML**.")

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

    st.subheader("3 · Output Type")
    output_type = st.radio(
        "Select output format:",
        options=["Map (Kit documents)", "Bookmap (Book documents)"],
        index=0,
        help="Map produces a standard .ditamap. Bookmap produces a structured bookmap with chapters.",
    )
    is_bookmap = output_type == "Bookmap (Book documents)"

    st.subheader("4 · Page Range (PDF only, optional)")
    page_range = st.text_input(
        "Pages to extract",
        placeholder="e.g. 1-5, 8, 12-15  (leave blank for all pages)",
        help="Specify pages or ranges separated by commas. Leave blank to convert all pages.",
        disabled=False,
    )
    if page_range and page_range.strip():
        import re as _re
        if not _re.match(r'^[\d\s,\-]+$', page_range):
            st.warning("⚠️ Invalid format — use numbers, commas and hyphens only. e.g. 1-5, 8, 12-15")

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
            blocks = (extract_pdf(file_bytes, page_range=page_range) if is_pdf
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

            if is_bookmap:
                map_str  = gen.generate_bookmap(topic_files, map_title=map_title)
                map_name = Path(file_name).stem + ".ditamap"
                map_type = "bookmap"
            else:
                map_str  = gen.generate_ditamap(topic_files, map_title=map_title)
                map_name = Path(file_name).stem + ".ditamap"
                map_type = "map"

            n_topics = len(topic_files)
            _status(f"✅ `[GENERATOR]` — {n_topics} topic(s) + .{'bookmap' if is_bookmap else 'ditamap'}")

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
                "ditamap_str":  map_str,
                "ditamap_name": map_name,
                "map_type":     map_type,
                "n_topics":     n_topics,
                "source_name":  file_name,
                "map_title":    map_title,
                "elapsed":      elapsed,
                "blocks":       blocks,
                "is_bookmap":   is_bookmap,
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
        is_bookmap   = res.get("is_bookmap", False)
        map_label    = "bookmap" if is_bookmap else "ditamap"

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

            col_map, col_sel, col_all = st.columns(3)

            with col_map:
                st.download_button(
                    f"⬇️ .{map_label}",
                    data=ditamap_str.encode("utf-8"),
                    file_name=ditamap_name,
                    mime="application/xml",
                    use_container_width=True,
                    help=f"Download the DITA {'book' if is_bookmap else ''}map referencing all topics",
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
                    scoped_map = (
                        Generator().generate_bookmap(sel_tuples, map_title=f"{map_title} (selection)")
                        if is_bookmap else
                        Generator().generate_ditamap(sel_tuples, map_title=f"{map_title} (selection)")
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

            # ── Block diagnostics ────────────────────────────────────────
            import json as _json
            with st.expander("🔬 Block diagnostics (debug)", expanded=False):
                blks = res["blocks"]
                st.caption(f"{len(blks)} total blocks after mapping")
                rows = []
                for b in blks:
                    rows.append({
                        "type":         b.get("type"),
                        "dita_element": b.get("dita_element"),
                        "list_kind":    b.get("metadata", {}).get("list_kind", ""),
                        "text":         b.get("text", "")[:60],
                    })
                # Summary counts
                from collections import Counter
                elem_counts = Counter(r["dita_element"] for r in rows)
                type_counts = Counter(r["type"] for r in rows)
                st.markdown("**Block types (extractor):**  " +
                            "  ".join(f"`{k}` × {v}" for k, v in sorted(type_counts.items())))
                st.markdown("**DITA elements (mapper):**  " +
                            "  ".join(f"`{k}` × {v}" for k, v in sorted(elem_counts.items())))
                numbered = [r for r in rows if r["list_kind"] == "numbered"]
                st.markdown(f"**Numbered list_items detected:** {len(numbered)}")
                if numbered:
                    for r in numbered[:10]:
                        st.text(f"  [{r['dita_element']}] {r['text']}")
                    if len(numbered) > 10:
                        st.caption(f"  … and {len(numbered) - 10} more")
                # Full JSON download
                diag_json = _json.dumps(rows, indent=2, ensure_ascii=False)
                st.download_button(
                    "⬇️ Download block JSON",
                    data=diag_json.encode("utf-8"),
                    file_name=Path(res["source_name"]).stem + "_blocks.json",
                    mime="application/json",
                )
