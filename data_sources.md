# Data Sources Documentation

## Open-Meteo API

### Overview
**Open-Meteo** is a free, open-source weather API that provides accurate weather forecasts without requiring authentication.

- **URL**: https://api.open-meteo.com/v1/forecast
- **Authentication**: None required
- **Rate Limit**: 10,000 requests/day (sufficient for our use case)
- **Response Format**: JSON

### API Endpoint


### Request Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `latitude` | 38.2527 | Location latitude (Louisville, KY) |
| `longitude` | -85.7585 | Location longitude (Louisville, KY) |
| `daily` | See below | Daily weather metrics to retrieve |
| `hourly` | See below | Hourly weather metrics to retrieve |
| `timezone` | America/New_York | Timezone for timestamps |

### Daily Parameters Extracted

| Field | Description | Unit | Conversion |
|-------|-------------|------|-----------|
| `time` | Date | ISO 8601 | Used as-is |
| `temperature_2m_max` | Daily high temperature | °C | × 9/5 + 32 → °F |
| `temperature_2m_min` | Daily low temperature | °C | × 9/5 + 32 → °F |
| `precipitation_sum` | Total daily precipitation | mm | ÷ 25.4 → inches |
| `precipitation_probability_max` | Max rain probability | % | Used as-is |
| `uv_index_max` | Maximum UV index | Index | Used as-is |
| `weathercode` | WMO weather code | Code | Reference for conditions |

### Hourly Parameters Extracted

| Field | Description | Unit | Conversion |
|-------|-------------|------|-----------|
| `time` | Timestamp | ISO 8601 | Used as-is |
| `relative_humidity_2m` | Air humidity | % | Used as-is |
| `wind_speed_10m` | Wind speed at 10m | km/h | × 0.621371 → mph |
| `soil_temperature_0cm` | Soil surface temperature | °C | × 9/5 + 32 → °F |
| `soil_moisture_0_to_1cm` | Soil water content | m³/m³ | Used as-is |

### Example Response

```json
{
  "latitude": 38.2527,
  "longitude": -85.7585,
  "generationtime_ms": 0.567,
  "utc_offset_seconds": -18000,
  "timezone": "America/New_York",
  "timezone_abbreviation": "EDT",
  "elevation": 202.0,
  "daily": {
    "time": ["2026-06-15", "2026-06-16", ...],
    "temperature_2m_max": [28.5, 29.2, ...],
    "temperature_2m_min": [18.3, 19.1, ...],
    "precipitation_sum": [0.5, 2.3, ...],
    "precipitation_probability_max": [20, 45, ...],
    "uv_index_max": [7.5, 8.2, ...],
    "weathercode": [61, 63, ...]
  },
  "hourly": {
    "time": ["2026-06-15T00:00", "2026-06-15T01:00", ...],
    "relative_humidity_2m": [75, 78, ...],
    "wind_speed_10m": [5.2, 4.8, ...],
    "soil_temperature_0cm": [16.2, 15.8, ...],
    "soil_moisture_0_to_1cm": [0.25, 0.26, ...]
  }
}
