# FileFlow

**A forensic file organisation engine for legal and professional work.**

FileFlow scans your folders, understands what every file is using local AI, and moves everything into a clean, structured archive — without ever risking your originals. Nothing is deleted until a verified copy exists. Every run can be undone in one click.

Built for South African legal professionals. Runs 100% offline.

---

## The Problem It Solves

Years of Downloads folders. Job applications mixed with bank statements. Multiple versions of the same CV with names like `CV_FINAL_v3_ACTUAL_FINAL.pdf`. Recovered files from old drives with no names. Scanned documents that are technically PDFs but contain zero readable text.

FileFlow handles all of it — the normal files, the corrupted ones, the ones with no names, the duplicates. It reads the *content* of each file, not just the name, and makes a decision.

---

## How It Works

```
Scan → Understand → Preview → Approve → Organise
```

1. **Scan** — FileFlow recursively discovers every file in a folder, handling corrupted PDFs
   and ghost files without hanging.

2. **Understand** — Each file runs through the Cognition Stack: text extraction, AI
   classification via a local language model, and semantic deduplication. Files that can't be
   read go to a Quarantine folder — nothing is silently lost.

3. **Preview** — Before a single file moves, you see the full plan. Every file, every
   proposed destination, every duplicate flagged.

4. **Approve** — You confirm. FileFlow archives your originals to a staging area first.

5. **Organise** — Files are copied, MD5-verified, and logged. If anything fails mid-run, the
   session is flagged and nothing is left in a partial state.

---

## Safety Model

FileFlow is built around four guarantees that cannot be overridden by config:

- **Non-destructive** — originals are never touched until a bit-perfect copy is verified at the destination
- **100% local** — all AI inference runs via [Ollama](https://ollama.ai) on your machine; no file content ever leaves your computer
- **Full rollback** — every session is recorded in a `TransactionLedger`; one command restores everything to its original state
- **Audit trail** — a `Forensic_Manifest.json` is generated for every run, capturing every file's source, destination, and MD5 hash

Dry run is on by default. FileFlow will simulate the entire run and show you the result before it does anything real.

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) installed and running locally
- Windows 10/11 (primary target; macOS/Linux supported with minor adjustments)

**Required Ollama models:**

```bash
ollama pull ministral-3:3b        # Classification
ollama pull qwen3-embedding:4b    # Semantic deduplication
ollama pull qwen2.5:3b            # Summarisation
ollama pull qwen3-vl:4b           # Vision OCR (optional — for scanned images)
```

---

## Installation

```bash
git clone https://github.com/yourusername/fileflow.git
cd fileflow
pip install -r requirements.txt
```

Verify Ollama is running:

```bash
ollama list
# Should show your pulled models
```

---

## Usage

### Desktop App (Recommended)

```bash
python main.py
```

Opens the FileFlow UI in a desktop window. Chat with FileFlow to audit and organise your folders.

### CLI (Headless / Scripting)

**Audit only (no changes):**
```bash
python cli.py audit "C:\Users\you\Downloads"
```

**Dry-run organisation (simulates, does not move files):**
```bash
python cli.py organise "C:\Users\you\Downloads" --dry-run
```

**Live run (moves files — use with intention):**
```bash
python cli.py organise "C:\Users\you\Downloads" --dry-run False
```

**Rollback a session:**
```bash
# Find the manifest path from the run output, then:
python main.py --rollback "C:\Users\you\Desktop\FileFlow_Archive\Forensic_Manifest.json"
```

---

## Configuration

Two files control FileFlow's behaviour:

**`settings.yaml`** — AI models, scanning rules, execution flags  
**`config.json`** — Category taxonomy and keyword definitions

The most useful settings to know:

```yaml
# settings.yaml
execution:
  dry_run_default: true   # Set to false to run live without the --dry-run False flag

ai:
  triage_confidence_threshold: 0.7  # Below this, falls back to rule-based classification
  slm_model: ministral-3:3b         # Swap for any Ollama-compatible model

scanning:
  max_depth: 10
  ignored_dirs:
    - .venv
    - node_modules
    - FileFlow_Archive    # Prevents FileFlow from re-scanning its own output
```

```json
// config.json — add your own categories or keywords
"Professional": {
  "keywords": ["cv", "cover letter", "z83", "brief", "summons"],
  "extensions": [".pdf", ".docx"]
}
```

