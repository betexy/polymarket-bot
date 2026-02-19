from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from app.services.logger_service import log_storage
from app.services.settings_service import get_settings_service
from app.services.bet_status_checker import BetStatusChecker
from app.dependencies import _polymarket_client, _clob_client, _settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class BetSettingsUpdate(BaseModel):
    bet_amount: Optional[float] = None
    max_bets_per_market: Optional[int] = None
    max_bets_per_match: Optional[int] = None


@router.get("/", response_class=HTMLResponse)
async def dashboard_page():
    """Веб-страница для мониторинга ставок и логов"""
    html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket Bot - Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%233b82f6'/><text y='.9em' x='50%' text-anchor='middle' font-size='70'>🤖</text></svg>">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #333;
            transition: all 0.3s ease;
        }
        .stat-card.success .value { color: #10b981; }
        .stat-card.error .value { color: #ef4444; }
        .stat-card .value.updating {
            opacity: 0.6;
        }
        tr {
            transition: background-color 0.2s ease;
        }
        tr.new-row {
            animation: fadeIn 0.5s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-5px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .updating-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid #3b82f6;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-left: 8px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            background: white;
            border: none;
            border-radius: 8px 8px 0 0;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
        }
        .tab.active {
            background: #3b82f6;
            color: white;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .table-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: #f9fafb;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }
        tr:hover {
            background: #f9fafb;
        }
        .status {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }
        .status.success {
            background: #d1fae5;
            color: #065f46;
        }
        .status.error {
            background: #fee2e2;
            color: #991b1b;
        }
        .status.skipped {
            background: #fef3c7;
            color: #92400e;
        }
        .log-level {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }
        .log-level.INFO {
            background: #dbeafe;
            color: #1e40af;
        }
        .log-level.SUCCESS {
            background: #d1fae5;
            color: #065f46;
        }
        .log-level.WARNING {
            background: #fef3c7;
            color: #92400e;
        }
        .log-level.ERROR {
            background: #fee2e2;
            color: #991b1b;
        }
        .refresh-btn {
            padding: 10px 20px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
        }
        .refresh-btn:hover {
            background: #2563eb;
        }
        .timestamp {
            color: #6b7280;
            font-size: 12px;
        }
        .json-data {
            background: #f9fafb;
            padding: 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 11px;
            max-width: 400px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }
        /* Стили для раскрывающихся деталей ставки */
        .bet-row {
            cursor: pointer;
        }
        .bet-row:hover {
            background: #f0f9ff !important;
        }
        .bet-row.expanded {
            background: #eff6ff !important;
        }
        .bet-details-row {
            display: none;
        }
        .bet-details-row.expanded {
            display: table-row;
        }
        .bet-details-row td {
            background: #f8fafc;
            padding: 0;
            border-bottom: 2px solid #e5e7eb;
        }
        .bet-details-content {
            padding: 15px 20px;
            animation: slideDown 0.2s ease-out;
        }
        @keyframes slideDown {
            from { opacity: 0; max-height: 0; }
            to { opacity: 1; max-height: 500px; }
        }
        .bet-details-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .bet-details-section {
            background: white;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .bet-details-section h4 {
            color: #374151;
            font-size: 14px;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e5e7eb;
        }
        .bet-detail-item {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 13px;
            border-bottom: 1px solid #f3f4f6;
        }
        .bet-detail-item:last-child {
            border-bottom: none;
        }
        .bet-detail-label {
            color: #6b7280;
            font-weight: 500;
        }
        .bet-detail-value {
            color: #111827;
            font-weight: 500;
            text-align: right;
            max-width: 60%;
            word-break: break-all;
        }
        .expand-indicator {
            display: inline-block;
            width: 18px;
            height: 18px;
            text-align: center;
            line-height: 18px;
            background: #e5e7eb;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 8px;
            transition: transform 0.2s ease;
        }
        .bet-row.expanded .expand-indicator {
            transform: rotate(90deg);
            background: #3b82f6;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Polymarket Bot Dashboard</h1>
        
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
            <button class="refresh-btn" onclick="loadData()" id="refresh-btn">🔄 Обновить</button>
            <span id="update-status" style="color: #6b7280; font-size: 14px;"></span>
        </div>
        
        <div class="stats" id="stats">
            <!-- Статистика будет загружена здесь -->
        </div>
        
        <div class="chart-container" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px;">
            <h2 style="margin-bottom: 15px; color: #333; font-size: 18px;">График профита</h2>
            <canvas id="profitChart" style="max-height: 300px;"></canvas>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('bets')">Ставки</button>
            <button class="tab" onclick="showTab('logs')">Логи API</button>
            <button class="tab" onclick="showTab('settings')">Настройки</button>
        </div>
        
        <div id="bets-tab" class="tab-content active">
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Время</th>
                            <th>Команды</th>
                            <th>Маркет</th>
                            <th>Коэффициент</th>
                            <th>Прибыль %</th>
                            <th>Second BK</th>
                            <th>Источник</th>
                            <th>Статус</th>
                            <th>Сумма ставки</th>
                            <th>ROI</th>
                            <th>Результат</th>
                        </tr>
                    </thead>
                    <tbody id="bets-table">
                        <!-- Данные будут загружены здесь -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="logs-tab" class="tab-content">
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Время</th>
                            <th>Уровень</th>
                            <th>Сообщение</th>
                            <th>Данные</th>
                        </tr>
                    </thead>
                    <tbody id="logs-table">
                        <!-- Данные будут загружены здесь -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="settings-tab" class="tab-content">
            <div class="table-container" style="padding: 30px;">
                <h2 style="margin-bottom: 20px; color: #333;">Настройки ставок</h2>
                <form id="settings-form" onsubmit="saveSettings(event)">
                    <div style="margin-bottom: 20px;">
                        <label for="bet_amount" style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">
                            Сумма ставки (USD):
                        </label>
                        <input 
                            type="number" 
                            id="bet_amount" 
                            name="bet_amount" 
                            step="0.1" 
                            min="0.1" 
                            required
                            style="width: 100%; max-width: 300px; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px;"
                        />
                        <p style="margin-top: 5px; color: #6b7280; font-size: 12px;">
                            Сумма одной ставки в долларах США
                        </p>
                    </div>
                    
                    <div style="margin-bottom: 20px;">
                        <label for="max_bets_per_market" style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">
                            Макс. ставок на один маркет:
                        </label>
                        <input 
                            type="number" 
                            id="max_bets_per_market" 
                            name="max_bets_per_market" 
                            min="1" 
                            required
                            style="width: 100%; max-width: 300px; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px;"
                        />
                        <p style="margin-top: 5px; color: #6b7280; font-size: 12px;">
                            Максимальное количество ставок на один маркет (например, "Set 1 Winner")
                        </p>
                    </div>
                    
                    <div style="margin-bottom: 30px;">
                        <label for="max_bets_per_match" style="display: block; margin-bottom: 8px; font-weight: 500; color: #374151;">
                            Макс. ставок на один матч:
                        </label>
                        <input 
                            type="number" 
                            id="max_bets_per_match" 
                            name="max_bets_per_match" 
                            min="1" 
                            required
                            style="width: 100%; max-width: 300px; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px;"
                        />
                        <p style="margin-top: 5px; color: #6b7280; font-size: 12px;">
                            Максимальное количество ставок на один матч (по всем маркетам)
                        </p>
                    </div>
                    
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <button 
                            type="submit" 
                            style="padding: 12px 24px; background: #3b82f6; color: white; border: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer;"
                        >
                            💾 Сохранить настройки
                        </button>
                        <span id="settings-status" style="color: #6b7280; font-size: 14px;"></span>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
        // Кэш данных для сравнения
        let cachedData = {
            stats: null,
            bets: [],
            logs: [],
            profitData: null
        };
        
        // Флаг обновления для предотвращения одновременных запросов
        let isUpdating = false;
        
        function showTab(tabName) {
            // Скрываем все табы
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Показываем выбранный таб
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
        }
        
        async function loadData(showStatus = true) {
            if (isUpdating) return;
            isUpdating = true;
            
            const statusEl = document.getElementById('update-status');
            const refreshBtn = document.getElementById('refresh-btn');
            
            try {
                if (showStatus) {
                    statusEl.innerHTML = '<span class="updating-indicator"></span> Обновление...';
                    statusEl.style.color = '#3b82f6';
                    refreshBtn.disabled = true;
                    refreshBtn.style.opacity = '0.6';
                }
                
                // Параллельная загрузка всех данных
                const [statsResponse, betsResponse, logsResponse, profitResponse, balanceResponse] = await Promise.all([
                    fetch('/dashboard/api/stats?_=' + Date.now()),
                    fetch('/dashboard/api/bets-history?_=' + Date.now()),
                    fetch('/dashboard/api/logs-history?_=' + Date.now()),
                    fetch('/dashboard/api/profit-data?days=30&_=' + Date.now()),
                    fetch('/dashboard/api/balance?_=' + Date.now())
                ]);

                // Обрабатываем баланс
                if (balanceResponse.ok) {
                    const balData = await balanceResponse.json();
                    cachedData.balance = balData;
                }

                // Обрабатываем статистику
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    updateStats(stats);
                    cachedData.stats = stats;
                }
                
                // Обрабатываем ставки
                if (betsResponse.ok) {
                    const bets = await betsResponse.json();
                    updateBets(bets);
                    cachedData.bets = bets;
                }
                
                // Обрабатываем логи
                if (logsResponse.ok) {
                    const logs = await logsResponse.json();
                    updateLogs(logs);
                    cachedData.logs = logs;
                }
                
                // Обрабатываем график профита
                if (profitResponse.ok) {
                    const profitData = await profitResponse.json();
                    // Обновляем график только если данные изменились
                    if (JSON.stringify(profitData) !== JSON.stringify(cachedData.profitData)) {
                        updateProfitChart(profitData);
                        cachedData.profitData = profitData;
                    }
                }
                
                if (showStatus) {
                    statusEl.textContent = 'Обновлено: ' + new Date().toLocaleTimeString('ru-RU', { timeZone: 'Asia/Jakarta' });
                    statusEl.style.color = '#10b981';
                    refreshBtn.disabled = false;
                    refreshBtn.style.opacity = '1';
                    setTimeout(() => {
                        if (statusEl.textContent.includes('Обновлено:')) {
                            statusEl.textContent = '';
                        }
                    }, 2000);
                }
            } catch (error) {
                console.error('Error loading data:', error);
                if (showStatus) {
                    statusEl.textContent = 'Ошибка: ' + error.message;
                    statusEl.style.color = '#ef4444';
                    refreshBtn.disabled = false;
                    refreshBtn.style.opacity = '1';
                }
            } finally {
                isUpdating = false;
            }
        }
        
        function updateStats(stats) {
            const statsDiv = document.getElementById('stats');
            const totalProfit = stats.total_profit || 0.0;
            const profitClass = totalProfit >= 0 ? 'success' : 'error';
            const profitSign = totalProfit >= 0 ? '+' : '';
            const totalTurnover = stats.total_turnover || stats.total_invested || 0;
            const skippedOrders = stats.skipped_orders || 0;
            const failedOrders = stats.failed_orders || 0;
            
            // Рассчитываем общий ROI
            const totalROI = stats.total_roi !== null && stats.total_roi !== undefined ? stats.total_roi : null;
            const roiText = totalROI !== null ? (totalROI >= 0 ? '+' : '') + totalROI.toFixed(2) + '%' : '-';
            const roiClass = totalROI !== null ? (totalROI >= 0 ? 'success' : 'error') : '';
            
            // Баланс
            const bal = cachedData.balance;
            const balanceText = bal && bal.balance !== null && bal.balance !== undefined
                ? '$' + bal.balance.toFixed(2)
                : '-';

            statsDiv.innerHTML = `
                <div class="stat-card" style="background: #ecfdf5;">
                    <h3>Баланс USDC</h3>
                    <div class="value" style="color: #047857;">${balanceText}</div>
                </div>
                <div class="stat-card success">
                    <h3>Ставок на Полимаркет</h3>
                    <div class="value">${stats.successful_orders}</div>
                </div>
                <div class="stat-card" style="background: #e0e7ff;">
                    <h3>Оборот</h3>
                    <div class="value" style="color: #3730a3;">${totalTurnover.toFixed(2)} USD</div>
                </div>
                <div class="stat-card ${roiClass}">
                    <h3>ROI</h3>
                    <div class="value">${roiText}</div>
                </div>
                <div class="stat-card ${profitClass}">
                    <h3>Профит</h3>
                    <div class="value">${profitSign}${totalProfit.toFixed(2)} USD</div>
                </div>
                <div class="stat-card" style="background: #fef3c7;">
                    <h3>Пропущено / Ошибок</h3>
                    <div class="value" style="color: #92400e;">${skippedOrders} / ${failedOrders}</div>
                </div>
            `;
        }
        
        function updateBets(bets) {
            const tbody = document.getElementById('bets-table');
            
            if (bets.length === 0) {
                if (tbody.children.length === 0 || tbody.children[0].cells.length !== 11) {
                    tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; padding: 40px;">Нет данных о ставках</td></tr>';
                }
                return;
            }
            
            // Получаем состояние раскрытых строк из localStorage
            const expandedStates = getExpandedStates();
            
            // Создаем карту существующих строк по timestamp
            const existingRows = new Map();
            Array.from(tbody.children).forEach(row => {
                const timestampCell = row.querySelector('.timestamp');
                if (timestampCell) {
                    existingRows.set(timestampCell.textContent.trim(), row);
                }
            });
            
            // Очищаем tbody для пересоздания
            tbody.innerHTML = '';
            
            // Добавляем строки с анимацией для новых
            bets.forEach((bet, index) => {
                const betData = bet.bet_data;
                const result = bet.result;
                const status = result.status || 'unknown';
                const statusClass = status === 'success' ? 'success' : status === 'error' ? 'error' : 'skipped';
                const statusText = status === 'success' ? 'Успешно' : status === 'error' ? 'Ошибка' : 'Пропущено';
                
                // Получаем информацию о сумме ставки
                const betAmountUsd = bet.bet_amount_usd || (result.order_price && result.order_size ? result.order_price * result.order_size : null);
                const betAmountText = betAmountUsd ? `$${betAmountUsd.toFixed(2)}` : '-';
                
                // Получаем информацию о результате
                const settledStatus = bet.settled_status;
                const outcome = bet.outcome;
                const profit = bet.profit !== null && bet.profit !== undefined ? bet.profit : result.profit;
                const resultStatus = settledStatus || result.result_status || (profit !== null && profit !== undefined ? (profit >= 0 ? 'win' : 'loss') : 'pending');
                let resultText = '-';
                let resultClass = '';
                
                if (settledStatus === 'WIN' || (resultStatus === 'win' && outcome === 'WIN')) {
                    resultText = `✅ Выигрыш: +${profit ? profit.toFixed(2) : '0.00'} USD`;
                    resultClass = 'success';
                } else if (settledStatus === 'LOSE' || (resultStatus === 'loss' && outcome === 'LOSE')) {
                    resultText = `❌ Проигрыш: ${profit ? profit.toFixed(2) : '0.00'} USD`;
                    resultClass = 'error';
                } else if (resultStatus === 'closed') {
                    resultText = '⏸ Закрыт';
                    resultClass = 'skipped';
                } else if (status === 'success') {
                    resultText = '⏳ В ожидании';
                    resultClass = '';
                }
                
                const row = document.createElement('tr');
                const timestamp = formatDateTime(bet.timestamp);
                const isNew = !existingRows.has(timestamp);
                const isExpanded = expandedStates[timestamp] === true;
                
                row.classList.add('bet-row');
                row.dataset.betIndex = index;
                
                if (isNew && index < 5) {
                    row.classList.add('new-row');
                }
                if (isExpanded) {
                    row.classList.add('expanded');
                }
                
                // Используем market_display если доступно, иначе fallback к betData.market
                const marketDisplay = bet.market_display || betData.market || '-';
                const source = bet.source || betData.source || '-';
                
                // Форматируем ROI
                let roiText = '-';
                let roiClass = '';
                if (bet.roi !== null && bet.roi !== undefined) {
                    const roi = parseFloat(bet.roi);
                    if (!isNaN(roi)) {
                        roiText = (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%';
                        roiClass = roi >= 0 ? 'success' : 'error';
                    }
                }
                
                row.innerHTML = `
                    <td class="timestamp"><span class="expand-indicator">▶</span>${timestamp}</td>
                    <td>${escapeHtml(betData.homeTeam || '-')} vs ${escapeHtml(betData.awayTeam || '-')}</td>
                    <td>${escapeHtml(marketDisplay)}</td>
                    <td>${result.order_price ? (1 / result.order_price).toFixed(2) : (betData.coef || '-')}</td>
                    <td>${(() => {
                        if (result.order_price && betData.coef && betData.surebet_profit !== null && betData.surebet_profit !== undefined) {
                            // 1. Вычисляем 1/coef_BK2 из данных парсера: 1/coef_BK2 = 1 - profit/100 - 1/coef_parser
                            const inv_coef_bk2 = 1 - (betData.surebet_profit / 100) - (1 / parseFloat(betData.coef));
                            // 2. Реальная прибыль: real_profit = (1 - order_price - 1/coef_BK2) * 100
                            const real_profit = (1 - result.order_price - inv_coef_bk2) * 100;
                            return real_profit.toFixed(2) + '%';
                        }
                        return betData.surebet_profit ? betData.surebet_profit.toFixed(2) + '%' : '-';
                    })()}</td>
                    <td>${escapeHtml(betData.second_bookmaker || '-')}</td>
                    <td>${escapeHtml(source)}</td>
                    <td><span class="status ${statusClass}">${statusText}</span></td>
                    <td>${betAmountText}</td>
                    <td><span class="status ${roiClass}" style="${roiClass ? '' : 'color: #6b7280;'}">${roiText}</span></td>
                    <td><span class="status ${resultClass}">${resultText}</span></td>
                `;
                
                // Создаём строку с деталями
                const detailsRow = document.createElement('tr');
                detailsRow.classList.add('bet-details-row');
                detailsRow.dataset.betIndex = index;
                if (isExpanded) {
                    detailsRow.classList.add('expanded');
                }
                
                detailsRow.innerHTML = `
                    <td colspan="11">
                        <div class="bet-details-content">
                            <div class="bet-details-grid">
                                <div class="bet-details-section">
                                    <h4>📥 Запрос от парсера</h4>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Букмекер:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.bookmaker || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Второй букмекер:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.second_bookmaker || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Команда 1 (homeTeam):</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.homeTeam || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Команда 2 (awayTeam):</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.awayTeam || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Лига:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.league || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Спорт:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.sport || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Маркет:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.market || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Target:</span>
                                        <span class="bet-detail-value" style="font-weight: bold; color: #3b82f6;">${escapeHtml(betData.target || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Pivot:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.pivot || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Режим:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.mode || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Коэф PM (парсер):</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.coef || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Коэф ${escapeHtml(betData.second_bookmaker || 'BK2')} (вычисленный):</span>
                                        <span class="bet-detail-value">${(() => {
                                            if (betData.coef && betData.surebet_profit !== null && betData.surebet_profit !== undefined) {
                                                const inv_coef_bk2 = 1 - (betData.surebet_profit / 100) - (1 / parseFloat(betData.coef));
                                                if (inv_coef_bk2 > 0) {
                                                    return (1 / inv_coef_bk2).toFixed(2);
                                                }
                                            }
                                            return '-';
                                        })()}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Прибыль вилки (парсер):</span>
                                        <span class="bet-detail-value">${betData.surebet_profit ? betData.surebet_profit.toFixed(2) + '%' : '-'}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Источник:</span>
                                        <span class="bet-detail-value">${escapeHtml(betData.source || '-')}</span>
                                    </div>
                                </div>
                                <div class="bet-details-section">
                                    <h4>📤 Результат размещения на Polymarket</h4>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Статус:</span>
                                        <span class="bet-detail-value">${escapeHtml(result.status || '-')}</span>
                                    </div>
                                    ${result.polymarket_event ? `
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">🏟️ Событие PM:</span>
                                        <span class="bet-detail-value" style="color: #0369a1; font-weight: 600;">${escapeHtml(result.polymarket_event)}</span>
                                    </div>
                                    ` : ''}
                                    ${result.polymarket_market ? `
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">📊 Маркет PM:</span>
                                        <span class="bet-detail-value" style="color: #0369a1;">${escapeHtml(result.polymarket_market)}</span>
                                    </div>
                                    ` : ''}
                                    ${result.selected_outcome ? `
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">🎯 Поставили на:</span>
                                        <span class="bet-detail-value" style="font-weight: bold; color: #059669; font-size: 14px;">${escapeHtml(result.selected_outcome)}</span>
                                    </div>
                                    ` : ''}
                                    ${result.available_outcomes && result.available_outcomes.length > 0 ? `
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Доступные исходы:</span>
                                        <span class="bet-detail-value" style="font-size: 12px;">${escapeHtml(result.available_outcomes.join(' / '))}</span>
                                    </div>
                                    ` : ''}
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Order ID:</span>
                                        <span class="bet-detail-value" style="font-size: 11px;">${escapeHtml(result.order_id || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Market ID:</span>
                                        <span class="bet-detail-value" style="font-size: 11px;">${escapeHtml(result.market_id || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Token ID:</span>
                                        <span class="bet-detail-value" style="font-size: 11px;">${escapeHtml(result.token_id || '-')}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Цена покупки:</span>
                                        <span class="bet-detail-value">${result.order_price ? result.order_price.toFixed(4) : '-'}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">📈 Коэф Polymarket:</span>
                                        <span class="bet-detail-value" style="font-weight: bold; color: #059669;">${result.order_price ? (1 / result.order_price).toFixed(2) : '-'}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">💰 Реальная прибыль вилки:</span>
                                        <span class="bet-detail-value" style="font-weight: bold; color: ${(() => {
                                            if (result.order_price && betData.coef && betData.surebet_profit !== null && betData.surebet_profit !== undefined) {
                                                const inv_coef_bk2 = 1 - (betData.surebet_profit / 100) - (1 / parseFloat(betData.coef));
                                                const real_profit = (1 - result.order_price - inv_coef_bk2) * 100;
                                                return real_profit > 0 ? '#059669' : '#dc2626';
                                            }
                                            return '#6b7280';
                                        })()};">${(() => {
                                            if (result.order_price && betData.coef && betData.surebet_profit !== null && betData.surebet_profit !== undefined) {
                                                const inv_coef_bk2 = 1 - (betData.surebet_profit / 100) - (1 / parseFloat(betData.coef));
                                                const real_profit = (1 - result.order_price - inv_coef_bk2) * 100;
                                                return real_profit.toFixed(2) + '%';
                                            }
                                            return '-';
                                        })()}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Размер (shares):</span>
                                        <span class="bet-detail-value">${result.order_size ? result.order_size.toFixed(2) : '-'}</span>
                                    </div>
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Сумма ставки:</span>
                                        <span class="bet-detail-value">${betAmountUsd ? '$' + betAmountUsd.toFixed(2) : '-'}</span>
                                    </div>
                                    ${result.reason ? `
                                    <div class="bet-detail-item">
                                        <span class="bet-detail-label">Причина:</span>
                                        <span class="bet-detail-value" style="color: #dc2626;">${escapeHtml(result.reason)}</span>
                                    </div>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    </td>
                `;
                
                // Добавляем обработчик клика на строку
                row.addEventListener('click', () => toggleBetDetails(index, timestamp));
                
                tbody.appendChild(row);
                tbody.appendChild(detailsRow);
            });
        }
        
        function toggleBetDetails(index, timestamp) {
            const tbody = document.getElementById('bets-table');
            const row = tbody.querySelector(`.bet-row[data-bet-index="${index}"]`);
            const detailsRow = tbody.querySelector(`.bet-details-row[data-bet-index="${index}"]`);
            
            if (row && detailsRow) {
                const isExpanded = row.classList.toggle('expanded');
                detailsRow.classList.toggle('expanded');
                
                // Сохраняем состояние в localStorage
                saveExpandedState(timestamp, isExpanded);
            }
        }
        
        // Функции для работы с localStorage
        function getExpandedStates() {
            try {
                const stored = localStorage.getItem('expandedBets');
                return stored ? JSON.parse(stored) : {};
            } catch (e) {
                return {};
            }
        }
        
        function saveExpandedState(timestamp, isExpanded) {
            try {
                const states = getExpandedStates();
                if (isExpanded) {
                    states[timestamp] = true;
                } else {
                    delete states[timestamp];
                }
                // Ограничиваем количество сохранённых состояний (последние 50)
                const keys = Object.keys(states);
                if (keys.length > 50) {
                    keys.slice(0, keys.length - 50).forEach(key => delete states[key]);
                }
                localStorage.setItem('expandedBets', JSON.stringify(states));
            } catch (e) {
                console.warn('Could not save expanded state:', e);
            }
        }
        
        function isExpandedInStorage(timestamp) {
            const states = getExpandedStates();
            return states[timestamp] === true;
        }
        
        function updateLogs(logs) {
            const tbody = document.getElementById('logs-table');
            
            if (logs.length === 0) {
                if (tbody.children.length === 0 || tbody.children[0].cells.length !== 4) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 40px;">Нет логов</td></tr>';
                }
                return;
            }
            
            // Создаем карту существующих строк
            const existingRows = new Map();
            Array.from(tbody.children).forEach(row => {
                const timestampCell = row.querySelector('.timestamp');
                if (timestampCell) {
                    existingRows.set(timestampCell.textContent.trim(), row);
                }
            });
            
            // Очищаем tbody
            tbody.innerHTML = '';
            
            // Добавляем строки
            logs.forEach((log, index) => {
                const row = document.createElement('tr');
                const timestamp = formatDateTime(log.timestamp);
                const isNew = !existingRows.has(timestamp);
                
                if (isNew && index < 5) {
                    row.classList.add('new-row');
                }
                
                const jsonData = Object.keys(log.data || {}).length > 0 
                    ? JSON.stringify(log.data, null, 2).substring(0, 150) + (JSON.stringify(log.data || {}).length > 150 ? '...' : '')
                    : '-';
                
                row.innerHTML = `
                    <td class="timestamp">${timestamp}</td>
                    <td><span class="log-level ${log.level}">${log.level}</span></td>
                    <td>${escapeHtml(log.message)}</td>
                    <td class="json-data">${escapeHtml(jsonData)}</td>
                `;
                
                tbody.appendChild(row);
            });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatDateTime(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleString('ru-RU', { timeZone: 'Asia/Jakarta' });
        }
        
        // Функции для работы с настройками
        async function loadSettings() {
            try {
                const response = await fetch('/dashboard/api/settings?_=' + Date.now());
                if (!response.ok) throw new Error('Settings API error: ' + response.status);
                const settings = await response.json();
                
                document.getElementById('bet_amount').value = settings.bet_amount || 2.0;
                document.getElementById('max_bets_per_market').value = settings.max_bets_per_market || 1;
                document.getElementById('max_bets_per_match').value = settings.max_bets_per_match || 3;
            } catch (error) {
                console.error('Error loading settings:', error);
                const statusEl = document.getElementById('settings-status');
                statusEl.textContent = 'Ошибка загрузки настроек: ' + error.message;
                statusEl.style.color = '#ef4444';
            }
        }
        
        async function saveSettings(event) {
            event.preventDefault();
            const statusEl = document.getElementById('settings-status');
            
            try {
                statusEl.textContent = 'Сохранение...';
                statusEl.style.color = '#3b82f6';
                
                const formData = {
                    bet_amount: parseFloat(document.getElementById('bet_amount').value),
                    max_bets_per_market: parseInt(document.getElementById('max_bets_per_market').value),
                    max_bets_per_match: parseInt(document.getElementById('max_bets_per_match').value)
                };
                
                const response = await fetch('/dashboard/api/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Ошибка сохранения');
                }
                
                const updatedSettings = await response.json();
                statusEl.textContent = '✅ Настройки сохранены!';
                statusEl.style.color = '#10b981';
                
                setTimeout(() => {
                    statusEl.textContent = '';
                }, 3000);
            } catch (error) {
                console.error('Error saving settings:', error);
                statusEl.textContent = '❌ Ошибка: ' + error.message;
                statusEl.style.color = '#ef4444';
            }
        }
        
        // Загружаем настройки при открытии вкладки
        const originalShowTab = showTab;
        showTab = function(tabName) {
            originalShowTab(tabName);
            if (tabName === 'settings') {
                loadSettings();
            }
        };
        
        // График профита
        let profitChart = null;
        
        function updateProfitChart(profitData) {
            const ctx = document.getElementById('profitChart');
            if (!ctx || !window.Chart) return;
            
            const labels = profitData.map(d => {
                const date = new Date(d.date);
                return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'Asia/Jakarta' });
            });
            
            // Рассчитываем накопленный профит
            let cumulativeProfit = 0;
            const cumulativeProfits = profitData.map(d => {
                cumulativeProfit += d.profit || 0;
                return cumulativeProfit;
            });
            
            // Если график уже существует, обновляем данные плавно
            if (profitChart) {
                // Проверяем, изменились ли данные
                const currentLabels = profitChart.data.labels;
                const currentData = profitChart.data.datasets[0].data;
                
                const labelsChanged = JSON.stringify(currentLabels) !== JSON.stringify(labels);
                const dataChanged = JSON.stringify(currentData) !== JSON.stringify(cumulativeProfits);
                
                if (labelsChanged || dataChanged) {
                    profitChart.data.labels = labels;
                    profitChart.data.datasets[0].data = cumulativeProfits;
                    // Обновляем с плавной анимацией (duration: 500ms)
                    profitChart.update({
                        duration: 500,
                        easing: 'easeInOutQuart',
                        lazy: false
                    });
                }
                return;
            }
            
            // Создаем график только при первой загрузке
            profitChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Накопленный профит (USD)',
                        data: cumulativeProfits,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {
                        duration: 750,
                        easing: 'easeInOutQuart'
                    },
                    transitions: {
                        show: {
                            animations: {
                                x: { from: 0 },
                                y: { from: 0 }
                            }
                        },
                        hide: {
                            animations: {
                                x: { to: 0 },
                                y: { to: 0 }
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            ticks: {
                                callback: function(value) {
                                    return value.toFixed(2) + ' USD';
                                }
                            }
                        }
                    }
                }
            });
        }
        
        // Загружаем данные при загрузке страницы
        loadData(true);
        
        // Автообновление каждую минуту (без показа статуса)
        setInterval(() => loadData(false), 60000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@router.get("/api/stats")
async def get_stats():
    """API для получения статистики (все ставки из БД, без фильтрации по позициям)"""
    return log_storage.get_stats()



@router.get("/api/balance")
async def get_balance():
    """API для получения текущего баланса USDC на Polymarket"""
    # Прямая проверка через Web3 — работает для любого адреса
    proxy_address = getattr(_settings, 'polymarket_proxy_address', None)
    if proxy_address and _clob_client:
        try:
            balance = _clob_client.get_usdc_balance_direct(proxy_address)
            if balance is not None:
                return {"balance": round(balance, 2), "address": proxy_address}
        except Exception:
            pass

    # Fallback: через CLOB API
    if _clob_client and _clob_client.is_available():
        try:
            info = _clob_client.get_balance()
            bal = info.get("balance") if isinstance(info, dict) else info
            if bal is not None:
                return {"balance": round(float(bal), 2)}
        except Exception:
            pass

    return {"balance": None}


@router.get("/api/bets-history")
async def get_bets_history(limit: int = 100):
    """API для получения последних успешных ставок."""
    return log_storage.get_recent_bets(limit, status_filter="success")


@router.get("/api/logs-history")
async def get_logs_history(limit: int = 100):
    """API для получения истории логов"""
    return log_storage.get_recent_logs(limit)


@router.get("/api/profit-data")
async def get_profit_data(days: int = 30):
    """API для получения данных профита для графика"""
    return log_storage.get_profit_data(days)


@router.get("/api/real-pnl")
async def get_real_pnl():
    """Получение реального PnL из Polymarket API"""
    try:
        if not _polymarket_client:
            raise HTTPException(status_code=500, detail="Polymarket client not available")
        
        checker = BetStatusChecker(_polymarket_client)
        real_pnl = await checker.get_real_pnl_from_polymarket()
        
        # Также получаем наш расчет из БД
        stats = log_storage.get_stats()
        db_profit = stats.get("total_profit", 0.0)
        
        return {
            "polymarket_pnl": real_pnl,
            "database_profit": db_profit,
            "difference": round(real_pnl.get("total_pnl", 0) - db_profit, 2) if "error" not in real_pnl else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/settings")
async def get_settings():
    """API для получения настроек ставок"""
    settings_service = get_settings_service()
    return settings_service.get_settings()


@router.post("/api/settings")
async def update_settings(settings_update: BetSettingsUpdate):
    """API для обновления настроек ставок"""
    settings_service = get_settings_service()
    try:
        update_dict = settings_update.dict(exclude_none=True)
        if not update_dict:
            raise HTTPException(status_code=400, detail="No settings provided")
        updated_settings = settings_service.update_settings(update_dict)
        return updated_settings
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")
