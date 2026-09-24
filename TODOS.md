# TODOS

來源：2026-09-24 的 /office-hours 設計文件與 /plan-eng-review 審查報告。
- 設計：`~/.gstack/projects/ZoeWty-gym_user_amount_monitor/zoe-main-design-20260924-152728.md`
- 審查：`~/.gstack/projects/ZoeWty-gym_user_amount_monitor/main-eng-review-20260924-154434.md`

## 第 1 步：12 間、驗證層、上雲端（本週，時間敏感）

- [x] ~~`venues.json` schema 改為 per-source areas~~ → 改成更小的做法：聚合 API 本身就是場館清單，不再維護 12 間的列表，中山的雙 id 問題因此消失
- [x] 聚合 API 解析函式 + 測試（正常／缺欄位／非數字／空清單）
- [x] `poll.py`：聚合與 CYC 各自獨立 try/except；CYC 只取白名單區域（文山只拿 ice）
- [x] 讀取層加「超過容留」過濾 + 測試（北投泳池 974/200 是現成樣本）
- [x] ~~納入 12 間、註明別名~~ → 不需要：場館與名稱都來自聚合 API，只有一個 id 命名空間
- [ ] 部署到雲端 VM，Postgres 綁 127.0.0.1
- [x] `scripts/backup.sh`：dump 後自動還原到臨時資料庫比對列數，不符就 exit 1（演練內建，不是另一支要記得跑的腳本）
- [ ] 把 `scripts/backup.sh` 掛上 VM 的 cron，輸出目錄指到 VM 以外的儲存空間

## 本週的實地作業

- [ ] 問 3 位下班後會去運動中心的人：「上一次去了才發現人太多，是什麼時候？哪一間、幾點？」記下名字、場館、時間

## 之後（接近時各審一次）

- [x] 第 2 步（地圖部分）：Leaflet + OSM 地圖，12 間標點依使用率上色，點標記切換場館，瀏覽器定位 + 最近三間（距離在前端算，位置不上傳）
- [ ] 第 2 步（清單部分）：依使用率 + 距離排序的完整比較清單
- [x] 第 3 步：`/api/recommend` 確定性排序（依使用率，可選 near/max_km；營業時間內全 0 的場館排除）
- [x] Dify 串接方式：直接匯入 FastAPI 的 OpenAPI spec 當 Custom Tool（見 DIFY.md），已實測 Dify 容器打得到
- [ ] 在 Dify 介面上實際建出 Chatflow 並測三個情境（DIFY.md 第 4 節）
- [ ] 第 4 步：熱力圖（≥2 週資料）、到達時預測（≥4 週資料）
- [ ] 第 5 步：遷移 k8s，收集器改 CronJob
- [ ] 第 6 步：LINE

## 未解決

- [ ] 數值凍結偵測（驗證規則 3）要不要做？需跨列比較，成本高於前兩條
- [ ] 聚合 API 失效時的備援？CYC 只涵蓋 4 間
- [ ] 12 間營業時間是否都是 08:00–22:00？目前是未驗證的假設
- [ ] 座標來自 OpenStreetMap Nominatim，已用台北市範圍檢查過，但沒有逐間到現場核對
- [ ] 北投泳池的數字是否為累計進場人次？需再觀察幾天
- [ ] 付費方是誰？尚未跟任何潛在付費方談過
