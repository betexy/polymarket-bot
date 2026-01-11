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
        }
        .stat-card.success .value { color: #10b981; }
        .stat-card.error .value { color: #ef4444; }
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
            <button class="refresh-btn" onclick="loadData()">🔄 Обновить</button>
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
                            <th>Рынок</th>
                            <th>Коэффициент</th>
                            <th>Прибыль %</th>
                            <th>Second BK</th>
                            <th>Статус</th>
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
        
        async function loadData() {
            const statusEl = document.getElementById('update-status');
            try {
                statusEl.textContent = 'Обновление...';
                statusEl.style.color = '#3b82f6';
                
                // Загружаем статистику
                const statsResponse = await fetch('/dashboard/api/stats?_=' + Date.now());
                if (!statsResponse.ok) throw new Error('Stats API error: ' + statsResponse.status);
                const stats = await statsResponse.json();
                displayStats(stats);
                
                // Загружаем ставки
                const betsResponse = await fetch('/dashboard/api/bets-history?_=' + Date.now());
                if (!betsResponse.ok) throw new Error('Bets API error: ' + betsResponse.status);
                const bets = await betsResponse.json();
                displayBets(bets);
                
                // Загружаем данные для графика профита
                try {
                    const profitResponse = await fetch('/dashboard/api/profit-data?days=30&_=' + Date.now());
                    if (profitResponse.ok) {
                        const profitData = await profitResponse.json();
                        updateProfitChart(profitData);
                    }
                } catch (error) {
                    console.error('Error loading profit data:', error);
                }
                
                // Загружаем логи
                const logsResponse = await fetch('/dashboard/api/logs-history?_=' + Date.now());
                if (!logsResponse.ok) throw new Error('Logs API error: ' + logsResponse.status);
                const logs = await logsResponse.json();
                displayLogs(logs);
                
                statusEl.textContent = 'Обновлено: ' + new Date().toLocaleTimeString('ru-RU');
                statusEl.style.color = '#10b981';
                setTimeout(() => {
                    if (statusEl.textContent.includes('Обновлено:')) {
                        statusEl.textContent = '';
                    }
                }, 3000);
            } catch (error) {
                console.error('Error loading data:', error);
                statusEl.textContent = 'Ошибка: ' + error.message;
                statusEl.style.color = '#ef4444';
            }
        }
        
        function displayStats(stats) {
            const statsDiv = document.getElementById('stats');
            const totalProfit = stats.total_profit || 0.0;
            const profitClass = totalProfit >= 0 ? 'success' : 'error';
            const profitSign = totalProfit >= 0 ? '+' : '';
            
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
                    <div class="value" style="font-size: 14px;">${stats.last_update ? new Date(stats.last_update).toLocaleString('ru-RU') : 'Нет данных'}</div>
                </div>
            `;
        }
        
        function displayBets(bets) {
            const tbody = document.getElementById('bets-table');
            if (bets.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;">Нет данных о ставках</td></tr>';
                return;
            }
            
            tbody.innerHTML = bets.map(bet => {
                const betData = bet.bet_data;
                const result = bet.result;
                const status = result.status || 'unknown';
                const statusClass = status === 'success' ? 'success' : status === 'error' ? 'error' : 'skipped';
                const statusText = status === 'success' ? 'Успешно' : status === 'error' ? 'Ошибка' : 'Пропущено';
                
                // Получаем информацию о результате
                const profit = result.profit;
                const resultStatus = result.result_status || (result.profit !== null && result.profit !== undefined ? (result.profit >= 0 ? 'win' : 'loss') : 'pending');
                let resultText = '-';
                let resultClass = '';
                
                if (resultStatus === 'win') {
                    resultText = `✅ Выигрыш: +${profit ? profit.toFixed(2) : '0.00'} USD`;
                    resultClass = 'success';
                } else if (resultStatus === 'loss') {
                    resultText = `❌ Проигрыш: ${profit ? profit.toFixed(2) : '0.00'} USD`;
                    resultClass = 'error';
                } else if (resultStatus === 'closed') {
                    resultText = '⏸ Закрыт';
                    resultClass = 'skipped';
                } else if (status === 'success') {
                    resultText = '⏳ В ожидании';
                    resultClass = '';
                }
                
                return `
                    <tr>
                        <td class="timestamp">${formatDateTime(bet.timestamp)}</td>
                        <td>${betData.homeTeam || '-'} vs ${betData.awayTeam || '-'}</td>
                        <td>${betData.market || '-'}</td>
                        <td>${betData.coef || '-'}</td>
                        <td>${betData.surebet_profit ? betData.surebet_profit.toFixed(2) + '%' : '-'}</td>
                        <td>${betData.second_bookmaker || '-'}</td>
                        <td><span class="status ${statusClass}">${statusText}</span></td>
                        <td><span class="status ${resultClass}">${resultText}</span></td>
                    </tr>
                `;
            }).join('');
        }
        
        function displayLogs(logs) {
            const tbody = document.getElementById('logs-table');
            if (logs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 40px;">Нет логов</td></tr>';
                return;
            }
            
            tbody.innerHTML = logs.map(log => {
                return `
                    <tr>
                        <td class="timestamp">${formatDateTime(log.timestamp)}</td>
                        <td><span class="log-level ${log.level}">${log.level}</span></td>
                        <td>${log.message}</td>
                        <td class="json-data">${Object.keys(log.data || {}).length > 0 ? JSON.stringify(log.data, null, 2).substring(0, 150) : '-'}${JSON.stringify(log.data || {}).length > 150 ? '...' : ''}</td>
                    </tr>
                `;
            }).join('');
        }
        
        function formatDateTime(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleString('ru-RU');
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
                return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
            });
            
            // Рассчитываем накопленный профит
            let cumulativeProfit = 0;
            const cumulativeProfits = profitData.map(d => {
                cumulativeProfit += d.profit || 0;
                return cumulativeProfit;
            });
            
            if (profitChart) {
                profitChart.destroy();
            }
            
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
        loadData();
        
        // Автообновление каждые 5 секунд
        setInterval(loadData, 5000);
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
