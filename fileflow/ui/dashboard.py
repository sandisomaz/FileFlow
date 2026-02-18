from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box

console = Console()

class Dashboard:
    def display_welcome(self):
        console.print(Panel.fit(
            "[bold white on red] 🏛️  FILEFLOW V8: FORENSIC DEMO MODE (READ-ONLY) 🏛️ [/bold white on red]\n[dim]Forensic Reconstruction Engine | Sandbox Environment[/dim]",
            border_style="red"
        ))

    def show_staging_preview(self, preview_data: dict):
        """
        Displays a summary of the staging area.
        """
        table = Table(title="Staging Area Preview", box=box.ASCII)
        table.add_column("Entity / Category", style="cyan")
        table.add_column("Files Found", justify="right", style="green")
        table.add_column("Duplicates", justify="right", style="yellow")
        
        total_files = 0
        total_dupes = 0
        
        for entity, file_list in preview_data.items():
            count = len(file_list)
            dupes = sum(1 for f in file_list if f['duplicate'])
            
            table.add_row(entity, str(count), str(dupes))
            total_files += count
            total_dupes += dupes
            
        console.print(table)
        console.print(f"\n[bold]Total Files:[/bold] {total_files} | [bold yellow]Duplicates:[/bold yellow] {total_dupes}\n")

    def show_pruning_report(self, empty_folders: list):
        if not empty_folders:
             return
             
        table = Table(title="Folders to be Pruned", box=box.ASCII, style="red")
        table.add_column("Empty Directory Path", style="dim")
        
        # Limit to 10 for display
        for p in empty_folders[:10]:
            table.add_row(str(p))
            
        remaining = len(empty_folders) - 10
        if remaining > 0:
            table.add_row(f"... and {remaining} more")
            
        console.print(table)
        console.print(f"[bold red]Total Empty Folders:[/bold red] {len(empty_folders)}\n")

    def confirm_execution(self) -> bool:
        from rich.prompt import Confirm
        return Confirm.ask("[bold red]Proceed with these changes?[/bold red]")
