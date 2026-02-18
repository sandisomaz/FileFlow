#!/usr/bin/env python3
"""
FileFlow V8 - Production-Ready Forensic File Organizer
Main entry point with full pipeline execution.
"""

import argparse
import sys
import os
import io
from pathlib import Path

# Force UTF-8 for Windows console/redirection
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeRemainingColumn, TextColumn, BarColumn
from rich import print as rprint

# V8 Imports - All using new package structure
from fileflow.core.config import ConfigLoader
from fileflow.core.scanner import DeepScanner
from fileflow.intelligence.extractor import UnifiedExtractor
from fileflow.staging.manager import StagingManager
from fileflow.operations.executor import AtomicExecutor
from fileflow.operations.janitor import PruneExecutor
from fileflow.ui.dashboard import Dashboard

# V9 Cognition Imports
from fileflow.intelligence.bridge import Bridge
from fileflow.intelligence.judge import Judge

from fileflow.core.logger import SessionLogger, MigrationLogger, setup_forensic_logging

# Configure System Logging (Silence Terminal)
setup_forensic_logging()
console = Console()


def main():
    """Main execution pipeline."""
    parser = argparse.ArgumentParser(
        description="FileFlow V8 - Forensic File Organizer"
    )
    parser.add_argument("sources", nargs='*', help="Source directories to scan")
    parser.add_argument("--dest", help="Destination archive directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without moving files (safe preview)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the move (overrides dry-run default)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--rollback",
        type=str,
        help="Rollback a previous run (provide manifest path)"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Level 2 Forensic Diagnostic: Read-only deep audit of file metadata."
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Disable AI Judge (run in pure V8 rule-based mode)"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run model benchmark and exit"
    )
    
    args = parser.parse_args()
    
    # Initialize Audit Logger
    audit_logger = MigrationLogger()
    
    # Session Logging Layer
    from fileflow.core.logger import SessionLogger
    with SessionLogger() as logger:
        # Handle rollback mode
        if args.rollback:
            execute_rollback(args.rollback, force=args.force)
            return
            
        if not args.sources or (not args.audit and not args.rollback and not args.dest):
            parser.print_help()
            sys.exit(1)
        
        # Determine execution mode
        is_dry_run = not args.execute
        if args.dry_run or args.audit:
            is_dry_run = True
        
        # Handle benchmark mode
        if args.benchmark:
            from fileflow.intelligence.benchmark import Benchmark
            bench = Benchmark()
            console.print("\n[bold cyan]📊 Running Classification Benchmark...[/bold cyan]")
            report = bench.run_classification()
            console.print(f"\n[bold green]🏆 Winner: {report.winner}[/bold green]")
            console.print(f"[cyan]{report.recommendation}[/cyan]")
            bench.save_report(report)
            return

        # 1. Initialize Components
        dashboard = Dashboard()
        dashboard.display_welcome()
        
        config = ConfigLoader()
        extractor = UnifiedExtractor()

        # V9 Cognition: Initialise the Bridge and Judge
        judge = None
        if not args.no_ai:
            bridge = Bridge(
                slm_model="qwen2.5:1.5b",
                embed_model="nomic-embed-text",
            )
            if bridge.is_healthy():
                judge = Judge(bridge=bridge, extractor=extractor)
                console.print("[bold green]🧠 Cognition ONLINE[/bold green] — AI Judge active")
            else:
                console.print("[yellow]⚡ Cognition OFFLINE[/yellow] — Running in V8 rule-based mode")
        else:
            console.print("[dim]AI disabled (--no-ai flag)[/dim]")

        staging = StagingManager(extractor, judge=judge)
        executor = AtomicExecutor(dry_run=is_dry_run)
        
        source_paths = [Path(s).resolve() for s in args.sources]
        dest_path = Path(args.dest).resolve() if args.dest else None
        
        # Initialize Scanner with destination ignore logic
        scanner = DeepScanner(config, ignore_paths=[dest_path] if dest_path else [])
        
        for sp in source_paths:
            if not sp.exists():
                console.print(f"[bold red]❌ Source path does not exist: {sp}[/bold red]")
                sys.exit(1)
        
        # 2. Deep Scan
        console.print(f"\n[bold green]Phase 2: Deep Scan[/bold green]")
        
        file_list = []
        from fileflow.intelligence.diagnostic import DiagnosticService
        diag_service = DiagnosticService() if args.audit else None
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Scanning for files...[/bold cyan]"),
            BarColumn(bar_width=40),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("Scanning...", total=None)
            for sp in source_paths:
                progress.update(task, description=f"Scanning: {sp.name}")
                for file_path in scanner.scan(sp):
                    file_list.append(file_path)
                    if diag_service:
                        diag_service.analyze_file(file_path)
                    progress.update(task, description=f"Found: {len(file_list)} files")
        
        console.print(f"[green]DONE Scan Complete: {len(file_list)} files found[/green]")
        
        # Branch for Level 2 Diagnostic
        if args.audit:
            execute_audit_mode(diag_service)
            return

        # 3. Staging and Analysis
        console.print(f"\n[bold green]Phase 3: Deep Analysis & Staging[/bold green]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
            transient=True
        ) as progress:
            analyze_task = progress.add_task("Analyzing files...", total=len(file_list))
            for file_path in file_list:
                progress.update(analyze_task, description=f"Analyzing: {file_path.name[:60]}...")
                try:
                    staging.stage_file(file_path)
                except (RecursionError, Exception) as e:
                     audit_logger.log(
                        original=file_path,
                        entity="CRIT_FAILURE",
                        subtype="Recursion/Crash",
                        md5="N/A",
                        status="SKIPPED",
                        notes=f"Staging Crashed: {str(e)[:100]}"
                    )
                progress.advance(analyze_task)
            
            
        # 3b. Context Propagation (The Demo Polish)
        console.print(f"\n[bold cyan]Phase 3b: Context Propagation (Demo Polish)[/bold cyan]")
        staging.resolve_folder_context()

        # 4. Staging Preview & Cleanup Plan
        console.print(f"\n[bold green]Phase 4: Optimization Analysis[/bold green]")
        dashboard.show_staging_preview(staging.get_preview())
        
        janitor = PruneExecutor(dry_run=is_dry_run)
        all_prune_candidates = []
        for sp in source_paths:
            all_prune_candidates.extend(janitor.get_prune_candidates(sp))
            
        if all_prune_candidates:
             dashboard.show_pruning_report(all_prune_candidates)
    
        # 5. Forensic Manifest Generation
        manifest_path = dest_path / config.system.forensic_manifest_name if dest_path else None
        if manifest_path:
            try:
                if not dest_path.exists():
                    dest_path.mkdir(parents=True, exist_ok=True)
                staging.export_manifest(manifest_path)
                console.print(f"[cyan]Forensic Manifest prepared: {manifest_path}[/cyan]")
            except Exception as e:
                console.print(f"[red]WARNING: Could not save manifest: {e}[/red]")
    
        # 6. Execution Confirmation
        if is_dry_run:
            console.print(f"\n[bold yellow][!] SIMULATION MODE (DRY RUN)[/bold yellow]")
            console.print("No files will be moved. Run with [bold]--execute[/bold] to apply changes.")
        else:
            if args.force:
                console.print("[bold red]Force Execution Enabled. Skipping confirmation.[/bold red]")
            elif not dashboard.confirm_execution():
                console.print("[red]Operation Cancelled[/red]")
                sys.exit(0)
        
        # 7. Atomic Execution
        console.print(f"\n[bold green]Phase 5: Atomic Execution[/bold green]")
        from fileflow.operations.versioning import Versioning
        
        moved_count = 0
        total_staged = staging.get_staged_count()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]{task.description}[/bold green]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            exec_task = progress.add_task("Moving/Copying files...", total=total_staged)
            
            for entity, files in staging.staged_files.items():
                entity_folder = dest_path / entity if dest_path else None
                
                # Group by SubType for per-type versioning
                by_subtype = {}
                for f in files:
                    sub_type = f.metadata.get('sub_type', 'Document')
                    if sub_type not in by_subtype:
                        by_subtype[sub_type] = []
                    by_subtype[sub_type].append(f)
                    
                for sub_type, subtype_files in by_subtype.items():
                    # CRITICAL: CHRONOLOGICAL SORTING
                    try:
                        sorted_files = sorted(subtype_files, key=lambda x: x.path.stat().st_mtime)
                    except OSError:
                        sorted_files = subtype_files
                        
                    for index, staged_file in enumerate(sorted_files, start=1):
                        if staged_file.metadata.get('needs_quarantine'):
                            # Redirect corrupted files to Quarantine
                            q_reason = staged_file.metadata.get('quarantine_reason', 'Unknown').split(':')[0].strip()[:30].replace(' ', '_')
                            target_path = dest_path / "_Quarantine" / q_reason / staged_file.path.name if dest_path else None
                            new_name = f"[QUARANTINE] {staged_file.path.name}"
                        else:
                            new_name = Versioning.generate_name(
                                entity=entity,
                                original_path=staged_file.path,
                                index=index,
                                metadata=staged_file.metadata,
                                is_duplicate=staged_file.is_duplicate,
                                duplicate_hash=staged_file.hash_digest
                            )
                            target_path = entity_folder / new_name if entity_folder else None
                        
                        progress.update(exec_task, description=f"Processing: {new_name[:40]}")
                        
                        success = False
                        status = "SKIPPED"
                        
                        if is_dry_run:
                            success = True
                            status = "DRY_Run"
                            if staged_file.metadata.get('needs_quarantine'):
                                status = "DRY_Quarantine"
                        elif target_path:
                            if executor.safe_copy(staged_file.path, target_path):
                                success = True
                                status = "QUARANTINED" if staged_file.metadata.get('needs_quarantine') else "SUCCESS"
                            else:
                                status = "FAILED"
                        
                        if success:
                            moved_count += 1
                            
                        audit_logger.log(
                            original=staged_file.path,
                            entity=entity,
                            subtype=sub_type,
                            md5=staged_file.hash_digest,
                            status=status,
                            notes=staged_file.metadata.get('quarantine_reason', '')
                        )
                        
                        progress.advance(exec_task)
    
    console.print(f"\n[bold green]DONE Execution Complete[/bold green]")
    console.print(f"Files Processed: {moved_count}/{total_staged}")
    
    # Summary Report (Level 2 Discovery)
    entity_counts = {"Job Packets": 0, "Projects": 0, "Educational": 0, "Other": 0}
    for entity, files in staging.staged_files.items():
        if not files: continue
        sample_file = files[0]
        sub_type = sample_file.metadata.get('sub_type', '')
        file_type = sample_file.metadata.get('type', '')
        
        if file_type in ['job_packet', 'firm_application']:
            entity_counts["Job Packets"] += 1
        elif "Project_" in entity or sub_type == "ProjectFile":
            entity_counts["Projects"] += 1
        elif entity == "Educational_Materials":
            entity_counts["Educational"] += 1
        else:
            entity_counts["Other"] += 1

    console.print("\n[bold cyan]--- PHASE 2 DISCOVERY REPORT ---[/bold cyan]")
    from rich.table import Table
    from rich import box
    table = Table(title="Content Classification Summary", box=box.ASCII)
    table.add_column("Category", style="cyan")
    table.add_column("Count", style="white")
    for cat, count in entity_counts.items():
        table.add_row(cat, str(count))
    console.print(table)

    # 8. Cleanup (Janitor)
    if not is_dry_run and not args.force:
        from rich.prompt import Confirm
        if Confirm.ask("\n[bold red]🧹 Run cleanup (delete sources & empty folders)? [/bold red]"):
            report = janitor.purge_from_manifest(manifest_path)
            console.print(f"\n[bold]Janitor Purge Report:[/bold]")
            console.print(f"  Files Deleted: {report['deleted']}")
            console.print(f"  Space Reclaimed: {report['space_reclaimed_bytes']/1024/1024:.2f} MB")
            for sp in source_paths:
                pruned = janitor.execute_prune(sp)
                console.print(f"  Empty Folders Removed ({sp.name}): {pruned}")
    elif not is_dry_run and args.force:
         # In force mode, we just do it
         janitor.purge_from_manifest(manifest_path)
         for sp in source_paths:
            janitor.execute_prune(sp)

