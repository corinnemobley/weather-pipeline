┌─────────────────────────────┐
│        daily_weather        │
├─────────────────────────────┤
│ PK weather_date             │
│ temp_max_f                  │
│ temp_min_f                  │
│ precipitation_in            │
│ precipitation_probability   │
│ uv_index                    │
│ weather_code                │
│ extracted_at                │
└──────────────┬──────────────┘
               │
               │ 1-to-Many
               │
               ▼
┌─────────────────────────────┐
│ gardening_recommendations   │
├─────────────────────────────┤
│ PK recommendation_id        │
│ FK weather_date             │
│ frost_alert                 │
│ heat_alert                  │
│ watering_recommendation     │
│ planting_condition          │
│ temperature_range           │
│ uv_danger                   │
│ created_at                  │
└─────────────────────────────┘


┌─────────────────────────────┐
│       hourly_weather        │
├─────────────────────────────┤
│ PK hour_id                  │
│ weather_timestamp (UNIQUE)  │
│ relative_humidity           │
│ wind_speed_mph              │
│ soil_temp_f                 │
│ soil_moisture               │
│ extracted_at                │
└─────────────────────────────┘
