# FileFlow V10 — Forensic File Organisation Engine

**A 100% local, AI-powered document classification, deduplication, and forensic archiving platform for legal and professional workflows.**

FileFlow scans unorganised, multi-generational folder structures, reads and understands the full text and context of every file using local AI, builds a clean virtual target directory, and safely executes bit-perfect file moves — with an audit trail and single-click full rollback guarantee.

Built primarily for legal professionals, corporate administrators, and privacy-focused environments. Runs completely offline. Zero data leaves your machine.

---

## Key Highlights

- **100% Local Intelligence** — All AI text classification, vision OCR, and vector embeddings execute locally via [Ollama](https://ollama.ai). No cloud APIs, zero external network traffic.
- **Forensic Bit-Perfect Verification** — Original files are never modified or cleaned up until a bit-level MD5 checksum match is verified at the target path.
- **Infinite Undo & Audit Trail** — Every file movement is wrapped in a session transaction recorded in `data/audit_ledger.json` and exported to `Forensic_Manifest.json`. Any session can be completely reversed with a single command.
- **Dry-Run by Default** — Default system configuration prevents destructive operations; every run is simulated first in memory or rendered as a zero-byte hard-link preview.
- **Corrupted PDF & OCR Tolerance** — PDF text extraction executes inside an isolated child process pool with strict timeouts to eliminate engine freezes on malformed files. Unreadable or scanned documents automatically escalate to Vision OCR (`qwen3-vl:4b`).
- **Relational & Semantic Memory** — Integrates LanceDB vector search (`data/vectors.lance`) for duplicate detection and an SQLite fact graph (`data/knowledge_graph.sqlite`) for relational document grouping by case numbers, ID numbers, and reference codes.

---

## How It Works

```
┌──────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────┐     ┌──────────────┐
│  1. Scan │ ──► │2. Understand│ ──► │  3. Preview │ ──► │4. Approve │ ──► │ 5. Organise  │
└──────────┘     └─────────────┘     └─────────────┘     └───────────┘     └──────────────┘
  Recursive       AI Ruling, OCR,       Zero-Byte        User Review       MD5 Copying,
  Discovery       Context Resolver      Shadow Map       & Confirmation    Ledger Record
```

1. **Scan** — `DeepScanner` recursively traverses source directories, detecting ghost files (<1KB) and identifying unreadable formats without crashing on recursion loops.
2. **Understand** — Files pass through the **Cognition Stack**: fast-path regex triage (`Sniffer`), SLM classification (`Judge`), folder context propagation (`Refinery`), vision OCR (`Eye`), and vector embedding generation (`Inspector`). Unresolvable files are routed to `_Quarantine`.
3. **Preview** — The system constructs an in-memory staging map and optionally renders a zero-copy hard-link tree (`ShadowMapper`). You see every proposed path and duplicate flag before anything moves.
4. **Approve** — You review the proposal in the Desktop UI or CLI and confirm execution.
5. **Organise** — `AtomicExecutor` copies files, verifies MD5 checksums pre- and post-move, logs transaction steps in `TransactionLedger`, and produces `Forensic_Manifest.json`.

---

## Safety Model & Core Guarantees

FileFlow enforces four non-negotiable architectural safety rules:

| Guarantee | Enforcement Mechanism |
| :--- | :--- |
| **Non-Destructive** | Original source files remain untouched until an exact MD5 hash match is confirmed at the destination. Code-level safety locks prevent premature cleanup. |
| **100% Offline** | All inference routes via `127.0.0.1:11434` (Ollama localhost API). Web API CORS is strictly locked to localhost to block external browser attacks. |
| **Full Rollback** | `TransactionLedger` logs pre- and post-move state. Rollback restores original file locations byte-for-byte using recorded source paths. |
| **Audit Compliance** | Every session outputs a structured `Forensic_Manifest.json` capturing timestamp, source path, target path, file size, and MD5 hash. |

---

## Requirements & Environment

- **Operating System:** Windows 10 / 11 (Primary target); macOS / Linux supported.
- **Python:** 3.10 or higher.
- **AI Runtime:** [Ollama](https://ollama.ai) installed and running locally.

### Required Ollama Models

Pull the following models prior to launching FileFlow:

```bash
# Core classification and ruling model
ollama pull ministral-3:3b

# Vector embedding engine for semantic search and deduplication
ollama pull qwen3-embedding:4b

# Document summarisation engine
ollama pull qwen2.5:3b

# Vision OCR engine for scanned PDFs and image documents
ollama pull qwen3-vl:4b
```

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sandisomaz/fileflow.git
   cd fileflow
   ```

2. **Set up virtual environment:**
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify local Ollama service:**
   ```bash
   ollama list
   ```

---

## Usage

### 1. Desktop Application (GUI)

The primary interface is a desktop application powered by PyWebView and FastAPI.

```bash
python main.py
```

- Launches an application window (1340x860, maximized).
- Features interactive chat, folder selection, real-time file discovery metrics, category breakdown charts, and plan approval screens.
- Generates a desktop shortcut automatically on Windows.

### 2. Headless Command Line Interface (CLI)

For headless operations or automated scripts:

**Audit Mode (Analysis only, no changes):**
```bash
python cli.py audit "C:\Users\Username\Downloads"
```

**Dry-Run Organisation (Simulates movement, renders report):**
```bash
python cli.py organise "C:\Users\Username\Downloads" --dry-run
```

**Live Execution (Copies files with MD5 verification):**
```bash
python cli.py organise "C:\Users\Username\Downloads" --dry-run False
```

### 3. Rollback a Session

To reverse a completed organisation session:

```bash
python main.py --rollback "C:\Users\Username\Desktop\FileFlow_Archive\Forensic_Manifest.json"
```

---

## Configuration Reference

FileFlow separates configuration into two distinct files to isolate execution parameters from domain taxonomy:

- **`settings.yaml`** — System parameters, AI models, scanning depth, vector paths, and safety defaults.
- **`config.json`** — Category taxonomy definitions, extension lists, and keyword matching rules for rule-based fallbacks.

### Key `settings.yaml` Options

```yaml
execution:
  dry_run_default: true           # Safety default (forces preview approval)

ai:
  slm_model: ministral-3:3b        # Main classification model
  embed_model: qwen3-embedding:4b  # Semantic search embedding model
  summarise_model: qwen2.5:3b      # Summarisation model
  triage_confidence_threshold: 0.7 # Below this threshold, falls back to rules

scanning:
  max_depth: 10
  ignored_dirs:
    - .venv
    - node_modules
    - FileFlow_Archive            # Prevents self-scanning output folders
```

### Taxonomy Rules in `config.json`

```json
{
  "Professional": {
    "keywords": ["cv", "cover letter", "z83", "brief", "summons", "affidavit"],
    "extensions": [".pdf", ".docx", ".doc"]
  },
  "Life_Admin": {
    "keywords": ["statement", "invoice", "receipt", "lease", "tax", "sars"],
    "extensions": [".pdf", ".csv", ".xlsx", ".png", ".jpg"]
  }
}
```

### Adding a New Document Category

To add a new document category to FileFlow:

1. Add category definition and keywords to `config.json` (enables rule-based fallback).
2. Update category instructions in `config/prompts/ruling.md` (informs the SLM during AI ruling).
3. **Update `VALID_CATEGORIES` in [`app/brain/judge.py`](file:///c:/Users/sandi/Desktop/FileFlow/app/brain/judge.py)** — `VALID_CATEGORIES` is a hardcoded Python set. Unregistered categories will be normalized to `"Unknown"`.

---

## Document Taxonomy Matrix

FileFlow classifies documents into six sovereign target categories:

| Category | Primary Contents |
| :--- | :--- |
| **`Professional`** | CVs, cover letters, legal briefs, court summons, contracts, corporate correspondence. |
| **`Education`** | Academic transcripts, course modules, study guides, exam papers, certificates. |
| **`Development`** | Source code files, technical specifications, configuration files, scripts, repository dumps. |
| **`Life_Admin`** | Bank statements, SARS tax returns, utility bills, lease agreements, identity documents, medical records. |
| **`Waste`** | Exact duplicates, zero-byte empty files, temporary cache files (`.tmp`, `.~lock`). |
| **`_Quarantine`** | Corrupted files, password-protected PDFs, unreadable binaries preserved safely without deletion. |

---

## Repository Structure

```
FileFlow/
├── main.py                     # GUI Desktop launcher & FastAPI background server
├── cli.py                      # Headless CLI entry point
├── settings.yaml               # Engine settings, model config, scanning rules
├── config.json                 # Category taxonomy definitions and keywords
├── requirements.txt            # Python dependencies
│
├── app/
│   ├── api.py                  # PyWebView API bridge & FastAPI REST endpoints
│   ├── brain/                  # Cognition Stack (AI & Analysis)
│   │   ├── bridge.py           # Ollama API reliability layer & fallback handler
│   │   ├── judge.py            # Sovereign Archivist classification engine
│   │   ├── eye.py              # Vision OCR handler for scanned documents
│   │   ├── inspector.py        # Document summarisation & embedding pipeline
│   │   ├── extractor.py        # Process-isolated PDF and text extractor
│   │   ├── refinery.py         # Folder context propagation & grounding resolver
│   │   ├── sniffer.py          # Fast-path (<100ms) regex triage engine
│   │   ├── triage_pool.py      # Multi-tier async worker pool (V10)
│   │   ├── discovery.py        # Vector semantic search interface
│   │   ├── listener.py         # Folder watcher for continuous background ingestion
│   │   └── diagnostic.py       # Structural audit & complexity reporting
│   │
│   ├── muscle/                 # Physical File Operations & Staging
│   │   ├── scanner.py          # Deep recursive non-destructive folder scanner
│   │   ├── manager.py          # Staging manager & move proposal builder
│   │   ├── unpacker.py         # Entity-based folder flattening & reconstruction
│   │   ├── executor.py         # Atomic move engine with pre/post MD5 verification
│   │   ├── librarian.py        # AI smart filename generator
│   │   ├── versioning.py       # Collision-free file versioning engine
│   │   ├── shadow_mapper.py    # Zero-copy hard-link preview engine (V10)
│   │   ├── stream_unpacker.py  # Async streaming discovery processor (V10)
│   │   ├── transaction_ledger.py # Audit logger & 1-click full rollback engine
│   │   ├── janitor.py          # Safe directory pruner & staging cleanup
│   │   ├── resource_monitor.py # Dynamic CPU/RAM resource throttle controller
│   │   └── models.py           # Core dataclasses (StagedFile, TriageResult, etc.)
│   │
│   └── memory/                 # State & Persistence Layer
│       ├── config.py           # ConfigLoader (YAML + JSON unification)
│       ├── database.py         # SQLite persistence for chat, sessions, and audits
│       ├── memory.py           # LanceDB vector database store
│       ├── knowledge_graph.py  # Fact graph linking documents by extracted entities
│       └── abbreviations.py    # Entity abbreviation & shortener map
│
├── ui/                         # Desktop Frontend
│   ├── index.html              # Modern single-page web interface
│   ├── css/                    # Custom styling rules
│   └── js/                     # PyWebView integration & UI controllers
│
├── config/prompts/             # System Prompts for Local AI
│   ├── ruling.md               # Sovereign Archivist prompt template
│   ├── summarize.md            # Document summary prompt template
│   └── ux_translator_v2.md    # Intent parsing prompt template
│
├── tests/                      # Automated Test Suite (170+ tests)
└── data/                       # Persistent Data Storage
    ├── fileflow.db             # SQLite session & audit database
    ├── knowledge_graph.sqlite  # Entity relation fact graph
    ├── audit_ledger.json       # Transaction movement ledger
    └── vectors.lance/          # LanceDB semantic embedding store
```

---

## Testing & Verification

FileFlow includes a comprehensive automated test suite with over 170 tests using `pytest`.

To run the test suite:

```bash
pytest tests/ -v
```

### Key Test Suites

- [`test_bridge.py`](file:///c:/Users/sandi/Desktop/FileFlow/tests/test_bridge.py) — Validates Ollama API communication, retries, and fallback handling.
- [`test_extractor.py`](file:///c:/Users/sandi/Desktop/FileFlow/tests/test_extractor.py) — Tests PDF/DOCX/text extraction and process isolation.
- [`test_judge.py`](file:///c:/Users/sandi/Desktop/FileFlow/tests/test_judge.py) — Verifies classification accuracy and fast/slow path routing.
- [`test_unpacker.py`](file:///c:/Users/sandi/Desktop/FileFlow/tests/test_unpacker.py) — Tests entity grouping and directory reconstruction.
- [`test_regression_fixes.py`](file:///c:/Users/sandi/Desktop/FileFlow/tests/test_regression_fixes.py) — Ensures safety defaults (dry run, CORS security, hash validation) remain unbroken.

> **Note on test suite:** `test_recovery.py::test_sibling_packet_reassociation` is explicitly marked `xfail`. It documents a known boundary case in folder-context propagation when non-standard entity names surround weak files.

---

## Developer Architecture Notes

1. **Multiprocessing Isolation:** On Windows, `multiprocessing.freeze_support()` is executed at startup in [`main.py`](file:///c:/Users/sandi/Desktop/FileFlow/main.py). All PDF extractions run via `multiprocessing.Pool` child processes with 2-second timeouts to isolate malformed PDF parser crashes from the main process.
2. **CORS Security:** WebAPI CORS in [`main.py`](file:///c:/Users/sandi/Desktop/FileFlow/main.py) is explicitly bound to `http://127.0.0.1:4173`. Wildcard CORS is disabled to prevent unauthorized local browser scripts from interacting with the file operations bridge.
3. **Graceful Degraded Mode:** If Ollama is unverified or offline, FileFlow seamlessly falls back to regex and rule-based heuristic classification without failing or showing popup errors.

---

## Licence & Notice

Private repository. All rights reserved. Maintain canonical implementation in private repository; public portfolio mirrors retain architectural documentation.