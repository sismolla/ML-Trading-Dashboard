import MetaTrader5 as mt5
import json
import os
import time
from datetime import datetime, timedelta, timezone
import sys
import MetaTrader5 as mt5
import pandas as pd

class positionHandeler:
    def __init__(self,volume=0.01,tp = 40,sl=15,symbol='XAUUSDm',pos_type= 'buy',file_name = 'tickets.json'):
        self.volume = volume
        self.tp = tp
        self.sl = sl
        self.symbol = symbol
        self.pos_type = pos_type
        self.file_name = file_name

    def place_order_and_save_ticket(self):
        if not mt5.initialize():
            print("❌ Initialization failed")
            return

        if not mt5.symbol_select(self.symbol, True):
            print(f"❌ Symbol {self.symbol} not available")
            mt5.shutdown()
            return

        info = mt5.symbol_info(self.symbol)
        tick = mt5.symbol_info_tick(self.symbol)
        if not info or not tick:
            print("❌ Failed to get symbol info or tick")
            mt5.shutdown()
            return

        # Adjust pip value dynamically based on symbol decimals
        price = tick.ask if self.pos_type == "buy" else tick.bid
        digits = info.digits
        pip = 1.0

        # Check minimum lot size
        min_lot = info.volume_min
        if self.volume < min_lot:
            print(f"❌ Lot size too small (min: {min_lot})")
            mt5.shutdown()
            return

        price = tick.ask if self.pos_type == "buy" else tick.bid
        sl = price - self.sl * pip if self.pos_type == "buy" else price + self.sl * pip
        tp = price + self.tp * pip if self.pos_type == "buy" else price - self.tp * pip

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.volume,
            "type": mt5.ORDER_TYPE_BUY if self.pos_type == "buy" else mt5.ORDER_TYPE_SELL,
            "price": round(price, digits),
            "sl": round(sl, digits),
            "tp": round(tp, digits),
            "deviation": 10,
            "magic": 123456,
            "comment": "Python MT5 order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Trade opened! Ticket: {result.order}")
            
            # Load existing tickets or create new list
            if os.path.exists(self.file_name):
                with open(self.file_name, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {"tickets": []}
            else:
                data = {"tickets": []}
            
            # Append new trade (with full details)
            new_trade = {
                "ticket": result.order,
                "symbol": self.symbol,
                "type": self.pos_type,
                "lot": self.volume,
                "open_price": round(price, digits),
                "sl": round(sl, digits),
                "tp": round(tp, digits),
                "timestamp": str(mt5.symbol_info_tick(self.symbol).time)
            }
            data["tickets"].append(new_trade)
            
            # Save updated data
            with open(self.file_name, "w") as f:
                json.dump(data, f, indent=4)
        else:
            print(f"❌ Trade failed: {result.retcode} | message: {result.comment}")

        mt5.shutdown()

    def close_trades_by_tickets(self):
        if not mt5.initialize():
            print("❌ MT5 initialization failed")
            return False

        try:
            with open(self.file_name, "r") as f:
                tickets_data = json.load(f)
            stored_tickets = [trade["ticket"] for trade in tickets_data.get("tickets", [])]
        except (FileNotFoundError, json.JSONDecodeError):
            print("❌ No tickets file or invalid format")
            mt5.shutdown()
            return False

        if not stored_tickets:
            print("ℹ️ No tickets found in the file")
            mt5.shutdown()
            return True

        # Get all open positions
        open_positions = mt5.positions_get()
        if open_positions is None:
            print("ℹ️ No open positions found")
            mt5.shutdown()
            return True

        # Close positions that match stored tickets
        closed_count = 0
        for position in open_positions:
            if position.ticket in stored_tickets:
                symbol = position.symbol
                price = mt5.symbol_info_tick(symbol).bid if position.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(symbol).ask

                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": position.ticket,
                    "symbol": symbol,
                    "volume": position.volume,
                    "type": mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                    "price": price,
                    "deviation": 10,
                    "magic": position.magic,
                    "comment": f"Closed by script",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                result = mt5.order_send(close_request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"✅ Closed position {position.ticket} ({symbol})")
                    closed_count += 1
                else:
                    print(f"❌ Failed to close {position.ticket}: {result.comment}")

        print(f"📊 Total closed: {closed_count}/{len(stored_tickets)}")
        mt5.shutdown()
        return closed_count > 0
    
    def format_duration(self,seconds):
        """Formats seconds into HH:MM:SS string."""
        minutes, sec = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m {sec}s"

    def wait_until_next_h4_close_and_return_true(self):
        """
        Sleeps until the next 4-hour candle close time (UTC) and returns True.
        H4 closes at: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
        """
        now_utc = datetime.now(timezone.utc)
        print(f"\n🕒 Current UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")

        # Determine next H4 close
        block_start_hour = (now_utc.hour // 4) * 4
        current_block_start = now_utc.replace(hour=block_start_hour, minute=0, second=0, microsecond=0)
        next_close = current_block_start + timedelta(hours=4)
        if now_utc >= next_close:
            next_close += timedelta(hours=4)

        # Calculate and format wait time
        seconds_to_wait = (next_close - now_utc).total_seconds()
        formatted_time = self.format_duration(seconds_to_wait)

        print(f"⏳ Waiting {formatted_time} (until {next_close.strftime('%Y-%m-%d %H:%M:%S')} UTC)...")

        time.sleep(seconds_to_wait)

        print(f"\n✅ H4 candle closed at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return True
    

    def mt5_downloader(self,timeframe):
        symbol = 'XAUUSDm'
        num_bars = 10

        if not mt5.initialize():
            print("❌ MT5 initialization failed.")
            mt5.shutdown()
            return pd.DataFrame()


        if not mt5.symbol_select(symbol, True):
            print(f"❌ Symbol '{symbol}' not found or not visible in Market Watch.")
            mt5.shutdown()
            return pd.DataFrame()

        candles = mt5.copy_rates_from_pos(symbol, timeframe, 1, num_bars)

        if candles is None:
            print("❌ Failed to retrieve data.")
            mt5.shutdown()
            return pd.DataFrame()

        data = pd.DataFrame(candles)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        data.drop(columns=['real_volume'], inplace=True)

        print(f"\n✅ Downloaded {len(data)} candles for {symbol} on {timeframe}.")

        mt5.shutdown()

        return data

    def main(self):
        while True:
            if self.wait_until_next_h4_close_and_return_true():
                time.sleep(1.5)
                df = self.mt5_downloader(mt5.TIMEFRAME_D1)
                df = df.rename(columns={'time': 'Time', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'})
                last = df.iloc[[-1]]
                current_time = str(last['Time'].values[0])
                
                with open('time_checking.txt', 'r') as f:
                    previous_time = f.read()

                if current_time != previous_time:
                    with open('time_checking.txt', 'w') as f:
                        f.write(current_time)
                    
                    print("📈 Now it's time to run trading model or logic.")
                    self.close_trades_by_tickets()
                    self.place_order_and_save_ticket()
                    break  # ✅ exit loop after action
                else:
                    print("⏳ Data not updated yet. Waiting 2 seconds...")
                    time.sleep(1)



