from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, DirectoryTree, DataTable, Button, Label, RichLog, Static
from textual.binding import Binding
from textual import on
from pathlib import Path
import os
from fileflow.core.scanner import Scanner
from fileflow.core.organizer import Organizer, MoveLogger

class FileFlowApp(App):
    CSS = """
    Screen {
        layout: horizontal;
    }
    #sidebar {
        width: 30%;
        height: 100%;
        dock: left;
        border-right: solid green;
    }
    #main {
        width: 70%;
        height: 100%;
        padding: 1;
    }
    #actions {
        height: auto;
        dock: bottom;
        padding: 1;
        background: $boost;
    }
    DataTable {
        height: 1fr;
        border: solid cyan;
    }
    RichLog {
        height: 20%;
        border-top: solid yellow;
        background: $surface;
    }
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "scan", "Scan Selected"),
        Binding("o", "organize", "Organize"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="sidebar"):
            yield Label("📁 Select Folder to Scan:")
            yield DirectoryTree(os.path.expanduser("~\\Desktop"))
        
        with Vertical(id="main"):
            yield Label("📄 Scanned Files")
            yield DataTable(id="results_table")
            yield RichLog(id="log", highlight=True, markup=True)
            
            with Horizontal(id="actions"):
                yield Button("🔍 Scan Selected", id="btn_scan", variant="primary")
                yield Button("🚀 Organize Files", id="btn_organize", variant="success", disabled=True)
                yield Button("↩️ Undo Last", id="btn_undo", variant="warning")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Filename", "Detected Position", "Applicant", "Date", "Path")
        self.scanned_files = []
        self.selected_path = Path(os.path.expanduser("~\\Desktop"))

    @on(DirectoryTree.DirectorySelected)
    def handle_dir_select(self, event: DirectoryTree.DirectorySelected):
        self.selected_path = event.path
        self.query_one(RichLog).write(f"[cyan]Selected: {self.selected_path}[/cyan]")

    @on(Button.Pressed, "#btn_scan")
    def action_scan(self):
        log = self.query_one(RichLog)
        table = self.query_one(DataTable)
        
        if not self.selected_path or not self.selected_path.exists():
            log.write("[red]Invalid folder selected![/red]")
            return

        log.write(f"[bold green]Scanning {self.selected_path}...[/bold green]")
        table.clear()
        self.scanned_files = []
        
        # Run scan (synchronous for now, could be threaded)
        results = Scanner.scan_directory(self.selected_path, recursive=True)
        
        count = 0
        for folder, files in results.items():
            for f in files:
                meta = f['metadata']
                table.add_row(
                    f['name'],
                    meta.get('position', '?'),
                    meta.get('applicant', '?'),
                    f['date'].strftime("%Y-%m-%d"),
                    f['path']
                )
                self.scanned_files.append(f)
                count += 1
        
        log.write(f"[green]Found {count} files.[/green]")
        if count > 0:
            self.query_one("#btn_organize").disabled = False

    @on(Button.Pressed, "#btn_organize")
    def action_organize(self):
        log = self.query_one(RichLog)
        if not self.scanned_files:
            log.write("[yellow]No files to organize.[/yellow]")
            return

        dest_base = self.selected_path / "_Organized_Output"
        log.write(f"[bold yellow]Organizing to {dest_base}...[/bold yellow]")
        
        success_count = 0
        for f in self.scanned_files:
            success, msg = Organizer.organize_file(f, dest_base, dry_run=False)
            if success:
                success_count += 1
                # log.write(f"[dim]Moved {f['name']}[/dim]")
            else:
                log.write(f"[red]Failed {f['name']}: {msg}[/red]")
        
        log.write(f"[bold green]Done! Organized {success_count} files.[/bold green]")
        self.query_one("#btn_organize").disabled = True
        self.scanned_files = [] # Clear after organize
        self.query_one(DataTable).clear()

    @on(Button.Pressed, "#btn_undo")
    def action_undo(self):
        log = self.query_one(RichLog)
        success, msg = MoveLogger.undo_last_move()
        if success:
            log.write(f"[green]Undo: {msg}[/green]")
        else:
            log.write(f"[red]Undo Failed: {msg}[/red]")

if __name__ == "__main__":
    app = FileFlowApp()
    app.run()