---

## Document Categories

FileFlow classifies every file into one of the following categories:

| Category | What belongs here |
|---|---|
| `Professional` | CVs, cover letters, Z83 forms, legal briefs, court documents, firm correspondence |
| `Education` | Study guides, exam papers, course materials, certificates, transcripts |
| `Development` | Code files, scripts, technical documentation, config files |
| `Life_Admin` | Bank statements, invoices, receipts, lease agreements, ID documents, medical records |
| `Waste` | Duplicates, empty files, corrupted files, temporary files |
| `_Quarantine` | Files that could not be read or classified; preserved but flagged |

Classification uses document content first, filename second. A file named `random_scan.pdf` that
contains a bank statement will be classified as `Life_Admin`, not guessed from its name.

---

## Architecture Summary

```
main.py (Orchestrator)
    │
    ├── DeepScanner          — recursive file discovery
    ├── Cognition Stack      — AI + rule-based file understanding
    │     ├── Bridge         — Ollama reliability layer
    │     ├── Judge          — classification and ruling
    │     ├── Eye            — vision OCR for images and scanned PDFs
    │     ├── Memory         — LanceDB semantic vector store
    │     └── Inspector      — folder context propagation
    │
    ├── StagingManager       — builds the organisation plan in memory
    ├── Librarian            — generates clean, consistent filenames
    │
    ├── AtomicExecutor       — MD5-verified file copy engine
    ├── TransactionLedger    — audit log and infinite undo
    └── PruneExecutor        — rollback and cleanup
```

For the full technical breakdown see [SYSTEM_MAP.md](./SYSTEM_MAP.md).

---

## Project Structure

```
FileFlow/
├── main.py                  # Entry point
├── cli.py                   # Headless CLI
├── settings.yaml            # Primary configuration
├── config.json              # Category definitions
├── requirements.txt
│
├── app/
│   ├── api.py               # FastAPI + pywebview bridge
│   ├── brain/               # Cognition Stack (AI)
│   ├── muscle/              # File operations
│   ├── memory/              # Config and state
│   └── types.py             # Shared dataclasses
│
├── ui/
│   └── index.html           # Desktop UI
│
├── prompts/                 # SLM prompt templates
│   ├── ruling.md            # Sovereign Archivist prompt
│   ├── summarize.md         # Document summary prompt
│   └── ux_translator_v2.md  # UX intent parser prompt
│
└── data/
    ├── audit_ledger.json    # Session transaction log
    └── vectors.lance/       # Semantic memory index
```

---

## Development Notes

**Python version:** 3.10+ required (walrus operator `:=` used in hash loops)

**Windows multiprocessing:** `multiprocessing.freeze_support()` is called at the top of `main.py`.
This is mandatory for PyInstaller-frozen executables. Do not remove it.

**PDF extraction architecture:** Each PDF is extracted in an isolated child process via
`multiprocessing.Pool`. This prevents corrupted or malformed PDFs from hanging or crashing the
main process. The timeout is 2 seconds per file.

**Ollama dependency:** If Ollama is offline at startup, FileFlow degrades gracefully to
rule-based classification. No crash, no error dialog — it just works slower and less accurately.
The Bridge module handles health checks and retries transparently.

**Adding a new category:**
1. Add the category definition to `config.json` with keywords and extensions
2. Add the category name to the taxonomy table in `prompts/ruling.md`
3. Restart FileFlow — no code changes required

---

## Roadmap

| Feature | Status |
|---|---|
| Core pipeline (scan → stage → execute → rollback) | ✅ Complete |
| AI classification via local SLM | ✅ Complete |
| Semantic deduplication via embeddings | ✅ Complete |
| Vision OCR for scanned images | ✅ Complete |
| Desktop UI (pywebview + FastAPI) | ✅ Complete |
| Async streaming processor (StreamUnpacker) | 🔧 V10 stub |
| Hard-link zero-byte preview (ShadowMapper) | 🔧 V10 stub |
| Relational file grouping (Stories Engine) | 📋 Designed |
| Trust Mode (fully autonomous, non-tech users) | 📋 Designed |

---

## Licence

Private repository. All rights reserved.

---

*Built by Sandiso Mazibuko — Legal Technologist*  
*"The law is the operating system of civilisation. And operating systems can be upgraded."*
