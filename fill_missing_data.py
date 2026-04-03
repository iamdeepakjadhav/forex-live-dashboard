#!/usr/bin/env python3
"""
Fill Missing Data - Main Orchestrator
Detects gaps in forex data and fills them from Dukascopy

Usage:
  python fill_missing_data.py --report      # Show gaps only
  python fill_missing_data.py --fill        # Detect and fill gaps
  python fill_missing_data.py --symbol EURUSD --fill  # Fill specific symbol
  python fill_missing_data.py --validate    # Verify after fill
"""

import asyncio
import argparse
import sys
import time
from datetime import datetime
from typing import List
from pathlib import Path

# Add forex_system to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent / "forex_system"))

from src.data_gap_detector import DataGapDetector
from src.data_filler import DataFiller


def print_header(title):
    """Print formatted header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")


def print_stats_table(results: dict):
    """Print results in table format"""
    print("\n" + "-"*70)
    print(f"{'Symbol':<15} {'Status':<15} {'Missing':<12} {'Inserted':<12}")
    print("-"*70)
    
    total_inserted = 0
    
    for symbol, result in results.items():
        status = result.get("status", "unknown")
        missing = result.get("missing_hours", 0)
        inserted = result.get("inserted", 0)
        
        total_inserted += inserted
        
        # Color coding (text only)
        status_display = f"✅ {status}" if status == "success" else f"❌ {status}"
        
        print(f"{symbol:<15} {status_display:<20} {missing:<12} {inserted:<12}")
    
    print("-"*70)
    print(f"{'TOTAL':<15} {'':<15} {'':<12} {total_inserted:<12}")
    print("-"*70 + "\n")
    
    return total_inserted


def main():
    parser = argparse.ArgumentParser(
        description="Fill missing forex data from Dukascopy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fill_missing_data.py --report              # Show only gaps
  python fill_missing_data.py --fill                # Fill all gaps
  python fill_missing_data.py --symbol EURUSD --fill  # Fill one symbol
  python fill_missing_data.py --fill --validate     # Fill + verify
        """
    )
    
    parser.add_argument('--report', action='store_true', 
                        help='Show gap report only (no download)')
    parser.add_argument('--fill', action='store_true',
                        help='Download and fill gaps')
    parser.add_argument('--symbol', type=str,
                        help='Process specific symbol only')
    parser.add_argument('--validate', action='store_true',
                        help='Validate data after fill')
    parser.add_argument('--max-workers', type=int, default=None,
                        help='Max parallel workers (default: CPU count)')
    
    args = parser.parse_args()
    
    # If no action specified, show report
    if not args.report and not args.fill and not args.validate:
        args.report = True
    
    print_header("🌍 FOREX DATA FILLER")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize detector
    detector = DataGapDetector()
    
    if not detector.connect():
        print("❌ Failed to connect to database")
        sys.exit(1)
    
    try:
        # Phase 1: Generate report
        if args.report or args.fill:
            print_header("📊 PHASE 1: GAP DETECTION")
            
            report = detector.generate_full_report()
            
            if not report:
                print("❌ No data found in database")
                sys.exit(1)
            
            # Filter by symbol if specified
            if args.symbol:
                report = {s: data for s, data in report.items() if s.startswith(args.symbol)}
                if not report:
                    print(f"❌ Symbol {args.symbol} not found")
                    sys.exit(1)
        
        # Phase 2: Fill gaps
        if args.fill:
            print_header("📥 PHASE 2: DOWNLOADING & FILLING")
            
            # Collect missing hours by symbol
            symbol_hours = {}
            for symbol, data in report.items():
                missing = data.get("missing_hours", [])
                if missing:
                    symbol_hours[symbol] = missing
            
            if not symbol_hours:
                print("✅ No gaps found - database is complete!")
                detector.close()
                return
            
            print(f"📌 Will fill {len(symbol_hours)} symbol(s):")
            for symbol in sorted(symbol_hours.keys()):
                print(f"   • {symbol}: {len(symbol_hours[symbol])} hours")
            
            # Fill gaps
            filler = DataFiller(max_workers=args.max_workers)
            
            fill_start = time.time()
            
            # Run async fill for all symbols in parallel
            results = asyncio.run(filler.fill_multiple_symbols(symbol_hours))
            
            # Convert results list to dict
            results_dict = {r["symbol"]: r for r in results}
            
            # Print summary
            fill_elapsed = time.time() - fill_start
            total_inserted = print_stats_table(results_dict)
            
            print(f"⏱️  Fill time: {fill_elapsed:.2f}s")
            print(f"📊 Total candles inserted: {total_inserted}")
        
        # Phase 3: Validation
        if args.validate:
            print_header("✅ PHASE 3: VALIDATION")
            
            print("🔄 Re-checking gaps after fill...")
            
            validator_report = detector.generate_full_report()
            
            symbols_still_missing = {s: data for s, data in validator_report.items() 
                                     if data["stats"]["missing"] > 0}
            
            if not symbols_still_missing:
                print("\n🎉 All gaps filled successfully!")
            else:
                print(f"\n⚠️  Still have {len(symbols_still_missing)} symbols with gaps:")
                for symbol in sorted(symbols_still_missing.keys()):
                    stats = symbols_still_missing[symbol]["stats"]
                    print(f"   • {symbol}: {stats['missing']} hours ({stats['coverage']})")
        
        # Final summary
        print_header("✨ COMPLETE")
        print(f"Finish Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("✅ All operations completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        detector.close()


if __name__ == "__main__":
    main()
