# ML Trading Dashboard

A comprehensive machine learning-based trading dashboard for MetaTrader 5, featuring automated trading, prediction models, and performance analytics.

## Features

- **Automated Trading System**: Execute trades based on ML predictions with automatic stop-loss and take-profit management
- **ML Prediction Models**: Ensemble of LightGBM, CatBoost, and XGBoost classifiers for market direction prediction
- **Technical Indicators**: RSI, MACD, Bollinger Bands, ATR, Stochastic, and Smart Money Concepts (SMC)
- **Django Dashboard**: Web-based interface for monitoring predictions, performance metrics, and backtesting
- **Multi-Timeframe Analysis**: Supports D1, H4, H2, H1, M30, M15 timeframes
- **Performance Tracking**: Win/loss analysis, probability distributions, and symbol/timeframe performance matrices

## Project Structure

```
ml_dashboard/
├── automatic_trade_handeler/      # Automated trading module
│   ├── main_model.py              # ML model training and prediction
│   ├── runner.py                  # Main trading execution script
│   ├── positionHandeler.py        # Position management and order execution
│   ├── feauters.py                # Feature engineering
│   └── drive_upload.py            # MT5 data downloader
│
├── model_dashboard/               # Django web application
│   ├── dashboard/                 # Main dashboard app
│   │   ├── Ml_model.py           # ML model with multi-timeframe support
│   │   ├── views.py              # Django views and API endpoints
│   │   ├── models.py             # Database models
│   │   ├── forms.py              # Form definitions
│   │   ├── urls.py               # URL routing
│   │   ├── SmartMoneyZones.py    # SMC analysis
│   │   ├── runner.py             # Model runner script
│   │   └── templates/            # HTML templates
│   │
│   ├── profiteHandler/            # Profit tracking app
│   │   ├── main_model.py         # ML model for profit handler
│   │   ├── views.py              # Profit dashboard views
│   │   ├── models.py             # Database models
│   │   └── templates/            # HTML templates
│   │
│   └── model_dashboard/           # Django project settings
│       ├── settings.py
│       ├── urls.py
│       └── wsgi.py
│
├── main.html                      # Main dashboard UI
├── page.html                      # Secondary page
├── style.css                      # Stylesheets
├── tickets.json                   # Trade ticket storage
└── README.md                      # This file
```

## Requirements

### Python Dependencies
```bash
pip install Django
pip install MetaTrader5
pip install pandas
pip install numpy
pip install scikit-learn
pip install lightgbm
pip install catboost
pip install xgboost
pip install ta
pip install plotly
pip install pytz
```

### MetaTrader 5
- MetaTrader 5 terminal installed and running
- Trading account with API access enabled
- Symbols added to Market Watch (e.g., XAUUSDm, EURUSDm)

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd ml_dashboard
```

2. **Install Python dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure Django**
```bash
cd model_dashboard
python manage.py migrate
python manage.py createsuperuser
```

4. **Set up MetaTrader 5**
- Open MT5 terminal
- Enable "Allow algorithmic trading" in Tools > Options > Expert Advisors
- Add desired symbols to Market Watch

## Usage

### Running the Django Dashboard

```bash
cd model_dashboard
python manage.py runserver
```

Access the dashboard at `http://localhost:8000`

### Running Automated Trading

```bash
cd automatic_trade_handeler
python runner.py
```

### Downloading Historical Data

```bash
cd automatic_trade_handeler
python drive_upload.py
```

## Configuration

### Symbol Settings
Edit the following files to change trading symbols:
- `automatic_trade_handeler/runner.py`: Change `symbol='XAUUSDm'`
- `automatic_trade_handeler/positionHandeler.py`: Change default symbol
- `model_dashboard/dashboard/runner.py`: Update symbol parameters

### Timeframe Settings
Supported timeframes:
- `mt5.TIMEFRAME_D1` - Daily
- `mt5.TIMEFRAME_H4` - 4 Hour
- `mt5.TIMEFRAME_H2` - 2 Hour
- `mt5.TIMEFRAME_H1` - 1 Hour
- `mt5.TIMEFRAME_M30` - 30 Minute
- `mt5.TIMEFRAME_M15` - 15 Minute

### Risk Management
Edit `positionHandeler.py` to adjust:
- `volume`: Lot size (default: 0.01)
- `sl`: Stop-loss in pips (default: 15)
- `tp`: Take-profit in pips (default: 40)

## ML Model Details

### Features
- **Technical Indicators**: SMA, EMA, RSI, MACD, Bollinger Bands, ATR
- **Volume Indicators**: OBV, VWAP, A/D Line, CMF, PVT, MFI
- **Smart Money Concepts**: Fair Value Gaps (FVG), Order Blocks (OB), Liquidity
- **Market Sessions**: Asian, London, New York session flags
- **Candlestick Patterns**: Engulfing, Break of Structure (BOS)

### Ensemble Model
The system uses an ensemble of three classifiers:
1. **LightGBM**: Gradient boosting with 50 estimators
2. **CatBoost**: Gradient boosting with categorical feature support
3. **XGBoost**: Extreme gradient boosting

The final prediction is the average probability of all three models.

## Dashboard Features

### Main Dashboard
- Model launch form with symbol and timeframe selection
- Real-time log viewer for model training progress
- Prediction history with timestamps

### Trading Dashboard
- Win/loss distribution chart
- Performance by timeframe
- Probability distribution histogram
- Symbol performance matrix
- Recent predictions with countdown timers

### Smart Money Dashboard
- Trend direction indicators
- Entry signals with confluence scores
- Liquidity sweep detection
- Order block identification
- Fair Value Gap markers

## Risk Warnings

⚠️ **IMPORTANT**: This software is for educational and research purposes only.

- Trading involves substantial risk of loss
- Past performance does not guarantee future results
- Always test strategies on demo accounts first
- Never risk more than you can afford to lose
- The authors are not responsible for any financial losses

## Troubleshooting

### MT5 Connection Issues
- Ensure MT5 terminal is running
- Check if symbol is added to Market Watch
- Verify "Allow algorithmic trading" is enabled

### Django Database Issues
```bash
python manage.py migrate --run-syncdb
```

### Model File Not Found
- Ensure the trained model file exists at the specified path
- Train a new model using the dashboard's model launch feature

### Memory Issues
- Reduce `num_bars` parameter in model initialization
- Close unused applications
- Increase system RAM if necessary

## Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is provided as-is for educational purposes.

## Support

For issues and questions:
- Check the troubleshooting section
- Review the code comments
- Open an issue on GitHub

## Changelog

### Version 1.0
- Initial release
- Automated trading system
- Django dashboard
- ML prediction models
- Performance analytics
