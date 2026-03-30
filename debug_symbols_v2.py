import yfinance as yf  # type: ignore

symbols_to_test = {
    "00888": ["00888.TW", "00888.TWO"],
    "00945B": ["00945B.TW", "00945B.TWO"],
    "6190": ["6190.TW", "6190.TWO"]
}

print("Testing yfinance for multiple suffixes:")
for base, variants in symbols_to_test.items():
    print(f"\n=== {base} ===")
    for sym in variants:
        print(f"  Testing {sym}: ", end="", flush=True)
        tkr = yf.Ticker(sym)
        try:
            # Try history first as it's more reliable for checking existence
            hist = tkr.history(period="5d")
            if not hist.empty:
                last_price = hist['Close'].iloc[-1]
                print(f"[SUCCESS] Price: {last_price:.2f}")
            else:
                print("[EMPTY] No history data")
        except Exception as e:
            print(f"[ERROR] {e}")
