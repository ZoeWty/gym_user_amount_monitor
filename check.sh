#!/usr/bin/env bash
# 資料從哪裡斷掉？從源頭往螢幕方向一站一站檢查。
# 第一個出錯的站就是問題所在 —— 後面的站不用看。
set -uo pipefail
cd "$(dirname "$0")"
V="${1:-ngsc}"

echo "現在時間: $(date '+%H:%M %Z')   場館: $V"

echo
echo "① 上游網站 —— 對方有沒有給資料？"
curl -s -m 10 "https://$V.cyc.org.tw/api" || echo "  ✗ 連不到上游"

echo
echo "② 容器 —— 三個服務都活著嗎？"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'

echo
echo "③ poller —— 最近一次抓取成功了嗎？(log 是 UTC，台灣時間要 +8)"
docker compose logs poller --no-log-prefix --tail 30 2>/dev/null \
  | grep -vE "httpx HTTP" | tail -5

echo
echo "④ 資料庫 —— 資料真的寫進去了嗎？"
docker compose exec -T db psql -U gym -d gym -tAc \
  "SELECT to_char(ts AT TIME ZONE 'Asia/Taipei','MM-DD HH24:MI:SS')||'  '||area||'='||current
   FROM occupancy WHERE venue='$V' ORDER BY ts DESC LIMIT 4;" 2>/dev/null \
  || echo "  ✗ 查不到資料庫"

echo
echo "⑤ 有沒有重複列？(同一個 venue/area/ts 出現兩次 = 某個區域被兩個來源寫入)"
docker compose exec -T db psql -U gym -d gym -tAc \
  "SELECT coalesce(string_agg(venue||'/'||area, ', '), '  無') FROM
   (SELECT venue, area FROM occupancy GROUP BY venue, area, ts HAVING count(*) > 1) d;" \
  2>/dev/null || echo "  ✗ 查不到資料庫"

echo
echo "⑥ API —— 後端吐出來的是什麼？"
curl -s -m 5 "http://localhost:8000/api/latest?venue=$V" || echo "  ✗ API 沒回應"

echo
echo "── ①~⑥ 都正常 = 後端沒事，問題在瀏覽器快取，按 Cmd+Shift+R 硬重新整理 ──"
