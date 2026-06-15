# Weather Pipeline

An end-to-end data engineering pipeline that acquires weather data from a REST API, processes it with Python, stores it in PostgreSQL, and visualizes it with Power BI.

## Architecture

```
Open-Meteo API → Python ETL → PostgreSQL →    Dashboard
      ↓              ↓              ↓            ↓
  Weather Data   Transform &    Structured   Interactive
                 Validate       Tables       Visualizations
```

## Features

- **Automated Data Collection**: Daily weather data from Open-Meteo API (free, no key required)
- **Data Quality**: Error handling, logging, and validation
- **Intelligent Storage**: Upsert logic to prevent duplicates
- **Smart Alerts**: Frost, heat, and watering recommendations
- **Scheduled Execution**: GitHub Actions workflow (runs daily at 6 AM EST)
- **Production Ready**: Connection pooling, indexes, and error recovery

## Database Schema

### Tables

**daily_weather**
```
weather_date (PK) | temp_max_f | temp_min_f | precipitation_in | 
precipitation_probability | uv_index | weather_code | extracted_at
```

**hourly_weather**
```
hour_id (PK) | weather_timestamp (UNIQUE) | relative_humidity | 
wind_speed_mph | soil_temp_f | soil_moisture | extracted_at
```

**gardening_recommendations**
```
recommendation_id (PK) | weather_date (FK) | frost_alert | heat_alert | 
watering_recommendation | planting_condition | created_at
```

### Setup

Clone the repository:
```bash
git clone https://github.com/corinnemobley/weather-pipeline.git
cd weather-pipeline
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Create PostgreSQL database:
```bash
psql -U postgres -c "CREATE DATABASE garden_weather_db;"
```

Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### Run ETL Pipeline

```bash
python src/etl_pipeline.py
```

Expected output:
```
2026-06-02 14:30:45,123 - INFO - Starting ETL pipeline...
2026-06-02 14:30:45,234 - INFO - Database connection successful
2026-06-02 14:30:45,345 - INFO - Database tables created/verified
2026-06-02 14:30:45,456 - INFO - Extracting data from Open-Meteo API...
2026-06-02 14:30:46,567 - INFO - Successfully extracted weather data from API
2026-06-02 14:30:46,678 - INFO - Transforming data...
2026-06-02 14:30:46,789 - INFO - Data transformation completed successfully
2026-06-02 14:30:47,890 - INFO - Loading data into PostgreSQL...
2026-06-02 14:30:48,901 - INFO - Data loaded successfully into PostgreSQL
2026-06-02 14:30:48,912 - INFO - ✅ ETL PIPELINE COMPLETED SUCCESSFULLY
```

## Automated Scheduling

The pipeline runs automatically via GitHub Actions every day at 6 AM EST.

To set up:
1. Go to **Settings** → **Secrets and Variables** → **Actions**
2. Add repository secrets:
   - `DB_PASSWORD`: Your PostgreSQL password
   - `DB_USER`: Database user (default: `postgres`)
   - `DB_HOST`: Database host (default: `localhost`)
   - `DB_PORT`: Database port (default: `5432`)
   - `DB_NAME`: Database name (default: `garden_weather_db`)

## Query Examples

Check current weather:
```sql
SELECT weather_date, temp_max_f, temp_min_f, precipitation_probability
FROM daily_weather
ORDER BY weather_date DESC
LIMIT 7;
```

Find frost alert days:
```sql
SELECT weather_date, frost_alert, planting_condition
FROM gardening_recommendations
WHERE frost_alert = TRUE
ORDER BY weather_date;
```

Analyze soil moisture trend:
```sql
SELECT DATE(weather_timestamp), AVG(soil_moisture) as avg_moisture
FROM hourly_weather
GROUP BY DATE(weather_timestamp)
ORDER BY DATE DESC
LIMIT 30;
```

## Configuration

### Change Location
Edit `src/etl_pipeline.py`:
```python
extract_weather(latitude=YOUR_LAT, longitude=YOUR_LONG)
```

Or via environment variables:
```bash
export LATITUDE=40.7128
export LONGITUDE=-74.0060
```

### Change Refresh Schedule
Edit `.github/workflows/weather-etl.yml`:
```yaml
schedule:
  - cron: '0 11 * * *'  # Currently: 11 AM UTC = 6 AM EST
```

## Project Structure

```
weather-pipeline/
├── src/
│   └── etl_pipeline.py          # Main ETL script
│   └── dashboard.py             # Dashboard
├── .github/
│   └── workflows/
│       └── weather-etl.yml      # Automated pipeline trigger
├── .env.example                 # Environment template
├── ER_diagram.md                # Entity Relationship Diagram
├── README.md                    # This file
├── data_sources.md              # Data source
├── project_proposal.md          # Initial project proposal
└── requirements.txt             # Python dependencies
```

## Troubleshooting

### Error: "connection refused"
```bash
# Check if PostgreSQL is running
psql -U postgres -c "SELECT 1;"
```

### Error: "DB_PASSWORD not set"
```bash
# Ensure .env exists and has DB_PASSWORD
cat .env
```

### Error: "No such table"
```bash
# Check if tables were created
psql -U postgres -d garden_weather_db -c "\dt"
```

## Logging

Logs are printed to console. For persistent logs:
```bash
python src/etl_pipeline.py >> logs/etl_$(date +%Y%m%d_%H%M%S).log 2>&1
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| requests | 2.31.0 | HTTP requests to Open-Meteo API |
| pandas | 2.1.4 | Data transformation and cleaning |
| sqlalchemy | 2.0.23 | ORM and database queries |
| psycopg2 | 2.9.9 | PostgreSQL adapter |
| python-dotenv | 1.0.0 | Environment variable management |

## Future Improvements

- [ ] Multi-location weather tracking
- [ ] Historical weather archive (30+ years)
- [ ] Machine learning predictions
- [ ] Slack/email alerts
- [ ] REST API for dashboard queries
- [ ] Docker containerization
- [ ] AWS/Azure cloud deployment
