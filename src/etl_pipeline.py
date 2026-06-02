import os
import logging
from datetime import datetime
import requests
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, exc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# -----------------------------
# DATABASE CONNECTION
# -----------------------------
def get_engine():
    """Create and return PostgreSQL engine with error handling."""
    load_dotenv()

    password = os.getenv("DB_PASSWORD")
    db_user = os.getenv("DB_USER", "postgres")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "garden_weather_db")

    if not password:
        raise ValueError("DB_PASSWORD environment variable not set")

    connection_string = f"postgresql+psycopg2://{db_user}:{password}@{db_host}:{db_port}/{db_name}"
    
    try:
        engine = create_engine(connection_string)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return engine
    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise


# -----------------------------
# EXTRACT (Open-Meteo)
# -----------------------------
def extract_weather(latitude=38.2527, longitude=-85.7585):
    """
    Fetch weather data from Open-Meteo API.
    
    Args:
        latitude: Location latitude (default: Louisville, KY)
        longitude: Location longitude (default: Louisville, KY)
    
    Returns:
        dict: JSON response from API
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,"
        f"precipitation_sum,precipitation_probability_max,"
        f"uv_index_max,weathercode"
        f"&hourly=relative_humidity_2m,wind_speed_10m,"
        f"soil_temperature_0cm,soil_moisture_0_to_1cm"
        f"&timezone=America/New_York"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        logger.info("Successfully extracted weather data from API")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        raise


# -----------------------------
# TRANSFORM
# -----------------------------
def transform(data):
    """
    Transform raw API data into structured DataFrames.
    
    Args:
        data: Raw JSON response from Open-Meteo API
    
    Returns:
        tuple: (daily_weather, hourly_weather, recommendations) DataFrames
    """
    try:
        # DAILY WEATHER
        daily_weather = pd.DataFrame({
            "weather_date": pd.to_datetime(data["daily"]["time"]),
            "temp_max_f": data["daily"]["temperature_2m_max"],
            "temp_min_f": data["daily"]["temperature_2m_min"],
            "precipitation_in": data["daily"]["precipitation_sum"],
            "precipitation_probability": data["daily"]["precipitation_probability_max"],
            "uv_index": data["daily"]["uv_index_max"],
            "weather_code": data["daily"]["weathercode"],
            "extracted_at": datetime.utcnow()
        })

        # HOURLY WEATHER
        hourly_weather = pd.DataFrame({
            "weather_timestamp": pd.to_datetime(data["hourly"]["time"]),
            "relative_humidity": data["hourly"]["relative_humidity_2m"],
            "wind_speed_mph": data["hourly"]["wind_speed_10m"],
            "soil_temp_f": data["hourly"]["soil_temperature_0cm"],
            "soil_moisture": data["hourly"]["soil_moisture_0_to_1cm"],
            "extracted_at": datetime.utcnow()
        })

        # RECOMMENDATIONS (derived from daily data)
        recommendations = pd.DataFrame({
            "weather_date": daily_weather["weather_date"],
            "frost_alert": daily_weather["temp_min_f"] < 36,
            "heat_alert": daily_weather["temp_max_f"] > 90,
            "watering_recommendation": daily_weather["precipitation_probability"].apply(
                lambda x: "Skip watering" if x > 60 else "Water if needed"
            ),
            "planting_condition": daily_weather["temp_min_f"].apply(
                lambda x: "Good" if x > 50 else "Poor"
            ),
            "created_at": datetime.utcnow()
        })

        logger.info("Data transformation completed successfully")
        return daily_weather, hourly_weather, recommendations

    except KeyError as e:
        logger.error(f"Data transformation failed - missing key: {str(e)}")
        raise


# -----------------------------
# LOAD (SQLAlchemy + PostgreSQL)
# -----------------------------
def create_tables(engine):
    """Create database tables if they don't exist."""
    try:
        with engine.begin() as conn:
            # Daily weather table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_weather (
                weather_date DATE PRIMARY KEY,
                temp_max_f FLOAT,
                temp_min_f FLOAT,
                precipitation_in FLOAT,
                precipitation_probability INTEGER,
                uv_index FLOAT,
                weather_code INTEGER,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))

            # Hourly weather table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hourly_weather (
                hour_id SERIAL PRIMARY KEY,
                weather_timestamp TIMESTAMP UNIQUE,
                relative_humidity FLOAT,
                wind_speed_mph FLOAT,
                soil_temp_f FLOAT,
                soil_moisture FLOAT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))

            # Gardening recommendations table
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gardening_recommendations (
                recommendation_id SERIAL PRIMARY KEY,
                weather_date DATE REFERENCES daily_weather(weather_date) ON DELETE CASCADE,
                frost_alert BOOLEAN,
                heat_alert BOOLEAN,
                watering_recommendation TEXT,
                planting_condition TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))

            # Create indexes for better query performance
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_hourly_timestamp 
            ON hourly_weather(weather_timestamp);
            """))

            logger.info("Database tables created/verified")

    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to create tables: {str(e)}")
        raise


def load(engine, daily, hourly, recs):
    """
    Load transformed data into PostgreSQL with upsert logic.
    
    Args:
        engine: SQLAlchemy engine
        daily: Daily weather DataFrame
        hourly: Hourly weather DataFrame
        recs: Recommendations DataFrame
    """
    try:
        with engine.begin() as conn:
            # Load daily weather (upsert on date)
            for _, row in daily.iterrows():
                conn.execute(text("""
                INSERT INTO daily_weather 
                (weather_date, temp_max_f, temp_min_f, precipitation_in, 
                 precipitation_probability, uv_index, weather_code, extracted_at)
                VALUES (:date, :temp_max, :temp_min, :precip, :precip_prob, :uv, :code, :extracted)
                ON CONFLICT (weather_date) DO UPDATE SET
                    temp_max_f = EXCLUDED.temp_max_f,
                    temp_min_f = EXCLUDED.temp_min_f,
                    precipitation_in = EXCLUDED.precipitation_in,
                    precipitation_probability = EXCLUDED.precipitation_probability,
                    uv_index = EXCLUDED.uv_index,
                    weather_code = EXCLUDED.weather_code,
                    extracted_at = EXCLUDED.extracted_at;
                """), {
                    "date": row["weather_date"],
                    "temp_max": row["temp_max_f"],
                    "temp_min": row["temp_min_f"],
                    "precip": row["precipitation_in"],
                    "precip_prob": row["precipitation_probability"],
                    "uv": row["uv_index"],
                    "code": row["weather_code"],
                    "extracted": row["extracted_at"]
                })

            # Load hourly weather (skip duplicates gracefully)
            for _, row in hourly.iterrows():
                try:
                    conn.execute(text("""
                    INSERT INTO hourly_weather 
                    (weather_timestamp, relative_humidity, wind_speed_mph, 
                     soil_temp_f, soil_moisture, extracted_at)
                    VALUES (:timestamp, :humidity, :wind, :soil_temp, :soil_moisture, :extracted)
                    ON CONFLICT (weather_timestamp) DO NOTHING;
                    """), {
                        "timestamp": row["weather_timestamp"],
                        "humidity": row["relative_humidity"],
                        "wind": row["wind_speed_mph"],
                        "soil_temp": row["soil_temp_f"],
                        "soil_moisture": row["soil_moisture"],
                        "extracted_at": row["extracted_at"]
                    })
                except exc.IntegrityError:
                    # Skip if duplicate timestamp exists
                    pass

            # Load recommendations (delete old, insert new for the day)
            for _, row in recs.iterrows():
                conn.execute(text("""
                DELETE FROM gardening_recommendations 
                WHERE weather_date = :date;
                """), {"date": row["weather_date"]})

                conn.execute(text("""
                INSERT INTO gardening_recommendations 
                (weather_date, frost_alert, heat_alert, watering_recommendation, 
                 planting_condition, created_at)
                VALUES (:date, :frost, :heat, :watering, :planting, :created)
                """), {
                    "date": row["weather_date"],
                    "frost": row["frost_alert"],
                    "heat": row["heat_alert"],
                    "watering": row["watering_recommendation"],
                    "planting": row["planting_condition"],
                    "created_at": row["created_at"]
                })

        logger.info("Data loaded successfully into PostgreSQL")

    except exc.SQLAlchemyError as e:
        logger.error(f"Failed to load data: {str(e)}")
        raise


# -----------------------------
# MAIN PIPELINE
# -----------------------------
def main():
    """Execute the complete ETL pipeline."""
    try:
        logger.info("Starting ETL pipeline...")
        
        # Database setup
        engine = get_engine()
        create_tables(engine)

        # Extract
        logger.info("Extracting data from Open-Meteo API...")
        data = extract_weather()

        # Transform
        logger.info("Transforming data...")
        daily, hourly, recs = transform(data)

        # Load
        logger.info("Loading data into PostgreSQL...")
        load(engine, daily, hourly, recs)

        logger.info("✅ ETL PIPELINE COMPLETED SUCCESSFULLY")
        return True

    except Exception as e:
        logger.error(f"❌ ETL PIPELINE FAILED: {str(e)}")
        raise


if __name__ == "__main__":
    main()
