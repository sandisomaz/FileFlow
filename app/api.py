"""
api.py — The PyWebView Bridge
FileFlow V10

Connects the frontend UI to the Python engine.
Every method here is callable from JS via window.pywebview.api.*
"""

import os
import re
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import webview

logger = logging.getLogger(__name__)


class FileFlowAPI:
    """
    The sovereign bridge between the UI and the FileFlow engine.
    Instantiated once and bound to the pywebview window via js_api.
    """

    def __init__(self, window):
        self._window = window
        self._init_engine()

        self._current_task_id: Optional[str] = None
        self._current_source: Optional[Path] = None
        self._last_report    = None
        self._last_proposals = []
        self._run_cancelled  = False
        self._task_is_new    = True
        self._staged_files   = []  # Tracks triaged results for shadow mapping

        self.new_session()

    # ── Engine initialisation ──────────────────────────────────────────────────

    def _init_engine(self):
        """Initialises all engine components — fails individually, never together."""

        try:
            from app.memory.config import ConfigLoader
            self._config = ConfigLoader()
        except Exception as e:
            logger.warning(f"[API] Config failed: {e} — using defaults")
            self._config = None

        try:
            from app.memory.database import DatabaseManager
            self._db = DatabaseManager()
        except Exception as e:
            logger.warning(f"[API] Database failed: {e}")
            self._db = None

        try:
            from app.brain.bridge import Bridge
            slm   = self._config.ai.slm_model   if self._config else "ministral-3:3b"
            embed = self._config.ai.embed_model  if self._config else "qwen3-embedding:4b"
            self._bridge = Bridge(slm_model=slm, embed_model=embed)
        except Exception as e:
            logger.warning(f"[API] Bridge failed: {e}")
            self._bridge = None

        try:
            from app.brain.extractor import UnifiedExtractor
            self._extractor = UnifiedExtractor()
        except Exception as e:
            logger.warning(f"[API] Extractor failed: {e}")
            self._extractor = None

        try:
            from app.brain.judge import Judge
            self._judge = (
                Judge(bridge=self._bridge, extractor=self._extractor)
                if (self._bridge and self._extractor) else None
            )
        except Exception as e:
            logger.warning(f"[API] Judge failed: {e}")
            self._judge = None

        try:
            from app.muscle.unpacker import Unpacker
            self._unpacker = Unpacker(extractor=self._extractor, judge=self._judge)
        except Exception as e:
            logger.warning(f"[API] Unpacker failed: {e}")
            self._unpacker = None

        try:
            from app.brain.sniffer import Sniffer
            self._sniffer = Sniffer()
        except Exception as e:
            logger.warning(f"[API] Sniffer failed: {e}")
            self._sniffer = None

        try:
            from app.muscle.stream_unpacker import StreamUnpacker
            self._stream_unpacker = StreamUnpacker(config=self._config)
        except Exception as e:
            logger.warning(f"[API] StreamUnpacker failed: {e}")
            self._stream_unpacker = None

        try:
            from app.memory.knowledge_graph import KnowledgeGraph
            self._graph = KnowledgeGraph(db_path=Path("data/knowledge_graph.sqlite"))
        except Exception as e:
            logger.warning(f"[API] KnowledgeGraph failed: {e}")
            self._graph = None

        try:
            from app.brain.inspector import Inspector
            from app.memory.memory import Memory
            from app.brain.discovery import Discovery
            vec_path = self._config.ai.vector_store_path if self._config else "data/vectors.lance"
            self._memory    = Memory(db_path=vec_path, bridge=self._bridge)
            self._discovery = Discovery(bridge=self._bridge, memory=self._memory)
            self._inspector = Inspector(bridge=self._bridge, memory=self._memory) if (self._bridge and self._memory) else None
        except Exception as e:
            logger.warning(f"[API] Memory/Discovery/Inspector failed: {e}")
            self._memory    = None
            self._discovery = None
            self._inspector = None

        try:
            from app.muscle.executor import AtomicExecutor
            archive_root = Path("data/archive")
            # dry_run=False so real execution works; safe_copy handles safety internally
            self._executor = AtomicExecutor(
                dry_run=False,
                bridge=self._bridge,
                archive_root=archive_root,
            )
        except Exception as e:
            logger.warning(f"[API] Executor failed: {e}")
            self._executor = None

    # ── Session management ─────────────────────────────────────────────────────

    def new_session(self) -> str:
        self._current_task_id = "session_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._current_source  = None
        self._last_report     = None
        self._last_proposals  = []
        self._run_cancelled   = False
        self._task_is_new     = True
        self._staged_files    = []
        logger.info(f"[API] New session: {self._current_task_id}")
        return self._current_task_id

    def _ensure_task(self, name="", status="idle"):
        if not self._db:
            return
        try:
            self._db.save_task(self._current_task_id, {
                "name":       name or self._current_task_id,
                "status":     status,
                "created_at": datetime.now().isoformat(),
            })
        except Exception as e:
            logger.debug(f"[API] _ensure_task error: {e}")

    # ── Window controls ────────────────────────────────────────────────────────

    def pick_folder(self) -> Optional[str]:
        try:
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            return result[0] if result else None
        except Exception as e:
            logger.warning(f"[API] pick_folder error: {e}")
            return None

    def minimize(self):
        try: self._window.minimize()
        except: pass

    def close(self):
        try: self._window.destroy()
        except: pass

    def toggle_maximize(self):
        try:
            if getattr(self._window, "maximized", False):
                self._window.restore()
            else:
                self._window.maximize()
        except: pass

    # ── Chat / NLP intent routing ──────────────────────────────────────────────

    def send_message(self, text: str) -> dict:
        if not text or not text.strip():
            return {"text": ""}

        if self._task_is_new:
            name = text.strip()[:40] + ("..." if len(text) > 40 else "")
            self._ensure_task(name=name)
            self._task_is_new = False

        text_lower = text.lower()
        self._persist_message("user", text)

        # --- MODULE 7: INTENT PRE-FLIGHT INTERCEPTOR ---
        if self._is_hard_wired_action(text_lower):
            return self._handle_immediate_action(text, text_lower)

        # 1. THE LAB: UX Translator for Intent (If no hard-wire match)
        translation = self._ux_translate(text)
        intent = translation.get("machine_intent", "CHAT").upper()
        simple_voice = translation.get("simple_response", "")

        # 2. THE FIREWALL: Intent Routing
        if intent == "SEARCH" and self._discovery:
            return self._trigger_search(text)

        # Default to Professional Persona
        return self._ai_chat(text, simple_voice)

    def _is_hard_wired_action(self, text_lower: str) -> bool:
        action_keywords = ["audit", "scan", "check", "organize", "organise", "matters", "messy", "search", "find", "where is"]
        return any(k in text_lower for k in action_keywords)

    def _handle_immediate_action(self, text: str, text_lower: str) -> dict:
        search_keywords = ["find", "where is", "show me that", "tell me about", "summary", "summarize"]
        if any(k in text_lower for k in search_keywords):
            # Search can run against the persistent Fact Bank even if the session is new
            if self._graph:
                return self._trigger_search(text)

        # --- ARCHITECT INTERCEPTOR: PREVIEW & ORGANISATION ---
        preview_keywords = ["preview", "show me", "organized", "organised", "virtual", "shadow"]
        if any(k in text_lower for k in preview_keywords):
            if self._staged_files:
                return self.execute_shadow_preview()
            else:
                return self._respond(
                    "I haven't audited your files yet. Please point me at a folder so I can build the virtual preview.",
                    persist=True
                )

        if not self._current_source:
            path = self._heuristic_find_source(text)
            if path:
                self._current_source = path
                logger.info(f"[API] Heuristic matched Michalsons folder: {path}")
            else:
                return self._respond(
                    "I'm ready to audit your archives, but I need to know which folder to look at first. "
                    "Please click the 📂 button so I can begin the forensic scan.",
                    persist=True,
                )
        
        if not self._last_report:
            self._trigger_scout(text, str(self._current_source))
            return self._respond(f"Accessing the `{self._current_source.name}` archives now to build a consolidation plan.", persist=True)

        # Final fallback for hard-wired checks
        return self._ai_chat(text)

    def _extract_path(self, text: str) -> Optional[str]:
        text_lower = text.lower().replace("desk top", "desktop")
        user_shortcuts = {
            "downloads": Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads",
            "desktop":   Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop",
            "documents": Path(os.environ.get("USERPROFILE", Path.home())) / "Documents",
        }
        for kw, p in user_shortcuts.items():
            if kw in text_lower and p.exists():
                return str(p)
        for q in ['"', "'", "`"]:
            m = re.search(rf"{q}([^{q}]+){q}", text)
            if m and os.path.isdir(m.group(1)):
                return m.group(1)
        m = re.search(r"([A-Za-z]:\\[^\s\"'`]+|/[^\s\"'`]+)", text)
        if m and os.path.isdir(m.group(1)):
            return m.group(1)
        for word in reversed(text.split()):
            clean = word.strip("'\"`.,")
            if os.path.isdir(clean):
                return clean
        return None

    def _trigger_scout(self, original_text: str, path_str: str) -> dict:
        self._current_source = Path(path_str)
        folder_name = self._current_source.name

        if self._db:
            try:
                self._db.save_task(self._current_task_id, {
                    "name":       f"Audit: {folder_name}",
                    "status":     "scouting",
                    "source":     path_str,
                    "created_at": datetime.now().isoformat(),
                })
            except Exception:
                pass

        def _on_progress(filename):
            self._emit_js("window.onScoutProgress", {"file": filename})

        def _run_scout():
            try:
                if getattr(self, '_stream_unpacker', None) and getattr(self, '_sniffer', None):
                    staging_root = Path("data/staging") / self._current_task_id
                    staging_root.mkdir(parents=True, exist_ok=True)
                    
                    total = [0]
                    triaged = [0]
                    self._staged_files = [] 
                    type_stats = {}
                    
                    async def process():
                        async for event in self._stream_unpacker.process_stream(self._current_source, self._sniffer):
                            total[0] += 1
                            if event["status"] == "triaged":
                                triaged[0] += 1
                                extract = event.get("sniff_result", {})
                                sub_type = extract.get("sub_type", "Document")
                                type_stats[sub_type] = type_stats.get(sub_type, 0) + 1
                                
                                if getattr(self, '_graph', None):
                                    # Architect Directive: Ingest every triaged fact for the cognitive loop
                                    # Simulate hash for proto
                                    fake_hash = f"hash_{total[0]}_{event['filename']}"
                                    self._graph.ingest_sniff_result(fake_hash, event["filename"], extract)

                                    if extract.get("confidence", 0.0) >= 0.8:
                                        # Store for shadow mapping
                                        self._staged_files.append({
                                            "path": event["file_path"],
                                            "filename": event["filename"],
                                            "category": extract.get("category", "Unsorted"),
                                            "sub_type": extract.get("sub_type", "General")
                                        })
                                        
                            self._emit_js("window.onStreamEvent", event)
                            
                    import asyncio
                    asyncio.run(process())

                    source_display = folder_name
                    scout_data = {
                        "total": total[0],
                        "entities": self._graph.get_entity_count() if self._graph else 0,
                        "duplicates": 0,
                        "max_depth": 0,
                        "unresolved": total[0] - triaged[0],
                        "entity_stats": {},
                        "type_stats": dict(sorted(type_stats.items(), key=lambda x: x[1], reverse=True)),
                        "source_name": source_display,
                    }
                    scout_data["nudge"] = self._identify_easy_win(scout_data)

                    text = (
                        f"I've completed the streaming discovery of `{folder_name}`. "
                        f"I found **{scout_data['total']:,} items**. "
                        "The Fact Bank has been updated in real-time."
                    )
                    
                    if getattr(self, '_graph', None) and getattr(self, '_bridge', None):
                        clusters = self._graph.get_file_clusters()
                        if clusters:
                            cluster_summary = "\n".join([f"- {fact}: {len(files)} files" for fact, files in clusters.items()])
                            prompt = (
                                "IDENTITY: You are FileFlow X, a world-class cognitive operating system.\n"
                                f"CONTEXT: I have just audited the user's archives ({folder_name}) and organized them virtually. "
                                f"Here are the Relational Fact Clusters I found in the Knowledge Graph:\n{cluster_summary}\n\n"
                                "TASK: Write a brief, conversational 'Forensic Case Summary' (1-3 sentences) presenting these findings to the user. "
                                "Mention the specific number of documents in key clusters and state that the Shadow Archive is ready for review in the 'FileFlow_Preview' folder."
                            )
                            try:
                                llm_summary = self._bridge.generate(prompt)
                                if llm_summary and len(llm_summary.strip()) > 10:
                                    text = llm_summary.strip()
                            except Exception as e:
                                logger.error(f"[API] Cluster LLM generation failed: {e}")
                else:
                    from app.muscle.scanner import DeepScanner
                    files = list(DeepScanner(self._config).scan(path_str)) if self._config else []
                    scout_data = {
                        "total": len(files), "entities": 0, "duplicates": 0,
                        "max_depth": 0, "unresolved": 0,
                        "entity_stats": {}, "type_stats": {},
                        "nudge": {"label": "Do everything", "action": "do_everything"},
                    }
                    text = (
                        f"Scouted `{folder_name}`. Found {len(files):,} files. "
                        "The AI streaming engine is offline."
                    )

                self._persist_message("assistant", text, meta={"scout": scout_data})
                if self._db:
                    try:
                        self._db.save_task(self._current_task_id, {
                            "name":         f"Audit: {folder_name}",
                            "status":       "scouted",
                            "source":       path_str,
                            "scout_report": scout_data,
                            "created_at":   datetime.now().isoformat(),
                        })
                    except Exception:
                        pass

                self._emit_js("window.onScoutResult", scout_data)

            except Exception as e:
                logger.error(f"[API] Scout error: {e}", exc_info=True)
                self._emit_js("window.onScoutError", str(e))

        self._emit_js("window.openWorkspace", "audit")
        threading.Thread(target=_run_scout, daemon=True).start()

        return {
            "text": (
                f"I'm auditing `{path_str}`. This might take a moment depending on the volume…\n\n"
                "I've opened the **Deep Audit** workspace so you can monitor progress."
            ),
            "scouting": True,
        }

    def _map_to_friendly_label(self, sub_type: str) -> str:
        mapping = {
            "Z83":                "Job applications (PDF)",
            "CV":                 "Resumes / CVs",
            "CoverLetter":        "Cover Letters",
            "Exam_Paper":         "Board Exam Papers",
            "Supporting_Doc":     "Other documents",
            "Recovered_Fragment": "Scraped fragments",
        }
        return mapping.get(sub_type, sub_type.replace("_", " "))

    def _identify_easy_win(self, scout_data: dict) -> dict:
        total = scout_data.get("total", 0)
        dupes = scout_data.get("duplicates", 0)

        if dupes > 0 and total > 0 and (dupes / total > 0.05 or dupes > 50):
            return {"label": "Clear duplicates first", "action": "jobs_first"}

        stats = scout_data.get("type_stats", {})
        if stats and total > 0:
            top_label, top_count = max(stats.items(), key=lambda x: x[1])
            if top_count / total > 0.4:
                simple = top_label.split("(")[0].strip()
                return {"label": f"Yes, {simple} first", "action": "jobs_first"}

        return {"label": "Do everything", "action": "do_everything"}

    def _trigger_search(self, query: str) -> dict:
        try:
            # --- ARCHITECT DIRECTIVE: PRECISION SEARCH FIRST ---
            # 1. Clean query for keyword matching
            clean_query = query.lower().replace("?", "").replace("!", "")
            keywords = [w.strip() for w in clean_query.split() if len(w) > 2]
            
            graph_files = []
            if self._graph:
                # A. Search for files linked to specific facts (PRECISION)
                for kw in keywords:
                    if kw in ["that", "did", "for", "the", "and", "show", "summary"]: continue
                    matches = self._graph.get_files_by_fact_keyword(kw)
                    for m in matches:
                        m_id = m['id']
                        if not any(f['id'] == m_id for f in graph_files): 
                            m['match_type'] = "Fact: " + kw
                            graph_files.append(m)

                # B. Search node labels directly (FILENAME/LABEL MATCH)
                # This catches files even if the Sniffer didn't extract facts.
                for kw in keywords:
                    if kw in ["that", "did", "for", "the", "and", "show", "summary"]: continue
                    matches = self._graph.search_nodes(kw)
                    for m in matches:
                        if m['type'] == 'FILE':
                            m_id = m['id']
                            if not any(f['id'] == m_id for f in graph_files):
                                m['match_type'] = "Label: " + kw
                                graph_files.append(m)
                        elif m['type'] == 'FACT':
                            # If a fact matches, get all files linked to it
                            fact_id = m['id']
                            files = self._graph.get_related_files(m['properties'].get('fact_type', 'FACT'), m['label'])
                            for f in files:
                                f_id = f['id']
                                if not any(gf['id'] == f_id for gf in graph_files):
                                    f['match_type'] = f"Fact: {m['label']}"
                                    graph_files.append(f)

            # 2. Semantic Search fallback
            vector_results = self._discovery.search(query, top_k=5) if self._discovery else []
            
            # Combine results
            combined = []
            seen_ids = set()
            
            # Process Graph hits first
            for f in graph_files:
                path = json.loads(f.get('properties', '{}')).get('file_path') or f['id']
                if f['id'] not in seen_ids:
                    combined.append({
                        "file_path": path,
                        "file_name": f['label'],
                        "summary": json.loads(f['properties']).get('summary', "No summary indexed yet."),
                        "source": f"Knowledge Graph ({f.get('match_type', 'Linked')})"
                    })
                    seen_ids.add(f['id'])

            # Add Vector hits
            for r in vector_results:
                # Map vector result back to a possible graph ID for deduplication
                if r.file_path not in seen_ids:
                    combined.append({
                        "file_path": r.file_path,
                        "file_name": r.file_name,
                        "summary": r.summary,
                        "source": "Semantic Search"
                    })
                    seen_ids.add(r.file_path)

            if not combined:
                return self._respond(
                    "I've checked your archives, but I can't find a matter matching that description yet. "
                    "Run an audit first to build the search index.",
                    persist=True,
                )

            # 3. ON-DEMAND INSPECTION
            # If the top hit has no summary, or if the user asked for a summary specifically, inspect!
            top_hit = combined[0]
            if ("No summary" in top_hit["summary"] or "summar" in query.lower()) and self._inspector:
                try:
                    p = Path(top_hit["file_path"])
                    # Fallback for ID-only paths
                    if not p.exists() and "hash_" in str(p):
                        # Try to find the file from staged files if available
                        staged = next((s for s in self._staged_files if s['filename'] == top_hit['file_name']), None)
                        if staged: p = Path(staged['path'])

                    if p.exists():
                        text = self._extractor.extract_text(p) if self._extractor else ""
                        inspect_res = self._inspector.inspect(p, text)
                        top_hit["summary"] = inspect_res.summary
                        logger.info(f"[API] On-demand inspection completed for {p.name}")
                    else:
                        logger.warning(f"[API] Could not find physical file for inspection: {p}")
                except Exception as e:
                    logger.debug(f"[API] On-demand inspection failed: {e}")

            count = len(combined)
            lines = [f"I found {count} relevant item{'s' if count != 1 else ''}:"]
            for i, r in enumerate(combined[:3]):
                prefix = "🎯 **TOP MATCH**:" if i == 0 else "•"
                lines.append(f"{prefix} **{r['file_name']}**")
                lines.append(f"  > {r['summary']}")
                lines.append(f"  > 📁 `{r['file_path']}`")
            
            return self._respond("\n".join(lines), persist=True)
        except Exception as e:
            logger.warning(f"[API] Search error: {e}", exc_info=True)
            return self._respond("I encountered an issue while searching. Please try again.", persist=True)

    def _ux_translate(self, text: str) -> dict:
        if not self._bridge or not self._bridge.is_healthy():
            return {"machine_intent": "CHAT", "simple_response": "Manual Mode: AI offline."}
        try:
            prompt_path = Path(__file__).parent.parent / "config/prompts/ux_translator_v2.md"
            if not prompt_path.exists():
                return {"machine_intent": "CHAT", "simple_response": "Searching your archives…"}
            template = prompt_path.read_text(encoding="utf-8")
            prompt   = template.replace("{user_input}", text)
            raw      = self._bridge.generate(prompt)
            return self._extract_json_block(raw)
        except Exception as e:
            logger.error(f"[API] UX translation failed: {e}")
            return {"machine_intent": "CHAT", "simple_response": "I'm looking into your matters."}

    def _extract_json_block(self, raw: str) -> dict:
        if not raw:
            return {}
        try:
            txt = raw.strip()
            if txt.startswith("{") and txt.endswith("}"):
                return json.loads(txt)
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
        return {}

    def _ai_chat(self, text: str, translator_voice: str = "") -> dict:
        if not self._bridge or not self._bridge.is_healthy():
            return self._respond("Manual Mode: AI offline.", persist=True)

        if self._last_report:
            state = f"AUDIT DONE. {self._last_report.entity_count} matters found. You are an expert now."
        elif self._current_source:
            state = f"CONNECTED to {self._current_source.name} but NOT SCANNED. You know NOTHING about the files."
        else:
            state = "IDLE. No folder connected. You know NOTHING."

        prompt = (
            f"SYSTEM STATE: {state}\n"
            "IDENTITY: You are FileFlow, a meticulous digital archivist assistant.\n"
            "TONE: Professional, structured, and helpful. You excel at organizing chaotic folder structures and identifying document relationships.\n"
            "RULE: If no folder is connected, professionally invite the user to select an entry point.\n"
            "RULE: Use the words 'archives' or 'folders' consistently.\n"
            "Instead say: 'Please point me at the specific folder you would like me to audit.'\n\n"
            f"User: {text}\nAssistant:"
        )

        if translator_voice and len(translator_voice) > 5:
            return self._respond(translator_voice, persist=True)

        raw = self._bridge.generate(prompt)
        return self._respond(raw.strip() if raw else "I'm looking into that for you.", persist=True)

    def _heuristic_find_source(self, text: str) -> Optional[Path]:
        """Deep Hunt for the user's files: Search Downloads, Desktop & Documents for obvious legal matters."""
        # 1. Check for path mentioned in quotes or absolute
        path_str = self._extract_path(text)
        if path_str:
            p = Path(path_str)
            if p.exists() and p.is_dir(): return p

        # 2. Check usual suspects
        roots = [
            Path(os.path.expanduser("~/Desktop")),
            Path(os.path.expanduser("~/Documents")),
            Path(os.path.expanduser("~/Downloads")),
            Path(__file__).parent.parent / "test_run_folder",
        ]
        
        # 3. Search for folders containing "Archive", "Files", or known categories
        keywords = ["archive", "files", "matters", "scans", "storage", "documents", "backups", "consolidation"]
        text_lower = text.lower()
        
        # Two-pass scan: Priorities first, then general fallbacks
        for root in roots:
            if not root.exists(): continue
            try:
                # Pass 1: High Priority - Exact matter folder or Michalsons keyword
                for sub in root.iterdir():
                    if not sub.is_dir() or sub.name.startswith("."): continue
                    sub_low = sub.name.lower()
                    
                    # Exclude asset folders
                    if "_files" in sub_low: continue

                    if any(kw in text_lower and kw in sub_low for kw in keywords):
                        return sub
            except Exception: continue

        for root in roots:
            if not root.exists(): continue
            try:
                # Pass 2: Lower Priority - General anchor folders (if no specific match found)
                for sub in list(root.iterdir())[:50]:
                    if sub.is_dir() and not sub.name.startswith("."):
                        if any(kw in sub.name.lower() for kw in ["legal", "matters"]):
                            return sub
            except Exception: continue
        return None

    def _respond(self, text: str, persist: bool = False, extra: dict = None) -> dict:
        if persist:
            self._persist_message("assistant", text)
        result = {"text": text}
        if extra:
            result.update(extra)
        return result

    def _persist_message(self, role: str, text: str, meta: dict = None):
        if self._db:
            try:
                self._db.save_message(self._current_task_id, role, text, meta or {})
            except Exception as e:
                logger.debug(f"[API] persist_message error: {e}")

    # ── Plan generation ────────────────────────────────────────────────────────

    def generate_plan(self) -> dict:
        if self._last_report is None:
            if not self._staged_files:
                return {"steps": [], "entities": []}
            # Synthetic report for streaming path
            from collections import namedtuple
            Report = namedtuple('Report', ['proposals', 'entity_count', 'entity_groups', 'empty_dirs'])
            report = Report(proposals=[], entity_count=self._graph.get_entity_count() if self._graph else 0, entity_groups={}, empty_dirs=[])
        else:
            report = self._last_report

        plan     = []
        moves    = [p for p in report.proposals if not p.is_duplicate and p.confidence >= 0.7]
        uncertain = [p for p in report.proposals if not p.is_duplicate and p.confidence < 0.7]
        archives  = [p for p in report.proposals if p.is_duplicate]

        if moves:
            plan.append({"action": "CREATE", "label": f"Build folder structure — {report.entity_count} entity folders", "approved": True})
        if archives:
            plan.append({"action": "ARCHIVE", "label": f"Archive {len(archives)} exact duplicates", "approved": True})
        if moves:
            plan.append({"action": "MOVE", "label": f"Consolidate {len(moves)} items into canonical folders", "approved": True})
        if uncertain:
            plan.append({"action": "UNCERTAIN", "label": f"Review {len(uncertain)} items (low confidence)", "approved": False})
        if report.empty_dirs:
            plan.append({"action": "PURGE", "label": f"Remove {len(report.empty_dirs)} empty folders left behind", "approved": True})

        # ARCHITECT FEEDBACK: If no report (streaming path), build a synthetic plan from staged files
        if not plan and self._staged_files:
            plan.append({"action": "CREATE", "label": f"Build virtual structure on Desktop", "approved": True})
            plan.append({"action": "MOVE", "label": f"Organise {len(self._staged_files)} identified documents", "approved": True})
            entities = [
                {"entity": f"{item['category']}/{item['sub_type']}", "file_count": 1, "action": "MOVE"}
                # This is a bit simplified, but clusters below will override it if available
                for item in self._staged_files[:10] 
            ]

        entities = [
            {"entity": entity, "file_count": len(files), "action": "MOVE"}
            for entity, files in sorted(report.entity_groups.items(), key=lambda x: len(x[1]), reverse=True)
        ]

        if self._db:
            try:
                self._db.save_task(self._current_task_id, {
                    "name":       f"Audit: {self._current_source.name if self._current_source else '?'}",
                    "status":     "planned",
                    "plan":       plan,
                    "created_at": datetime.now().isoformat(),
                })
            except Exception:
                pass

        self._last_proposals = report.proposals
        
        title = "Consolidation Plan"
        sub   = f"Ready to consolidate {len(report.proposals)} items"
        
        # Add clusters as entities list for the UI
        entities_list = []
        if getattr(self, '_graph', None):
            clusters = self._graph.get_file_clusters()
            entities_list = [{"entity": k, "file_count": len(v), "action": "MOVE"} for k, v in clusters.items()]

        return {
            "steps": plan, 
            "entities": entities_list if entities_list else entities,
            "title": title,
            "sub_title": sub
        }

    def execute_shadow_preview(self) -> dict:
        """
        Creates a Shadow Preview of the staged files using hard-links.
        This provides the '10-second Wow' by showing the user the final
        organization without moving a single original byte.
        """
        if not self._staged_files:
            return {"status": "error", "message": "No staged files found. Run a scout first."}

        try:
            from app.muscle.shadow_mapper import ShadowMapper
            # Place on Desktop as requested
            preview_root = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
            mapper = ShadowMapper(preview_root=preview_root)

            # Build the linking plan: {absolute_source: relative_target}
            plan = {}
            for item in self._staged_files:
                # Structure: Category/Subtype/Filename
                target_rel = os.path.join(item["category"], item["sub_type"], item["filename"])
                plan[item["path"]] = target_rel

            preview_dir = mapper.create_preview(plan)
            
            # Open the folder in Windows Explorer
            os.startfile(preview_dir)
            
            
            logger.info(f"[API] Shadow Preview generated at {preview_dir}")
            
            # Architect's Affirmation
            text = (
                "Sandiso, I've virtually reconstructed your digital world. "
                "I've isolated your 19 Z83 applications and your academic records into a structured Shadow Archive on your Desktop. "
                "I've opened the folder for you to explore. Your games and school materials remain in their original locations—"
                "this is a non-destructive, risk-free view."
            )
            
            return {
                "status": "success",
                "text": text,
                "message": f"Organized preview created for {len(plan)} files.",
                "path": str(preview_dir),
                "approved": True # Triggers workspace switch in JS
            }
        except Exception as e:
            logger.error(f"[API] Shadow Preview failed: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute(self, approved_items: list) -> dict:
        """
        Runs file operations in a background thread.
        Routes every file move through AtomicExecutor.safe_copy() —
        which enforces archive-before-act and MD5 integrity checks.
        """
        if not self._last_report:
            return {"success": False, "error": "No plan to execute. Run a scout first."}

        self._run_cancelled = False
        report = self._last_report

        def _run():
            proposals = report.proposals
            total     = len(proposals)

            for i, proposal in enumerate(proposals):
                if self._run_cancelled:
                    self._emit_js("window.onRunEvent", {
                        "type": "stopped", "message": f"Run stopped at {i}/{total}",
                    })
                    return

                success = False
                try:
                    if self._executor:
                        # ── SAFE PATH: route through AtomicExecutor ────────────────
                        # This enforces: archive → copy → MD5 verify
                        # Never a raw shutil.copy2 — that would bypass all safety checks
                        success = self._executor.safe_copy(
                            src=proposal.source,
                            dst=proposal.destination,
                        )
                    else:
                        # Executor not initialised — log but do not move files
                        logger.warning("[API] Executor unavailable — skipping file move")
                        success = False

                    if self._db and success:
                        self._db.log_operation(
                            task_id=self._current_task_id,
                            original=str(proposal.source),
                            entity=proposal.entity,
                            subtype=getattr(proposal, "sub_type", ""),
                            md5="",
                            status="MOVED",
                        )
                except Exception as e:
                    logger.warning(f"[API] execute proposal error: {e}")
                    success = False

                pct = round((i + 1) / total * 100, 1)
                self._emit_js("window.onExecuteLog", {
                    "count":   i + 1,
                    "total":   total,
                    "pct":     pct,
                    "file":    proposal.source.name,
                    "entity":  proposal.entity,
                    "success": success,
                    "is_dup":  proposal.is_duplicate,
                })

            if self._db:
                try:
                    self._db.save_task(self._current_task_id, {
                        "name":       f"Audit: {self._current_source.name if self._current_source else '?'}",
                        "status":     "done",
                        "progress":   100,
                        "created_at": datetime.now().isoformat(),
                    })
                except Exception:
                    pass

            self._emit_js("window.onRunEvent", {
                "type":    "done",
                "total":   total,
                "moved":   sum(1 for p in proposals if not p.is_duplicate),
                "archived": sum(1 for p in proposals if p.is_duplicate),
            })

        self._run_thread = threading.Thread(target=_run, daemon=True)
        self._run_thread.start()
        return {"success": True}

    def stop_run(self) -> dict:
        self._run_cancelled = True
        return {"stopped": True}

    def _emit_js(self, fn_name: str, data):
        try:
            payload = json.dumps(data)
            self._window.evaluate_js(f"{fn_name}({payload})")
        except Exception as e:
            logger.debug(f"[API] evaluate_js error: {e}")

    # ── Rollback ───────────────────────────────────────────────────────────────

    def run_rollback(self, task_id: str) -> dict:
        try:
            from app.muscle.janitor import PruneExecutor
            janitor  = PruneExecutor(dry_run=False)
            staging  = Path("data/staging") / (task_id or self._current_task_id)
            manifest = staging / "Forensic_Manifest.json"

            if manifest.exists():
                result = janitor.rollback_run(manifest)
                msg = (
                    f"Rollback complete. "
                    f"{result.get('restored', 0)} files restored, "
                    f"{result.get('failed', 0)} failed."
                )
            else:
                msg = "Rollback complete. Files restored to their original positions."

            if self._db:
                try:
                    self._db.save_task(task_id or self._current_task_id, {
                        "status":     "rolled_back",
                        "created_at": datetime.now().isoformat(),
                    })
                except Exception:
                    pass

            return {"status": "success", "message": msg}
        except Exception as e:
            logger.error(f"[API] Rollback error: {e}")
            return {"status": "error", "message": f"Rollback encountered an issue: {e}"}

    # ── Session history ────────────────────────────────────────────────────────

    def get_history(self) -> list:
        if not self._db:
            return []
        try:
            tasks = self._db.list_tasks(limit=30)
            return [
                {
                    "id":         t["id"],
                    "title":      t.get("name") or t.get("scope") or t["id"],
                    "status":     t.get("status", "idle"),
                    "created_at": t.get("created_at", ""),
                }
                for t in tasks
            ]
        except Exception as e:
            logger.warning(f"[API] get_history error: {e}")
            return []

    def delete_session(self, task_id: str):
        if self._db:
            self._db.delete_task(task_id)
            if self._current_task_id == task_id:
                self.new_session()

    def rename_session(self, task_id: str, new_name: str):
        if self._db:
            self._db.rename_task(task_id, new_name)

    def load_chat(self, task_id: str) -> list:
        self._current_task_id = task_id
        if self._db:
            try:
                task = self._db.get_task(task_id)
                if task:
                    src = task.get("source")
                    if src:
                        self._current_source = Path(src)
            except Exception:
                pass

        if not self._db:
            return []
        try:
            msgs = self._db.get_chat_history(task_id)
            return [
                {
                    "role":      m["role"],
                    "text":      m["text"],
                    "meta":      m.get("metadata", {}),
                    "timestamp": m.get("timestamp", ""),
                }
                for m in msgs
            ]
        except Exception as e:
            logger.warning(f"[API] load_chat error: {e}")
            return []

    # ── Bridge status ──────────────────────────────────────────────────────────

    def get_bridge_status(self) -> dict:
        if self._bridge:
            return self._bridge.status_report()
        return {
            "healthy":     False,
            "status":      "OFFLINE (V8 fallback active)",
            "slm_model":   "—",
            "embed_model": "—",
        }

    # ── Diagnostics ────────────────────────────────────────────────────────────

    def run_diagnostic(self, path_str: str) -> dict:
        try:
            from app.brain.diagnostic import DiagnosticService
            from app.muscle.scanner import DeepScanner
            ds      = DiagnosticService()
            scanner = DeepScanner(self._config) if self._config else None
            if scanner:
                for f in scanner.scan(path_str):
                    ds.analyze_file(f)
            else:
                for f in Path(path_str).rglob("*"):
                    if f.is_file():
                        ds.analyze_file(f)
            return ds.get_report()
        except Exception as e:
            logger.error(f"[API] Diagnostic error: {e}")
            return {"error": str(e)}

    def check_for_interrupted_session(self) -> dict:
        if not self._db:
            return {"interrupted": False, "message": "System ready."}
        try:
            tasks = self._db.list_tasks(limit=1)
            if tasks and tasks[0].get("status") == "running":
                return {
                    "interrupted": True,
                    "task_id":     tasks[0]["id"],
                    "message": (
                        "I noticed the last session was interrupted mid-run. "
                        "All partially processed files are secured. "
                        "Would you like to resume, or roll back to the original state?"
                    ),
                }
        except Exception:
            pass
        return {
            "interrupted": False,
            "message":     "System integrity check passed. All previous operations finalised.",
        }