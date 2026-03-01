"""
ThinkingApp — The Glass Box Interface for FileFlow V9
Interactive "Colleague" Mode
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Static, Log, Button, Label, Markdown
from textual import work
from textual.message import Message

# Import Core Systems
from fileflow.core.config import ConfigLoader
from fileflow.core.scanner import DeepScanner
from fileflow.staging.manager import StagingManager
from fileflow.intelligence.extractor import UnifiedExtractor
from fileflow.intelligence.judge import Judge
from fileflow.intelligence.bridge import Bridge


class SuggestionCard(Static):
    """
    An interactive card representing a single file move suggestion.
    Mirrors the 'Intelligent File Suggestion' UI pattern.
    """
    
    class Approved(Message):
        """Emitted when user approves the suggestion."""
        def __init__(self, card):
            self.card = card
            super().__init__()

    class Dismissed(Message):
        """Emitted when user dismisses the suggestion."""
        def __init__(self, card):
            self.card = card
            super().__init__()

    def __init__(
        self, 
        file_path: Path, 
        category: str, 
        entity: str, 
        reasoning: str,
        confidence: float,
        target_path: Optional[Path] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.file_path = file_path
        self.category = category
        self.entity = entity
        self.reasoning = reasoning
        self.confidence = confidence
        self.target_path = target_path

    def compose(self) -> ComposeResult:
        # Determine icon/color based on category
        icon = "📄"
        color = "cyan"
        if self.category == "Professional": 
            icon = "💼"
            color = "green"
        elif self.category == "Education": 
            icon = "🎓"
            color = "blue"
        elif self.category == "Waste": 
            icon = "🗑️"
            color = "red"
        
        with Vertical(classes="card-container"):
            # Header
            with Horizontal(classes="card-header"):
                yield Label(f"{icon} {self.file_path.name}", classes=f"card-title text-{color}")
                yield Label(f"{int(self.confidence * 100)}%", classes="card-conf")

            # Body (The Reasoning)
            yield Label(f"Move to: {self.entity}", classes="card-action")
            yield Label(f"Why: {self.reasoning}", classes="card-reason")

            # Actions
            with Horizontal(classes="card-buttons"):
                yield Button("Approve", variant="success", id="btn_approve", classes="action-btn")
                yield Button("Dismiss", variant="error", id="btn_dismiss", classes="action-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_approve":
            self.post_message(self.Approved(self))
        elif event.button.id == "btn_dismiss":
            self.post_message(self.Dismissed(self))


class ThinkingApp(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 2fr 1fr;
        background: #0f171f;
    }

    /* Left Pane: The Stream of Suggestions */
    #suggestion_stream {
        height: 100%;
        border-right: solid #1e293b;
        background: #0f171f;
        padding: 1;
        scrollbar-gutter: stable;
    }

    /* Right Pane: Stats & Log */
    #sidebar {
        height: 100%;
        background: #0d1117;
        padding: 1;
    }

    /* Card Styling - Glassmorphism attempt in TUI */
    .card-container {
        background: #1e293b;
        border: solid #334155;
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border-radius: 1; /* Textual support usually limited here in terminal */
    }

    .card-header {
        height: 1;
        justify-content: space-between;
        margin-bottom: 1;
    }

    .card-title {
        text-style: bold;
    }
    
    .text-green { color: #4ade80; }
    .text-blue { color: #60a5fa; }
    .text-red { color: #f87171; }
    .text-cyan { color: #22d3ee; }

    .card-action {
        color: white;
        text-style: bold;
    }

    .card-reason {
        color: #94a3b8;
        padding-bottom: 1;
    }

    .card-buttons {
        height: 3;
        align: right middle;
    }

    .action-btn {
        margin-left: 1;
    }
    
    #log_view {
        height: 1fr;
        border-top: solid #334155;
    }
    """

    def __init__(self, source_paths: list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_paths = source_paths
        self.approved_moves = []
        self.files_scanned = 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="suggestion_stream"):
            yield Label("[bold white]Intelligent Suggestions[/bold white]", classes="pane-header")
            # Cards will be added here dynamically

        with Vertical(id="sidebar"):
            yield Label("[bold white]System Status[/bold white]")
            yield Label("Initializing...", id="status_label")
            yield Log(id="log_view", highlight=True, markup=True)

    def on_mount(self) -> None:
        self.run_scan_thread()

    def on_suggestion_card_approved(self, message: SuggestionCard.Approved):
        card = message.card
        self.approved_moves.append((card.file_path, card.target_path))
        self.log_msg(f"[green]✓ Approved:[/green] {card.file_path.name}")
        card.remove()

    def on_suggestion_card_dismissed(self, message: SuggestionCard.Dismissed):
        card = message.card
        self.log_msg(f"[red]✗ Dismissed:[/red] {card.file_path.name}")
        card.remove()

    def log_msg(self, text: str):
        self.query_one(Log).write_line(text)

    @work(thread=True)
    def run_scan_thread(self):
        self.call_from_thread(self.log_msg, "Initializing AI Stack...")
        
        # Initialize Core
        config = ConfigLoader()
        extractor = UnifiedExtractor()
        bridge = Bridge()
        judge = Judge(bridge=bridge, extractor=extractor)
        staging = StagingManager(extractor, judge=judge)
        scanner = DeepScanner(config)

        if bridge.is_healthy():
            self.call_from_thread(self.query_one("#status_label", Label).update, f"Brain: {bridge.slm_model}")
        else:
            self.call_from_thread(self.query_one("#status_label", Label).update, "Brain: V8 Fallback Mode")

        for source in self.source_paths:
            path_obj = Path(source)
            if not path_obj.exists(): continue
            
            for file_path in scanner.scan(path_obj):
                self.files_scanned += 1
                
                # Simulate analysis delay for "Thinking" effect if using V8 only
                # if not bridge.is_healthy(): time.sleep(0.1)

                try:
                    # 1. Stage & Judge
                    staging.stage_file(file_path)
                    
                    # 2. Retrieve Ruling
                    # (In a real refactor, staging_manager would return the StagedFile directly)
                    found_staged = None
                    for ent, files in staging.staged_files.items():
                        if files and files[-1].path == file_path:
                            found_staged = files[-1]
                            break
                    
                    if found_staged:
                        cat = found_staged.metadata.get('ai_category', 'Unknown')
                        conf = found_staged.metadata.get('ai_confidence', 0.6)
                        reason = found_staged.metadata.get('ai_reasoning', 'Pattern Match')
                        ent = found_staged.metadata.get('entity', 'Unclassified')
                        
                        # Strip standard log noise from reason if it's too long
                        if len(reason) > 100: reason = reason[:97] + "..."

                        # 3. Create Card interaction on UI thread
                        self.call_from_thread(
                            self.add_suggestion,
                            file_path, cat, ent, reason, conf
                        )
                        
                except Exception as e:
                    self.call_from_thread(self.log_msg, f"[red]Error analyzing {file_path.name}: {e}[/red]")

    def add_suggestion(self, file_path, category, entity, reasoning, confidence):
        container = self.query_one("#suggestion_stream")
        card = SuggestionCard(
            file_path=file_path,
            category=category,
            entity=entity,
            reasoning=reasoning,
            confidence=confidence
        )
        container.mount(card)
        card.scroll_visible()


if __name__ == "__main__":
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["C:/Users/sandi/Desktop/FileFlow/test_run_folder"]
    app = ThinkingApp(paths)
    app.run()
