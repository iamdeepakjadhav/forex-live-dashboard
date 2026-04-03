"""
Data Gap Detector - Finds missing hours in the database
Uses efficient queries to detect gaps in historical data
"""

import psycopg2
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple


class DataGapDetector:
    """
    Detects missing hours in candles_data table
    Compares expected hours vs actual hours in DB
    """

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

    def get_all_symbols(self) -> List[str]:
        """Get all symbols from candles_data table"""
        sql = """
        SELECT DISTINCT symbol FROM candles_data ORDER BY symbol
        """
        try:
            self.cursor.execute(sql)
            return [row[0] for row in self.cursor.fetchall()]
        except psycopg2.Error as err:
            print(f"❌ Error fetching symbols: {err}")
            return []

    def get_date_range(self, symbol: str) -> Tuple[datetime, datetime]:
        """Get min and max dates for a symbol"""
        sql = """
        SELECT MIN(datetime), MAX(datetime) 
        FROM candles_data 
        WHERE symbol=%s AND timeframe='1H'
        """
        try:
            self.cursor.execute(sql, (symbol,))
            min_date, max_date = self.cursor.fetchone()
            if min_date and max_date:
                return min_date, max_date
            return None, None
        except psycopg2.Error as err:
            print(f"❌ Error fetching date range: {err}")
            return None, None

    def get_existing_hours(self, symbol: str, start_date: datetime, end_date: datetime) -> set:
        """Get all existing hour timestamps for a symbol"""
        sql = """
        SELECT DISTINCT datetime 
        FROM candles_data 
        WHERE symbol=%s AND timeframe='1H' 
        AND datetime >= %s AND datetime <= %s
        ORDER BY datetime
        """
        try:
            self.cursor.execute(sql, (symbol, start_date, end_date))
            return set(row[0] for row in self.cursor.fetchall())
        except psycopg2.Error as err:
            print(f"❌ Error fetching existing hours: {err}")
            return set()

    def generate_expected_hours(self, start_date: datetime, end_date: datetime) -> set:
        """
        Generate all expected hours between dates
        Excludes weekends (Saturday=5, Sunday=6)
        Excludes Friday 22:00+ and Sunday before 22:00 (forex closed)
        """
        expected = set()
        current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current <= end_date:
            # Skip weekends completely
            if current.weekday() < 5:  # Monday-Friday
                expected.add(current)
            elif current.weekday() == 4:  # Friday
                # Include Friday up to 22:00 UTC (market closes)
                if current.hour < 22:
                    expected.add(current)
            # Sunday after 22:00 UTC (market opens for next week)
            elif current.weekday() == 6 and current.hour >= 22:
                expected.add(current)
            
            current += timedelta(hours=1)
        
        return expected

    def find_missing_hours(self, symbol: str) -> Tuple[List[datetime], Dict]:
        """
        Find all missing hours for a symbol
        Returns: (list of missing hours, statistics dict)
        """
        print(f"\n🔍 Analyzing {symbol}...")
        
        min_date, max_date = self.get_date_range(symbol)
        if not min_date or not max_date:
            print(f"   ⚠️  No data found for {symbol}")
            return [], {"total_expected": 0, "total_existing": 0, "missing": 0}

        print(f"   📅 Date range: {min_date.date()} to {max_date.date()}")
        
        # Get existing and expected
        existing = self.get_existing_hours(symbol, min_date, max_date)
        expected = self.generate_expected_hours(min_date, max_date)
        
        # Find gaps
        missing = sorted(list(expected - existing))
        
        # Statistics
        stats = {
            "total_expected": len(expected),
            "total_existing": len(existing),
            "missing": len(missing),
            "coverage": f"{(len(existing)/len(expected)*100):.1f}%" if expected else "0%"
        }
        
        print(f"   ✅ Expected: {stats['total_expected']}, Existing: {stats['total_existing']}, Missing: {stats['missing']} ({stats['coverage']})")
        
        return missing, stats

    def generate_full_report(self) -> Dict:
        """Generate report for all symbols"""
        print("\n" + "="*60)
        print("📊 DATA GAP DETECTION REPORT")
        print("="*60)
        
        symbols = self.get_all_symbols()
        if not symbols:
            print("❌ No symbols found in database")
            return {}
        
        total_report = {}
        grand_total_missing = 0
        
        for symbol in symbols:
            missing, stats = self.find_missing_hours(symbol)
            total_report[symbol] = {
                "missing_hours": missing,
                "stats": stats
            }
            grand_total_missing += stats["missing"]
        
        print("\n" + "="*60)
        print(f"🎯 SUMMARY")
        print("="*60)
        print(f"Total Symbols: {len(symbols)}")
        print(f"Total Missing Hours Across All: {grand_total_missing}")
        
        symbols_with_gaps = {s: data for s, data in total_report.items() if data["stats"]["missing"] > 0}
        print(f"Symbols with Gaps: {len(symbols_with_gaps)}")
        
        if symbols_with_gaps:
            print("\n📌 Symbols Needing Data Fill:")
            for symbol in sorted(symbols_with_gaps.keys()):
                stats = symbols_with_gaps[symbol]["stats"]
                print(f"   • {symbol}: {stats['missing']} hours missing ({stats['coverage']} coverage)")
        
        print("="*60 + "\n")
        
        return total_report

    def get_missing_hours_for_symbol(self, symbol: str) -> List[datetime]:
        """Utility: Get missing hours for a specific symbol quickly"""
        min_date, max_date = self.get_date_range(symbol)
        if not min_date or not max_date:
            return []
        
        existing = self.get_existing_hours(symbol, min_date, max_date)
        expected = self.generate_expected_hours(min_date, max_date)
        missing = sorted(list(expected - existing))
        
        return missing
