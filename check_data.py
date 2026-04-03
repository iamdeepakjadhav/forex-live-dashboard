import psycopg2

conn = psycopg2.connect(host='localhost', user='postgres', password='root', database='forex_data')
cur = conn.cursor()

# Check tick data
cur.execute('SELECT COUNT(*) as total FROM ticks')
total = cur.fetchone()[0]

cur.execute('SELECT MIN(tick_time) as earliest, MAX(tick_time) as latest FROM ticks')
earliest, latest = cur.fetchone()

cur.execute('SELECT DISTINCT symbol FROM ticks ORDER BY symbol')
symbols = [row[0] for row in cur.fetchall()]

print(f'✅ Total Ticks: {total}')
print(f'📅 Date Range: {earliest} to {latest}')
print(f'📊 Symbols: {symbols}')

# Check years available
cur.execute("SELECT DISTINCT EXTRACT(YEAR FROM tick_time)::int as year FROM ticks ORDER BY year DESC")
years = [row[0] for row in cur.fetchall()]
print(f'📆 Years Available: {years}')

cur.close()
conn.close()
