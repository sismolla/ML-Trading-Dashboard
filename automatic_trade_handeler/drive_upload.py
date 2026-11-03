import sys
import MetaTrader5 as mt5
import pandas as pd

def mt5_downloader(timeframe, symbol='XAUUSDm', num_bars=100000, output_file='xauusd_data.csv'):
    """
    Downloads historical candle data from MT5 and saves to a CSV file.

    Args:
        timeframe: MT5 timeframe constant (e.g. mt5.TIMEFRAME_M1).
        symbol (str): Symbol to download (default: 'XAUUSDm').
        
        num_bars (int): Number of candles to download.
        output_file (str): CSV file name to save.

    Returns:
        pd.DataFrame: DataFrame of OHLCV data.
    """

    if not mt5.initialize():
        print("❌ MT5 initialization failed.")
        mt5.shutdown()
        return pd.DataFrame()

    if not mt5.symbol_select(symbol, True):
        print(f"❌ Symbol '{symbol}' not found or not visible in Market Watch.")
        mt5.shutdown()
        return pd.DataFrame()

    candles = mt5.copy_rates_from_pos(symbol, timeframe, 1, num_bars)

    if candles is None or len(candles) == 0:
        print("❌ Failed to retrieve data.")
        mt5.shutdown()
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.drop(columns=['real_volume'], inplace=True)

    # Save to CSV
    df.to_csv(output_file, index=False)
    print(f"✅ Downloaded {len(df)} candles for {symbol} at timeframe {timeframe}.")
    print(f"💾 Saved to file: {output_file}")

    mt5.shutdown()
    return df

# === Run it as a script ===
if __name__ == "__main__":
    from MetaTrader5 import TIMEFRAME_H4
    mt5_downloader(TIMEFRAME_H4)
