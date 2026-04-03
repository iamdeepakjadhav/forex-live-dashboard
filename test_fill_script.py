#!/usr/bin/env python3
"""
Quick test of fill_missing_data scripts
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "forex_system"))

from src.data_gap_detector import DataGapDetector

print("\n" + "="*70)
print("Testing Data Gap Detector")
print("="*70 + "\n")

detector = DataGapDetector()

if not detector.connect():
    print("FAILED: Cannot connect to database")
    sys.exit(1)

print("Connected to database successfully!\n")

# Get all symbols
symbols = detector.get_all_symbols()
print(f"Found {len(symbols)} symbols\n")

# Show gaps for each symbol
print("-"*70)
print(f"{'Symbol':<15} {'Missing Hours':<20} {'Coverage':<15}")
print("-"*70)

total_missing = 0
for symbol in symbols:
    missing, stats = detector.find_missing_hours(symbol)
    total_missing += stats['missing']
    coverage = stats['coverage']
    missing_count = stats['missing']
    
    status = "COMPLETE" if missing_count == 0 else f"{missing_count} hours"
    print(f"{symbol:<15} {status:<20} {coverage:<15}")

print("-"*70)
print(f"\nTotal Missing Hours Across All Symbols: {total_missing}\n")

if total_missing > 0:
    print("To fill these gaps, run:")
    print("  python fill_missing_data.py --fill\n")
else:
    print("All data is complete - no gaps found!\n")

detector.close()
print("="*70 + "\n")
