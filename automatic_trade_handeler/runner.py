from positionHandeler import positionHandeler
import pickle
import os
import MetaTrader5 as mt5
from main_model import ModelLearning

def run():
    model_path = 'C:/Users/HP/Desktop/ml_dashboard/model_dashboard/profiteHandler/trained_model_finalisma.pkl'

    # Check if model file exists
    if not os.path.exists(model_path):
        print(f"❌ Model file not found: {model_path}")
        return

    with open(model_path, 'rb') as file:
        loaded_model = pickle.load(file)

    # Get data
    models = ModelLearning(d1=mt5.TIMEFRAME_H4, symbol='XAUUSDm', num_bars=100000)
    df, X_new_data = models.main()

    # Check if data was retrieved successfully
    if df is None or df.empty:
        print("❌ Failed to retrieve data from MT5")
        return

    last_row = df.iloc[[-1]].copy()
    prediction_features = last_row.drop(columns=['target'])
    print('this is the last row value/////////////',last_row)

    last_row_prediction = loaded_model.predict(prediction_features)
    print(f'last_row prediction: {last_row_prediction[0]}')
    last_row_prediction_prob = loaded_model.predict_proba(prediction_features)

    order_type = 'buy' if last_row_prediction[0] > 0 else 'sell'

    order = positionHandeler(symbol='XAUUSDm', volume=0.01, sl=15, tp=40, pos_type=order_type)
    order.main()

    print(f"✅ Trade executed at: {order_type.upper()} | Prob: {max(last_row_prediction_prob):.2f}")
    

if __name__ == "__main__":
    run()
