#!/bin/bash
# Обновляет apr.json и отправляет уведомления об изменениях LP1 в Telegram.

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/cron_apr.log"
LOCK="/tmp/revert_apr_cron.lock"

exec 200>"$LOCK"
flock -n 200 || { echo "[$(date '+%F %T')] уже запущен, пропуск" >> "$LOG"; exit 0; }

cd "$DIR"
echo "[$(date '+%F %T')] fetch start" >> "$LOG"
timeout 240 python3 fetch_revert_apr.py >> "$LOG" 2>&1 || {
    echo "[$(date '+%F %T')] fetch failed" >> "$LOG"; exit 1;
}

# LP1 notifications run on every tick (range changes don't always affect APR)
python3 notify_lp.py >> "$LOG" 2>&1 || true

if git diff --quiet apr.json 2>/dev/null; then
    echo "[$(date '+%F %T')] no changes" >> "$LOG"
    exit 0
fi

git add apr.json
git commit -m "auto: update apr $(date '+%F %H:%M')" >> "$LOG" 2>&1
git push >> "$LOG" 2>&1
echo "[$(date '+%F %T')] pushed" >> "$LOG"
