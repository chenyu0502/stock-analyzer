import http.server
import socketserver
import json
import os
import subprocess
import sys
import time
import urllib.request
import typing
from pathlib import Path
from urllib.parse import urlparse

# ── 設定 ─────────────────────────────────────────────────────
PORT = 5000
BASE_DIR = Path(__file__).parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
REPORTS_DIR = BASE_DIR / "reports"
PYTHON_SCRIPT = BASE_DIR / "analyze_portfolio.py"

def fetch_tw_stock_name(symbol: str) -> str:
    """嘗試透過多個 API 抓取台灣股票的中文名稱

    查詢順序：
    1. TWSE CodeQuery（上市/上櫃通用）
    2. MIS API otc_（上櫃備援）
    3. MIS API tse_（上市備援）
    """
    print(f"[DEBUG] 正在查詢台股中文名稱: {symbol}")
    # 支援 2330.TW, 8110.TWO, 00720B.TWO 等格式
    symbol_only = symbol.split('.')[0].upper()

    # 簡單過濾：非純數字且字碼 < 4 的通常是美股代號
    if not symbol_only.isdigit() and not any(c.isdigit() for c in symbol_only):
        return ""

    # ── 方法 1：TWSE CodeQuery ────────────────────────────────
    try:
        url = f"https://www.twse.com.tw/zh/api/codeQuery?query={symbol_only}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            suggestions = data.get('suggestions', [])
            for s in suggestions:
                parts = s.split('\t')
                if len(parts) >= 2:
                    code, name = parts[0].strip(), parts[1].strip()
                    if code == symbol_only:
                        print(f"[DEBUG] CodeQuery 成功: {symbol} -> {name}")
                        return name
            print(f"[DEBUG] CodeQuery 無精確匹配: {symbol}")
    except Exception as e:
        print(f"[SERVER] CodeQuery error for {symbol}: {e}")

    # ── 方法 2：MIS API（上櫃 otc_ 優先，再試上市 tse_）────────
    for ex in ("otc", "tse"):
        try:
            ts = int(time.time() * 1000)
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex}_{symbol_only}.tw&_={ts}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                msg = data.get('msgArray', [])
                if msg:
                    name = msg[0].get('n', '').strip()
                    if name:
                        print(f"[DEBUG] MIS ({ex}) 成功: {symbol} -> {name}")
                        return name
        except Exception as e:
            print(f"[SERVER] MIS ({ex}) error for {symbol}: {e}")

    return ""

