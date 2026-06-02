# Power BI Integration Guide

## Overview
This document outlines how to connect your PostgreSQL weather database to Power BI for interactive visualization.

## Prerequisites
- Power BI Desktop (free version available)
- PostgreSQL running locally or on a cloud service
- Database credentials

## Connection Steps

### 1. Install PostgreSQL ODBC Driver
- Download: [PostgreSQL ODBC Driver](https://www.postgresql.org/download/windows/)
- Follow installation wizard

### 2. Create PostgreSQL ODBC Data Source
On Windows:
1. Open **ODBC Data Source Administrator** (search in Start Menu)
2. Click **Add** under "User DSN"
3. Select **PostgreSQL Unicode**
4. Configure:
   - **Data Source Name**: `weather-pipeline`
   - **Server**: `localhost` (or your remote host)
   - **Port**: `5432`
   - **Database**: `garden_weather_db`
   - **Username**: `postgres`
   - **Password**: (your DB password)
5. Click **Test** to verify connection
6. Click **Save**

### 3. Connect Power BI to PostgreSQL

#### Option A: Direct ODBC Connection (Recommended for Local)
1. Open **Power BI Desktop**
2. Click **Get Data** → **More**
3. Search for **ODBC**
4. Click **Connect**
5. Select **weather-pipeline** data source
6. Enter credentials if prompted
7. Select tables: `daily_weather`, `hourly_weather`, `gardening_recommendations`
8. Click **Load**

#### Option B: Direct PostgreSQL Connection
1. Open **Power BI Desktop**
2. Click **Get Data** → **More**
3. Search for **PostgreSQL Database**
4. Click **Connect**
5. Enter:
   - **Server**: `localhost`
   - **Database**: `garden_weather_db`
6. Enter credentials
7. Select tables and click **Load**

#### Option C: Cloud-based (Azure PostgreSQL)
If using Azure Database for PostgreSQL:
1. Create PostgreSQL instance in Azure
2. Migrate local database (using `pg_dump` and `pg_restore`)
3. Follow Option B with Azure server address

## Data Model in Power BI

### Tables
- **daily_weather**: Daily forecasts and historical data
- **hourly_weather**: Hourly measurements
- **gardening_recommendations**: Derived alerts and recommendations

### Relationships
```
daily_weather (1) ──→ (M) gardening_recommendations
daily_weather (1) ──→ (M) hourly_weather (on date)
```

### Suggested Measures & Columns
```
Daily Avg Temperature = AVERAGE('daily_weather'[temp_max_f]) + AVERAGE('daily_weather'[temp_min_f]) / 2
Frost Risk Days = COUNTROWS(FILTER('gardening_recommendations', [frost_alert] = TRUE))
High UV Days = COUNTROWS(FILTER('daily_weather', [uv_index] > 8))
```

## Dashboard Ideas

### 1. **Weather Overview**
- Current temperature range (card)
- 7-day forecast line chart (temp min/max)
- Precipitation probability gauge
- UV Index trend

### 2. **Gardening Alerts**
- Frost Alert indicator (red if True)
- Heat Alert indicator (orange if True)
- Watering recommendations list
- Planting condition status

### 3. **Soil & Humidity**
- Soil temperature trend (area chart)
- Soil moisture gauge
- Wind speed time series
- Relative humidity heatmap

### 4. **Historical Analysis**
- Rolling 30-day precipitation total
- Temperature min/max bands
- Weather patterns calendar
- Alerts history

## Refresh Schedule

### Local Data
- Set refresh to manual or hourly via Power BI Desktop
- Export to Power BI Service for cloud sync

### Cloud Data
1. In Power BI Service, go to **Settings** → **Datasets**
2. Select your dataset
3. Click **Scheduled Refresh**
4. Set refresh times (up to 8x daily on Pro)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Connection Failed" | Verify PostgreSQL is running: `psql -U postgres` |
| "Authentication Failed" | Check DB credentials in ODBC/connection settings |
| "Table Not Found" | Ensure ETL pipeline has run; check schema with `\dt` in psql |
| "Slow Refresh" | Add indexes to frequently queried columns (already done for `hourly_weather.weather_timestamp`) |

## Best Practices

✅ **DO:**
- Set up automatic ETL runs via GitHub Actions
- Create separate Power BI workspaces for dev/prod
- Use row-level security if sharing sensitive data
- Schedule refreshes during off-peak hours
- Keep Power BI Desktop and gateway updated

❌ **DON'T:**
- Store plaintext passwords in Power BI
- Share PBIX files with hardcoded credentials
- Use direct SQL queries for every visualization (use datasets)
- Exceed refresh limits on free tier

## Advanced Features

### Real-time Dashboard (Power BI Premium)
If using Power BI Premium, enable DirectQuery mode:
1. In Power BI Desktop: **File** → **Options** → **Power Query Editor**
2. Switch to **DirectQuery** mode
3. Publish to Premium capacity

### Automated Alerts
- Set up Power Automate workflow triggered by frost_alert or heat_alert
- Send email/Teams notification to gardening group

## Next Steps
1. Complete ETL pipeline setup
2. Test local PostgreSQL connection
3. Install ODBC driver
4. Create Power BI prototype dashboard
5. Deploy to Power BI Service and share with stakeholders
