from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from app.services.logger_service import log_storage
from app.services.settings_service import get_settings_service

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
                const [statsResponse, betsResponse, logsResponse, profitResponse] = await Promise.all([
                    fetch('/dashboard/api/stats?_=' + Date.now()),
                    fetch('/dashboard/api/bets-history?_=' + Date.now()),
                    fetch('/dashboard/api/logs-history?_=' + Date.now()),
                    fetch('/dashboard/api/profit-data?days=30&_=' + Date.now())
                ]);
                
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
            
            // Плавное обновление значений
            const statCards = statsDiv.querySelectorAll('.stat-card .value');
            if (statCards.length > 0) {
                // Обновляем только значения, не пересоздавая карточки
                const values = [
                    stats.total_bets,
                    stats.successful_orders,
                    `${profitSign}${totalProfit.toFixed(2)} USD`,
                    stats.skipped_orders || 0,
                    stats.failed_orders,
                    stats.last_update ? new Date(stats.last_update).toLocaleString('ru-RU', { timeZone: 'Asia/Jakarta' }) : 'Нет данных'
                ];
                
                statCards.forEach((el, idx) => {
                    if (idx < values.length) {
                        el.classList.add('updating');
                        setTimeout(() => {
                            el.textContent = values[idx];
                            el.classList.remove('updating');
                        }, 100);
                    }
                });
            } else {
                // Первая загрузка - создаем карточки
                statsDiv.innerHTML = `
                    <div class="stat-card">
                        <h3>Всего ставок</h3>
                        <div class="value">${stats.total_bets}</div>
                    </div>
                    <div class="stat-card success">
                        <h3>Размещено на Polymarket</h3>
                        <div class="value">${stats.successful_orders}</div>
                    </div>
                    <div class="stat-card ${profitClass}">
                        <h3>Общий профит</h3>
                        <div class="value">${profitSign}${totalProfit.toFixed(2)} USD</div>
                    </div>
                    <div class="stat-card" style="background: #fef3c7;">
                        <h3>Пропущено</h3>
                        <div class="value" style="color: #92400e;">${stats.skipped_orders || 0}</div>
                    </div>
                    <div class="stat-card error">
                        <h3>Ошибок</h3>
                        <div class="value">${stats.failed_orders}</div>
                    </div>
                    <div class="stat-card">
                        <h3>Последнее обновление</h3>
                        <div class="value" style="font-size: 14px;">${stats.last_update ? new Date(stats.last_update).toLocaleString('ru-RU', { timeZone: 'Asia/Jakarta' }) : 'Нет данных'}</div>
                    </div>
                `;
            }
        }
        
        function updateBets(bets) {
            const tbody = document.getElementById('bets-table');
            
            if (bets.length === 0) {
                if (tbody.children.length === 0 || tbody.children[0].cells.length !== 10) {
                    tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; padding: 40px;">Нет данных о ставках</td></tr>';
                }
                return;
            }
            
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
                
                if (isNew && index < 5) {
                    row.classList.add('new-row');
                }
                
                // Используем market_display если доступно, иначе fallback к betData.market
                const marketDisplay = bet.market_display || betData.market || '-';
                const source = bet.source || betData.source || '-';
                
                row.innerHTML = `
                    <td class="timestamp">${timestamp}</td>
                    <td>${betData.homeTeam || '-'} vs ${betData.awayTeam || '-'}</td>
                    <td>${marketDisplay}</td>
                    <td>${betData.coef || '-'}</td>
                    <td>${betData.surebet_profit ? betData.surebet_profit.toFixed(2) + '%' : '-'}</td>
                    <td>${betData.second_bookmaker || '-'}</td>
                    <td>${source}</td>
                    <td><span class="status ${statusClass}">${statusText}</span></td>
                    <td>${betAmountText}</td>
                    <td><span class="status ${resultClass}">${resultText}</span></td>
                `;
                
                tbody.appendChild(row);
            });
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
        
        // Автообновление каждые 5 секунд (без показа статуса)
        setInterval(() => loadData(false), 5000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@router.get("/api/stats")
async def get_stats():
    """API для получения статистики"""
    return log_storage.get_stats()


@router.get("/api/bets-history")
async def get_bets_history(limit: int = 100):
    """API для получения истории ставок"""
    return log_storage.get_recent_bets(limit)


@router.get("/api/logs-history")
async def get_logs_history(limit: int = 100):
    """API для получения истории логов"""
    return log_storage.get_recent_logs(limit)


@router.get("/api/profit-data")
async def get_profit_data(days: int = 30):
    """API для получения данных профита для графика"""
    return log_storage.get_profit_data(days)


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
