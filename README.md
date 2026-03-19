![Python](https://img.shields.io/badge/python-3.11-blue)
![DITA](https://img.shields.io/badge/DITA-2.0-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-proof--of--concept-yellow)
📸 [View Screenshots](SCREENSHOTS.md)

# DITA Converter Tool [![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://dita-converter-testnaipat.streamlit.app/)

A lightweight, open-source proof-of-concept that converts text-based **PDF** and **DOCX** files into valid **DITA 2.0 XML** via a rule-based pipeline with a Streamlit web UI.

> **Status**: v1.1 Proof of Concept — fully functional
> **DITA Version**: 2.0
> **Style Reference**: Gilbarco Passport Technical Manuals (MDE-5570A, MDE-3839Q)
> **Conversion time**: ~2.3 seconds per document

---

## Quick Start

### Prerequisites

- Python 3.11
- pip

### Install

```bash
git clone https://github.com/Lockdndream/dita-converter.git
cd dita-converter
pip install -r requirements.txt
```

### Run the UI

```bash
streamlit run ui/app.py
```

Open `http://localhost:8501` — upload a PDF or DOCX and download your DITA output.

---

## Pipeline

```
Upload PDF or DOCX
        │
        ▼
  ┌─────────────┐   pdfplumber / python-docx
  │  Extractor  │ → Content Tree (list of block dicts)
  └─────────────┘
        │
        ▼
  ┌─────────────┐   config/mapping_rules.yaml (PyYAML)
  │   Mapper    │ → Annotated Content Tree (dita_element on each block)
  └─────────────┘
        │
        ▼
  ┌─────────────┐   lxml — per-topic type detection
  │  Generator  │ → One .dita file per H1 section + .ditamap
  └─────────────┘
        │
        ▼
  ┌─────────────┐   lxml well-formedness check
  │  Validator  │ → ValidationResult + human-readable report per topic
  └─────────────┘
        │
        ▼
  DITA Map view → select topics → download single .dita or scoped ZIP
```

---

## Features

| Feature | Detail |
|---|---|
| **Multi-topic output** | Each H1 section becomes a separate `.dita` file |
| **Per-topic type detection** | `task` (steps found) · `reference` (table-heavy) · `concept` (prose) · `topic` (ambiguous) |
| **DITA map** | `.ditamap` generated automatically, referencing all topic files |
| **Selective export** | Check individual topics in the map view — download one `.dita` or a scoped ZIP |
| **Image support (DOCX)** | Provide the extracted `media/` folder path to link images in DITA `<image>` elements |
| **Validation report** | Per-topic well-formedness check with error, warning, and content stats |
| **DITA 2.0** | Full OASIS DITA 2.0 namespace and DOCTYPE on all output |

---

## Project Structure

```
dita-converter/
├── agents/
│   ├── __init__.py
│   ├── extractor.py       # PDF/DOCX → Content Tree
│   ├── mapper.py          # Content Tree + YAML rules → Annotated Tree
│   ├── generator.py       # Annotated Tree → DITA 2.0 XML + .ditamap
│   └── validator.py       # XML validation + report per topic
├── config/
│   └── mapping_rules.yaml # Style mapping rules (editable, no code change needed)
├── ui/
│   └── app.py             # Streamlit web application
├── tests/
├── docs/                  # Architecture, Source of Truth, Project Plan, Services
├── sample_inputs/         # Reference PDFs/DOCX for mapping calibration
├── runtime.txt            # Pins Python 3.11 for Streamlit Cloud
├── .gitignore
├── CHANGELOG.md
├── requirements.txt
└── README.md
```

---

## DOCX Image Extraction

Images inside `.docx` files are embedded in the archive. To link them in DITA `<image>` elements:

1. Copy your `.docx` file
2. Rename the copy: `.docx` → `.zip`
3. Extract the `.zip`
4. Navigate to the extracted folder → `word/` → `media/`
5. Paste the full path to `media/` in the UI image folder field

**Example path:** `D:\Projects\ToDita - Claude\extracted\word\media`

---

## Mapping Rules

Edit `config/mapping_rules.yaml` to adapt the tool to different document styles — **no code changes required**.

```yaml
# Change how headings map
heading_map:
  h1_first: title          # First H1 → topic <title>
  h1: section_title        # Subsequent H1 → new topic file
  h2: sectiondiv_title     # H2 → <div>

# Add a new note keyword
note_map:
  - pattern: "^NOTICE"
    element: note
    type: note
    match: block_header
```

---

## Sample Output

From `MDE-5570A.pdf` — one of three generated topic files:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA 2.0 Task//EN" "task.dtd">
<task xmlns="https://docs.oasis-open.org/dita/ns/2.0" xml:lang="en-US">
  <title>Feature Activation</title>
  <shortdesc>After completing the on-boarding process with POS and the Payment Network...</shortdesc>
  <taskbody>
    <steps>
      <step>
        <cmd>From the MWS main screen, go to Set Up &gt; Network Menu &gt; Mobile Payment</cmd>
      </step>
    </steps>
    <note type="important">
      Before configuring Conexxus Mobile Payment, ensure the following prerequisites are met.
    </note>
  </taskbody>
</task>
```

Generated `.ditamap`:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA 2.0 Map//EN" "map.dtd">
<map xmlns="https://docs.oasis-open.org/dita/ns/2.0" xml:lang="en-US">
  <title>MDE-5570A</title>
  <topicref href="introduction.dita" type="concept" navtitle="Introduction"/>
  <topicref href="feature_activation.dita" type="task" navtitle="Feature Activation"/>
  <topicref href="troubleshooting.dita" type="reference" navtitle="Troubleshooting"/>
</map>
```

---

## Development Agent Model

Built using a four-role development workflow (meta-layer, not runtime):

| Agent | Role |
|---|---|
| **[ALLOCATOR]** | Defines tasks and acceptance criteria per session |
| **[CODER]** | Writes all production code |
| **[REVIEWER]** | Validates against acceptance criteria — no code merges without sign-off |
| **[SCRIBE]** | Writes commit messages and updates documentation |

---

## Limitations (v1.1)

| Limitation | Workaround / Future |
|---|---|
| Text-based PDFs only | Scanned PDFs → v2 with OCR (Tesseract) |
| Rule-based mapping | LLM-assisted mapping for ambiguous content → v3 |
| Images require manual extraction (DOCX) | Auto-extraction on upload → v2 |
| No DITA validation against full DTD | DTD-aware validation → v2 |

---

## Dependencies

| Library | Version | Purpose |
|---|---|---|
| pdfplumber | 0.10.x | PDF text and table extraction |
| python-docx | 1.1.x | DOCX parsing and image relationship resolution |
| PyYAML | 6.x | Mapping rules config |
| lxml | 5.x | XML generation, validation, ditamap |
| streamlit | 1.35.x | Web UI |

All dependencies are open-source (MIT/BSD/Apache 2.0).
**Total runtime cost: $0.00** — no API keys, no cloud services.

---

## Roadmap

| Version | Focus |
|---|---|
| v1.1 | ✅ DITA 2.0 · Multi-topic · .ditamap · Selective export · Image support |
| v2.0 | Full DTD validation · Auto DOCX image extraction · Scanned PDF OCR |
| v2.1 | DITA map editor in UI · Drag-to-reorder topics |
| v3.0 | LLM-assisted mapping for ambiguous content |
| v3.1 | Docker + cloud deployment (Fly.io / Render) |

---

## License

MIT License — see `LICENSE` for details.
