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
from rich.panel import Panel
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
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Embed all documents in source folders into the semantic memory index"
    )
    parser.add_argument(
        "--search",
        type=str,
        metavar="QUERY",
        help="Search your indexed files with a natural language query"
    )
    parser.add_argument(
        "--flatten",
        action="store_true",
        help="Flatten deeply nested folders into a staging area (max depth: 2)"
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Apply smart AI-powered renaming to staged files"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch source folders for new files and auto-process them in real time"
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
            
        if not args.sources or (not args.audit and not args.rollback and not args.dest
                                 and not args.embed and not args.search and not args.benchmark
                                 and not args.flatten and not args.watch):
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
            console.print("\n[bold cyan]\U0001f4ca Running Classification Benchmark...[/bold cyan]")
            report = bench.run_classification()
            console.print(f"\n[bold green]\U0001f3c6 Winner: {report.winner}[/bold green]")
            console.print(f"[cyan]{report.recommendation}[/cyan]")
            bench.save_report(report)
            return

        # Handle search mode (--search "query")
        if args.search:
            from fileflow.intelligence.bridge import Bridge
            from fileflow.intelligence.memory import Memory
            from fileflow.intelligence.discovery import Discovery
            bridge = Bridge()
            if not bridge.is_healthy():
                console.print("[bold red]\u26a0 Ollama is offline. Cannot perform semantic search.[/bold red]")
                console.print("[dim]Start Ollama with: ollama serve[/dim]")
                return
            memory = Memory(db_path="fileflow_data/vectors.lance", bridge=bridge)
            discovery = Discovery(bridge=bridge, memory=memory)
            stats = discovery.stats()
            if stats.get("total_records", 0) == 0:
                console.print("[yellow]\u26a1 Memory index is empty. Run --embed first to index your files.[/yellow]")
                return
            results = discovery.search(args.search, top_k=10)
            dashboard = Dashboard()
            dashboard.show_search_results(discovery.format_results(results, query=args.search))
            return

        # Handle embed mode (--embed)
        if args.embed:
            from fileflow.intelligence.bridge import Bridge
            from fileflow.intelligence.memory import Memory
            from fileflow.intelligence.inspector import Inspector
            from fileflow.intelligence.extractor import UnifiedExtractor
            from fileflow.core.scanner import DeepScanner
            bridge = Bridge()
            if not bridge.is_healthy():
                console.print("[bold red]\u26a0 Ollama is offline. Cannot embed documents.[/bold red]")
                console.print("[dim]Start Ollama with: ollama serve[/dim]")
                return
            memory = Memory(db_path="fileflow_data/vectors.lance", bridge=bridge)
            inspector = Inspector(bridge=bridge, memory=memory)
            extractor = UnifiedExtractor()
            scanner = DeepScanner()
            source_paths = [Path(s).resolve() for s in args.sources]
            console.print(f"[bold cyan]\U0001f9e0 Embedding documents from {len(source_paths)} source(s)...[/bold cyan]")
            total_embedded = 0
            total_skipped = 0
            for source in source_paths:
                files = scanner.scan(source)
                console.print(f"  Found {len(files)} files in {source.name}")
                for fp in files:
                    try:
                        text = ""
                        if fp.suffix.lower() == ".pdf":
                            from fileflow.staging.manager import StagingManager
                            sm = StagingManager(extractor)
                            text = sm._safe_extract(fp) or ""
                        meta = extractor.extract_metadata(text, file_path=fp)
                        result = inspector.inspect(
                            file_path=fp,
                            text=text,
                            category=meta.get("ai_category", "Unknown"),
                            sub_type=extractor.classify_sub_type(fp, text),
                            entity=meta.get("entity", ""),
                        )
                        if result.embedded:
                            total_embedded += 1
                        else:
                            total_skipped += 1
                    except Exception as e:
                        logger.warning(f"Embed failed for {fp.name}: {e}")
                        total_skipped += 1
            console.print(f"\n[bold green]\u2705 Embedded: {total_embedded} | Skipped (unchanged): {total_skipped}[/bold green]")
            console.print(f"[dim]Index stored at: fileflow_data/vectors.lance[/dim]")
            return

        # Handle flatten mode (--flatten)
        if args.flatten:
            from fileflow.operations.unpacker import Unpacker
            from fileflow.operations.executor import AtomicExecutor as _Executor
            source_paths = [Path(s).resolve() for s in args.sources]
            staging = Path(args.dest).resolve() if args.dest else source_paths[0].parent / "_Flattened"
            unpacker = Unpacker(max_depth=2)
            all_proposals = []
            for source in source_paths:
                console.print(f"[cyan]Analysing nesting in {source.name}...[/cyan]")
                report = unpacker.analyse(source, staging)
                console.print(unpacker.summarise(report))
                all_proposals.extend(report.proposals)
            if not all_proposals:
                console.print("[bold green]\u2705 Nothing to flatten.[/bold green]")
                return
            if not args.force and not args.execute:
                console.print(f"\n[yellow]Dry-run mode. Use --execute to apply {len(all_proposals)} moves.[/yellow]")
                return
            executor = _Executor(dry_run=not args.execute)
            moved = 0
            for proposal in all_proposals:
                if executor.safe_copy(proposal.source, proposal.destination):
                    moved += 1
            console.print(f"\n[bold green]\u2705 Flattened {moved} files to {staging}[/bold green]")
            return


        # Handle watch mode (--watch)
        if args.watch:
            from fileflow.intelligence.listener import Listener
            from fileflow.intelligence.bridge import Bridge
            from fileflow.intelligence.memory import Memory
            from fileflow.intelligence.inspector import Inspector
            from fileflow.intelligence.extractor import UnifiedExtractor as _UE
            from fileflow.staging.manager import StagingManager as _SM

            source_paths = [Path(s).resolve() for s in args.sources]

            # Initialise the AI stack
            _bridge = Bridge()
            _inspector = None
            _staging = None

            if _bridge.is_healthy():
                _memory = Memory(db_path="fileflow_data/vectors.lance", bridge=_bridge)
                _inspector = Inspector(bridge=_bridge, memory=_memory)
                console.print("[bold green]\U0001f9e0 Cognition ONLINE[/bold green] — Inspector active")
            else:
                console.print("[yellow]\u26a1 Cognition OFFLINE[/yellow] — Watching without embedding")

            _extractor = _UE()
            _staging = _SM(_extractor)

            def _on_event(event):
                icon = "\u2705" if not event.result.get("error") else "\u274c"
                summary = event.result.get("summary", "")
                console.print(
                    f"  {icon} [cyan]{event.file_path.name}[/cyan] "
                    f"[dim]{event.event_type}[/dim]"
                    + (f" — {summary[:60]}" if summary else "")
                )

            listener = Listener(
                inspector=_inspector,
                staging_manager=_staging,
                debounce=2.0,
            )

            console.print(Panel.fit(
                f"[bold cyan]\U0001f441  FileFlow Listener — ACTIVE[/bold cyan]\n"
                f"[dim]Watching {len(source_paths)} folder(s). Press Ctrl+C to stop.[/dim]",
                border_style="cyan",
            ))
            for sp in source_paths:
                console.print(f"  \U0001f4c2 [dim]{sp}[/dim]")
            console.print()

            listener.watch(source_paths, on_event=_on_event)

            # Print final stats after shutdown
            console.print(f"\n[dim]{listener.stats.summary()}[/dim]")
            return

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


