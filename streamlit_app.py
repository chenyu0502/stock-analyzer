import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
import re
import time
import plotly.express as px
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional

# ── 設定 ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
STOCKS_JSON = BASE_DIR / "stocks.json"

st.set_page_config(
    page_title="Antigravity Portfolio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS 樣式 (Antigravity 系列高級感 - 支援主題切換) ───────────────────────────
st.markdown("""
<style>
    /* 卡片玻璃擬態 - 移除硬編碼顏色以支援 Light/Dark Theme */
    div.stMetric {
        background: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.1);
        border-radius: 12px;
        padding: 20px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        backdrop-filter: blur(10px);
    }
    /* 標題字體 */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
    }
    /* 修改按鈕樣式 - 保持 Premium 感但確保可見度 */
    .stButton>button {
        border-radius: 8px;
        background-image: linear-gradient(90deg, #6366f1, #818cf8);
        border: none;
        color: white !important;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    }
    /* 強制修改 Streamlit 預設 Metric 顏色以符合台灣標準 (Red=Up, Green=Down) */
    /* 注意：Streamlit 內部使用的是 [data-testid="stMetricDelta"] */
    [data-testid="stMetricDelta"] svg {
        display: none; /* 隱藏預設箭頭以避免混淆 */
    }
</style>
""", unsafe_allow_html=True)

# ── 工具函式 ─────────────────────────────────────────────────
def safe_round(val: Any, ndigits: int = 2) -> float:
    if val is None: return 0.0
    try:
        return round(float(val), ndigits)
    except:
        return 0.0

def fmt_currency(val: float) -> str:
    return f"TWD {val:,.0f}"

# ── 資料操作 ─────────────────────────────────────────────────
def load_stocks() -> List[Dict[str, Any]]:
    if not STOCKS_JSON.exists():
        return {"holdings": []}
    try:
        with open(STOCKS_JSON, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except:
        return {"holdings": []}

def save_stocks(data: Dict[str, Any]):
    with open(STOCKS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── 行情抓取核心 ─────────────────────────────────────────────
@st.cache_data(ttl=300) # 5分鐘快取
def get_market_data(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not holdings: return []
    symbols = [h["symbol"] for h in holdings]
    tickers = yf.Tickers(" ".join(symbols))
    results = []

    for h in holdings:
        symbol = h["symbol"]
        name = h["name"]
        shares = float(h["shares"])
        entry = float(h["entry_price"])
        
        try:
            tkr = tickers.tickers[symbol]
            info = tkr.fast_info
            
            # 優先嘗試快速屬性
            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)
            
            # 備援機制：history
            if price is None:
                hist = tkr.history(period="2d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]
                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
            
            p_val = float(price) if price else 0.0
            pc_val = float(prev_close) if prev_close else p_val
            
            change = p_val - pc_val
            change_pct = (change / pc_val * 100) if pc_val != 0 else 0.0
            
            cost_basis = entry * shares
            market_value = p_val * shares
            unrealized = market_value - cost_basis
            unrealized_pct = (unrealized / cost_basis * 100) if cost_basis != 0 else 0.0
            today_pnl = change * shares
            
            results.append({
                "symbol": symbol,
                "name": name,
                "shares": shares,
                "entry_price": entry,
                "current_price": p_val,
                "change_pct": change_pct,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "unrealized_pct": unrealized_pct,
                "today_pnl": today_pnl
            })
        except Exception as e:
            st.warning(f"無法抓取 {symbol}: {e}")
            results.append({**h, "current_price": 0, "change_pct": 0, "market_value": 0, "unrealized_pnl": 0, "unrealized_pct": 0, "today_pnl": 0})
            
    return results

# ── 新聞抓取邏輯 ─────────────────────────────────────────────
@st.cache_data(ttl=1800) # 30分鐘快取
def get_news(quotes: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    # 這裡簡化邏輯，抓取主要市場新聞與持股相關
    search_query = "台股 今日"
    url = f"https://news.google.com/rss/search?q={quote(search_query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    items = []
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
            for item in root.iter("item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                source = "Google News"
                # 清理標題
                title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
                items.append({"title": title, "url": link, "source": source})
                if len(items) >= top_n: break
    except:
        pass
    return items

# ── 主界面 ───────────────────────────────────────────────────
def main():
    st.title("📊 Antigravity Dashboard")
    st.caption(f"最後分析時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 載入資料
    stocks_data = load_stocks()
    holdings = stocks_data.get("holdings", [])

    # 2. Sidebar: 管理與新增
    with st.sidebar:
        st.header("🛠️ 持股管理")
        with st.form("add_stock_form", clear_on_submit=True):
            new_symbol = st.text_input("股票代號 (如 2330.TW)", placeholder="2330.TW").upper()
            new_name = st.text_input("顯示名稱 (可留空，系統自動抓取)", placeholder="台積電")
            new_shares = st.number_input("股數", min_value=1, value=1000, step=100)
            new_price = st.number_input("購入價格", min_value=0.1, value=100.0, step=0.1)
            submitted = st.form_submit_state = st.form_submit_button("新增/更新持股")
            
            if submitted and new_symbol:
                # 簡單抓取名稱備援
                if not new_name:
                    try:
                        new_name = yf.Ticker(new_symbol).info.get("shortName", new_symbol)
                    except:
                        new_name = new_symbol
                
                # 更新或新增
                found = False
                for h in holdings:
                    if h["symbol"] == new_symbol:
                        h["shares"] = new_shares
                        h["entry_price"] = new_price
                        h["name"] = new_name
                        found = True
                        break
                if not found:
                    holdings.append({"symbol": new_symbol, "name": new_name, "shares": new_shares, "entry_price": new_price})
                
                save_stocks({"holdings": holdings})
                st.success(f"{new_symbol} 已更新")
                st.rerun()

        if st.button("強制刷新市場數據"):
            st.cache_data.clear()
            st.rerun()

    if not holdings:
        st.info("目前尚無持股資料，請使用側邊欄新增。")
        return

    # 3. 抓取行情
    with st.spinner("正在獲取即時行情..."):
        quotes = get_market_data(holdings)

    # 4. KPI 總覽
    total_cost = sum(q["entry_price"] * q["shares"] for q in quotes)
    total_market = sum(q["market_value"] for q in quotes)
    total_unrealized = total_market - total_cost
    total_unrealized_pct = (total_unrealized / total_cost * 100) if total_cost != 0 else 0.0
    today_pnl = sum(q["today_pnl"] for q in quotes)

    col1, col2, col3 = st.columns(3)
    col1.metric("當前總市值", fmt_currency(total_market), f"成本: {fmt_currency(total_cost)}", delta_color="off")
    # 台灣股市色標：紅漲綠跌 -> 使用 delta_color="inverse"
    col2.metric("累積損益", fmt_currency(total_unrealized), f"{total_unrealized_pct:+.2f}%", delta_color="inverse")
    col3.metric("今日損益變化", fmt_currency(today_pnl), delta_color="inverse")

    st.divider()

    # 5. 持股明細 (使用 Data Editor)
    st.subheader("📈 持股概況")
    df = pd.DataFrame(quotes)
    
    # 重構欄位名稱
    df_display = df.rename(columns={
        "symbol": "代號",
        "name": "名稱",
        "shares": "股數",
        "entry_price": "成本",
        "current_price": "現價",
        "change_pct": "漲跌%",
        "market_value": "市值",
        "unrealized_pnl": "累積損益",
        "unrealized_pct": "報酬%",
        "today_pnl": "今日損益"
    })

    # 定義台灣色標渲染函式
    def style_taiwan(val):
        try:
            v = float(val)
            if v > 0: return 'color: #ff4b4b;' # 紅色 (亮)
            if v < 0: return 'color: #00873c;' # 綠色 (亮)
        except:
            pass
        return ''

    # 套用樣式到特定位數與顏色
    df_styled = df_display.style.map(style_taiwan, subset=['漲跌%', '報酬%', '累積損益', '今日損益']) \
                                .format({
                                    "漲跌%": "{:+.2f}%",
                                    "報酬%": "{:+.2f}%",
                                    "現價": "{:.2f}",
                                    "市值": "{:,.0f}",
                                    "累積損益": "{:+,.0f}",
                                    "今日損益": "{:+,.0f}"
                                })

    st.dataframe(
        df_styled,
        hide_index=True,
        use_container_width=True
    )

    # 6. 資產分佈與新聞 (兩欄)
    left_col, right_col = st.columns([1, 1.2])
    
    with left_col:
        st.subheader("🍕 資產分佈")
        fig = px.pie(df, values='market_value', names='symbol', hole=0.4, 
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)

    with right_col:
        st.subheader("📰 市場重點新聞")
        news = get_news(quotes)
        if news:
            for n in news:
                st.markdown(f"**[{n['source']}]** [{n['title']}]({n['url']})")
                st.write("---")
        else:
            st.write("暫無最新消息")

    # 7. 刪除管理 (底部折疊)
    with st.expander("🗑️ 刪除持股"):
        del_symbol = st.selectbox("選擇要刪除的股票", [h["symbol"] for h in holdings])
        if st.button(f"確認刪除 {del_symbol}"):
            holdings = [h for h in holdings if h["symbol"] != del_symbol]
            save_stocks({"holdings": holdings})
            st.success(f"{del_symbol} 已移除")
            st.rerun()

if __name__ == "__main__":
    main()
