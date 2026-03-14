![Python](https://img.shields.io/badge/python-3.9+-blue)
![DITA](https://img.shields.io/badge/DITA-1.3-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-proof--of--concept-yellow)
📸 [View Screenshots](SCREENSHOTS.md)

# DITA Converter Tool [![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://dita-converter-testnaipat.streamlit.app/)


A lightweight, open-source proof-of-concept that converts text-based **PDF** and **DOCX** files into valid **DITA 1.3 XML** via a rule-based pipeline with a Streamlit web UI.

> **Status**: v1.0 Proof of Concept — fully functional  
> **DITA Version**: 1.3 (2.0 migration path documented in `docs/`)  
> **Style Reference**: Gilbarco Passport Technical Manuals (MDE-5570A, MDE-3839Q)  
> **Conversion time**: ~2.3 seconds per document

---

## Quick Start

### Prerequisites

- Python 3.9+
- pip

### Install

```bash
git clone https://github.com/your-org/dita-converter.git
cd dita-converter
pip install -r requirements.txt
```

### Run the UI

```bash
streamlit run ui/app.py
```

Open `http://localhost:8501` — upload a PDF or DOCX and download your `.dita` file.

### Run Tests

```bash
# Integration test (uses sample PDFs)
python -m pytest tests/ -v

# Quick pipeline smoke test
python -c "
from agents.extractor import Extractor
from agents.mapper import Mapper
from agents.generator import Generator
from agents.validator import Validator

ext = Extractor('sample_inputs/your_file.pdf')
tree = ext.extract()
annotated, topic_type = Mapper('config/mapping_rules.yaml').map(tree)
xml = Generator(topic_type).generate(annotated)
result = Validator().validate(xml, ext.dropped_count)
print(result.report)
"
```

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
  ┌─────────────┐   lxml
  │  Generator  │ → DITA 1.3 XML string with DOCTYPE
  └─────────────┘
        │
        ▼
  ┌─────────────┐   lxml well-formedness check
  │  Validator  │ → ValidationResult + human-readable report
  └─────────────┘
        │
        ▼
  Download .dita + View report in UI
```

---

## Project Structure

```
dita-converter/
├── agents/
│   ├── __init__.py
│   ├── extractor.py       # Module 1: PDF/DOCX → Content Tree
│   ├── mapper.py          # Module 2: Content Tree + YAML → annotated tree
│   ├── generator.py       # Module 3: Annotated tree → DITA 1.3 XML
│   └── validator.py       # Module 4: XML validation + report
├── config/
│   └── mapping_rules.yaml # Style mapping rules (user-editable, no code change needed)
├── ui/
│   └── app.py             # Streamlit web application
├── tests/
│   ├── test_extractor.py
│   ├── test_mapper.py
│   └── test_generator_validator.py
├── docs/                  # Architecture, Source of Truth, Project Plan, Services
├── sample_inputs/         # Reference PDFs and DOCX files for mapping calibration
├── .gitignore
├── CHANGELOG.md
├── requirements.txt
└── README.md
```

---

## Mapping Rules

Edit `config/mapping_rules.yaml` to adapt the tool to different document styles — **no code changes required**.

```yaml
# Example: change how headings map
heading_map:
  h1_first: title          # First H1 → topic <title>
  h1: section_title        # Subsequent H1 → <section>
  h2: sectiondiv_title     # H2 → <sectiondiv>

# Example: add a new note keyword
note_map:
  - pattern: "^NOTICE"
    element: note
    type: note
    match: block_header
```

---

## Sample Output

From `MDE-5570A.pdf` (Gilbarco Passport Conexxus Mobile Payment Guide):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN"
       "task.dtd">
<task id="introduction" xml:lang="en-US">
  <title>Introduction</title>
  <shortdesc>This manual provides setup and configuration information...</shortdesc>
  <taskbody>
    <section>
      <title>Feature Activation</title>
      <p>After completing the on-boarding process with POS and the Payment Network...</p>
      <steps>
        <step>
          <cmd>From the MWS main screen, go to Set Up &gt; Network Menu &gt; Mobile Payment</cmd>
        </step>
      </steps>
      <note type="important">
        <p>Before configuring the Conexxus Mobile Payment, ensure the following:</p>
      </note>
    </section>
  </taskbody>
</task>
```

---

## Development Agent Model

Built using a four-role development workflow (meta-layer, not runtime):

| Agent | Role |
|---|---|
| **ALLOCATOR** | Defines tasks and acceptance criteria per session |
| **CODER** | Writes all production code |
| **REVIEWER** | Validates against acceptance criteria — no code merges without sign-off |
| **SCRIBE** | Writes commit messages and updates documentation |

---

## Limitations (v1)

| Limitation | Workaround / Future |
|---|---|
| Text-based PDFs only | Scanned PDFs → v2 with OCR (Tesseract) |
| One DITA topic per file | DITA maps → v2 |
| Images are placeholders | Image extraction → v2 |
| Local deployment only | Cloud: Streamlit Community Cloud or Fly.io |
| DITA 1.3 output | DITA 2.0 migration path in `docs/01_Architecture.docx` |

---

## Dependencies

| Library | Version | Purpose |
|---|---|---|
| pdfplumber | 0.10.x | PDF text and table extraction |
| python-docx | 1.1.x | DOCX parsing |
| PyYAML | 6.x | Mapping rules config |
| lxml | 5.x | XML generation and validation |
| streamlit | 1.35.x | Web UI |
| pytest | 8.x | Testing |

All dependencies are open-source with permissive licenses (MIT/BSD/Apache 2.0).  
**Total runtime cost: $0.00** — no API keys, no cloud services, runs entirely locally.

---

## Roadmap

| Version | Focus |
|---|---|
| v1.1 | Full pytest suite, improved mapping, better validation reporting |
| v2.0 | DITA map generation, multi-topic output per file |
| v2.1 | Scanned PDF support via OCR |
| v3.0 | DITA 2.0 output |
| v3.1 | Cloud deployment (Docker + Fly.io/Render) |

---

## License

MIT License — see `LICENSE` for details.
