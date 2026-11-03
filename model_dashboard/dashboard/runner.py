from Ml_model import ModelLearning 
import MetaTrader5 as mt5

model = ModelLearning(
            d1=mt5.TIMEFRAME_D1,
            d2=mt5.TIMEFRAME_H4,
            d3=mt5.TIMEFRAME_H2,
            floor_time='1D',
            timeframe1='4h',
            timeframe2='2h',
            symbol='XAUUSDm',
            num_bars=100000,
            report = True
        )

model.main()