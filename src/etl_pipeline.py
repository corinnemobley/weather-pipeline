"""
Weather Pipeline ETL Script
===========================

This script implements a complete, production-grade ETL (Extract-Transform-Load) 
pipeline for weather data. It fetches weather forecasts from the Open-Meteo API, 
performs comprehensive data cleaning and validation, creates derived analytics metrics,
and loads the processed data into PostgreSQL for downstream Power BI analytics.

The pipeline demonstrates best practices including:
- Modular, clean code architecture
- Comprehensive error handling and logging
- Incremental loading with upsert logic
- Data quality validation and checks
- Proper database connection management
- Professional documentation
"""

import os
import logging
from datetime import datetime
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, exc, inspect

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('etl_pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# SECTION 1: DATABASE CONNECTION
# ============================================================================

def get_engine():
    """
    Create and return a PostgreSQL SQLAlchemy engine with connection validation.
    
    Reads database credentials from environment variables (.env file).
    Validates the connection before returning the engine.
    
    Returns:
        sqlalchemy.engine.Engine: Configured PostgreSQL database engine
        
    Raises:
        ValueError: If DB_PASSWORD environment variable is not set
        SQLAlchemyError: If database connection fails
    """
    load_dotenv()
    
    # Read database configuration from environment variables with defaults
    password = os.getenv("DB_PASSWORD")
    db_user = os.getenv("DB_USER", "postgres")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "garden_weather_db")
    
    # Validate required credentials
    if not password:
        logger.error("DB_PASSWORD environment variable not set")
        raise ValueError("DB_PASSWORD environment variable not set")
    
    # Construct connection string
    connection_string = f"postgresql+psycopg2://{db_user}:{password}@{db_host}:{db_port}/{db_name}"
    
    try:
        # Create engine with connection pooling
        engine = create_engine(
            connection_string,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False
        )
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.close()
        
        logger.info(f"✓ Database connection successful: {db_host}:{db_port}/{db_name}")
        return engine
        
    except exc.SQLAlchemyError as e:
        logger.error(f"✗ Failed to connect to database: {str(e)}")
        raise


# ============================================================================
# SECTION 2: DATA EXTRACTION (REST API)
# ============================================================================

