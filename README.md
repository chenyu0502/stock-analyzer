# Antigravity Stock Portfolio 投資組合追蹤系統

這是一個專為台灣投資者設計的個人股票投資組合追蹤與分析系統。它整合了 yfinance 的即時數據與 Google News 的新聞監控，並提供一個直觀的網頁儀表板，協助您即時掌握持股損益與市場趨勢。

## 🌟 主要特色

- **多重 API 台股名稱查詢**：整合 TWSE CodeQuery 與 MIS API，確保台股及 ETF 名稱顯示正確（如元大高股息、台積電等）。
- **自動化損益計算**：即時抓取現價，自動計算累積損益、今日漲跌幅及持股權重。
- **新聞監控與利空警示**：結合 Google News RSS 掃描 Top 3 關鍵消息，具備「裁員、爆雷、虧損」等關鍵字偵測並紅字標註。
- **動態操作建議**：根據漲跌幅與獲利狀況，自動生成「加碼、持平、減碼」建議。
- **輕量化網頁儀表板**：內建 Python HTTP Server，無需安裝複雜架構即可於瀏覽器檢視專業報表。

## 🚀 快速上手

### 1. 環境準備
確保您的環境已安裝 Python 3.8+，並建議使用虛擬環境：

```bash
# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境 (Windows)
.\.venv\Scripts\activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 2. 設定持股
編輯專案根目錄下的 `stocks.json`。格式如下：

```json
{
  "holdings": [
    {
      "symbol": "2330.TW",
      "name": "台積電",
      "shares": 1000,
      "entry_price": 800
    }
  ]
}
```

### 3. 啟動服務
執行儀表板伺服器：

```bash
python dashboard_server.py
```
啟動後開啟瀏覽器訪問：`http://localhost:5000`

## 📂 專案結構

- `analyze_portfolio.py`: 核心分析引擎，負責抓取價格、新聞並生成損益報告。
- `dashboard_server.py`: 本地 API 伺服器，負責提供網頁存取與即時操作。
- `dashboard/`: 包含 `index.html` 與 React 儀表板前端代碼。
- `reports/`: 存放生成的 JSON 格式分析報表。
- `stocks.json`: 儲存您的投資組合清單。

## 🛠️ 開發與維護

- **更新數據**：您可以透過儀表板上的「重新整理」按鈕觸發新的分析循環。
- **新增股票**：可直接在儀表板 UI 中輸入代號與價格新增，系統會自動補全名稱。
- **中文編碼**：本系統已針對 Windows 環境優化，強制使用 UTF-8 處理 JSON 與路徑。

---
*註：本工具僅供研究與分析參考，不構成任何投資建議。*
