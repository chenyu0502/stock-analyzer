import urllib.request
import json
import time

def check_otc(symbol_only):
    # Try different combinations for OTC
    variants = [
        f"otc_{symbol_only}.tw",
        f"tse_{symbol_only}.tw",
        f"otc_{symbol_only.upper()}.tw"
    ]
    for ch in variants:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ch}&_={int(time.time()*1000)}"
        print(f"Testing {ch}: {url}")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                msg = data.get('msgArray', [])
                if msg:
                    print(f"SUCCESS with {ch}: {msg[0].get('n')}")
                    return msg[0].get('n')
                else:
                    print(f"No msgArray for {ch}")
        except Exception as e:
            print(f"Error for {ch}: {e}")
    return None

check_otc("8110")
