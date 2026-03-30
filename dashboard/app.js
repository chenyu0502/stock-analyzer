/**
 * app.js — 持股儀表板前端邏輯
 * 讀取 ../reports/latest.json 並動態渲染所有區塊。
 * 每 60 秒自動重整一次，顯示倒數計時。
 */

// ── 設定 ─────────────────────────────────────────────────────
const REPORT_PATH = '../reports/latest.json';
const AUTO_REFRESH_S = 60;  // 自動重整間隔（秒）

// ── 工具函式 ─────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function fmt(n, decimals = 0) {
  if (n == null) return '<span class="na-text">N/A</span>';
  return n.toLocaleString('zh-TW', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPrice(n) {
  if (n == null) return '<span class="na-text">N/A</span>';
  return n.toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function pnlClass(n) {
  if (n == null) return '';
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
}

function pnlSign(n) {
  if (n == null) return '';
  return n > 0 ? '+' : '';
}

function changeBadge(pct) {
  if (pct == null) return '<span class="badge flat">N/A</span>';
  const cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat';
  return `<span class="badge ${cls}">${pnlSign(pct)}${pct.toFixed(2)}%</span>`;
}

// ── 渲染 Summary Cards ────────────────────────────────────────
function renderSummary(s) {
  $('totalValue').innerHTML = `<span class="${pnlClass(0)}">TWD ${fmt(s.total_market_value)}</span>`;
  $('totalCost').textContent = `成本：TWD ${fmt(s.total_cost_basis)}`;

  $('unrealizedPnl').innerHTML = `<span class="${pnlClass(s.total_unrealized_pnl)}">
    ${pnlSign(s.total_unrealized_pnl)}TWD ${fmt(Math.abs(s.total_unrealized_pnl))}</span>`;
  $('unrealizedPct').innerHTML = `<span class="${pnlClass(s.total_unrealized_pnl)}">
    ${pnlSign(s.total_unrealized_pct)}${s.total_unrealized_pct?.toFixed(2) ?? 'N/A'}%</span>`;

  $('todayPnl').innerHTML = `<span class="${pnlClass(s.today_total_pnl)}">
    ${pnlSign(s.today_total_pnl)}TWD ${fmt(Math.abs(s.today_total_pnl))}</span>`;
  $('coveredSymbols').textContent = `已取得 ${s.covered_symbols} / ${s.total_symbols} 支`;
}

// ── 渲染 Top Movers ───────────────────────────────────────────
function renderMovers(gainers, losers) {
  const makeItem = m =>
    `<li class="mover-item">
      <div>
        <div class="mover-name">${m.name}</div>
        <div class="mover-symbol">${m.symbol}</div>
      </div>
      ${changeBadge(m.change_pct)}
    </li>`;

  $('topGainersList').innerHTML = gainers.map(makeItem).join('') || '<li class="na-text" style="padding:8px">無資料</li>';
  $('topLosersList').innerHTML = losers.map(makeItem).join('') || '<li class="na-text" style="padding:8px">無資料</li>';
}

// ── 渲染 Holdings Table ───────────────────────────────────────
function renderHoldings(holdings) {
  const rows = holdings.map(h => {
    const warnRow = h.unrealized_pct != null && h.unrealized_pct < -30 ? 'warn-row' : '';
    const cpClass = pnlClass(h.change_pct);
    const upClass = pnlClass(h.unrealized_pnl);

    // 今日漲跌欄
    let chgCell = '<span class="na-text">N/A</span>';
    if (h.change != null && h.change_pct != null) {
      const sign = h.change >= 0 ? '+' : '';
      const cls = h.change > 0 ? 'up-text' : h.change < 0 ? 'down-text' : '';
      chgCell = `<span class="${cls}">${sign}${h.change.toFixed(2)} (${sign}${h.change_pct.toFixed(2)}%)</span>`;
    }

    // 今日損益欄
    let todayCell = '<span class="na-text">N/A</span>';
    if (h.today_pnl != null) {
      todayCell = `<span class="${pnlClass(h.today_pnl)}">${pnlSign(h.today_pnl)}${fmt(h.today_pnl)}</span>`;
    }

    // 累積損益欄
    let upCell = '<span class="na-text">N/A</span>';
    if (h.unrealized_pnl != null) {
      upCell = `<span class="${upClass}">${pnlSign(h.unrealized_pnl)}${fmt(h.unrealized_pnl)}</span>`;
    }
    let upPctCell = '<span class="na-text">N/A</span>';
    if (h.unrealized_pct != null) {
      upPctCell = `<span class="${upClass}">${pnlSign(h.unrealized_pct)}${h.unrealized_pct.toFixed(2)}%</span>`;
    }

    const shares = (h.shares / 1000).toFixed(h.shares % 1000 === 0 ? 0 : 1);

    const advice = h.action_advice || '觀察';
    const reason = h.advice_reason || '-';
    let advClass = 'hold';
    if (advice === '加碼') advClass = 'buy';
    if (advice === '減碼') advClass = 'sell';

    return `<tr class="${warnRow}">
      <td><span class="sym-code">${h.symbol}</span></td>
      <td class="sym-name">${h.name}</td>
      <td class="num">${fmtPrice(h.current_price)}</td>
      <td class="num">${chgCell}</td>
      <td class="num">${todayCell}</td>
      <td class="num">${shares}</td>
      <td class="num">${h.market_value != null ? fmt(h.market_value) : '<span class="na-text">N/A</span>'}</td>
      <td class="num">${upCell}</td>
      <td class="num">${upPctCell}</td>
      <td>
        <div class="advice-cell">
          <span class="advice-tag ${advClass}">${advice}</span>
          <span class="advice-reason">${reason}</span>
        </div>
      </td>
    </tr>`;
  });

  $('holdingsTbody').innerHTML = rows.join('');
}

// ── 渲染 News ─────────────────────────────────────────────────
function renderNews(news) {
  if (!news || news.length === 0) {
    $('newsList').style.display = 'none';
    $('noNews').style.display = 'block';
    return;
  }
  $('newsList').style.display = 'flex';
  $('noNews').style.display = 'none';

  $('newsList').innerHTML = news.map(n => {
    const bearishCls = n.is_bearish ? 'bearish' : '';
    const bearishTag = n.is_bearish ? '<span class="bearish-tag">⚠ 利空</span>' : '';
    const url = n.url || '#';
    const meta = n.published ? `<div class="news-meta">${n.source ?? ''} · ${n.published}</div>` : '';
    return `<div class="news-card ${bearishCls}">
        <div class="news-rank">${n.rank}</div>
        <div class="news-body">
          <a class="news-title" href="${url}" target="_blank" rel="noopener">
            ${n.title}${bearishTag}
          </a>
          ${meta}
        </div>
      </div>`;
  }).join('');
}

// ── 主載入函式 ────────────────────────────────────────────────
async function loadReport() {
  const btn = $('refreshBtn');
  btn.classList.add('spinning');

  try {
    let data;
    // 若為直接雙擊打開的 file:// 協定，瀏覽器會阻隔 fetch 讀取本地 JSON
    // 改用動態注入 JS 的方式取得資料
    if (window.location.protocol === 'file:') {
      data = await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `../reports/latest.js?t=${Date.now()}`;
        script.onload = () => {
          resolve(window.LATEST_REPORT);
          document.head.removeChild(script); // 載入後移除
        };
        script.onerror = () => reject(new Error('無法載入 latest.js'));
        document.head.appendChild(script);
      });
    } else {
      // 伺服器模式：先觸發後端更新數據
      console.log('[DASHBOARD] 觸發後端更新...');
      try {
        const refreshResp = await fetch('/api/refresh');
        if (!refreshResp.ok) throw new Error('後端更新失敗');
        console.log('[DASHBOARD] 後端更新完成');
      } catch (e) {
        console.error('[DASHBOARD] 重新整理 API 失敗:', e);
        showToast('⚠️ 無法連線至後端伺服器', true);
      }

      const resp = await fetch(`${REPORT_PATH}?t=${Date.now()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      data = await resp.json();
    }

    // Header
    $('lastUpdated').textContent = data.generated_at ?? '—';
    $('sessionBadge').textContent = data.session ?? '分析';

    // Render sections
    renderSummary(data.summary);
    renderMovers(data.summary.top_gainers ?? [], data.summary.top_losers ?? []);
    renderHoldings(data.holdings ?? []);
    renderNews(data.top_news ?? []);

    showToast('✅ 數據已更新');
  } catch (err) {
    console.warn('loadReport error:', err);
    // 顯示佔位符，提示需要先執行分析腳本
    $('lastUpdated').textContent = '尚無數據';
    $('holdingsTbody').innerHTML = `<tr><td colspan="9" class="na-text" style="padding:32px;text-align:center">
      請先執行 analyze_portfolio.py 以產生報告<br>
      <small style="color:#4b5563;margin-top:6px;display:block">cd d:\\ZZ_Chenyu\\Antigravity &amp;&amp; python analyze_portfolio.py</small>
    </td></tr>`;
    $('newsList').style.display = 'none';
    $('noNews').style.display = 'block';
    $('noNews').textContent = '報告尚未產生，請先執行分析腳本。';
    showToast('⚠️ 尚無報告資料', true);
  } finally {
    btn.classList.remove('spinning');
  }
}

// ── Toast 通知 ────────────────────────────────────────────────
function showToast(msg, isWarn = false) {
  const t = $('toast');
  t.textContent = msg;
  t.style.borderColor = isWarn ? 'rgba(239,68,68,0.4)' : 'rgba(99,102,241,0.4)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── 自動重整倒數 ──────────────────────────────────────────────
let countdown = AUTO_REFRESH_S;
setInterval(() => {
  countdown--;
  $('autoRefreshCountdown').textContent = `自動更新：${countdown}s`;
  if (countdown <= 0) {
    countdown = AUTO_REFRESH_S;
    loadReport();
  }
}, 1000);

// ── 初始載入 ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', loadReport);
