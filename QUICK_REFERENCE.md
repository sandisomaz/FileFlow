# FileFlow V8 - Quick Reference Guide

## 🚨 EMERGENCY FIX SUMMARY

**Problem**: System hangs on corrupted PDFs (ThreadPoolExecutor can't terminate)

**Solution**: Switched to ProcessPoolExecutor + Ghost file detection

**Files Changed**: 3 files
1. `fileflow/staging/manager.py` → ProcessPoolExecutor with 3s timeout
2. `fileflow/intelligence/extractor.py` → Unified extraction logic
3. `fileflow/core/config.py` → Merged config system

---

## ⚡ QUICK START

### Installation (If Not Already Done)
```bash
cd C:\Users\sandi\Desktop\FileFlow
pip install pypdf PyYAML rich textual
```

### Test Run (Safe)
```bash
python main.py "C:\Users\sandi\Desktop\INTERNSHIP_DEMO_SOURCE" ^
    --dest "C:\Users\sandi\Desktop\Professional_Archive_2026" ^
    --dry-run
```

### Real Run (After Testing)
```bash
python main.py "C:\Users\sandi\Desktop\INTERNSHIP_DEMO_SOURCE" ^
    --dest "C:\Users\sandi\Desktop\Professional_Archive_2026" ^
    --execute
```

---

## 🎯 KEY FEATURES

| Feature | Description | Benefit |
|---------|-------------|---------|
| **Ghost Detection** | Skips files < 1KB | Instant skip, no wasted CPU |
| **3s Timeout** | Hard limit on PDF extraction | No infinite hangs |
| **Process Isolation** | ProcessPoolExecutor | Terminates stuck processes |
| **Content Hashing** | MD5 of text content | Smart deduplication |
| **Forensic Manifest** | JSON audit trail | Complete rollback capability |
| **Quarantine** | Isolates corrupted files | Safe handling of bad data |

---

## 📋 COMMON COMMANDS

### Dry Run (Preview Only)
```bash
python main.py <source> --dest <destination> --dry-run
```

### Execute (Move Files)
```bash
python main.py <source> --dest <destination> --execute
```

### Force Mode (No Prompts)
```bash
python main.py <source> --dest <destination> --execute --force
```

### Audit Mode (No Changes)
```bash
python main.py <source> --audit
# Output: reports/discovery_audit_YYYYMMDD.txt
```

### Rollback
```bash
python main.py --rollback "C:\path\to\Forensic_Manifest.json"
```

---

## 🔍 WHAT TO WATCH FOR

### ✅ Good Signs
```
✅ [GHOST] Skipping tiny/empty file: filename.pdf (42 bytes)
✅ [TIMEOUT] Skipping corrupted PDF: broken.pdf
✅ Phase 3: Deep Analysis & Staging  [████████████] 100%
✅ DONE Execution Complete
```

### ❌ Bad Signs (Indicates Fix Not Applied)
```
❌ System hangs indefinitely on one file
❌ No progress bar movement for > 5 minutes
❌ KeyboardInterrupt required to exit
❌ ThreadPoolExecutor visible in stack trace
```

---

## 🛠️ TROUBLESHOOTING

### Problem: Import Error
```
ModuleNotFoundError: No module named 'fileflow'
```
**Solution**: Run from project root
```bash
cd C:\Users\sandi\Desktop\FileFlow
python main.py ...
```

### Problem: Still Hanging?
**Check 1**: Verify manager.py has ProcessPoolExecutor
```bash
findstr /C:"ProcessPoolExecutor" fileflow\staging\manager.py
```
Should return matches. If not, fix wasn't applied.

**Check 2**: Verify worker function exists
```bash
findstr /C:"def worker_extract_pdf_text" fileflow\staging\manager.py
```
Should return match. If not, wrong version.

### Problem: No Files Processed
**Check**: Ignore rules in settings.yaml
```yaml
scanning:
  ignored_dirs:
    - _FileFlow_Final_Clean_V8  # Don't scan output folder
```
Make sure your source isn't in ignore list.

### Problem: Permission Denied
**Solution**: Run as Administrator or check file locks
```bash
# Close any programs that might have files open
# Try again
```

---

## 📊 PERFORMANCE EXPECTATIONS

**Your System**: Ryzen 5 5500U, 12GB RAM

| Files | Expected Time | Notes |
|-------|---------------|-------|
| 100 files | 30-60 seconds | Mostly PDFs |
| 500 files | 2-4 minutes | Mixed types |
| 1000 files | 4-8 minutes | With timeouts |

**Timeout Budget**:
- Each stuck PDF: Max 3 seconds
- Ghost files: < 1ms each
- Good files: 0.5-2s average

---

## 🗂️ OUTPUT STRUCTURE

```
Professional_Archive_2026/
├── Forensic_Manifest.json           # Rollback data
│
├── JUDGES_SECRETARY/                # Entity folder
│   ├── JUDGES_SEC_CV_20240215_v1.pdf
│   ├── JUDGES_SEC_Z83_20240215_v2.pdf
│   └── JUDGES_SEC_Certificate_20240215_v3.pdf
│
├── REF_12345_2024/                  # Reference-based folder
│   └── REF_12345_2024_Z83_20240215_v1.pdf
│
├── _Quarantine/                     # Corrupted files
│   ├── Invalid_PDF_Header/
│   │   └── broken.pdf
│   └── PDF_extraction_timeout/
│       └── stuck.pdf
│
└── Ghost_Files/                     # Empty/tiny files
    └── empty.pdf
```

---

## 📝 LOG FILES

**Session Log**: `logs/session_YYYYMMDD_HHMMSS.log`
- Contains: Full execution transcript
- Use for: Debugging, audit trail

**Audit CSV**: `logs/migration_audit.csv`
- Contains: Per-file operations
- Columns: Timestamp, Original_Path, New_Entity, SubType, MD5, Status, Notes

**Forensic Log**: `logs/system_forensics.log`
- Contains: DEBUG-level system events
- Use for: Deep troubleshooting

---

## 🔐 SAFETY CHECKLIST

Before running `--execute`:

- [ ] Tested with `--dry-run` first
- [ ] Verified no hangs during dry run
- [ ] Checked preview looks correct
- [ ] Have enough disk space (2x source size)
- [ ] Backed up critical files elsewhere
- [ ] Know rollback command location

---

## 🆘 EMERGENCY PROCEDURES

### If System Hangs (Old Bug)
1. Press Ctrl+C to interrupt
2. Check if fix was applied: `findstr ProcessPoolExecutor fileflow\staging\manager.py`
3. If no match, apply fix: `copy manager_fixed.py fileflow\staging\manager.py`
4. Retry

### If Files Went to Wrong Place
1. Locate manifest: `<destination>\Forensic_Manifest.json`
2. Run rollback: `python main.py --rollback "path\to\Forensic_Manifest.json"`
3. Review settings.yaml rules
4. Re-run with adjusted config

### If Corrupted Files Detected
1. Check `_Quarantine` folder in destination
2. Review `quarantine_reason` in manifest
3. Options:
   - Ignore (file was bad anyway)
   - Repair PDF with external tool
   - Re-scan repaired file

---

## 📞 VERIFICATION COMMANDS

### Check Version
```bash
python -c "from fileflow.core.config import ConfigLoader; print(ConfigLoader().system.version)"
# Should print: 8.0.0
```

### Check ProcessPool Fix
```bash
python -c "from fileflow.staging.manager import worker_extract_pdf_text; print('Fixed!')"
# Should print: Fixed!
```

### Check Unified Extractor
```bash
python -c "from fileflow.intelligence.extractor import UnifiedExtractor; print('OK')"
# Should print: OK
```

### Run Diagnostic
```bash
python main.py "C:\Users\sandi\Desktop\INTERNSHIP_DEMO_SOURCE" --audit
# Generates: reports/discovery_audit_YYYYMMDD.txt
```

---

## 🎓 CONFIGURATION TIPS

### Increase Timeout (For Very Large PDFs)
Edit `settings.yaml`:
```yaml
execution:
  timeout_pdf_extraction: 5  # Default: 3 seconds
```

### Decrease Ghost Threshold (Skip More Files)
Edit `settings.yaml`:
```yaml
execution:
  ghost_file_threshold: 2048  # Default: 1024 bytes (1KB)
```

### Add Custom Ignore Rules
Edit `settings.yaml`:
```yaml
scanning:
  ignored_dirs:
    - MyCustomFolder
    - TempFiles
```

### Add New Categories
Edit `config.json`:
```json
"categories": {
  "My_Category": {
    "priority": 10,
    "keywords": ["keyword1", "keyword2"],
    "extensions": [".pdf", ".docx"]
  }
}
```

---

## 📈 OPTIMIZATION TIPS

### For Large Datasets (1000+ files)
1. Use `--audit` first to profile
2. Check `reports/discovery_audit_*.txt` for anomalies
3. Clean up large files (>50MB) separately
4. Run main process on remaining files

### For Speed
1. Use SSD if available
2. Close other programs
3. Disable real-time antivirus temporarily
4. Consider parallel processing (future feature)

### For Accuracy
1. Review settings.yaml keyword lists
2. Add known company names to law_firms
3. Test with small subset first
4. Manually verify first 10 files

---

## ✅ POST-RUN CHECKLIST

- [ ] Check `Forensic_Manifest.json` exists
- [ ] Review `logs/migration_audit.csv`
- [ ] Spot-check 10 random files in destination
- [ ] Verify no files lost (source count = destination count)
- [ ] Test rollback command (dry-run mode)
- [ ] Archive manifest for future reference

---

**Version**: 8.0.0-UNIFIED-FIX
**Last Updated**: 2026-02-15
**Status**: ✅ PRODUCTION READY
