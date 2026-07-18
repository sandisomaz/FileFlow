"""
stream_unpacker.py — The Streaming Processor
FileFlow X (V10)

This module replaces the "Batch and Wait" logic of V9.
Instead of scanning a directory, processing all files, and then returning a single Report,
this processor `yields` files as they are discovered. 

This enables the UI to populate instantly (The 10-Second Wow) and feeds the Tiered Triage Pool
(The Sniffer -> The Judge) concurrently.
"""

import logging
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Dict, Any

logger = logging.getLogger(__name__)

class StreamUnpacker:
    """
    Scans a directory and yields files immediately for processing.
    """
    
    def __init__(self, config=None):
        self.config = config
        self.supported_extensions = {'.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg'}
        
    async def stream_directory(self, root_dir: Path, processing_queue_length: callable) -> AsyncGenerator[Path, None]:
        """
        Recursively scans a directory, yielding valid files instantly.
        Implements Backpressure Management: awaits if queue > 100.
        """
        if not root_dir.exists() or not root_dir.is_dir():
            logger.error(f"[StreamUnpacker] Invalid root directory: {root_dir}")
            return

        # Stack-based traversal to avoid deep recursion limits
        stack = [root_dir]
        
        while stack:
            # Check BACKPRESSURE
            current_q_len = processing_queue_length()
            if current_q_len > 100:
                logger.warning(f"[StreamUnpacker] BACKPRESSURE ACTIVE: Queue at {current_q_len}. Yielding to event loop...")
                await asyncio.sleep(0.5)
                continue

            current_dir = stack.pop()
            try:
                for entry in current_dir.iterdir():
                    if entry.is_symlink():
                        continue 
                        
                    if entry.is_dir():
                        if not entry.name.startswith('.') and "Windows" not in entry.parts:
                            stack.append(entry)
                    elif entry.is_file():
                        if entry.suffix.lower() in self.supported_extensions:
                            yield entry
                            # Yield control occasionally even under limit
                            await asyncio.sleep(0)
            except PermissionError:
                logger.warning(f"[StreamUnpacker] Permission denied accessing {current_dir}")
            except Exception as e:
                logger.error(f"[StreamUnpacker] Error reading {current_dir}: {e}")

    async def process_stream(self, root_dir: Path, sniffer_module=None, get_queue_len=lambda: 0) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Consumes the raw file stream, runs Level 1 Triage (Sniffer), and yields the result.
        Passes the queue_length checker to the internal directory streamer.
        """
        async for file_path in self.stream_directory(root_dir, get_queue_len):
            event = {
                "file_path": str(file_path),
                "filename": file_path.name,
                "status": "discovered",
                "sniff_result": None
            }
            
            if sniffer_module:
                # Assuming sniffer.sniff(file_path) returns a SniffResult
                try:
                    result = sniffer_module.sniff(file_path)
                    event["status"] = "triaged"
                    event["sniff_result"] = {
                        "confidence": getattr(result, "confidence", 0.0),
                        "category": getattr(result, "category", "Unknown"),
                        "sub_type": getattr(result, "sub_type", "Document"),
                        "facts": getattr(result, "facts", {})
                    }
                    if event["sniff_result"]["confidence"] >= 0.8:
                        event["action"] = "bypass_judge"
                    else:
                        event["action"] = "escalate_to_judge"
                except Exception as e:
                    logger.error(f"Sniffer failed on {file_path.name}: {e}")
                    event["action"] = "escalate_to_judge"
            else:
                event["action"] = "escalate_to_judge"
                
            yield event
