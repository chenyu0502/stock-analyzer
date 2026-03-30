import yfinance as yf # type: ignore
import json

symbols = ["00888.TW", "00945B.TWO", "6190.TW"]

print("Testing yfinance for symbols:")
for sym in symbols:
    print(f"\n--- {sym} ---")
    tkr = yf.Ticker(sym)
    
    print("fast_info:")
    try:
        info = tkr.fast_info
        for attr in ["last_price", "previous_close", "currency"]:
            print(f"  {attr}: {getattr(info, attr, 'N/A')}")
    except Exception as e:
        print(f"  [ERROR] fast_info failed: {e}")

    print("history (1m):")
    try:
        hist = tkr.history(period="1d")
        if not hist.empty:
            print(hist.tail())
        else:
            print("  Empty history")
    except Exception as e:
        print(f"  [ERROR] history failed: {e}")
