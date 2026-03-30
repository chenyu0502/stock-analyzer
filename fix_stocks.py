import json
import os

STOCKS_JSON = "stocks.json"

# Detect encoding
encoding = "utf-8-sig"
try:
    with open(STOCKS_JSON, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
except Exception:
    encoding = "cp950"
    with open(STOCKS_JSON, "r", encoding="cp950") as f:
        data = json.load(f)

# Update symbols
mapped_symbols = {
    "00888.TW": "00888.TWO",
    "00945B.TWO": "00945B.TW",
    "6190.TW": "6190.TWO",
    "00888": "00888.TWO",   # Handle case without suffix
    "00945B": "00945B.TW",
    "6190": "6190.TWO"
}

updated = False
for h in data["holdings"]:
    original = h["symbol"]
    if original in mapped_symbols:
        h["symbol"] = mapped_symbols[original]
        print(f"Updated {original} -> {h['symbol']}")
        updated = True
    elif original.endswith(".TW") or original.endswith(".TWO"):
        base = original.split(".")[0]
        if base in mapped_symbols:
            h["symbol"] = mapped_symbols[base]
            print(f"Updated {original} -> {h['symbol']}")
            updated = True

if updated:
    with open(STOCKS_JSON, "w", encoding=encoding) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\nstocks.json updated successfully.")
else:
    print("\nNo updates needed or symbols not found.")
