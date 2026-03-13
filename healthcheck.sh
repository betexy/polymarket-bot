#!/bin/bash
# Polymarket Bot Health Check
# Checks if the dashboard is responding, restarts service if not

LOG="/root/polymarket_bot/bot.log"
SERVICE="polymarket-bot"
MAX_FAILURES=3
FAILURE_FILE="/tmp/polymarket_bot_failures"

# Initialize failure counter
if [ ! -f "$FAILURE_FILE" ]; then
    echo 0 > "$FAILURE_FILE"
fi

FAILURES=$(cat "$FAILURE_FILE")

# Check if service is active
if ! systemctl is-active --quiet "$SERVICE"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - HEALTHCHECK: Service not running, starting..." >> "$LOG"
    systemctl start "$SERVICE"
    echo 0 > "$FAILURE_FILE"
    exit 0
fi

# Check if HTTP endpoint responds (timeout 10s)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8000/dashboard/ 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
    # Success - reset failure counter
    if [ "$FAILURES" -gt 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - HEALTHCHECK: Recovered after $FAILURES failures" >> "$LOG"
    fi
    echo 0 > "$FAILURE_FILE"
    exit 0
fi

# Failure
FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$FAILURE_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - HEALTHCHECK: Dashboard unreachable (HTTP $HTTP_CODE), failure $FAILURES/$MAX_FAILURES" >> "$LOG"

if [ "$FAILURES" -ge "$MAX_FAILURES" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - HEALTHCHECK: $MAX_FAILURES consecutive failures, restarting service..." >> "$LOG"
    systemctl restart "$SERVICE"
    echo 0 > "$FAILURE_FILE"
fi
