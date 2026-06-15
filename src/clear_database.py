"""
Clear all data from the weather pipeline database
"""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

# Database connection
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    database=os.getenv("DB_NAME", "garden_weather_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD")
)

cursor = conn.cursor()

try:
    print("Clearing database...")
    
    # Delete in order of dependencies (recommendations depends on daily_weather)
    cursor.execute("DELETE FROM gardening_recommendations;")
    print(f"✓ Deleted gardening_recommendations")
    
    cursor.execute("DELETE FROM hourly_weather;")
    print(f"✓ Deleted hourly_weather")
    
    cursor.execute("DELETE FROM daily_weather;")
    print(f"✓ Deleted daily_weather")
    
    # Verify it's empty
    cursor.execute("SELECT COUNT(*) FROM daily_weather;")
    daily_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM hourly_weather;")
    hourly_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM gardening_recommendations;")
    recs_count = cursor.fetchone()[0]
    
    print("\n" + "=" * 50)
    print("DATABASE STATUS:")
    print("=" * 50)
    print(f"daily_weather: {daily_count} rows")
    print(f"hourly_weather: {hourly_count} rows")
    print(f"gardening_recommendations: {recs_count} rows")
    print("=" * 50)
    
    if daily_count == 0 and hourly_count == 0 and recs_count == 0:
        print("✅ Database is now clean!")
    else:
        print("⚠️ Some data still remains")
    
    conn.commit()
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