def fetch_single_quote(symbol: str, entry_price: float, shares: float, name: str) -> dict:
    """快速抓取單支股票的即時行情並計算損益（用於新增股票後即時回傳）"""
    print(f"[DEBUG] 快速查價: {symbol}")
    
    # ── yfinance 延遲載入 (避免 import 時執行 pip 安裝) ───────────
    try:
        import yfinance as yf
    except ImportError:
        print("[SERVER] yfinance 未安裝，正在背景安裝...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
        import yfinance as yf

    def get_data(sym: str) -> tuple[float | None, float | None]:
        try:
            tkr = yf.Ticker(sym)
            info = tkr.fast_info
            p = getattr(info, 'last_price', None)
            pc = getattr(info, 'previous_close', None)
            
            if p is None:
                hist = tkr.history(period='2d', auto_adjust=True)
                if not hist.empty:
                    p = float(hist['Close'].iloc[-1])
                    if len(hist) >= 2:
                        pc = float(hist['Close'].iloc[-2])
            return p, pc
        except Exception:
            return None, None

    try:
        # 1. 嘗試原始代號
        price, prev_close = get_data(symbol)
        
        # 2. 如果失敗，嘗試變體代號
        if price is None:
            variant = ""
            if symbol.endswith(".TW"):
                variant = symbol.replace(".TW", ".TWO")
            elif symbol.endswith(".TWO"):
                variant = symbol.replace(".TWO", ".TW")
            
            if variant:
                print(f"[DEBUG] 嘗試變體代號: {variant}")
                price, prev_close = get_data(variant)

        if price is None:
            return {}

        # ── 計算邏輯 ───────────────────────────────────────────
        price_f: float = float(price)
        price_rounded = round(price_f, 4)  # type: ignore
        
        cost_basis = round(entry_price * shares, 2)  # type: ignore
        market_value = round(price_f * shares, 2)  # type: ignore
        unrealized_pnl = round(market_value - cost_basis, 2)  # type: ignore
        unrealized_pct = round(unrealized_pnl / cost_basis * 100, 2) if cost_basis else 0  # type: ignore

        change: float | None = None
        change_pct: float | None = None
        today_pnl: float | None = None
        
        if prev_close is not None:
            pc_f: float = float(prev_close)
            pc_rounded: float = round(pc_f, 4)  # type: ignore
            
            diff: float = price_f - pc_rounded
            change_f: float = round(diff, 4)  # type: ignore
            change = change_f
            
            if pc_rounded != 0:
                change_pct = round((change_f / pc_rounded) * 100, 2)  # type: ignore
            
            today_pnl = round(change_f * shares, 2)  # type: ignore
            prev_close = pc_rounded

        return {
            "symbol": symbol,
            "name": name,
            "shares": shares,
            "entry_price": entry_price,
            "current_price": price_rounded,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pct": unrealized_pct,
            "today_pnl": today_pnl,
        }
    except Exception as e:
        print(f"[SERVER] fetch_single_quote error for {symbol}: {e}")
        return {}

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path
        
        # 處理 API 請求
        if clean_path == "/api/refresh":
            self.handle_refresh()
        else:
            # 處理靜態檔案
            # 優先從 dashboard 找，若找不到且路徑包含 reports 則從 reports 找
            if clean_path.startswith("/reports/"):
                relative_path = clean_path.lstrip("/") # 移除開頭的 /
                file_path = BASE_DIR / relative_path
            else:
                # 預設從 dashboard 目錄服務
                temp_path = clean_path
                if temp_path == "/":
                    temp_path = "/index.html"
                file_path = DASHBOARD_DIR / temp_path.lstrip("/")
            
            if file_path.exists() and file_path.is_file():
                self.serve_file(file_path)
            else:
                self.send_error(404, f"File Not Found: {clean_path}")

    def handle_refresh(self):
        print(f"\n[SERVER] 收到重新整理請求，執行 {PYTHON_SCRIPT.name}...")
        try:
            # 執行分析腳本
            # 使用 sys.executable 確保使用同一個 Python 環境
            # 強制使用 UTF-8 編碼以解決 Windows 上的 Unicode 編碼問題
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            result = subprocess.run([sys.executable, str(PYTHON_SCRIPT)], 
                                    capture_output=True, text=True, encoding="utf-8", env=env)
            
            if result.returncode == 0:
                print("[SERVER] 分析完成。")
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Connection", "close")
                self.end_headers()
                response = {"status": "success", "message": "Report updated"}
                self.wfile.write(json.dumps(response).encode("utf-8"))
            else:
                print(f"[SERVER] 分析失敗！\nError: {result.stderr}")
                self.send_response(500)
                self.send_header("Connection", "close")
                self.end_headers()
                response = {"status": "error", "message": result.stderr}
                self.wfile.write(json.dumps(response).encode("utf-8"))
        except Exception as e:
            print(f"[SERVER] 發生異常：{e}")
            self.send_response(500)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self):
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path

        if clean_path == "/api/stocks":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_error(400, "Empty request body")
                return
            
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

            symbol = data.get("symbol", "").strip().upper()
            shares = data.get("shares")
            entry_price = data.get("price") 

            if not symbol or shares is None or entry_price is None:
                self.send_error(400, "Missing required fields: symbol, shares, price")
                return

            try:
                shares = float(shares)
                entry_price = float(entry_price)
            except ValueError:
                self.send_error(400, "Invalid number format for shares or price")
                return

            try:
                # 1. 優先嘗試擷取中文名稱 (限台股)
                name = fetch_tw_stock_name(symbol)
                
                # 2. 如果沒抓到 (非台股或 API 失敗)，再用 yfinance 的英文名稱
                if not name:
                    try:
                        import yfinance as yf
                    except ImportError:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
                        import yfinance as yf
                    tkr = yf.Ticker(symbol)
                    info = tkr.info
                    name = info.get("shortName") or info.get("longName") or "未知"
            except Exception as e:
                print(f"[SERVER] Failed to fetch name for {symbol}: {e}")
                name = "未知"

            stocks_json_path = BASE_DIR / "stocks.json"
            try:
                with open(stocks_json_path, encoding="utf-8-sig") as f:
                    stocks_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                try:
                    with open(stocks_json_path, encoding="cp950") as f:
                        stocks_data = json.load(f)
                except Exception:
                    stocks_data = {"holdings": []}

            if not isinstance(stocks_data, dict):
                stocks_data = {"holdings": []}
                
            stocks_data = typing.cast(typing.Dict[str, typing.Any], stocks_data)

            if "holdings" not in stocks_data:
                stocks_data["holdings"] = []

            for h in stocks_data["holdings"]:
                if h["symbol"] == symbol:
                    h["shares"] = shares
                    h["entry_price"] = entry_price
                    h["name"] = name
                    break
            else:
                stocks_data["holdings"].append({
                    "symbol": symbol,
                    "name": name,
                    "shares": shares,
                    "entry_price": entry_price
                })

            with open(stocks_json_path, "w", encoding="utf-8") as f:
                json.dump(stocks_data, f, ensure_ascii=False, indent=2)

            # ── 即時抓取該股現價（只查一支，約 2-3 秒）──────
            quote = fetch_single_quote(symbol, entry_price, shares, name)
            print(f"[SERVER] 股票已儲存並查價完成: {symbol} -> {quote.get('current_price', 'N/A')}")

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": "Stock added/updated successfully",
                "quote": quote
            }, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path

        if clean_path == "/api/stocks":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_error(400, "Empty request body")
                return
            
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

            symbol = data.get("symbol", "").strip()
            if not symbol:
                self.send_error(400, "Missing symbol")
                return

            stocks_json_path = BASE_DIR / "stocks.json"
            try:
                with open(stocks_json_path, encoding="utf-8-sig") as f:
                    stocks_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                try:
                    with open(stocks_json_path, encoding="cp950") as f:
                        stocks_data = json.load(f)
                except Exception:
                    stocks_data = {"holdings": []}

            if not isinstance(stocks_data, dict):
                stocks_data = {"holdings": []}

            stocks_data = typing.cast(typing.Dict[str, typing.Any], stocks_data)

            if "holdings" in stocks_data:
                stocks_data["holdings"] = [h for h in stocks_data["holdings"] if h["symbol"] != symbol]
                with open(stocks_json_path, "w", encoding="utf-8") as f:
                    json.dump(stocks_data, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Stock deleted successfully"}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, file_path):
        self.send_response(200)
        # 根據副檔名設定 Content-Type
        if file_path.suffix == ".html":
            self.send_header("Content-type", "text/html")
        elif file_path.suffix == ".js":
            self.send_header("Content-type", "application/javascript")
        elif file_path.suffix == ".css":
            self.send_header("Content-type", "text/css")
        elif file_path.suffix == ".json":
            self.send_header("Content-type", "application/json")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

class ReusableHTTPServer(http.server.HTTPServer):
    """
    自定義 HTTPServer 以允許立即重複使用位址。
    這樣可以避免在重新啟動伺服器時出現 [WinError 10048] (通訊埠已被占用) 的錯誤。
    """
    allow_reuse_address = True

def main():
    # 確保切換到正確的工作目錄
    os.chdir(BASE_DIR)
    
    # 使用自定義的 ReusableHTTPServer 啟動伺服器
    with ReusableHTTPServer(("", PORT), DashboardHandler) as httpd:
        print(f"==================================================")
        print(f"  Antigravity Dashboard Server 已啟動")
        print(f"  網址: http://localhost:{PORT}")
        print(f"  按下 Ctrl+C 可停止伺服器")
        print(f"==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[SERVER] 伺服器已停止。")
            httpd.server_close()

if __name__ == "__main__":
    main()
