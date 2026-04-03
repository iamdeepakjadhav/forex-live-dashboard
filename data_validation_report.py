#!/usr/bin/env python3
"""
Data Validation Report - Detailed analysis of database completeness
Shows before/after comparison and identifies remaining gaps
"""

import psycopg2
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add forex_system to path
sys.path.insert(0, str(Path(__file__).parent / "forex_system"))


class DataValidationReport:
    """Generates detailed reports on data completeness"""

    def __init__(self, host="localhost", user="postgres", password="root", database="forex_data"):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.conn = None
        self.cursor = None

    def connect(self):
        """Connect to PostgreSQL"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            self.cursor = self.conn.cursor()
            return True
        except psycopg2.Error as err:
            print(f"❌ PostgreSQL connection error: {err}")
            return False

    def close(self):
        """Close database connection"""
        if self.conn:
            self.cursor.close()
            self.conn.close()

    def get_candle_stats(self) -> Dict:
        """Get statistics about candles_data table"""
        stats = {}
        
        # Total candles by timeframe
        sql = """
        SELECT timeframe, COUNT(*) as count 
        FROM candles_data 
        GROUP BY timeframe 
        ORDER BY timeframe
        """
        try:
            self.cursor.execute(sql)
            stats['by_timeframe'] = {row[0]: row[1] for row in self.cursor.fetchall()}
        except psycopg2.Error as err:
            print(f"❌ Error: {err}")
            stats['by_timeframe'] = {}
        
        # Total candles by symbol
        sql = """
        SELECT symbol, COUNT(*) as count 
        FROM candles_data 
        GROUP BY symbol 
        ORDER BY symbol
        """
        try:
            self.cursor.execute(sql)
            stats['by_symbol'] = {row[0]: row[1] for row in self.cursor.fetchall()}
        except psycopg2.Error as err:
            stats['by_symbol'] = {}
        
        # Grand total
        stats['total'] = sum(stats['by_timeframe'].values())
        
        return stats

    def get_coverage_by_symbol(self) -> Dict[str, Tuple[int, int, float]]:
        """
        Get coverage % for each symbol
        Returns: {symbol: (expected_hours, existing_hours, coverage_percent)}
        """
        from src.data_gap_detector import DataGapDetector
        
        detector = DataGapDetector(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database
        )
        
        if not detector.connect():
            return {}
        
        symbols = detector.get_all_symbols()
        coverage = {}
        
        for symbol in symbols:
            missing, stats = detector.find_missing_hours(symbol)
            expected = stats['total_expected']
            existing = stats['total_existing']
            coverage_pct = float(stats['coverage'].rstrip('%'))
            
            coverage[symbol] = {
                'expected': expected,
                'existing': existing,
                'missing': stats['missing'],
                'coverage': coverage_pct
            }
        
        detector.close()
        return coverage

    def print_candle_report(self):
        """Print candles data report"""
        print("\n" + "="*70)
        print("  📊 CANDLES DATA REPORT")
        print("="*70 + "\n")
        
        stats = self.get_candle_stats()
        
        print("By Timeframe:")
        print("-"*70)
        for tf, count in sorted(stats['by_timeframe'].items()):
            bar = "█" * (count // 100000)
            print(f"  {tf:<10} {count:>15,} candles  {bar}")
        
        print(f"\n{'Total Candles:':<30} {stats['total']:>15,}\n")
        
        print("By Symbol:")
        print("-"*70)
        total_per_symbol = {}
        for timeframe, count in stats['by_timeframe'].items():
            sql = """
            SELECT symbol, COUNT(*) 
            FROM candles_data 
            WHERE timeframe=%s 
            GROUP BY symbol 
            ORDER BY symbol
            """
            try:
                self.cursor.execute(sql, (timeframe,))
                for symbol, count in self.cursor.fetchall():
                    if symbol not in total_per_symbol:
                        total_per_symbol[symbol] = 0
                    total_per_symbol[symbol] += count
            except:
                pass
        
        for symbol in sorted(total_per_symbol.keys()):
            count = total_per_symbol[symbol]
            bar = "█" * (count // 100000)
            print(f"  {symbol:<15} {count:>15,}  {bar}")

    def print_coverage_report(self):
        """Print coverage by symbol"""
        print("\n" + "="*70)
        print("  📈 COVERAGE ANALYSIS")
        print("="*70 + "\n")
        
        coverage = self.get_coverage_by_symbol()
        
        if not coverage:
            print("❌ No data available for analysis")
            return
        
        print(f"{'Symbol':<15} {'Expected':<15} {'Existing':<15} {'Missing':<15} {'Coverage':<10}")
        print("-"*70)
        
        total_expected = 0
        total_existing = 0
        total_missing = 0
        
        for symbol in sorted(coverage.keys()):
            data = coverage[symbol]
            expected = data['expected']
            existing = data['existing']
            missing = data['missing']
            cov = data['coverage']
            
            total_expected += expected
            total_existing += existing
            total_missing += missing
            
            # Color code: green if >95%, yellow if >80%, red if <80%
            cov_display = f"{cov:.1f}%"
            cov_bar = "█" * int(cov/10) + "░" * (10 - int(cov/10))
            
            print(f"{symbol:<15} {expected:<15,} {existing:<15,} {missing:<15,} {cov_display:<10} {cov_bar}")
        
        print("-"*70)
        overall_cov = (total_existing / total_expected * 100) if total_expected > 0 else 0
        print(f"{'TOTAL':<15} {total_expected:<15,} {total_existing:<15,} {total_missing:<15,} {overall_cov:.1f}%")
        print("="*70 + "\n")
        
        # Summary
        if overall_cov >= 95:
            print("✅ Excellent coverage! Data is nearly complete")
        elif overall_cov >= 80:
            print("⚠️  Good coverage, but some gaps remain")
        else:
            print("❌ Significant gaps detected. Recommend filling data")
    
    def print_date_range_report(self):
        """Print date range coverage"""
        print("\n" + "="*70)
        print("  📅 DATE RANGE REPORT")
        print("="*70 + "\n")
        
        sql = """
        SELECT 
            symbol,
            MIN(datetime) as min_date,
            MAX(datetime) as max_date,
            to_char(MIN(datetime), 'YYYY-MM-DD') as min_str,
            to_char(MAX(datetime), 'YYYY-MM-DD') as max_str
        FROM candles_data 
        WHERE timeframe='1H'
        GROUP BY symbol
        ORDER BY symbol
        """
        
        try:
            self.cursor.execute(sql)
            rows = self.cursor.fetchall()
            
            print(f"{'Symbol':<15} {'From':<15} {'To':<15} {'Days':<10}")
            print("-"*70)
            
            for symbol, min_ts, max_ts, min_str, max_str in rows:
                if min_ts and max_ts:
                    days = (max_ts - min_ts).days
                    print(f"{symbol:<15} {min_str:<15} {max_str:<15} {days:<10}")
            
            print("="*70 + "\n")
            
        except psycopg2.Error as err:
            print(f"❌ Error: {err}")

    def generate_full_report(self):
        """Generate complete validation report"""
        print("\n" + "="*80)
        print("🌍 " + " "*35 + "DATA VALIDATION REPORT")
        print("="*80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        self.print_candle_report()
        self.print_date_range_report()
        self.print_coverage_report()
        
        print("="*80)


def main():
    """Run validation report"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate data validation report")
    parser.add_argument('--host', default='localhost', help='Database host')
    parser.add_argument('--user', default='postgres', help='Database user')
    parser.add_argument('--password', default='root', help='Database password')
    parser.add_argument('--database', default='forex_data', help='Database name')
    
    args = parser.parse_args()
    
    validator = DataValidationReport(
        host=args.host,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    if validator.connect():
        validator.generate_full_report()
        validator.close()
    else:
        print("❌ Failed to connect to database")


if __name__ == "__main__":
    main()
