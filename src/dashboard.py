"""
Weather Pipeline Analytics Dashboard (MVP)
===========================================

A Plotly Dash-based interactive analytics dashboard that visualizes weather data
and gardening recommendations from the PostgreSQL database.

Features:
- Real-time data visualization
- Interactive charts and filters
- Business insights for gardeners
- Responsive design
- Live database connectivity
"""

import os
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

class DatabaseConnection:
    """Handles all database operations for the dashboard."""
    
    def __init__(self):
        """Initialize database connection from environment variables."""
        load_dotenv()
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = os.getenv("DB_PORT", "5432")
        self.database = os.getenv("DB_NAME", "postgres")
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD")
        
        if not self.password:
            raise ValueError("DB_PASSWORD environment variable not set")
        
        logger.info(f"Database configuration loaded: {self.host}:{self.port}/{self.database}")
    
    def get_connection(self):
        """Create and return a database connection."""
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            logger.info("Database connection established")
            return conn
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise
    
    def query_daily_weather(self):
        """Fetch daily weather data from database."""
        try:
            conn = self.get_connection()
            query = """
            SELECT * FROM daily_weather 
            ORDER BY weather_date DESC
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty:
                logger.warning("No daily weather data found in database")
                return pd.DataFrame()
            
            logger.info(f"Fetched {len(df)} daily weather records")
            return df
        except Exception as e:
            logger.error(f"Error fetching daily weather: {str(e)}")
            return pd.DataFrame()
    
    def query_hourly_weather(self):
        """Fetch hourly weather data from database."""
        try:
            conn = self.get_connection()
            query = """
            SELECT * FROM hourly_weather 
            ORDER BY weather_timestamp DESC
            LIMIT 168
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty:
                logger.warning("No hourly weather data found in database")
                return pd.DataFrame()
            
            logger.info(f"Fetched {len(df)} hourly weather records")
            return df
        except Exception as e:
            logger.error(f"Error fetching hourly weather: {str(e)}")
            return pd.DataFrame()
    
    def query_recommendations(self):
        """Fetch gardening recommendations from database."""
        try:
            conn = self.get_connection()
            query = """
            SELECT * FROM gardening_recommendations 
            ORDER BY weather_date DESC
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty:
                logger.warning("No recommendations found in database")
                return pd.DataFrame()
            
            logger.info(f"Fetched {len(df)} recommendations")
            return df
        except Exception as e:
            logger.error(f"Error fetching recommendations: {str(e)}")
            return pd.DataFrame()


# ============================================================================
# DATA PROCESSING & ANALYTICS
# ============================================================================

class DataAnalytics:
    """Processes and analyzes weather data for insights."""
    
    def __init__(self, db_connection):
        """Initialize with database connection."""
        self.db = db_connection
        self.daily_data = None
        self.hourly_data = None
        self.recommendations = None
        self.load_data()
    
    def load_data(self):
        """Load all data from database."""
        logger.info("Loading data from database...")
        self.daily_data = self.db.query_daily_weather()
        self.hourly_data = self.db.query_hourly_weather()
        self.recommendations = self.db.query_recommendations()
        self.daily_data['weather_date'] = pd.to_datetime(self.daily_data['weather_date'])
        self.daily_data = self.daily_data.sort_values('weather_date')
        
        logger.info("Data loaded successfully")
    
    def refresh_data(self):
        """Refresh data from database."""
        logger.info("Refreshing data from database...")
        self.load_data()
    
    def get_current_weather(self):
        """Get the most recent weather data."""
        if self.daily_data.empty:
            return {
                'date': 'No Data',
                'temp_max': 'N/A',
                'temp_min': 'N/A',
                'precipitation': 'N/A'
            }
        
        latest = self.daily_data.sort_values('weather_date').iloc[-1]
        return {
            'date': pd.to_datetime(latest['weather_date']).strftime('%A, %B %d, %Y'),
            'temp_max': f"{latest['temp_max_f']:.1f}°F",
            'temp_min': f"{latest['temp_min_f']:.1f}°F",
            'precipitation': f"{latest['precipitation_in']:.2f}in"
        }
    
    def get_frost_alerts(self):
        """Count frost alert days."""
        if self.recommendations.empty:
            return 0
        return (self.recommendations['frost_alert'] == True).sum()
    
    def get_heat_alerts(self):
        """Count heat alert days."""
        if self.recommendations.empty:
            return 0
        return (self.recommendations['heat_alert'] == True).sum()
    
    def get_avg_temperature(self):
    """Calculate average temperature as the midpoint between highs and lows."""
    if self.daily_data.empty:
        return 'N/A'
    
    # True average: (sum of all temps) / (number of temps)
    total_temps = (self.daily_data['temp_max_f'].sum() + 
                   self.daily_data['temp_min_f'].sum())
    count_temps = len(self.daily_data) * 2  # 2 temps per day (high + low)
    avg = total_temps / count_temps
    return f"{avg:.1f}°F"
    
    def get_total_precipitation(self):
        """Calculate total precipitation."""
        if self.daily_data.empty:
            return 'N/A'
        total = self.daily_data['precipitation_in'].sum()
        return f"{total:.2f}in"


# ============================================================================
# DASH APPLICATION SETUP
# ============================================================================

# Initialize database and analytics
try:
    db = DatabaseConnection()
    analytics = DataAnalytics(db)
except Exception as e:
    logger.error(f"Failed to initialize application: {str(e)}")
    analytics = None

# Initialize Dash app with Bootstrap theme
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

app.title = "Weather Pipeline Analytics Dashboard"

# ============================================================================
# DASHBOARD LAYOUT
# ============================================================================

app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col([
            html.H1("🌦️ Weather Pipeline Analytics Dashboard", 
                   className="mb-2 mt-4 text-primary"),
            html.P("Real-time weather data and gardening recommendations",
                  className="text-muted")
        ], width=12)
    ]),
    
    html.Hr(),
    
    # Key Metrics Row
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4("Current Weather", className="card-title"),
                    html.P(id="current-date", className="text-muted small"),
                    html.Div(id="current-weather-content")
                ])
            ])
        ], md=3),
        
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4("Frost Alerts", className="card-title"),
                    html.H2(id="frost-count", children="0", className="text-danger"),
                    html.P("Days with frost risk (temp < 36°F)", className="text-muted small")
                ])
            ])
        ], md=3),
        
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4("Heat Alerts", className="card-title"),
                    html.H2(id="heat-count", children="0", className="text-warning"),
                    html.P("Days with heat stress (temp > 90°F)", className="text-muted small")
                ])
            ])
        ], md=3),
        
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4("Avg Temperature", className="card-title"),
                    html.H2(id="avg-temp", children="N/A", className="text-info"),
                    html.P("7-day average", className="text-muted small")
                ])
            ])
        ], md=3),
    ], className="mb-4"),
    
    # Charts Row 1
    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-1",
                type="default",
                children=[
                    dcc.Graph(id="temp-range-chart")
                ]
            )
        ], md=6),
        
        dbc.Col([
            dcc.Loading(
                id="loading-2",
                type="default",
                children=[
                    dcc.Graph(id="precipitation-chart")
                ]
            )
        ], md=6),
    ], className="mb-4"),
    
    # Charts Row 2
    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-3",
                type="default",
                children=[
                    dcc.Graph(id="uv-index-chart")
                ]
            )
        ], md=6),
        
        dbc.Col([
            dcc.Loading(
                id="loading-4",
                type="default",
                children=[
                    dcc.Graph(id="alerts-breakdown")
                ]
            )
        ], md=6),
    ], className="mb-4"),
    
    # Hourly Data
    dbc.Row([
        dbc.Col([
            dcc.Loading(
                id="loading-5",
                type="default",
                children=[
                    dcc.Graph(id="hourly-humidity-chart")
                ]
            )
        ], md=12),
    ], className="mb-4"),
    
    # Recommendations Table
    dbc.Row([
        dbc.Col([
            html.H3("Gardening Recommendations", className="mt-4 mb-3"),
            html.Div(id="recommendations-table")
        ], md=12)
    ], className="mb-4"),
    
    # Footer
    dbc.Row([
        dbc.Col([
            html.Hr(),
            html.P(
                [
                    html.Small(
                        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ",
                        id="update-time"
                    ),
                    html.Small(
                        html.Button(
                            "Refresh Data",
                            id="refresh-button",
                            className="btn btn-sm btn-outline-primary"
                        ),
                        className="ms-2"
                    )
                ],
                className="text-muted text-center"
            )
        ], md=12)
    ]),
    
    # Store for refresh callback
    dcc.Interval(
        id='interval-component',
        interval=300000,  # Refresh every 5 minutes
        n_intervals=0
    ),
    
    dcc.Store(id='refresh-store', data=0)
    
], fluid=True, style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh'})


# ============================================================================
# CALLBACKS - Data Updates
# ============================================================================

@app.callback(
    [Output("current-date", "children"),
     Output("current-weather-content", "children"),
     Output("frost-count", "children"),
     Output("heat-count", "children"),
     Output("avg-temp", "children")],
    [Input("interval-component", "n_intervals"),
     Input("refresh-button", "n_clicks")],
    prevent_initial_call=False
)
def update_metrics(n_intervals, n_clicks):
    """Update key metrics from database."""
    try:
        analytics.refresh_data()
        current = analytics.get_current_weather()
        
        weather_content = html.Div([
            html.P(f"High: {current['temp_max']}", className="mb-1"),
            html.P(f"Low: {current['temp_min']}", className="mb-1"),
            html.P(f"Precipitation: {current['precipitation']}")
        ])
        
        return (
            current['date'],
            weather_content,
            str(analytics.get_frost_alerts()),
            str(analytics.get_heat_alerts()),
            analytics.get_avg_temperature()
        )
    except Exception as e:
        logger.error(f"Error updating metrics: {str(e)}")
        return "N/A", "Error loading data", "0", "0", "N/A"


# ============================================================================
# CALLBACKS - Charts
# ============================================================================

@app.callback(
    Output("temp-range-chart", "figure"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_temperature_chart(n_intervals):
    """Generate temperature range chart."""
    try:
        if analytics.daily_data.empty:
            return go.Figure().add_annotation(text="No data available")
        
        df = analytics.daily_data.copy()
        df['weather_date'] = pd.to_datetime(df['weather_date'])
        df = df.sort_values('weather_date')
        
        fig = go.Figure()
        
        # Add temperature range as a shaded area
        fig.add_trace(go.Scatter(
            x=df['weather_date'],
            y=df['temp_max_f'],
            name='High Temperature',
            mode='lines+markers',
            line=dict(color='#FF6B6B', width=2),
            marker=dict(size=6)
        ))
        
        fig.add_trace(go.Scatter(
            x=df['weather_date'],
            y=df['temp_min_f'],
            name='Low Temperature',
            mode='lines+markers',
            line=dict(color='#4ECDC4', width=2),
            marker=dict(size=6),
            fill='tonexty',
            fillcolor='rgba(78, 205, 196, 0.2)'
        ))
        
        # Add frost line
        fig.add_hline(
            y=36,
            line_dash="dash",
            line_color="red",
            annotation_text="Frost Line (36°F)",
            annotation_position="right"
        )
        
        fig.update_layout(
            title="Temperature Forecast (7-Day Range)",
            xaxis_title="Date",
            yaxis_title="Temperature (°F)",
            hovermode='x unified',
            height=400,
            template='plotly_white',
            showlegend=True
        )
        
        return fig
    except Exception as e:
        logger.error(f"Error generating temperature chart: {str(e)}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


@app.callback(
    Output("precipitation-chart", "figure"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_precipitation_chart(n_intervals):
    """Generate precipitation chart."""
    try:
        if analytics.daily_data.empty:
            return go.Figure().add_annotation(text="No data available")
        
        df = analytics.daily_data.copy()
        df['weather_date'] = pd.to_datetime(df['weather_date'])
        df = df.sort_values('weather_date')
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Precipitation bars
        fig.add_trace(
            go.Bar(
                x=df['weather_date'],
                y=df['precipitation_in'],
                name='Precipitation (in)',
                marker=dict(color='#6C63FF'),
                hovertemplate='<b>%{x|%b %d}</b><br>Precipitation: %{y:.2f} in<extra></extra>'
            ),
            secondary_y=False
        )
        
        # Precipitation probability line
        fig.add_trace(
            go.Scatter(
                x=df['weather_date'],
                y=df['precipitation_probability'],
                name='Rain Probability (%)',
                line=dict(color='#FFB627', width=3),
                mode='lines+markers',
                hovertemplate='<b>%{x|%b %d}</b><br>Probability: %{y:.0f}%<extra></extra>'
            ),
            secondary_y=True
        )
        
        fig.update_yaxes(title_text="<b>Precipitation (inches)</b>", secondary_y=False)
        fig.update_yaxes(title_text="<b>Rain Probability (%)</b>", secondary_y=True, range=[0, 100])
        fig.update_xaxes(title_text="Date")
        
        fig.update_layout(
            title="Precipitation Forecast & Rain Probability",
            hovermode='x unified',
            height=400,
            template='plotly_white',
            showlegend=True
        )
        
        return fig
    except Exception as e:
        logger.error(f"Error generating precipitation chart: {str(e)}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


@app.callback(
    Output("uv-index-chart", "figure"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_uv_index_chart(n_intervals):
    """Generate UV index chart."""
    try:
        if analytics.daily_data.empty:
            return go.Figure().add_annotation(text="No data available")
        
        df = analytics.daily_data.copy()
        df['weather_date'] = pd.to_datetime(df['weather_date'])
        df = df.sort_values('weather_date')
        
        # Classify UV index
        uv_colors = df['uv_index'].apply(
            lambda x: '#2ECC71' if x < 3 else (
                '#F39C12' if x < 6 else (
                    '#E67E22' if x < 8 else '#C0392B'
                )
            )
        )
        
        fig = go.Figure(data=[
            go.Bar(
                x=df['weather_date'],
                y=df['uv_index'],
                marker=dict(color=uv_colors),
                hovertemplate='<b>%{x|%b %d}</b><br>UV Index: %{y:.1f}<extra></extra>'
            )
        ])
        
        fig.add_hline(y=8, line_dash="dash", line_color="red", 
                     annotation_text="High Risk (>8)")
        
        fig.update_layout(
            title="UV Index Forecast",
            xaxis_title="Date",
            yaxis_title="UV Index",
            height=400,
            template='plotly_white',
            showlegend=False,
            hovermode='x'
        )
        
        return fig
    except Exception as e:
        logger.error(f"Error generating UV index chart: {str(e)}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


@app.callback(
    Output("alerts-breakdown", "figure"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_alerts_breakdown(n_intervals):
    """Generate alerts breakdown chart."""
    try:
        if analytics.recommendations.empty:
            return go.Figure().add_annotation(text="No data available")
        
        frost_count = (analytics.recommendations['frost_alert'] == True).sum()
        heat_count = (analytics.recommendations['heat_alert'] == True).sum()
        good_days = len(analytics.recommendations) - frost_count - heat_count
        
        fig = go.Figure(data=[
            go.Pie(
                labels=['Good Conditions', 'Frost Risk', 'Heat Risk'],
                values=[good_days, frost_count, heat_count],
                marker=dict(colors=['#2ECC71', '#3498DB', '#E74C3C']),
                hole=.4,
                hovertemplate='<b>%{label}</b><br>Days: %{value}<br>%{percent}<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title="Planting Condition Summary (7-Day)",
            height=400,
            template='plotly_white'
        )
        
        return fig
    except Exception as e:
        logger.error(f"Error generating alerts breakdown: {str(e)}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


@app.callback(
    Output("hourly-humidity-chart", "figure"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_hourly_humidity_chart(n_intervals):
    """Generate hourly humidity and wind chart."""
    try:
        if analytics.hourly_data.empty:
            return go.Figure().add_annotation(text="No data available")
        
        df = analytics.hourly_data.copy()
        df['weather_timestamp'] = pd.to_datetime(df['weather_timestamp'])
        df = df.sort_values('weather_timestamp').tail(72)  # Last 72 hours
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(
            go.Scatter(
                x=df['weather_timestamp'],
                y=df['relative_humidity'],
                name='Humidity (%)',
                line=dict(color='#3498DB', width=2),
                mode='lines',
                hovertemplate='<b>%{x|%b %d %H:%M}</b><br>Humidity: %{y:.0f}%<extra></extra>'
            ),
            secondary_y=False
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['weather_timestamp'],
                y=df['wind_speed_mph'],
                name='Wind Speed (mph)',
                line=dict(color='#E67E22', width=2),
                mode='lines',
                hovertemplate='<b>%{x|%b %d %H:%M}</b><br>Wind: %{y:.1f} mph<extra></extra>'
            ),
            secondary_y=True
        )
        
        fig.update_yaxes(title_text="<b>Humidity (%)</b>", secondary_y=False, range=[0, 100])
        fig.update_yaxes(title_text="<b>Wind Speed (mph)</b>", secondary_y=True)
        fig.update_xaxes(title_text="Date & Time")
        
        fig.update_layout(
            title="Hourly Humidity & Wind Speed (72 Hours)",
            height=400,
            template='plotly_white',
            hovermode='x unified',
            showlegend=True
        )
        
        return fig
    except Exception as e:
        logger.error(f"Error generating hourly chart: {str(e)}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


# ============================================================================
# CALLBACKS - Recommendations Table
# ============================================================================

@app.callback(
    Output("recommendations-table", "children"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_recommendations_table(n_intervals):
    """Generate recommendations table."""
    try:
        if analytics.recommendations.empty:
            return html.P("No recommendations available")
        
        df = analytics.recommendations.copy()
        df['weather_date'] = pd.to_datetime(df['weather_date']).dt.strftime('%b %d, %Y')
        
        # Create table rows
        rows = []
        for _, row in df.iterrows():
            frost_badge = dbc.Badge(
                "FROST RISK", 
                color="danger" if row['frost_alert'] else "success",
                className="me-2"
            )
            
            heat_badge = dbc.Badge(
                "HEAT RISK", 
                color="warning" if row['heat_alert'] else "success",
                className="me-2"
            )
            
            rows.append(
                dbc.Row([
                    dbc.Col(row['weather_date'], md=2),
                    dbc.Col(html.Div([frost_badge]), md=2),
                    dbc.Col(html.Div([heat_badge]), md=2),
                    dbc.Col(row['watering_recommendation'], md=2),
                    dbc.Col(row['planting_condition'], md=2, className="text-info"),
                    dbc.Col(f"{row['temperature_range']:.1f}°F" if pd.notna(row['temperature_range']) else "N/A", md=2),
                ], className="border-bottom py-2")
            )
        
        return dbc.Container([
            dbc.Row([
                dbc.Col("Date", md=2, className="fw-bold"),
                dbc.Col("Frost Alert", md=2, className="fw-bold"),
                dbc.Col("Heat Alert", md=2, className="fw-bold"),
                dbc.Col("Watering", md=2, className="fw-bold"),
                dbc.Col("Planting", md=2, className="fw-bold"),
                dbc.Col("Temp Range", md=2, className="fw-bold"),
            ], className="border-top border-bottom py-2 mb-2 bg-light"),
            *rows
        ], fluid=True)
    except Exception as e:
        logger.error(f"Error generating recommendations table: {str(e)}")
        return html.P(f"Error loading recommendations: {str(e)}")


# ============================================================================
# ERROR HANDLING
# ============================================================================

@app.callback(
    Output("update-time", "children"),
    Input("interval-component", "n_intervals"),
    prevent_initial_call=False
)
def update_timestamp(n_intervals):
    """Update the last refresh timestamp."""
    return f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    if analytics is None:
        logger.error("Failed to initialize analytics. Check database connection.")
        print("ERROR: Could not connect to database. Please check your .env file and database connection.")
    else:
        logger.info("Starting Dash application on http://127.0.0.1:8050")
        print("\n" + "="*70)
        print("Weather Pipeline Analytics Dashboard")
        print("="*70)
        print("\nDashboard is running at: http://127.0.0.1:8050")
        print("\nFeatures:")
        print("  ✓ Real-time weather visualization")
        print("  ✓ Frost and heat alerts")
        print("  ✓ 7-day forecast charts")
        print("  ✓ Gardening recommendations")
        print("  ✓ Interactive data exploration")
        print("\nPress Ctrl+C to stop the server")
        print("="*70 + "\n")
        
        app.run(debug=True, host="127.0.0.1", port=8050)
