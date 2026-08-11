"""
triage_pool.py — Tiered Triage Pool (Module 3)
FileFlow X (V10)

Handles the intelligent routing of files discovered by the StreamUnpacker.
1. Tier 1 (Sniffer - Regex/Heuristics)
2. Tier 2 (Judge - Local LLM/Ministral)
3. Tier 3 (Eye - Vision/OCR)
"""

import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator

logger = logging.getLogger(__name__)

class TriagePool:
    def __init__(self, sniffer=None, judge=None, eye=None):
        self.sniffer = sniffer
        self.judge = judge
        self.eye = eye
        self.queue = asyncio.Queue()
        self.active_workers = 3 # Default workers
    
    def get_queue_length(self) -> int:
        """Used by the StreamUnpacker to trigger Backpressure."""
        return self.queue.qsize()

    async def ingest_stream(self, stream_generator):
        """Asynchronously pulls from the StreamUnpacker and adds to the Triage Queue."""
        async for item in stream_generator:
            await self.queue.put(item)
            logger.debug(f"[TriagePool] Ingested {item.name}. Queue: {self.queue.qsize()}")

    async def _worker(self, worker_id: int, results_queue: asyncio.Queue):
        """Processes items from the queue through the Tiers."""
        while True:
            file_path = await self.queue.get()
            event = {
                "file_path": str(file_path),
                "filename": file_path.name,
                "status": "processing",
                "tier_used": None,
                "extract": {}
            }
            
            try:
                # ------ TIER 1: The Sniffer ------
                if self.sniffer:
                    # In a real impl, we'd extract some text first depending on file size/type
                    # For V10 MVP, we let Sniffer check filename and basic metadata
                    sniff_result = self.sniffer.sniff(file_path, extracted_text="") 
                    if sniff_result.confidence >= 0.8:
                        event["status"] = "triaged"
                        event["tier_used"] = "Sniffer"
                        event["extract"] = {
                            "confidence": sniff_result.confidence,
                            "category": sniff_result.category,
                            "sub_type": sniff_result.sub_type,
                            "facts": sniff_result.facts
                        }
                        await results_queue.put(event)
                        self.queue.task_done()
                        continue
                
                # ------ TIER 3: The Eye (Pre-check for empty text) ------
                # If we had a fast way to check if it's purely an image/scanned PDF without text
                empty_text = False # Placeholder logic for "0 characters extracted"
                if empty_text and self.eye:
                    logger.info(f"[{file_path.name}] Sent to Tier 3 (Eye)")
                    # eye_result = await self.eye.process(file_path)
                    pass

                # ------ TIER 2: The Judge ------
                if self.judge:
                    event["status"] = "triaged"
                    event["tier_used"] = "Judge"
                    # Mocking Judge call for architectural structure
                    # result = await asyncio.to_thread(self.judge.ruling, extracted_content)
                    event["extract"] = {"category": "Unknown", "sub_type": "Document", "confidence": 0.5}
                else:
                    event["status"] = "failed"
                    event["error"] = "No suitable Tier found to process file."

            except Exception as e:
                logger.error(f"[TriageWorker-{worker_id}] Error on {file_path.name}: {e}")
                event["status"] = "error"
                event["error"] = str(e)
            
            await results_queue.put(event)
            self.queue.task_done()

    async def process_queue(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the workers and yields finished events."""
        results_queue = asyncio.Queue()
        
        # Start workers
        workers = [
            asyncio.create_task(self._worker(i, results_queue))
            for i in range(self.active_workers)
        ]
        
        # Wait for the main queue to finish processing
        # We need a way to know when streaming is done AND queue is empty.
        # For this prototype, we'll yield as results come in.
        
        # In a robust implementation, this would loop until the stream signals EOF 
        # AND queue.empty().
        while True:
            # Non-blocking check or await with timeout
            try:
                result = await asyncio.wait_for(results_queue.get(), timeout=1.0)
                yield result
                results_queue.task_done()
            except asyncio.TimeoutError:
                # Check if workers are idle and main queue is empty
                if self.queue.empty():
                    break
        
        # Cancel workers once done
        for w in workers:
            w.cancel()