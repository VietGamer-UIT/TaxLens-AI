"""
Script: Aggressive project clean up for Production Readiness.
Removes legacy EntradeX files, unused SQL scripts, and cleans cache.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent

def cleanup():
    legacy_dir = ROOT / "legacy"
    if legacy_dir.exists():
        shutil.rmtree(legacy_dir)
        print(f"Deleted: {legacy_dir}")

    sql_dir = ROOT / "SQL-Scripts"
    if sql_dir.exists():
        shutil.rmtree(sql_dir)
        print(f"Deleted: {sql_dir}")

    # Remove pycache recursively
    for p in ROOT.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p)
            print(f"Deleted: {p}")

if __name__ == "__main__":
    print("Running aggressive cleanup...")
    cleanup()
    print("Cleanup complete. Ready for Git.")
