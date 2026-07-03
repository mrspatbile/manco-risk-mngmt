#!/usr/bin/env python3
"""
clean_data_outputs.py
=====================
Safe cleanup of regenerated data output folders.

Deletes only:
  - data/positions/
  - data/reports/
  - data/daily_exports/

Never deletes:
  - data/risk_management.db
  - data/yf_cache/

Usage:
  python3 -m fund_risk_workflow.tools.clean_data_outputs
    → Dry-run: print folders that would be deleted

  python3 -m fund_risk_workflow.tools.clean_data_outputs --confirm
    → Actually delete the folders

Safety:
  - Default is dry-run (no deletion without --confirm)
  - Checks that target paths are inside project /data
  - Skips non-existent folders
  - Never touches risk_management.db or yf_cache/
"""

import sys
import shutil
from pathlib import Path

# Resolve project root from module location
# src/fund_risk_workflow/tools/clean_data_outputs.py -> project root
MODULE_DIR = Path(__file__).parent  # tools/
FUND_RISK_WORKFLOW_DIR = MODULE_DIR.parent  # fund_risk_workflow/
SRC_DIR = FUND_RISK_WORKFLOW_DIR.parent  # src/
PROJECT_ROOT = SRC_DIR.parent  # project root
DATA_DIR = PROJECT_ROOT / 'data'

# Folders to clean (regenerated outputs only)
CLEANUP_TARGETS = [
    DATA_DIR / 'positions',
    DATA_DIR / 'reports',
    DATA_DIR / 'daily_exports',
]

# Folders that must never be deleted
PROTECTED = [
    DATA_DIR / 'risk_management.db',
    DATA_DIR / 'yf_cache',
]


def validate_target(target: Path) -> bool:
    """
    Verify that target is inside project /data and not protected.

    Returns True if target is safe to delete, False otherwise.
    """
    try:
        # Check that target is inside DATA_DIR
        target.relative_to(DATA_DIR)

        # Check that target is not a protected file/folder
        if target in PROTECTED or any(target == p for p in PROTECTED):
            return False

        return True
    except ValueError:
        # target is outside DATA_DIR
        return False


def dry_run():
    """Print folders that would be deleted."""
    print("DRY-RUN: The following folders would be deleted:\n")

    any_found = False
    for target in CLEANUP_TARGETS:
        if not validate_target(target):
            print(f"  ✗ PROTECTED: {target}")
            continue

        if target.exists():
            print(f"  → {target.relative_to(PROJECT_ROOT)}")
            any_found = True
        else:
            print(f"  ⊘ (does not exist, would be skipped)")

    if not any_found:
        print("  No folders found to clean.")

    print("\nTo confirm deletion, run:")
    print("  python3 -m fund_risk_workflow.tools.clean_data_outputs --confirm")


def confirm_delete():
    """Actually delete the folders."""
    print("Cleaning data outputs...\n")

    deleted_count = 0
    for target in CLEANUP_TARGETS:
        if not validate_target(target):
            print(f"  ✗ PROTECTED (skipped): {target.relative_to(PROJECT_ROOT)}")
            continue

        if not target.exists():
            print(f"  ⊘ SKIPPED (not found): {target.relative_to(PROJECT_ROOT)}")
            continue

        try:
            shutil.rmtree(target)
            print(f"  ✓ DELETED: {target.relative_to(PROJECT_ROOT)}")
            deleted_count += 1
        except Exception as e:
            print(f"  ✗ ERROR deleting {target.relative_to(PROJECT_ROOT)}: {e}")
            return False

    print(f"\n✓ Cleanup complete ({deleted_count} folder(s) deleted)")
    return True


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == '--confirm':
            success = confirm_delete()
            sys.exit(0 if success else 1)
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Usage: python3 -m fund_risk_workflow.tools.clean_data_outputs [--confirm]")
            sys.exit(1)
    else:
        dry_run()
        sys.exit(0)


if __name__ == '__main__':
    main()
