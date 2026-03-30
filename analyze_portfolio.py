from __future__ import annotations
"""
analyze_portfolio.py
====================
每個交易日 09:00 (早盤) 與 14:30 (盤後) 自動執行。
- 從 stocks.json 讀取持股
- 用 yfinance 抓取即時 / 最新收盤價、漲跌幅
- 用 yfinance .news + Google News RSS 取得 Top 3 新聞
- 計算持股損益
- 輸出 reports/report_YYYYMMDD_HHMM.json 供儀表板讀取
- 同步複製為 reports/latest.json（儀表板常態讀取入口）
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote
from typing import Any, TYPE_CHECKING, List, Dict, cast, Tuple

# ── 套件安裝保護 ─────────────────────────────────────────────
try:
    import yfinance as yf  # type: ignore
except ImportError:
    print("[SETUP] yfinance 未安裝，正在安裝...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
    import yfinance as yf  # type: ignore

import xml.etree.ElementTree as ET

# ── 路徑設定 ─────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
STOCKS_JSON = BASE_DIR / "stocks.json"
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ── 工具函式 ─────────────────────────────────────────────────
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def session_label() -> str:
    hour = datetime.now().hour
    return "早盤" if hour < 12 else "盤後"

def safe_float(val: Any, default: float | None = None) -> float | None:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default

def safe_round(val: Any, ndigits: int = 2) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), ndigits)  # pyre-ignore
    except (TypeError, ValueError):
        return None

# ── 持股讀取 ─────────────────────────────────────────────────
def load_holdings() -> List[Dict[str, Any]]:
    # 嘗試用 utf-8-sig (處理帶 BOM 的 UTF-8) 或 cp950 (處理標準繁體中文)
    try:
        with open(STOCKS_JSON, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        with open(STOCKS_JSON, encoding="cp950") as f:
            data = json.load(f)
    return data["holdings"]

# ── 行情抓取 ─────────────────────────────────────────────────
def fetch_quotes(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    symbols = [h["symbol"] for h in holdings]
    print(f"[INFO] 抓取 {len(symbols)} 支持股行情...")

    # 批次下載（一次 API 呼叫，減少封鎖風險）
    tickers = yf.Tickers(" ".join(symbols))
    results = []

    for h in holdings:
        symbol: str = str(h["symbol"])
        name: str   = str(h["name"])
        shares: float = float(h["shares"])
        entry: float  = float(h["entry_price"])

        # Initialize with None/default
        price, prev_close = None, None
        change, change_pct = None, None
        cost_basis = safe_round(entry * shares, 2) or 0.0
        market_value, unrealized, unrealized_pct, today_pnl = None, None, None, None
        active_symbol = symbol

        try:
            # 優先從批次結果中獲取
            tkr = tickers.tickers[symbol]
            info = tkr.fast_info
            
            # Use safe retrieval for properties that might trigger network calls
            try:
                price = safe_float(getattr(info, "last_price", None))
                prev_close = safe_float(getattr(info, "previous_close", None))
            except Exception:
                price, prev_close = None, None

            # Fallback 1: 如果批次抓取失敗，嘗試用單一 Ticker 與 History
            if price is None:
                try:
                    hist = tkr.history(period="2d", auto_adjust=True)
                    if not hist.empty:
                        price = safe_float(hist["Close"].iloc[-1])
                        if len(hist) >= 2:
                            prev_close = safe_float(hist["Close"].iloc[-2])
                except Exception:
                    pass

            # Fallback 2: 嘗試副檔名切換 (.TW <-> .TWO)
            if price is None:
                variant = ""
                if symbol.endswith(".TW"):
                    variant = symbol.replace(".TW", ".TWO")
                elif symbol.endswith(".TWO"):
                    variant = symbol.replace(".TWO", ".TW")
                
                if variant:
                    try:
                        v_tkr = yf.Ticker(variant)
                        v_info = v_tkr.fast_info
                        price = safe_float(getattr(v_info, "last_price", None))
                        prev_close = safe_float(getattr(v_info, "previous_close", None))
                        
                        if price is None:
                            v_hist = v_tkr.history(period="2d", auto_adjust=True)
                            if not v_hist.empty:
                                price = safe_float(v_hist["Close"].iloc[-1])
                                if len(v_hist) >= 2:
                                    prev_close = safe_float(v_hist["Close"].iloc[-2])
                        
                        if price is not None:
                            active_symbol = variant
                            print(f"  [INFO] {symbol} 找不到資料，更換為 {variant} 成功")
                    except Exception:
                        pass

            if price is not None:
                # 即使沒抓到 prev_close 也允許繼續
                p_val = float(price)
                price = safe_round(p_val, 4)
                
                if prev_close is not None and prev_close != 0:
                    pc_val = float(prev_close)
                    prev_close = safe_round(pc_val, 4)
                    change = safe_round(p_val - pc_val, 4)  # type: ignore
                    change_pct = safe_round(change / pc_val * 100, 2) if change is not None else None  # type: ignore
                
                market_value = safe_round(p_val * shares, 2)  # type: ignore
                unrealized = safe_round(market_value - cost_basis, 2) if market_value is not None else None  # type: ignore
                unrealized_pct = safe_round(unrealized / cost_basis * 100, 2) if unrealized is not None and cost_basis != 0 else None  # type: ignore
                today_pnl = safe_round(change * shares, 2) if change is not None else None  # type: ignore
            else:
                # price 為 None 時的初始化已在上方完成
                pass

            def get_action_advice(up_pct_val: float | None, cp_pct_val: float | None) -> Tuple[str, str]:
                if up_pct_val is None or cp_pct_val is None:
                    return "觀察", "資料不足"
                
                # Explicit narrowing to satisfy type checkers
                up_pct = cast(float, up_pct_val)
                cp_pct = cast(float, cp_pct_val)

                if cp_pct > 3.0: # 今日強勢
                    if up_pct > 0:
                        return "加碼", "今日走勢強勁且累積獲利中，趨勢向上"
                    else:
                        return "持平", "今日強彈但仍處虧損，建議分批觀察"
                elif cp_pct < -3.0: # 今日弱勢
                    if up_pct < -10:
                        return "減碼", "累積虧損擴大且跌勢加劇，建議避險"
                    else:
                        return "持平", "急跌但累積損益尚可，暫時觀望"
                
                # 波動較小時
                if up_pct > 15:
                    return "加碼", "長期獲利穩定，可考慮逢低佈局"
                elif up_pct < -15:
                    return "減碼", "長期虧損嚴重，建議重新評機基本面"
                
                return "持平", "股價波動平穩，維持目前持股"

            advice, reason = get_action_advice(unrealized_pct, change_pct)

            results.append({
                "symbol":         symbol,
                "name":           name,
                "shares":         shares,
                "entry_price":    entry,
                "current_price":  price,
                "prev_close":     prev_close,
                "change":         change,
                "change_pct":     change_pct,
                "cost_basis":     cost_basis,
                "market_value":   market_value,
                "unrealized_pnl": unrealized,
                "unrealized_pct": unrealized_pct,
                "today_pnl":      today_pnl,
                "action_advice":  advice,
                "advice_reason":  reason,
            })
            status = f"{price:>8.2f}" if price else "   N/A  "
            chg    = f"{change_pct:+.2f}%" if change_pct else "    N/A"
            print(f"  [OK] {symbol:<15} {name:<12} {status}  {chg}")
        except Exception as e:
            print(f"  [FAIL] {symbol} 抓取失敗：{e}")
            results.append({
                "symbol": symbol, "name": name, "shares": shares,
                "entry_price": entry, "current_price": None,
                "change": None, "change_pct": None,
                "cost_basis": safe_round(entry * shares, 2) or 0.0,
                "market_value": None, "unrealized_pnl": None,
                "unrealized_pct": None, "today_pnl": None,
            })

    return results

# ── 新聞抓取 ─────────────────────────────────────────────────
def _google_news_rss(query: str, max_items: int = 3) -> list[dict]:
    """用 Google News RSS 抓特定關鍵字新聞。"""
    # 增加 when:1d 確保是 24 小時內的新聞
    search_query = f"{query} when:1d"
    url = f"https://news.google.com/rss/search?q={quote(search_query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    items = []
    try:
        req  = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urlopen(req, timeout=10)
        root = ET.fromstring(resp.read())
        for item in root.iter("item"):
            title   = item.findtext("title", "")
            link    = item.findtext("link",  "")
            pubdate = item.findtext("pubDate", "")
            # 去除 Google News 結尾的來源標籤（" - 媒體名稱"）
            title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
            if title:
                items.append({"title": title, "url": link, "published": pubdate, "source": "Google News"})
            if len(items) >= max_items:
                break
    except Exception as e:
        print(f"    [NEWS] Google RSS 失敗 ({query})：{e}")
    return items

def fetch_news(holdings: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """
    優先策略：
    1. 蒐集熱門個股（今日漲跌幅最大的前5支）
    2. 加入市場總體關鍵字（台股、外資、ETF）
    3. 去重後取 Top N
    """
    print(f"[INFO] 搜尋新聞...")
    seen_urls   = set()
    all_news: List[Dict[str, Any]] = []

    # 排序：漲跌幅絕對值最大的前5支優先搜尋
    active_holdings = [h for h in holdings if h.get("change_pct") is not None]
    active = sorted(
        active_holdings,
        key=lambda x: abs(x["change_pct"]), reverse=True
    )
    active = active[:5] # type: ignore

    search_terms = [f"{h['name']} 股價" for h in active] + [
        "台股 今日", "外資 買賣超", "ETF 高股息"
    ]

    for term in search_terms:
        for item in _google_news_rss(term, max_items=5):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                all_news.append(item)
        if len(all_news) >= top_n * 3:
            break
        time.sleep(0.3)  # 避免 rate-limit

    # 選取前 top_n 條並加上重要性標記
    selected = all_news[:top_n] # type: ignore
    for i, news in enumerate(selected):
        news["rank"] = i + 1
        # 簡易利空偵測
        bearish_kw = ["裁員", "財報雷", "虧損", "監管", "警示", "罰款", "倒閉", "下修", "停工", "爆雷"]
        news["is_bearish"] = any(kw in news["title"] for kw in bearish_kw)
        print(f"  {'[!!]' if news['is_bearish'] else '[NEWS]'} [{i+1}] {news['title'][:60]}")

    return selected

# ── 彙總計算 ─────────────────────────────────────────────────
def compute_summary(quotes: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [q for q in quotes if q["market_value"] is not None]

    total_cost       = sum((q["cost_basis"] for q in quotes), 0.0)
    total_value      = sum((q["market_value"] for q in valid), 0.0)
    total_unrealized = sum((q["unrealized_pnl"] for q in valid if q["unrealized_pnl"] is not None), 0.0)
    today_pnl        = sum((q["today_pnl"] for q in valid if q["today_pnl"] is not None), 0.0)

    if total_cost:
        # 強制在此轉為 float 讓型別檢查器正確推斷
        pct: float = (float(total_unrealized) / float(total_cost)) * 100.0
        unrealized_pct = round(pct, 2)  # type: ignore
    else:
        unrealized_pct = 0.0

    top_gainers_list = sorted(valid, key=lambda x: x.get("change_pct") or 0,  reverse=True)
    top_gainers = top_gainers_list[:3] # type: ignore
    top_losers_list = sorted(valid, key=lambda x: x.get("change_pct") or 0)
    top_losers = top_losers_list[:3] # type: ignore

    return {
        "total_cost_basis":       round(float(total_cost)),
        "total_market_value":     round(float(total_value)),
        "total_unrealized_pnl":   round(float(total_unrealized)),
        "total_unrealized_pct":   unrealized_pct,
        "today_total_pnl":        round(float(today_pnl)),
        "covered_symbols":        len(valid),
        "total_symbols":          len(quotes),
        "top_gainers": [{"symbol": q["symbol"], "name": q["name"],
                         "change_pct": q["change_pct"]} for q in top_gainers],
        "top_losers":  [{"symbol": q["symbol"], "name": q["name"],
                         "change_pct": q["change_pct"]} for q in top_losers],
    }

# ── 報告輸出 ─────────────────────────────────────────────────
def write_report(quotes: List[Dict[str, Any]], news: List[Dict[str, Any]], summary: Dict[str, Any]) -> Path:
    ts     = datetime.now().strftime("%Y%m%d_%H%M")
    fname  = REPORTS_DIR / f"report_{ts}.json"
    report = {
        "generated_at":  now_str(),
        "session":       session_label(),
        "currency":      "TWD",
        "summary":       summary,
        "holdings":      quotes,
        "top_news":      news,
    }
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 複製為 latest.json（儀表板常態讀取）
    latest = REPORTS_DIR / "latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        
    # 複製為 latest.js（供直接雙擊 HTML 開啟時跨過 CORS 限制）
    latest_js = REPORTS_DIR / "latest.js"
    with open(latest_js, "w", encoding="utf-8") as f:
        f.write(f"window.LATEST_REPORT = {json.dumps(report, ensure_ascii=False)};\n")

    print(f"\n[DONE] 報告已輸出：{fname}")
    print(f"       latest.json 與 latest.js 已更新")
    return fname

# ── 主程式 ───────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f" 持股分析系統  {now_str()}  ({session_label()})")
    print("=" * 60)

    holdings = load_holdings()
    print(f"[INFO] 讀取 {len(holdings)} 支持股\n")

    quotes  = fetch_quotes(holdings)
    news    = fetch_news(quotes)
    summary = compute_summary(quotes)

    print(f"\n[SUMMARY]")
    print(f"  總成本：    TWD {summary['total_cost_basis']:>12,.0f}")
    print(f"  當前市值：  TWD {summary['total_market_value']:>12,.0f}")
    print(f"  累積損益：  TWD {summary['total_unrealized_pnl']:>+12,.0f}  ({summary['total_unrealized_pct']:+.2f}%)")
    print(f"  今日損益：  TWD {summary['today_total_pnl']:>+12,.0f}")

    write_report(quotes, news, summary)
    print("\n✅ 完成！請開啟 dashboard/index.html 檢視儀表板。")

if __name__ == "__main__":
    main()
