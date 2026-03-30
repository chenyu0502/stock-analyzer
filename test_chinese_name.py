import sys
from pathlib import Path

# Add current dir to sys.path to import from dashboard_server
current_dir = str(Path(__file__).parent.absolute())
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from dashboard_server import fetch_tw_stock_name

def test():
    symbols = ["2330.TW", "0050.TW", "2317.TW", "8110.TWO", "AAPL"]
    for s in symbols:
        name = fetch_tw_stock_name(s)
        print(f"Symbol: {s} -> Name: {name}")

if __name__ == "__main__":
    test()
