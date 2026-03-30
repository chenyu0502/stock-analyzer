import urllib.request
import json
import time

def debug_mis_keys(ch):
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ch}&_={int(time.time()*1000)}"
    print(f"Testing {ch}: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            msg = data.get('msgArray', [])
            if msg:
                print(f"Raw Entry for {ch}: {msg[0]}")
            else:
                print(f"No msgArray for {ch}")
    except Exception as e:
        print(f"Error for {ch}: {e}")

debug_mis_keys("otc_8110.tw")
debug_mis_keys("tse_2330.tw")
