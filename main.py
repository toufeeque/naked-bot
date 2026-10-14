import os
import json
from fastapi import FastAPI, Request, HTTPException
from binance.client import Client
from binance.enums import *

app = FastAPI(title="Naked Scalper Webhook Bridge")

# Binance API Credentials from Environment Variables
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
IS_TESTNET = os.getenv("IS_TESTNET", "true").lower() == "true"

# Initialize Binance Client (Handles both Testnet and Live)
client = Client(API_KEY, API_SECRET, testnet=IS_TESTNET)

@app.get("/")
def home():
    return {
        "status": "ONLINE",
        "system": "Naked Scalper Pro V11 Bridge",
        "mode": "TESTNET (Paper Trading)" if IS_TESTNET else "LIVE (Real Money)"
    }

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        body = await request.body()
        data = json.loads(body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = data.get("action")
    raw_symbol = data.get("symbol", "BTCUSDT")
    symbol = raw_symbol.replace(".P", "").replace("BINANCE:", "").replace("BYBIT:", "")
    price = float(data.get("price", 0.0))
    sl = float(data.get("sl", 0.0))
    tp = float(data.get("tp", 0.0))

    try:
        # 1. BUY STOP ENTRY
        if action == "BUY":
            # Entry Stop Market Order
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=price,
                closePosition=False
            )
            # Attached Stop Loss
            sl_order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=sl,
                closePosition=True
            )
            return {"status": "SUCCESS", "action": "BUY_STOP_PLACED", "symbol": symbol, "price": price, "sl": sl}

        # 2. SELL STOP ENTRY
        elif action == "SELL":
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=price,
                closePosition=False
            )
            sl_order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=FUTURE_ORDER_TYPE_STOP_MARKET,
                stopPrice=sl,
                closePosition=True
            )
            return {"status": "SUCCESS", "action": "SELL_STOP_PLACED", "symbol": symbol, "price": price, "sl": sl}

        # 3. DYNAMIC TRAILING STOP UPDATE
        elif action == "UPDATE_SL":
            new_sl = float(data.get("new_sl", 0.0))
            client.futures_cancel_all_open_orders(symbol=symbol)
            positions = client.futures_position_information(symbol=symbol)
            pos_amt = 0.0
            for p in positions:
                if p["symbol"] == symbol:
                    pos_amt = float(p["positionAmt"])
                    break
            
            # Position active hai tabhi new SL lagao
            if pos_amt > 0:
                client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=new_sl,
                    closePosition=True
                )
            elif pos_amt < 0:
                client.futures_create_order(
                    symbol=symbol,
                    side=SIDE_BUY,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=new_sl,
                    closePosition=True
                )
            return {"status": "SUCCESS", "action": "SL_TRAILED", "new_sl": new_sl}

        # 4. CANCEL PENDING ORDERS
        elif action == "CANCEL":
            client.futures_cancel_all_open_orders(symbol=symbol)
            return {"status": "SUCCESS", "action": "ORDERS_CANCELLED"}

    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
