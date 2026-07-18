# FileFlow — System Map
**Version 9.2 · Last Updated 2026-02-19**

---

## What FileFlow Does

FileFlow is a forensic file organisation engine. It scans a folder, understands what every file
is using AI and rule-based analysis, and moves files into a clean, named structure — without
ever touching an original until a verified copy exists at the destination.

**Core guarantee:** No file is deleted or moved unless a bit-perfect MD5-verified copy already
exists at the target. Every operation is logged, and the entire run can be reversed in one command.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FileFlow V9.2                                │
│                   Forensic File Organisation Engine                  │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                      ┌────────────▼────────────┐
                      │        main.py           │
                      │     (Orchestrator)       │
                      └──────┬──────────┬────────┘
                             │          │
              ┌──────────────▼──┐   ┌───▼──────────────┐
              │  Config System   │   │   FastAPI + UI    │
              │  settings.yaml   │   │   (pywebview)     │
              │  config.json     │   └───────────────────┘
              └──────────────┬──┘
                             │
        ┌────────────────────┼─────────────────────┐
        │                    │                     │
   ┌────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
   │  Scanner  │      │  Cognition  │      │  Operations │
   │  Phase 1  │      │  Stack V9   │      │  Phase 4    │
   └────┬──────┘      └──────┬──────┘      └──────┬──────┘
        │                    │                     │
        └────────────────────▼─────────────────────┘
                             │
                    ┌────────▼────────┐
                    │ Staging Manager │
                    │    Phase 3      │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
     ┌────────▼────────┐          ┌─────────▼───────┐
     │ AtomicExecutor  │          │ TransactionLedger│
     │ (file moves)    │          │ (audit + undo)   │
     └────────┬────────┘          └─────────┬───────┘
              │                             │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │ Forensic        │
                    │ Manifest JSON   │
                    └─────────────────┘
```

---

## The Four Execution Phases

### Phase 1 — Forensic Discovery (scanner.py)

The `DeepScanner` performs a non-destructive recursive scan of the source directory.
Before any AI touches a file, the scanner identifies every file's path, size, and extension.
Ghost files (under 1KB) and corrupted files are quarantined immediately.

- Stack-based traversal (no recursion limit)
- Respects `ignored_dirs` and extension allow-lists from config
- Cycle-safe via resolved-path deduplication
- Max depth: configurable (default 10)

### Phase 2 — Cognition Staging (manager.py + Cognition Stack)

For every discovered file, a multi-tier analysis pipeline runs:

```
File
 │
 ├─► UnifiedExtractor     — raw text/metadata extraction (PDF, DOCX, image OCR)
 │       └─► ProcessPool  — each PDF extracted in an isolated child process
 │                          (prevents corrupted files from hanging the main process)
 │
 ├─► Judge (AI)           — Sovereign Archivist prompt → category + confidence ruling
 │       └─► Bridge       — Ollama reliability layer (health checks, fallback)
 │
 ├─► Inspector            — folder context propagation (fixes grounding errors)
 │
 └─► MD5 hash             — content-based deduplication fingerprint
```

If the Bridge is offline, the system falls back to rule-based classification silently.
No file is ever skipped — it either classifies or goes to Quarantine.

### Phase 3 — Virtual Reconstruction (StagingManager)

The system builds a complete picture of the organised structure in memory before
touching a single file. It generates:

- `Forensic_Manifest.json` — full record of every proposed file move
- Rich Dashboard preview — user reviews the plan before committing
- Duplicate map — MD5-based exact matches, semantic matches via embedding cosine similarity

Nothing physical happens in this phase. The user sees the result and approves.

### Phase 4 — Atomic Commitment (executor.py + transaction_ledger.py)

On user approval:

```
For each file:
  1. Archive original  →  ArchiveEngine creates timestamped backup
  2. Copy to target    →  shutil.copy2 preserves metadata
  3. MD5 verify        →  source hash == destination hash
  4. Record in Ledger  →  TransactionLedger logs pre/post hashes
  5. Mark verified     →  operation status = "verified"

On any failure:
  → Session flagged for rollback
  → Original never deleted
```

---

## The Cognition Stack (V9)

| Component | File | Responsibility | Model |
|---|---|---|---|
| Bridge | `bridge.py` | Unified Ollama interface, health checks, retry logic | — |
| Judge | `judge.py` | Document classification via Sovereign Archivist prompt | `ministral-3:3b` |
| Eye | `eye.py` | Vision OCR for scanned images and unreadable PDFs | `qwen3-vl:4b` |
| Memory | `memory.py` | Semantic vector storage and similarity search | `qwen3-embedding:4b` |
| Inspector | `inspector.py` | Folder context propagation and grounding correction | `qwen2.5:3b` |
| Librarian | `librarian.py` | AI-powered filename generation | `ministral-3:3b` |

All inference runs locally via Ollama. No data leaves the machine.

### Classification Decision Tree

```
File arrives at Judge
       │
       ├─ Bridge healthy?
       │     YES → Sovereign Archivist prompt → AI ruling (confidence 0.0–1.0)
       │     NO  → Skip to rule-based path
       │
       ├─ confidence >= 0.75?
       │     YES → Use AI category + entity
       │     NO  → Fall back to rule-based classification
       │
       └─ Rule-based: keyword match against config.json category definitions
             MATCH → Assign category
             NO MATCH → "Unknown" → Inspector context check → Quarantine if still unknown