def execute_audit_mode(diag_service):
    """
    Generates and saves the Level 2 Forensic Diagnostic report.
    """
    console.print("\n[bold green]Phase 3: Generating Forensic Audit Report[/bold green]")
    
    # Ensure reports directory exists
    report_dir = Path("reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"discovery_audit_{timestamp}.txt"
    
    diag_service.export_text_report(report_path)
    
    # Display summary to console
    data = diag_service.get_report()
    
    from rich.table import Table
    from rich import box
    
    # Extension Table
    ext_table = Table(title="Extension Breakdown (Top 10)", box=box.ASCII)
    ext_table.add_column("Extension", style="cyan")
    ext_table.add_column("Count", style="white")
    for ext, count in data['top_extensions']:
        ext_table.add_row(ext, str(count))
    console.print(ext_table)
    
    # Folder Density Table
    folder_table = Table(title="Top 5 Heaviest Folders", box=box.ASCII)
    folder_table.add_column("Folder Path", style="dim")
    folder_table.add_column("Files", style="white")
    for folder, count in data['top_folders'][:5]:
        folder_table.add_row(folder, str(count))
    console.print(folder_table)
    
    # Anomaly Alert
    if data['anomalies']:
        console.print(f"\n[bold red]⚠️  ANOMALY ALERT: {len(data['anomalies'])} large files found (>50MB)[/bold red]")
        for item in data['anomalies'][:3]:
             console.print(f"  - [{item['size_mb']} MB] {item['path']}")
    
    # Complexity Alert
    if data['deep_path_count'] > 0:
        console.print(f"\n[bold yellow]⚠️  COMPLEXITY ALERT: {data['deep_path_count']} long/deep paths detected[/bold yellow]")
        
    console.print(f"\n[bold green]✅ Audit Complete. Report saved to: {report_path}[/bold green]")


def execute_rollback(manifest_path_str: str, force: bool = False):
    console.print(f"\n[bold yellow]⚠️ ROLLBACK MODE[/bold yellow]")
    manifest_path = Path(manifest_path_str)
    if not manifest_path.exists():
        console.print(f"[red]❌ Manifest not found: {manifest_path}[/red]")
        sys.exit(1)
    
    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Restore files from {manifest_path.parent.name}?"):
            return
        
    janitor = PruneExecutor(dry_run=False)
    report = janitor.rollback_run(manifest_path)
    console.print(f"\n[bold]Rollback Summary:[/bold]")
    console.print(f"  Files Restored: {report['restored']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]FATA ERROR:[/bold red] {e}")
        sys.exit(1)