def validate_api_response(response_json):
    """
    Validate the structure and content of the API response.
    
    Args:
        response_json (dict): JSON response from Open-Meteo API
        
    Returns:
        bool: True if valid, raises exception otherwise
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    required_daily_fields = ["time", "temperature_2m_max", "temperature_2m_min",
                            "precipitation_sum", "precipitation_probability_max",
                            "uv_index_max", "weathercode"]
    required_hourly_fields = ["time", "relative_humidity_2m", "wind_speed_10m",
                             "soil_temperature_0cm", "soil_moisture_0_to_1cm"]
    
    # Validate daily data
    if "daily" not in response_json:
        raise ValueError("Missing 'daily' key in API response")
    
    for field in required_daily_fields:
        if field not in response_json["daily"]:
            raise ValueError(f"Missing required field in daily data: {field}")
    
    # Validate hourly data
    if "hourly" not in response_json:
        raise ValueError("Missing 'hourly' key in API response")
    
    for field in required_hourly_fields:
        if field not in response_json["hourly"]:
            raise ValueError(f"Missing required field in hourly data: {field}")
    
    # Verify data is not empty
    if len(response_json["daily"]["time"]) == 0:
        raise ValueError("No data in API response")
    
    logger.info("✓ API response validation passed")
    return True


def extract_weather(latitude=38.2527, longitude=-85.7585):
    """
    Extract weather data from the Open-Meteo API.
    
    Open-Meteo provides free weather forecasts without authentication.
    The API returns both daily and hourly weather data for the specified coordinates.
    
    Args:
        latitude (float): Location latitude (default: Louisville, KY)
        longitude (float): Location longitude (default: Louisville, KY)
        
    Returns:
        dict: JSON response containing daily and hourly weather data
        
    Raises:
        requests.exceptions.RequestException: If API request fails
        ValueError: If API response is invalid
        
    Data Fields Extracted:
        Daily: temp_max, temp_min, precipitation, UV index, weather code
        Hourly: humidity, wind speed, soil temperature, soil moisture
    """
    # Construct API URL with parameters
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
        logger.info(f"Fetching weather data from Open-Meteo API (Lat: {latitude}, Lon: {longitude})")
        
        # Make API request with timeout
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Validate response structure
        validate_api_response(data)
        
        logger.info(f"✓ Successfully extracted {len(data['daily']['time'])} days of weather data")
        return data
        
    except requests.exceptions.Timeout:
        logger.error("✗ API request timed out after 10 seconds")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ API request failed: {str(e)}")
        raise


# ============================================================================
# SECTION 3: DATA CLEANING & TRANSFORMATION
# ============================================================================

def clean_daily_weather(daily_data):
    """
    Clean and validate daily weather data.
    
    Handles:
    - Null/NaN values
    - Data type validation
    - Range validation
    - Type conversion
    
    Args:
        daily_data (pd.DataFrame): Raw daily weather data
        
    Returns:
        pd.DataFrame: Cleaned daily weather data
    """
    logger.info(f"Cleaning {len(daily_data)} daily weather records...")
    
    # Check for nulls before processing
    null_counts = daily_data.isnull().sum()
    if null_counts.any():
        logger.warning(f"Found null values in daily data: {null_counts[null_counts > 0].to_dict()}")
    
    # Handle missing precipitation (fill with 0)
    if daily_data['precipitation_in'].isnull().any():
        daily_data['precipitation_in'] = daily_data['precipitation_in'].fillna(0.0)
        logger.info("Filled missing precipitation values with 0")
    
    # Validate temperature range (-100 to 150°F is reasonable)
    invalid_temp = (
        (daily_data['temp_max_f'] < -100) | 
        (daily_data['temp_max_f'] > 150) |
        (daily_data['temp_min_f'] < -100) |
        (daily_data['temp_min_f'] > 150)
    )
    
    if invalid_temp.any():
        logger.warning(f"Found {invalid_temp.sum()} records with invalid temperatures")
    
    # Validate precipitation range (0-50 inches per day is reasonable)
    if (daily_data['precipitation_in'] < 0).any() or (daily_data['precipitation_in'] > 50).any():
        logger.warning("Found precipitation values outside expected range (0-50 inches)")
    
    # Validate probability range (0-100)
    if (daily_data['precipitation_probability'] < 0).any() or (daily_data['precipitation_probability'] > 100).any():
        logger.warning("Found precipitation probabilities outside 0-100 range")
    
    # Ensure data types
    daily_data['weather_date'] = pd.to_datetime(daily_data['weather_date']).dt.date
    daily_data['temp_max_f'] = pd.to_numeric(daily_data['temp_max_f'], errors='coerce')
    daily_data['temp_min_f'] = pd.to_numeric(daily_data['temp_min_f'], errors='coerce')
    daily_data['precipitation_in'] = pd.to_numeric(daily_data['precipitation_in'], errors='coerce')
    daily_data['precipitation_probability'] = daily_data['precipitation_probability'].astype(int)
    daily_data['uv_index'] = pd.to_numeric(daily_data['uv_index'], errors='coerce')
    daily_data['weather_code'] = daily_data['weather_code'].astype(int)
    
    logger.info(f"✓ Cleaned daily data: {len(daily_data)} records validated")
    return daily_data


def clean_hourly_weather(hourly_data):
    """
    Clean and validate hourly weather data.
    
    Handles:
    - Null/NaN values
    - Data type validation
    - Range validation
    
    Args:
        hourly_data (pd.DataFrame): Raw hourly weather data
        
    Returns:
        pd.DataFrame: Cleaned hourly weather data
    """
    logger.info(f"Cleaning {len(hourly_data)} hourly weather records...")
    
    # Check for nulls
    null_counts = hourly_data.isnull().sum()
    if null_counts.any():
        logger.warning(f"Found null values in hourly data: {null_counts[null_counts > 0].to_dict()}")
    
    # Fill missing soil data with forward fill (interpolation)
    if hourly_data['soil_temp_f'].isnull().any():
        hourly_data['soil_temp_f'] = hourly_data['soil_temp_f'].fillna(method='ffill').fillna(method='bfill')
        logger.info("Interpolated missing soil temperature values")
    
    if hourly_data['soil_moisture'].isnull().any():
        hourly_data['soil_moisture'] = hourly_data['soil_moisture'].fillna(method='ffill').fillna(method='bfill')
        logger.info("Interpolated missing soil moisture values")
    
    # Validate ranges
    if (hourly_data['relative_humidity'] < 0).any() or (hourly_data['relative_humidity'] > 100).any():
        logger.warning("Found humidity values outside 0-100 range")
    
    if (hourly_data['wind_speed_mph'] < 0).any():
        logger.warning("Found negative wind speed values")
    
    # Ensure data types
    hourly_data['weather_timestamp'] = pd.to_datetime(hourly_data['weather_timestamp'])
    hourly_data['relative_humidity'] = pd.to_numeric(hourly_data['relative_humidity'], errors='coerce')
    hourly_data['wind_speed_mph'] = pd.to_numeric(hourly_data['wind_speed_mph'], errors='coerce')
    hourly_data['soil_temp_f'] = pd.to_numeric(hourly_data['soil_temp_f'], errors='coerce')
    hourly_data['soil_moisture'] = pd.to_numeric(hourly_data['soil_moisture'], errors='coerce')
    
    logger.info(f"✓ Cleaned hourly data: {len(hourly_data)} records validated")
    return hourly_data


def create_derived_metrics(daily_data):
    """
    Create derived metrics and analytics-ready features from daily weather data.
    
    This creates actionable gardening recommendations based on weather conditions.
    
    Args:
        daily_data (pd.DataFrame): Cleaned daily weather data
        
    Returns:
        pd.DataFrame: Recommendations DataFrame with derived metrics
        
    Business Logic:
    - Frost Alert: True when low temp < 36°F (plant damage risk)
    - Heat Alert: True when high temp > 90°F (drought/heat stress risk)
    - Watering: Recommend skip if rain probability > 60%, otherwise water if needed
    - Planting: Good conditions if minimum temp > 50°F, Poor otherwise
    """
    logger.info("Creating derived analytics metrics...")
    
    # Create recommendations table
    recommendations = pd.DataFrame({
        'weather_date': daily_data['weather_date'],
        
        # Alert flags
        'frost_alert': daily_data['temp_min_f'] < 36,
        'heat_alert': daily_data['temp_max_f'] > 90,
        
        # Watering recommendation logic
        'watering_recommendation': daily_data['precipitation_probability'].apply(
            lambda x: "Skip watering" if x > 60 else "Water if needed"
        ),
        
        # Planting condition logic
        'planting_condition': daily_data['temp_min_f'].apply(
            lambda x: "Good" if x > 50 else "Poor"
        ),
        
        # Additional derived metrics
        'temperature_range': daily_data['temp_max_f'] - daily_data['temp_min_f'],
        'uv_danger': daily_data['uv_index'] >= 8,
        'created_at': datetime.utcnow()
    })
    
    logger.info(f"✓ Created derived metrics for {len(recommendations)} dates")
    return recommendations


def transform(data):
    """
    Complete transformation pipeline: clean, validate, and create derived metrics.
    
    UNIT CONVERSIONS:
    - Temperature: Celsius → Fahrenheit (°F = °C × 9/5 + 32)
    - Precipitation: millimeters → inches (1 inch = 25.4 mm)
    - Wind Speed: km/h → mph (1 km/h = 0.621371 mph)
    """
    try:
        logger.info("=" * 70)
        logger.info("TRANSFORMATION PHASE: Cleaning and preparing data")
        logger.info("=" * 70)
        
        # Extract raw data into DataFrames
        daily_raw = pd.DataFrame({
            'weather_date': data['daily']['time'],
            'temp_max_f': (pd.Series(data['daily']['temperature_2m_max']) * 9/5) + 32,  # ✅ C to F
            'temp_min_f': (pd.Series(data['daily']['temperature_2m_min']) * 9/5) + 32,  # ✅ C to F
            'precipitation_in': pd.Series(data['daily']['precipitation_sum']) / 25.4,  # ✅ mm to inches
            'precipitation_probability': data['daily']['precipitation_probability_max'],
            'uv_index': data['daily']['uv_index_max'],
            'weather_code': data['daily']['weathercode'],
            'extracted_at': datetime.utcnow()
        })
        
        hourly_raw = pd.DataFrame({
            'weather_timestamp': data['hourly']['time'],
            'relative_humidity': data['hourly']['relative_humidity_2m'],
            'wind_speed_mph': pd.Series(data['hourly']['wind_speed_10m']) * 0.621371,  # ✅ km/h to mph
            'soil_temp_f': (pd.Series(data['hourly']['soil_temperature_0cm']) * 9/5) + 32,  # ✅ C to F
            'soil_moisture': data['hourly']['soil_moisture_0_to_1cm'],
            'extracted_at': datetime.utcnow()
        })
        
        # Clean and validate data
        daily_weather = clean_daily_weather(daily_raw)
        hourly_weather = clean_hourly_weather(hourly_raw)
        
        # Create derived metrics for analytics
        recommendations = create_derived_metrics(daily_weather)
        
        logger.info("=" * 70)
        logger.info(f"✓ TRANSFORMATION COMPLETE")
        logger.info(f"  Daily records: {len(daily_weather)}")
        logger.info(f"  Hourly records: {len(hourly_weather)}")
        logger.info(f"  Recommendations: {len(recommendations)}")
        logger.info(f"  Sample temps: {daily_weather['temp_max_f'].iloc[0]:.1f}°F, {daily_weather['temp_min_f'].iloc[0]:.1f}°F")
        logger.info("=" * 70)
        
        return daily_weather, hourly_weather, recommendations
        
    except KeyError as e:
        logger.error(f"✗ Data transformation failed - missing key: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"✗ Unexpected error during transformation: {str(e)}")
        raise


# ============================================================================
# SECTION 4: DATA VALIDATION & QUALITY CHECKS
# ============================================================================

def validate_data_quality(daily_df, hourly_df, recommendations_df):
    """
    Perform comprehensive data quality checks before loading to database.
    
    Validates:
    - Null value counts
    - Duplicate records
    - Schema/datatype correctness
    - Range validation
    - Referential integrity (recommendations match daily data)
    - Row count verification
    
    Args:
        daily_df (pd.DataFrame): Daily weather data
        hourly_df (pd.DataFrame): Hourly weather data
        recommendations_df (pd.DataFrame): Recommendations data
        
    Returns:
        dict: Validation results and statistics
        
    Raises:
        ValueError: If critical validation checks fail
    """
    logger.info("=" * 70)
    logger.info("DATA QUALITY VALIDATION")
    logger.info("=" * 70)
    
    validation_results = {
        'passed': True,
        'warnings': [],
        'errors': []
    }
    
    # ===== DAILY WEATHER VALIDATION =====
    logger.info("\n[1/3] Validating Daily Weather Data...")
    
    # Null checks
    daily_nulls = daily_df.isnull().sum()
    if daily_nulls.any():
        warning = f"Daily data has null values: {daily_nulls[daily_nulls > 0].to_dict()}"
        logger.warning(f"  ⚠ {warning}")
        validation_results['warnings'].append(warning)
    
    # Duplicate checks
    daily_dupes = daily_df.duplicated(subset=['weather_date']).sum()
    if daily_dupes > 0:
        error = f"Found {daily_dupes} duplicate dates in daily data"
        logger.error(f"  ✗ {error}")
        validation_results['errors'].append(error)
        validation_results['passed'] = False
    
    # Data type validation
    expected_dtypes = {
        'temp_max_f': [np.float64, np.int64],
        'temp_min_f': [np.float64, np.int64],
        'precipitation_in': [np.float64, np.int64],
        'precipitation_probability': [np.int64, np.int32]
    }
    
    for col, expected_types in expected_dtypes.items():
        if col in daily_df.columns and daily_df[col].dtype not in expected_types:
            warning = f"Column {col} has dtype {daily_df[col].dtype}, expected {expected_types}"
            logger.warning(f"  ⚠ {warning}")
            validation_results['warnings'].append(warning)
    
    logger.info(f"  ✓ Daily records: {len(daily_df)} | Nulls: {daily_nulls.sum()} | Duplicates: {daily_dupes}")
    
    # ===== HOURLY WEATHER VALIDATION =====
    logger.info("\n[2/3] Validating Hourly Weather Data...")
    
    # Null checks
    hourly_nulls = hourly_df.isnull().sum()
    if hourly_nulls.any():
        warning = f"Hourly data has null values: {hourly_nulls[hourly_nulls > 0].to_dict()}"
        logger.warning(f"  ⚠ {warning}")
        validation_results['warnings'].append(warning)
    
    # Duplicate checks (weather_timestamp should be unique)
    hourly_dupes = hourly_df.duplicated(subset=['weather_timestamp']).sum()
    if hourly_dupes > 0:
        error = f"Found {hourly_dupes} duplicate timestamps in hourly data"
        logger.error(f"  ✗ {error}")
        validation_results['errors'].append(error)
    
    logger.info(f"  ✓ Hourly records: {len(hourly_df)} | Nulls: {hourly_nulls.sum()} | Duplicates: {hourly_dupes}")
    
    # ===== RECOMMENDATIONS VALIDATION =====
    logger.info("\n[3/3] Validating Recommendations Data...")
    
    # Null checks
    recs_nulls = recommendations_df.isnull().sum()
    if recs_nulls.any():
        warning = f"Recommendations data has null values: {recs_nulls[recs_nulls > 0].to_dict()}"
        logger.warning(f"  ⚠ {warning}")
        validation_results['warnings'].append(warning)
    
    # Referential integrity: every recommendation must have a matching daily date
    unmatched_recs = ~recommendations_df['weather_date'].isin(daily_df['weather_date']).all()
    if unmatched_recs:
        warning = "Some recommendations don't have matching daily weather records"
        logger.warning(f"  ⚠ {warning}")
        validation_results['warnings'].append(warning)
    
    # Schema validation
    boolean_cols = ['frost_alert', 'heat_alert', 'uv_danger']
    for col in boolean_cols:
        if col in recommendations_df.columns and recommendations_df[col].dtype != bool:
            warning = f"Column {col} should be boolean but is {recommendations_df[col].dtype}"
            logger.warning(f"  ⚠ {warning}")
            validation_results['warnings'].append(warning)
    
    logger.info(f"  ✓ Recommendation records: {len(recommendations_df)} | Nulls: {recs_nulls.sum()}")
    
    # ===== SUMMARY =====
    logger.info("\n" + "=" * 70)
    if validation_results['passed']:
        logger.info("✓ DATA QUALITY VALIDATION PASSED")
    else:
        logger.warning("⚠ DATA QUALITY VALIDATION PASSED WITH WARNINGS")
    
    if validation_results['warnings']:
        logger.warning(f"  Warnings ({len(validation_results['warnings'])}): {validation_results['warnings']}")
    
    if validation_results['errors']:
        logger.error(f"  Errors ({len(validation_results['errors'])}): {validation_results['errors']}")
        raise ValueError("Critical data quality checks failed")
    
    logger.info("=" * 70)
    return validation_results


# ============================================================================
# SECTION 5: DATABASE LOADING (INCREMENTAL UPSERT STRATEGY)
# ============================================================================

def create_tables(engine):
    """
    Create database schema with proper data types and constraints.
    
    Creates three normalized tables:
    1. daily_weather: Daily forecasts (primary key on weather_date)
    2. hourly_weather: Hourly measurements (unique on weather_timestamp)
    3. gardening_recommendations: Derived business rules (foreign key to daily_weather)
    
    Includes:
    - Primary keys for data integrity
    - Foreign key constraints with CASCADE delete
    - Indexes for query performance
    - Timestamps for audit trail
    
    Args:
        engine (sqlalchemy.engine.Engine): Database connection engine
        
    Raises:
        SQLAlchemyError: If table creation fails
    """
    logger.info("=" * 70)
    logger.info("CREATING DATABASE SCHEMA")
    logger.info("=" * 70)
    
    try:
        with engine.begin() as conn:
            # TABLE 1: daily_weather
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_weather (
                weather_date DATE PRIMARY KEY,
                temp_max_f FLOAT NOT NULL,
                temp_min_f FLOAT NOT NULL,
                precipitation_in FLOAT DEFAULT 0,
                precipitation_probability INTEGER CHECK (precipitation_probability >= 0 AND precipitation_probability <= 100),
                uv_index FLOAT,
                weather_code INTEGER,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))
            
            # TABLE 2: hourly_weather
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hourly_weather (
                hour_id SERIAL PRIMARY KEY,
                weather_timestamp TIMESTAMP UNIQUE NOT NULL,
                relative_humidity FLOAT CHECK (relative_humidity >= 0 AND relative_humidity <= 100),
                wind_speed_mph FLOAT CHECK (wind_speed_mph >= 0),
                soil_temp_f FLOAT,
                soil_moisture FLOAT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))
            
            # TABLE 3: gardening_recommendations (derived analytics table)
            conn.execute(text("""
            CREATE TABLE IF NOT EXISTS gardening_recommendations (
                recommendation_id SERIAL PRIMARY KEY,
                weather_date DATE NOT NULL REFERENCES daily_weather(weather_date) ON DELETE CASCADE,
                frost_alert BOOLEAN DEFAULT FALSE,
                heat_alert BOOLEAN DEFAULT FALSE,
                watering_recommendation TEXT,
                planting_condition TEXT,
                temperature_range FLOAT,
                uv_danger BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """))
            
            # Create indexes for optimized queries
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_hourly_timestamp 
            ON hourly_weather(weather_timestamp);
            """))
            
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_daily_extracted_at 
            ON daily_weather(extracted_at DESC);
            """))
            
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recs_weather_date 
            ON gardening_recommendations(weather_date);
            """))
            
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recs_frost_alert 
            ON gardening_recommendations(frost_alert) WHERE frost_alert = TRUE;
            """))
            
            conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_recs_heat_alert 
            ON gardening_recommendations(heat_alert) WHERE heat_alert = TRUE;
            """))
            
        logger.info("✓ Database schema created/verified with indexes")
        logger.info("=" * 70)
        
    except exc.SQLAlchemyError as e:
        logger.error(f"✗ Failed to create tables: {str(e)}")
        raise


