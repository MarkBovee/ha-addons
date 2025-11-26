#!/usr/bin/env python3
"""Sync shared modules to all add-on directories.

Home Assistant add-ons are built from their individual directories,
so the shared folder must exist in each add-on. This script copies
the root shared/ folder to each add-on directory.

Run this after making changes to shared modules:
    python sync_shared.py

Or with --watch for continuous sync during development:
    python sync_shared.py --watch
"""

import argparse
import os
import shutil
import sys
import time
from pathlib import Path


# Add-ons that use the shared folder
ADDONS = [
    'charge-amps-monitor',
    'energy-prices',
]


def get_repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).parent.resolve()


def sync_shared():
    """Copy shared/ to all add-on directories."""
    repo_root = get_repo_root()
    shared_src = repo_root / 'shared'
    
    if not shared_src.exists():
        print(f"Error: Source {shared_src} does not exist")
        return False
    
    success = True
    for addon in ADDONS:
        addon_dir = repo_root / addon
        if not addon_dir.exists():
            print(f"Warning: Add-on directory {addon} does not exist, skipping")
            continue
        
        shared_dst = addon_dir / 'shared'
        
        # Remove existing shared folder
        if shared_dst.exists():
            shutil.rmtree(shared_dst)
        
        # Copy new shared folder
        try:
            shutil.copytree(shared_src, shared_dst)
            print(f"✓ Synced shared/ to {addon}/shared/")
        except Exception as e:
            print(f"✗ Failed to sync to {addon}: {e}")
            success = False
    
    return success


def watch_and_sync(interval: float = 2.0):
    """Watch shared/ for changes and sync automatically."""
    repo_root = get_repo_root()
    shared_src = repo_root / 'shared'
    
    print(f"Watching {shared_src} for changes (Ctrl+C to stop)...")
    
    last_mtime = 0
    
    try:
        while True:
            # Get latest modification time of any file in shared/
            current_mtime = 0
            for f in shared_src.rglob('*'):
                if f.is_file() and not f.name.endswith('.pyc'):
                    mtime = f.stat().st_mtime
                    if mtime > current_mtime:
                        current_mtime = mtime
            
            # Sync if changed
            if current_mtime > last_mtime:
                if last_mtime > 0:  # Skip first sync message
                    print(f"\nChange detected, syncing...")
                sync_shared()
                last_mtime = current_mtime
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nStopped watching")


def main():
    parser = argparse.ArgumentParser(description='Sync shared modules to add-ons')
    parser.add_argument('--watch', '-w', action='store_true',
                       help='Watch for changes and sync automatically')
    parser.add_argument('--interval', '-i', type=float, default=2.0,
                       help='Watch interval in seconds (default: 2.0)')
    args = parser.parse_args()
    
    if args.watch:
        watch_and_sync(args.interval)
    else:
        success = sync_shared()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
