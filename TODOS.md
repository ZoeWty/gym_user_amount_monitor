# TODOS

來源：2026-09-24 的 /office-hours 設計文件與 /plan-eng-review 審查報告。
- 設計：`~/.gstack/projects/ZoeWty-gym_user_amount_monitor/zoe-main-design-20260924-152728.md`
- 審查：`~/.gstack/projects/ZoeWty-gym_user_amount_monitor/main-eng-review-20260924-154434.md`

## 第 1 步：12 間、驗證層、上雲端（本週，時間敏感）

- [ ] `venues.json` schema 改為 per-source areas；`venues.py` 加「同一場館區域不得重疊」驗證與測試
- [ ] 聚合 API 解析函式 + 測試（正常／缺欄位／非數字／空清單）
- [ ] `poll.py`：聚合與 CYC 各自獨立 try/except；CYC 只取白名單區域（文山只拿 ice）
- [ ] 讀取層加「超過容留」過濾 + 測試（北投泳池 974/200 是現成樣本）
- [ ] `venues.json` 納入 12 間；中山用 `zssc`，註明 `cssc` 是同一間的別名
- [ ] 部署到雲端 VM，Postgres 綁 127.0.0.1
- [ ] 每日 `pg_dump` 到 VM 以外
- [ ] **執行一次還原演練**：還原到空資料庫，確認列數與最新時間戳相符

## 本週的實地作業

- [ ] 問 3 位下班後會去運動中心的人：「上一次去了才發現人太多，是什麼時候？哪一間、幾點？」記下名字、場館、時間

## 之後（接近時各審一次）

- [ ] 第 2 步：依使用率加距離排序的比較清單、地圖
- [ ] 第 3 步：`/api/recommend`（確定性排序）、Dify chatbot
- [ ] 第 4 步：熱力圖（≥2 週資料）、到達時預測（≥4 週資料）
- [ ] 第 5 步：遷移 k8s，收集器改 CronJob
- [ ] 第 6 步：LINE

## 未解決

- [ ] 數值凍結偵測（驗證規則 3）要不要做？需跨列比較，成本高於前兩條
- [ ] 聚合 API 失效時的備援？CYC 只涵蓋 4 間
- [ ] 12 間營業時間是否都是 08:00–22:00？目前是未驗證的假設
- [ ] 北投泳池的數字是否為累計進場人次？需再觀察幾天
- [ ] 付費方是誰？尚未跟任何潛在付費方談過
