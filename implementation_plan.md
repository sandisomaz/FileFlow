## 🏁 Architectural Objective: The "Digital Memory"
Move from **Linear Process** to **Continuous Intelligence**. The goal is for the system to stop being a "utility" and start being an "agent" that understands the **Stories** behind your data (e.g., "The LLB Exam Prep Story", "The Private Legal Client X Story").

---

## 🏗️ Core Components: The "Intelligence Mesh"

### 1. UI Refactor: The "Laboratory"
**Objective**: Replace demo-centric "WOW" elements with a high-density, utility-first "Laboratory" skin.
- **Visuals**: "Industrial Dark" or "Clean Swiss" with high-density data tables.
- **Event-Stream UI**: A live "Discovery Feed" that scrolls in real-time as the brain makes links between files.
- **Graph View**: A visual map to see how "School Stuff" interacts with "Research" projects.

### 2. The Streaming Brain (Producer-Consumer)
- **Producer**: A high-speed filesystem walker (`stream_unpacker.py`).
- **Consumers**: A pool of SLMs and metadata extractors that work in parallel.
- **Differential Scanning**: MD5 persistence to avoid re-analysing 1,000s of static files.

### 3. The Knowledge Graph (Relational Memory)
**Objective**: Groups are no longer just "folders." Files are "Story Siblings" linked by shared facts:
- **Shared IDs**: Case numbers, IDs, phone numbers found in-text.
- **Temporal Links**: Files created during the same "Burst of Activity" (e.g., exam night).
- **Semantic Links**: Two files that talk about the same legal concept but never share a filename.

### 4. The Event-Driven Bridge
- **Reactive API**: Instead of `request -> wait -> response`, we move to `request -> [stream of events]`.
- **Backend Emits**: `onDiscovery`, `onLinkFound`, `onDeepThought`.
- **Frontend Reacts**: Updates the graph and the feed instantly.

---

## 🛠️ Proposed Changes (Phases)

### Phase 1: High-Density UI (Laboratory Skin)
- [MODIFY] `index.html`: Remove "Michalsons" persona, demo dots, and pulsing animations.
- [MODIFY] `index.html`: Implement CSS for high-density tables and real-time log streaming.

### Phase 2: Streaming Brain
- [NEW] `app/muscle/stream_unpacker.py`: Refactor `_walk_tree` into a generator.
- [MODIFY] `app/api.py`: Update `_run_scout` to handle the stream and update the UI incrementally.

### Phase 3: Knowledge Graph Integration
- [NEW] `app/brain/knowledge_graph.py`: Define the relational schema for file linking.

## 🛡️ Safety & Persistence (The Save Strategy)
**Objective**: "Save our work step-by-step" to ensure every major change is documented and reversible.
- **Atomic Commits**: Every phase (UI, Backend, Graph) will be its own Git commit.
- **Internal Checkpoints**: Before any destructive changes (like deleting old logic), we will create a `legacy_v1_backup` branch.
- **State Capture**: Every tool execution will be followed by a status check to verify stability.