```

---

## Safety Architecture

FileFlow is built around four non-negotiable guarantees:

| Guarantee | Implementation |
|---|---|
| **Non-destructive** | Source files never deleted until bit-perfect copy is MD5-verified at destination |
| **100% local** | All AI inference via Ollama on localhost. Zero network calls to external APIs |
| **Full rollback** | `TransactionLedger` records every operation. Single command reverses any session |
| **Audit trail** | `Forensic_Manifest.json` + session logs capture every file's journey |

### Safety Locks

The following operations are **permanently disabled in code** (not just toggled off by config):

- Source file deletion in `janitor.py` — commented out with `# SAFETY LOCK` markers
- Directory pruning in `PruneExecutor.execute_prune()` — same treatment
- These can only be re-enabled by a deliberate code change, never by a config flag

### Dry Run by Default

`dry_run_default: true` in `settings.yaml`. All execution paths require an explicit override.
The CLI requires `--dry-run False`. The UI requires the user to click Approve.

---

## Directory Structure

```
FileFlow/
├── main.py                          # Entry point — orchestrates all phases
├── settings.yaml                    # Primary config (AI models, paths, scanning rules)
├── config.json                      # Category definitions and keyword rules
│
├── app/
│   ├── api.py                       # FastAPI routes (pywebview bridge)
│   │
│   ├── brain/                       # Cognition Stack
│   │   ├── bridge.py                # Ollama reliability layer
│   │   ├── judge.py                 # AI classification engine
│   │   ├── inspector.py             # Context propagation
│   │   ├── eye.py                   # Vision OCR
│   │   ├── memory.py                # LanceDB vector store
│   │   ├── extractor.py             # Unified text/PDF/image extractor
│   │   └── refinery.py              # Folder context resolver
│   │
│   ├── muscle/                      # Physical Operations
│   │   ├── executor.py              # Atomic file mover + semantic dedup
│   │   ├── janitor.py               # Cleanup and rollback
│   │   ├── versioning.py            # Filename generation engine
│   │   ├── librarian.py             # AI-powered smart naming
│   │   ├── scanner.py               # Deep recursive file discovery
│   │   ├── shadow_mapper.py         # Hard-link preview (zero-byte risk)
│   │   ├── stream_unpacker.py       # Async streaming processor (V10)
│   │   ├── transaction_ledger.py    # Audit log and infinite undo
│   │   └── resource_monitor.py      # Ryzen-aware throttle control
│   │
│   ├── memory/                      # Config and State
│   │   ├── config.py                # Unified YAML + JSON config loader
│   │   └── abbreviations.py         # Entity name shortener
│   │
│   └── types.py                     # Shared dataclasses (StagedFile, etc.)
│
├── ui/                              # Frontend (served via FastAPI)
│   └── index.html                   # Single-file React-free UI
│
├── prompts/                         # SLM prompt templates
│   ├── ruling.md                    # Sovereign Archivist classification prompt
│   ├── summarize.md                 # Archivist's Eye summary prompt
│   ├── ux_translator_v2.md          # UX intent parser prompt
│   └── architecture_sketch.md       # V10 Stories engine design doc
│
├── data/
│   ├── audit_ledger.json            # TransactionLedger persistent store
│   └── vectors.lance/               # LanceDB semantic memory index
│
├── logs/                            # Session and forensic logs
└── reports/                         # Benchmark and audit reports
```

---

## Configuration Reference

FileFlow uses two config files with a strict separation of concerns:

| File | Owns | Never put here |
|---|---|---|
| `settings.yaml` | AI models, paths, scanning rules, execution flags, versioning format | Category definitions |
| `config.json` | Category taxonomy, keywords, regex patterns, file extensions per category | Paths, model names, flags |

The `ConfigLoader` merges both at startup. If either file is missing, hardcoded fallbacks apply.

### Key Settings

```yaml
# settings.yaml — most commonly changed values
ai:
  slm_model: ministral-3:3b        # Classification model
  embed_model: qwen3-embedding:4b  # Semantic dedup model
  triage_confidence_threshold: 0.7 # Below this → rule-based fallback

execution:
  dry_run_default: true            # ALWAYS true unless you know what you're doing

scanning:
  max_depth: 10
  target_extensions: [.pdf, .docx, .doc, .jpg, .png, .txt]
```

---

## Performance Benchmarks (Ryzen 5 5500U, 12GB RAM)

| Operation | Speed | Bottleneck |
|---|---|---|
| File scanning | 200+ files/sec | SSD I/O |
| PDF text extraction | 0.5–2s per file | CPU, page count |
| AI classification | ~6s per file | CPU inference (Ollama) |
| Embedding generation | ~0.5s per file | Token count |
| Vision OCR | 15–45s per file | CPU VRAM |
| MD5 hashing | 0.1–0.5s per MB | Fast on SSD |

For a folder of 800 files (mixed PDFs): estimated 3–8 minutes end-to-end.

---

## V10 Roadmap

The `stream_unpacker.py` and `shadow_mapper.py` modules are V10 stubs already in the codebase:

- **StreamUnpacker** — replaces batch-and-wait with async file streaming; UI populates as files are discovered rather than after full analysis
- **ShadowMapper** — hard-link preview of organised structure with zero physical copies; user can browse the "after" state before committing
- **Stories Engine** — relational grouping of files by shared metadata (Case ID, creation burst, semantic similarity) rather than flat folders
- **Trust Mode** — fully autonomous run for non-technical users; no approval steps, single undo button

---

*System Status: COGNITION ONLINE (V9.2)*
