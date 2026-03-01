"""
Diagnostic Service for Level 2 Forensic Auditing.
Analyzes file structures, sizes, and path complexities.
"""

from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter


class DiagnosticService:
    """
    Data-only auditor for architectural insights.
    Zero-move policy.
    """
    def __init__(self):
        self.extension_counts = Counter()
        self.folder_density = Counter()
        self.anomalies = [] # Files > 50MB
        self.deep_paths = [] # Paths > 200 chars or 10+ levels
        self.total_files = 0
        self.total_size = 0

    def analyze_file(self, path: Path):
        """
        Record metadata for a single file.
        """
        self.total_files += 1
        
        # 1. Extension Breakdown
        ext = path.suffix.lower() or ".no_ext"
        self.extension_counts[ext] += 1
        
        # 2. Folder Density
        parent_str = str(path.parent)
        self.folder_density[parent_str] += 1
        
        # 3. Size Anomaly Detection
        try:
            size_bytes = path.stat().st_size
            self.total_size += size_bytes
            if size_bytes > 50 * 1024 * 1024:
                self.anomalies.append({
                    "path": str(path),
                    "size_mb": round(size_bytes / (1024 * 1024), 2)
                })
        except OSError:
            pass
            
        # 4. Path Complexity Detection
        path_str = str(path)
        depth = len(path.parts)
        if len(path_str) > 200 or depth > 10:
            self.deep_paths.append({
                "path": path_str,
                "length": len(path_str),
                "depth": depth
            })

    def get_report(self) -> Dict:
        """
        Returns structured results for reporting.
        """
        return {
            "total_files": self.total_files,
            "total_size_gb": round(self.total_size / (1024**3), 2),
            "top_extensions": self.extension_counts.most_common(10),
            "top_folders": self.folder_density.most_common(10),
            "anomalies": sorted(self.anomalies, key=lambda x: x['size_mb'], reverse=True),
            "deep_path_count": len(self.deep_paths),
            "sample_deep_paths": self.deep_paths[:10]
        }

    def export_text_report(self, report_path: Path):
        """
        Saves a human-readable ASCII audit report.
        """
        data = self.get_report()
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("==================================================\n")
            f.write("      FILEFLOW LEVEL 2 FORENSIC AUDIT REPORT      \n")
            f.write(f"      Run Date: {Path(report_path).parent.parent.name}\n") # Simplistic
            f.write("==================================================\n\n")
            
            f.write(f"SUMMARY:\n")
            f.write(f"  Total Files Scanned: {data['total_files']}\n")
            f.write(f"  Total Data Size:    {data['total_size_gb']} GB\n\n")
            
            f.write("TOP 10 EXTENSIONS:\n")
            for ext, count in data['top_extensions']:
                f.write(f"  {ext:10}: {count} files\n")
            f.write("\n")
            
            f.write("TOP 10 HEAVIEST FOLDERS:\n")
            for folder, count in data['top_folders']:
                f.write(f"  [{count:4} files] {folder}\n")
            f.write("\n")
            
            f.write("ANOMALIES (FILES > 50MB):\n")
            if not data['anomalies']:
                f.write("  No large files detected.\n")
            for item in data['anomalies']:
                f.write(f"  [{item['size_mb']:>7} MB] {item['path']}\n")
            f.write("\n")
            
            f.write("PATH COMPLEXITY ALERT:\n")
            f.write(f"  Deep/Long Paths Detected: {data['deep_path_count']}\n")
            for item in data['sample_deep_paths']:
                f.write(f"  [Len: {item['length']:3} | Depth: {item['depth']:2}] {item['path']}\n")
            f.write("\n")
            f.write("--- END OF REPORT ---\n")
