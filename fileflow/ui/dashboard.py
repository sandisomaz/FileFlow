from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box

console = Console()

class Dashboard:
    def display_welcome(self):
        console.print(Panel.fit(
            "[bold white on dark_red] 🏛️  FILEFLOW COGNITION V9 🏛️ [/bold white on dark_red]\n[dim]Forensic Reconstruction Engine + AI Brain | Sandbox Environment[/dim]",
            border_style="dark_red"
        ))

    def show_staging_preview(self, preview_data: dict):
        """
        Displays a summary of the staging area.
        V9: Shows AI category badge and summary if available.
        """
        table = Table(title="Staging Area Preview", box=box.ASCII)
        table.add_column("Entity / Category", style="cyan")
        table.add_column("AI Category", style="magenta")
        table.add_column("Files", justify="right", style="green")
        table.add_column("Dupes", justify="right", style="yellow")
        table.add_column("AI Summary (sample)", style="dim", no_wrap=False, max_width=45)

        total_files = 0
        total_dupes = 0

        for entity, file_list in preview_data.items():
            count = len(file_list)
            dupes = sum(1 for f in file_list if f.get('duplicate'))

            # V9: Pull AI category and summary from first file that has them
            ai_category = ""
            sample_summary = ""
            for f in file_list:
                meta = f.get('metadata', {}) if isinstance(f, dict) else {}
                if meta.get('ai_category'):
                    ai_category = meta['ai_category']
                if meta.get('ai_summary'):
                    sample_summary = meta['ai_summary'][:80]
                if ai_category and sample_summary:
                    break

            # Colour-code the AI category
            cat_colour = {
                "Professional": "green",
                "Education": "blue",
                "Development": "cyan",
                "Life_Admin": "yellow",
                "Waste": "red",
                "Unknown": "dim",
            }.get(ai_category, "dim")

            ai_badge = f"[{cat_colour}]{ai_category}[/{cat_colour}]" if ai_category else "[dim]—[/dim]"

            table.add_row(entity, ai_badge, str(count), str(dupes), sample_summary or "—")
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

    def show_search_results(self, formatted_output: str):
        """Displays semantic search results in a panel."""
        console.print(Panel(
            formatted_output,
            title="[bold cyan]🔍 Semantic Search Results[/bold cyan]",
            border_style="cyan",
        ))

    def confirm_execution(self) -> bool:
        from rich.prompt import Confirm
        return Confirm.ask("[bold red]Proceed with these changes?[/bold red]")