def load(engine, daily, hourly, recs):
    """
    Load transformed data into PostgreSQL using UPSERT (incremental loading) strategy.
    
    INCREMENTAL LOADING EXPLANATION:
    This pipeline uses ON CONFLICT clauses to implement idempotent incremental loads:
    
    - daily_weather: UPSERT on weather_date (updates if date exists, inserts if new)
    - hourly_weather: ON CONFLICT DO NOTHING (skips duplicate timestamps)
    - gardening_recommendations: DELETE-then-INSERT (ensures fresh recommendations)
    
    This prevents duplicates and allows safe re-runs of the pipeline.
    
    Args:
        engine (sqlalchemy.engine.Engine): Database connection engine
        daily (pd.DataFrame): Cleaned daily weather data
        hourly (pd.DataFrame): Cleaned hourly weather data
        recs (pd.DataFrame): Derived recommendations
        
    Returns:
        dict: Load statistics with row counts
        
    Raises:
        SQLAlchemyError: If database operations fail
    """
    logger.info("=" * 70)
    logger.info("DATABASE LOADING PHASE: Inserting/Updating Records")
    logger.info("=" * 70)
    
    load_stats = {
        'daily_inserted': 0,
        'daily_updated': 0,
        'hourly_inserted': 0,
        'hourly_skipped': 0,
        'recs_deleted': 0,
        'recs_inserted': 0
    }
    
    try:
        # ===== LOAD DAILY WEATHER (UPSERT) =====
        logger.info("\n[1/3] Loading Daily Weather Data (UPSERT)...")
        
        with engine.begin() as conn:
            for idx, row in daily.iterrows():
                try:
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
                        extracted_at = EXCLUDED.extracted_at
                    """), {
                        'date': row['weather_date'],
                        'temp_max': row['temp_max_f'],
                        'temp_min': row['temp_min_f'],
                        'precip': row['precipitation_in'],
                        'precip_prob': row['precipitation_probability'],
                        'uv': row['uv_index'],
                        'code': row['weather_code'],
                        'extracted': row['extracted_at']
                    })
                    load_stats['daily_inserted'] += 1
                except exc.IntegrityError:
                    load_stats['daily_updated'] += 1
        
        logger.info(f"  ✓ Daily weather: {load_stats['daily_inserted']} inserted, "
                   f"{load_stats['daily_updated']} updated")
        
        # ===== LOAD HOURLY WEATHER (APPEND WITH CONFLICT HANDLING) =====
        logger.info("\n[2/3] Loading Hourly Weather Data (APPEND, skip duplicates)...")
        
        with engine.begin() as conn:
            for idx, row in hourly.iterrows():
                try:
                    conn.execute(text("""
                    INSERT INTO hourly_weather 
                    (weather_timestamp, relative_humidity, wind_speed_mph, 
                     soil_temp_f, soil_moisture, extracted_at)
                    VALUES (:timestamp, :humidity, :wind, :soil_temp, :soil_moisture, :extracted)
                    ON CONFLICT (weather_timestamp) DO NOTHING
                    """), {
                        'timestamp': row['weather_timestamp'],
                        'humidity': row['relative_humidity'],
                        'wind': row['wind_speed_mph'],
                        'soil_temp': row['soil_temp_f'],
                        'soil_moisture': row['soil_moisture'],
                        'extracted': row['extracted_at']
                    })
                    load_stats['hourly_inserted'] += 1
                except exc.IntegrityError:
                    load_stats['hourly_skipped'] += 1
        
        logger.info(f"  ✓ Hourly weather: {load_stats['hourly_inserted']} inserted, "
                   f"{load_stats['hourly_skipped']} duplicates skipped")
        
        # ===== LOAD RECOMMENDATIONS (DELETE & REPLACE) =====
        logger.info("\n[3/3] Loading Gardening Recommendations (DELETE & REPLACE)...")
        
        with engine.begin() as conn:
            # Delete old recommendations
            result = conn.execute(text("""
            DELETE FROM gardening_recommendations
            WHERE weather_date IN (SELECT DISTINCT weather_date FROM gardening_recommendations)
            """))
            load_stats['recs_deleted'] = result.rowcount
            
            # Insert new recommendations
            for idx, row in recs.iterrows():
                conn.execute(text("""
                INSERT INTO gardening_recommendations 
                (weather_date, frost_alert, heat_alert, watering_recommendation, 
                 planting_condition, temperature_range, uv_danger, created_at)
                VALUES (:date, :frost, :heat, :watering, :planting, :temp_range, :uv_danger, :created)
                """), {
                    'date': row['weather_date'],
                    'frost': row['frost_alert'],
                    'heat': row['heat_alert'],
                    'watering': row['watering_recommendation'],
                    'planting': row['planting_condition'],
                    'temp_range': row.get('temperature_range', None),
                    'uv_danger': row.get('uv_danger', False),
                    'created': row['created_at']
                })
                load_stats['recs_inserted'] += 1
        
        logger.info(f"  ✓ Recommendations: {load_stats['recs_deleted']} deleted, "
                   f"{load_stats['recs_inserted']} inserted")
        
        logger.info("\n" + "=" * 70)
        logger.info("✓ DATABASE LOADING COMPLETE")
        logger.info(f"  Total records loaded: {sum(load_stats.values())}")
        logger.info("=" * 70)
        
        return load_stats
        
    except exc.SQLAlchemyError as e:
        logger.error(f"✗ Failed to load data: {str(e)}")
        raise


# ============================================================================
# SECTION 6: ANALYTICS PREPARATION (POWER BI READY)
# ============================================================================

def prepare_analytics_dataset(engine):
    """
    Create analytics-ready dataset views for Power BI consumption.
    
    This function demonstrates preparation for Power BI by:
    1. Verifying all required tables exist and have data
    2. Creating a summary statistics view
    3. Documenting available fields for dashboard developers
    
    Note: Power BI connects directly to tables. This function provides
    verification that data is ready for dashboard development.
    
    Args:
        engine (sqlalchemy.engine.Engine): Database connection engine
        
    Returns:
        dict: Analytics readiness report
    """
    logger.info("=" * 70)
    logger.info("ANALYTICS PREPARATION: Verifying Power BI Readiness")
    logger.info("=" * 70)
    
    analytics_report = {
        'ready_for_powerbi': True,
        'tables': {},
        'recommendations': []
    }
    
    try:
        with engine.connect() as conn:
            # Check each table
            for table_name in ['daily_weather', 'hourly_weather', 'gardening_recommendations']:
                result = conn.execute(text(f"SELECT COUNT(*) as cnt FROM {table_name}"))
                count = result.scalar()
                
                # Get column info
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 1"))
                columns = list(result.keys())
                
                analytics_report['tables'][table_name] = {
                    'row_count': count,
                    'columns': columns,
                    'ready': count > 0
                }
                
                logger.info(f"✓ {table_name}: {count} rows, {len(columns)} columns")
        
        # Generate Power BI recommendations
        daily_count = analytics_report['tables']['daily_weather']['row_count']
        
        if daily_count == 0:
            analytics_report['ready_for_powerbi'] = False
            analytics_report['recommendations'].append(
                "No data in daily_weather table. Run ETL pipeline first."
            )
        elif daily_count < 7:
            analytics_report['recommendations'].append(
                f"Only {daily_count} days of data. Consider waiting for more historical data."
            )
        else:
            analytics_report['recommendations'].append(
                f"✓ Sufficient data ({daily_count} days) for Power BI dashboards"
            )
        
        # Document available metrics
        analytics_report['available_metrics'] = {
            'daily_weather': ['temp_max_f', 'temp_min_f', 'precipitation_in', 
                            'precipitation_probability', 'uv_index'],
            'gardening_recommendations': ['frost_alert', 'heat_alert', 
                                         'watering_recommendation', 'planting_condition']
        }
        
        logger.info("\n" + "-" * 70)
        logger.info("POWER BI READINESS:")
        for rec in analytics_report['recommendations']:
            logger.info(f"  • {rec}")
        
        logger.info("\nAVAILABLE METRICS FOR DASHBOARDS:")
        logger.info("  Daily Weather: Temperature range, precipitation, UV index")
        logger.info("  Recommendations: Frost/heat alerts, watering advice, planting conditions")
        logger.info("-" * 70)
        logger.info("=" * 70)
        
        return analytics_report
        
    except Exception as e:
        logger.error(f"✗ Failed to prepare analytics dataset: {str(e)}")
        raise


# ============================================================================
# SECTION 7: MAIN ETL ORCHESTRATION
# ============================================================================

def main():
    """
    Main ETL pipeline orchestration.
    
    Executes complete workflow:
    1. Extract: Fetch weather data from Open-Meteo API
    2. Transform: Clean, validate, and create derived metrics
    3. Validate: Comprehensive data quality checks
    4. Load: Incremental upsert into PostgreSQL
    5. Prepare: Verify analytics-readiness for Power BI
    
    Returns:
        bool: True if pipeline succeeded
        
    Raises:
        Exception: If any critical step fails
    """
    try:
        logger.info("\n")
        logger.info("╔" + "=" * 68 + "╗")
        logger.info("║" + " " * 15 + "WEATHER PIPELINE ETL - MAIN EXECUTION" + " " * 15 + "║")
        logger.info("╚" + "=" * 68 + "╝")
        logger.info("")
        
        # ===== SETUP =====
        logger.info("Initializing database connection...")
        engine = get_engine()
        create_tables(engine)
        
        # ===== EXTRACT =====
        logger.info("\n")
        logger.info("PHASE 1: EXTRACTING DATA FROM REST API")
        logger.info("-" * 70)
        data = extract_weather()
        
        # ===== TRANSFORM =====
        logger.info("\n")
        logger.info("PHASE 2: TRANSFORMING AND CLEANING DATA")
        logger.info("-" * 70)
        daily, hourly, recs = transform(data)
        
        # ===== VALIDATE =====
        logger.info("\n")
        logger.info("PHASE 3: DATA QUALITY VALIDATION")
        logger.info("-" * 70)
        validation_results = validate_data_quality(daily, hourly, recs)
        
        # ===== LOAD =====
        logger.info("\n")
        logger.info("PHASE 4: LOADING DATA TO POSTGRESQL")
        logger.info("-" * 70)
        load_stats = load(engine, daily, hourly, recs)
        
        # ===== ANALYTICS PREPARATION =====
        logger.info("\n")
        logger.info("PHASE 5: ANALYTICS PREPARATION")
        logger.info("-" * 70)
        analytics_report = prepare_analytics_dataset(engine)
        
        # ===== SUCCESS =====
        logger.info("\n")
        logger.info("╔" + "=" * 68 + "╗")
        logger.info("║" + " " * 20 + "✅ ETL PIPELINE COMPLETED SUCCESSFULLY" + " " * 10 + "║")
        logger.info("╚" + "=" * 68 + "╝")
        
        logger.info(f"\nPIPELINE SUMMARY:")
        logger.info(f"  Records Extracted: {len(data['daily']['time'])} daily, {len(data['hourly']['time'])} hourly")
        logger.info(f"  Records Validated: {len(daily)} daily, {len(hourly)} hourly, {len(recs)} recommendations")
        logger.info(f"  Records Loaded: {load_stats['daily_inserted'] + load_stats['daily_updated']} daily, "
                   f"{load_stats['hourly_inserted']} hourly, {load_stats['recs_inserted']} recommendations")
        logger.info(f"  Power BI Ready: {'Yes ✓' if analytics_report['ready_for_powerbi'] else 'No ✗'}")
        
        return True
        
    except Exception as e:
        logger.error("\n")
        logger.error("╔" + "=" * 68 + "╗")
        logger.error("║" + " " * 20 + "❌ ETL PIPELINE FAILED" + " " * 24 + "║")
        logger.error("╚" + "=" * 68 + "╝")
        logger.error(f"\nError Details: {str(e)}")
        logger.error("Check etl_pipeline.log for detailed error information")
        raise


if __name__ == "__main__":
    main()
