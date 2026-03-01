import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import your Core Logic
from fileflow.core.config import ConfigLoader
from fileflow.core.scanner import DeepScanner
from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.judge import Judge
from fileflow.intelligence.extractor import UnifiedExtractor
from fileflow.staging.manager import StagingManager
from fileflow.operations.executor import AtomicExecutor
from fileflow.operations.janitor import PruneExecutor
from fileflow.operations.librarian import Librarian
from fileflow.operations.versioning import Versioning
from fileflow.core.logger import MigrationLogger, MigrationReport
from fileflow.core.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# In-memory storage for active staged files (too big for DB blob usually)
_active_tasks = {}

def _get_config(): return ConfigLoader()
def _get_db(): return DatabaseManager()

# --- ROUTES ---

class ChatRequest(BaseModel):
    message: str

class ScanRequest(BaseModel):
    path: str
    scope: str = "all"

class ExecuteRequest(BaseModel):
    task_id: str
    dry_run: bool = False

@router.post("/chat")
def chat(req: ChatRequest):
    msg = req.message.lower()
    if "hello" in msg or "hi" in msg:
        resp = "Good afternoon. I am ready to assist with your document management. Would you like to audit a specific folder or sort through your recent matters?"
    elif "help" in msg:
        resp = "I can help you audit folders, identify duplicates, and organise case files into a professional taxonomy. Simply point me to a directory to begin."
    else:
        resp = "I've noted your request. To proceed with precision, please provide the path to the directory you wish to organise, or select an action from the menu."
    return {"response": resp}

@router.post("/scan")
def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    task_data = {
        "id": task_id,
        "status": "scanning",
        "progress": 0,
        "source": req.path,
        "stats": {},
        "scout_report": None
    }
    _active_tasks[task_id] = task_data
    _get_db().save_task(task_id, task_data)
    
    background_tasks.add_task(_run_scan, task_id, req.path)
    return {"task_id": task_id}

def _run_scan(task_id, path_str):
    task = _active_tasks[task_id]
    config = _get_config()
    scanner = DeepScanner(config)
    # Note: StagingManager in your code takes extractor/judge
    extractor = UnifiedExtractor()
    bridge = Bridge(slm_model=config.ai.slm_model)
    judge = Judge(bridge, extractor) if bridge.is_healthy() else None
    
    manager = StagingManager(extractor, judge)
    
    path = Path(path_str)
    files = list(scanner.scan(str(path)))
    
    # Simulate progress for UI
    total = len(files)
    for i, f in enumerate(files):
        manager.stage_file(f)
        if i % 5 == 0:
            task['progress'] = int((i / total) * 100)
            _get_db().save_task(task_id, task)
            
    # Resolve Context
    manager.resolve_folder_context()
    
    # Save results to memory
    task['staged'] = manager  # Store the object instance in memory
    
    # Create report for UI
    report = {
        "total": manager.get_staged_count(),
        "duplicates": sum(1 for files in manager.staged_files.values() for f in files if f.is_duplicate),
        "categories": {k: len(v) for k, v in manager.staged_files.items()},
        "source": path_str
    }
    
    task['scout_report'] = report
    task['status'] = 'scouted'
    task['progress'] = 100
    _get_db().save_task(task_id, task)

@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    return _active_tasks.get(task_id) or _get_db().get_task(task_id)

@router.get("/tasks/{task_id}/plan")
def get_plan(task_id: str):
    task = _active_tasks.get(task_id)
    if not task or 'staged' not in task:
        return {"error": "Task data not found in memory"}
    
    manager = task['staged']
    dest = Path(_get_config().paths.default_output)
    
    plan = []
    # Convert staged files to UI plan items
    for entity, files in manager.staged_files.items():
        if not files: continue
        plan.append({
            "action": "CREATE",
            "label": f"Folder: {entity}",
            "count": 1
        })
        move_count = sum(1 for f in files if not f.is_duplicate)
        if move_count:
            plan.append({
                "action": "MOVE",
                "label": f"Move to {entity}",
                "count": move_count
            })
            
    return {"plan": plan, "summary": {}}

@router.post("/tasks/{task_id}/execute")
def execute(req: ExecuteRequest, background_tasks: BackgroundTasks):
    task = _active_tasks.get(req.task_id)
    task['status'] = 'running'
    task['execution_log'] = []
    
    background_tasks.add_task(_run_execute, req.task_id, req.dry_run)
    return {"status": "started"}

def _run_execute(task_id, dry_run):
    task = _active_tasks[task_id]
    manager = task['staged']
    executor = AtomicExecutor(dry_run=dry_run)
    dest_base = Path(_get_config().paths.default_output)
    
    total = manager.get_staged_count()
    done = 0
    
    for entity, files in manager.staged_files.items():
        for f in files:
            if task['status'] == 'stopped': return
            
            # Simulate work for demo smoothness
            time.sleep(0.05) 
            
            dest = dest_base / entity / f.path.name
            success = executor.safe_copy(f.path, dest)
            
            status = "SUCCESS" if success else "FAILED"
            log_entry = {
                "file": f.path.name,
                "status": status,
                "entity": entity
            }
            task['execution_log'].append(log_entry)
            
            done += 1
            task['progress'] = int((done / total) * 100)
            
    task['status'] = 'done'
    _get_db().save_task(task_id, task)

@router.get("/tasks/{task_id}/stream")
async def stream(task_id: str):
    async def event_generator():
        while True:
            task = _active_tasks.get(task_id)
            if not task: break
            
            yield f"data: {json.dumps({
                'status': task['status'],
                'progress': task['progress'],
                'recent_log': task.get('execution_log', [])[-5:]
            })}\n\n"
            
            if task['status'] in ['done', 'stopped', 'error']:
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/tasks/{task_id}/stop")
def stop(task_id: str):
    if task_id in _active_tasks:
        _active_tasks[task_id]['status'] = 'stopped'
    return {"status": "stopped"}

@router.post("/tasks/{task_id}/rollback")
def rollback(task_id: str):
    # Stub for rollback
    return {"status": "rolled_back"}