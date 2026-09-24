# 運動中心人數監控

每 10 分鐘記錄各運動中心健身房／游泳池／冰宮的即時人數，並用 dashboard
顯示當下人數與單日各時段折線圖。

完整設計理由見 `~/.claude/plans/python-1-cosmic-orbit.md`。

## 快速開始

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # 填進 POSTGRES_PASSWORD
docker compose up -d --build
open http://localhost:8000
```

`poller` 會每 10 分鐘自動抓一次。想立刻抓一筆：

```bash
docker compose run --rm poller python poll.py
```

## 開發（不走 Docker 跑前端）

```bash
docker compose up -d db                       # 只開資料庫
python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt
cd backend && DATABASE_URL="postgresql://gym:<密碼>@localhost:5432/gym" \
  ../.venv/bin/uvicorn main:app --reload
cd frontend && npm install && npm run dev      # http://localhost:5173
```

`vite.config.ts` 已把 `/api` proxy 到 8000，所以前後端都不需要設 CORS。

測試：`cd backend && ../.venv/bin/python -m pytest test_parse.py -q`

## 新增一個場館

所有救國團運動中心共用同一種 API。先確認新場館有沒有：

```bash
curl -s https://<子網域>.cyc.org.tw/api
```

有回 `{"gym":[...]}` 就把它加進 `backend/venues.json`（k8s 則是編輯
`k8s/venues-configmap.yaml`）：

```json
{"id": "nhsc", "name": "內湖運動中心", "url": "https://nhsc.cyc.org.tw/api"}
```

**不需要改任何程式碼或資料庫 schema。** 場館數、每個場館有哪些區域
（有些有冰宮、有些沒有）都是資料而不是程式邏輯。

目前已確認可用：`ngsc` 南港、`nhsc` 內湖、`wssc` 文山（含冰宮）。

## 兩條不能改的規則

1. **抓取失敗時絕對不寫入 0。** 上游會用 `"找不到資源…"` 取代數字。
   把它存成 0，圖上就會出現一個和「真的沒人」無法區分的點。
   沒有資料就留空。
2. **缺漏的時段在圖上必須是斷線。** `/api/series` 對沒有資料的 bucket
   回 `null`，前端 `connectNulls={false}`。把斷點連起來等於畫出
   從來沒有採集過的資料。

## 營業時間

場館營業時間固定為台灣時間 **08:00–22:00**，定義在 `backend/main.py` 的
`OPEN_TIME` / `CLOSE_TIME`。

這個區間之外，場館關門、上游回傳 0，圖上會是一整片沒有意義的零，
把真正要看的白天區段壓扁。因此 `/api/latest` 與 `/api/series`
**都只回傳營業時間內的資料**。

過濾是在**讀取時**做的，不是寫入時：非營業時間的資料列照常存進資料庫。
所以要改時間、或要看回夜間資料，改常數就好，不需要回填。

## 本機常駐部署

```bash
docker compose up -d --build
```

**`--build` 不能省。** 沒有它，Compose 會沿用舊 image，程式改了卻不生效，
而容器狀態照樣顯示 `Up` —— 沒有任何錯誤訊息告訴你在跑舊程式碼。
確認容器裡真的是新程式：

```bash
docker compose exec -T poller grep -c "def parse_aggregate" poll.py
```

三個服務都設了 `restart: unless-stopped`，所以容器崩潰或 Docker 重啟後會自己回來。
資料放在具名 volume，`docker compose down` 不會刪。已實測：down 再 up，316 列一列沒少。

**還缺一步，要你自己點：** Docker Desktop 的
Settings → General → **Start Docker Desktop when you sign in** 打勾。
沒打勾的話，Mac 重開機後 Docker 本身不會啟動，`restart: unless-stopped` 也就無從生效。

想確認重開機後真的活著，重開一次再跑 `./check.sh`。

## 雲端部署

見 [DEPLOY.md](DEPLOY.md)。筆電會睡，雲端不會 —— 缺掉的早上補不回來。

## 筆電睡眠 = 資料斷掉

macOS 睡眠會把整個 Docker 虛擬機一起凍結，容器裡的 `time.sleep()` 不會前進。
容器狀態還是 `Up`，但那段時間完全沒有抓取 —— 圖上就是一個洞。
**沒有任何 Docker 設定能繞過這件事。**

想收完整的一天，選一個：

```bash
# A. 暫時不讓筆電睡（接電源、螢幕不要闔上）。Ctrl+C 結束
caffeinate -i

# B. 只在跑某個指令期間不睡
caffeinate -i docker compose logs -f poller
```

長期的正解是把 poller 放到雲端，那才是真正的 24 小時。

## 排查

```bash
./check.sh ngsc
```

從上游 → 容器 → poller log → 資料庫 → API 依序檢查，第一個出錯的站就是問題所在。

注意：**容器 log 是 UTC，台灣時間要 +8。**

## 對外公開

1. 在 Cloudflare Zero Trust 建立 tunnel，指向 `http://api:8000`。
2. 把 token 填進 `.env` 的 `CLOUDFLARE_TUNNEL_TOKEN`。
3. 設 Access 政策，限定自己的 email。
4. `docker compose --profile public up -d`

應用程式本身沒有任何認證程式碼——認證在應用程式外面，所以這個決定隨時可以換掉。

上線前確認 Postgres 沒有對外曝露（compose 已綁 `127.0.0.1`）：

```bash
nmap -Pn -p 5432 <你的對外 IP>    # 預期 closed / filtered
```

## k8s

```bash
kubectl create secret generic gym-monitor \
  --from-literal=postgres-password='<密碼>' \
  --from-literal=database-url='postgresql://gym:<密碼>@gym-db:5432/gym' \
  --from-literal=tunnel-token='<token>'
kubectl apply -f k8s/
```

`poll.py` 跑完一次就結束，所以排程直接交給 CronJob，專案裡沒有任何排程程式碼。

## 已知狀況

上游憑證鏈的中繼 CA（TWCA）缺少 RFC 5280 要求的 Subject Key Identifier
擴充欄位，而 Python 3.13+ 預設開啟 `VERIFY_X509_STRICT` 會直接拒絕。
`poll.py` 只關掉這一項檢查，**憑證鏈驗證與 hostname 驗證都還在**
（不是 `verify=False`）。上游修好憑證後可以移除。
