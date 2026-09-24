import { useEffect, useState } from 'react'
import OccupancyChart from './OccupancyChart'
import StatCard from './StatCard'
import VenueMap from './VenueMap'
import type { Latest, Series, Venue } from './types'

/** Today's date in Taipei, as YYYY-MM-DD, regardless of the browser's zone. */
const taipeiToday = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei' }).format(new Date())

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

// Upstream only refreshes once a minute, so polling faster gains nothing.
const REFRESH_MS = 60_000

// The poller runs every 10 minutes, so anything older than this means
// collection has stopped -- a laptop asleep, a dead container, a network
// outage. The number on the card stays plausible while going badly stale,
// which is the failure worth shouting about.
const STALE_MS = 15 * 60_000

/**
 * Fetch `url` now, and while `live` is true keep it current two ways:
 * on a timer, and whenever the tab returns to the foreground.
 *
 * The visibility half is the one that matters on a phone: mobile browsers
 * freeze timers in a backgrounded tab, so the moment you take the phone out
 * of your pocket is exactly when the data is stalest and the timer is least
 * likely to fire. Refetch then rather than waiting out the rest of the
 * interval. (A WebSocket would not help here -- the connection gets dropped
 * in the background too.)
 */
function useLiveFetch<T>(
  url: string | null,
  live: boolean,
  onError: (message: string) => void,
): T | null {
  const [data, setData] = useState<T | null>(null)

  useEffect(() => {
    if (!url) return
    let cancelled = false
    const load = () =>
      getJSON<T>(url)
        .then((d) => { if (!cancelled) setData(d) })
        .catch((e) => { if (!cancelled) onError(String(e)) })

    load()
    if (!live) return () => { cancelled = true }

    const timer = setInterval(load, REFRESH_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') load()
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [url, live, onError])

  return data
}

export default function App() {
  const [venues, setVenues] = useState<Venue[]>([])
  const [venue, setVenue] = useState<string>('')
  const [date, setDate] = useState<string>(taipeiToday())
  const [error, setError] = useState<string | null>(null)

  const today = taipeiToday()
  const isToday = date === today


  useEffect(() => {
    getJSON<Venue[]>('/api/venues')
      .then((vs) => {
        setVenues(vs)
        setVenue((v) => v || vs[0]?.id || '')
      })
      .catch((e) => setError(String(e)))
  }, [])

  // Both stay live only while today is on screen; a past day cannot change.
  const latest = useLiveFetch<Latest>(
    venue ? `/api/latest?venue=${venue}` : null, isToday, setError)
  const series = useLiveFetch<Series>(
    venue ? `/api/series?venue=${venue}&date=${date}` : null, isToday, setError)
  // Recomputed on every render, and useLiveFetch re-renders once a minute
  // whether the fetch succeeds or fails, so no separate ticker is needed.
  const fetchedAt = latest?.fetched_at ? new Date(latest.fetched_at) : null
  const age = fetchedAt ? Date.now() - fetchedAt.getTime() : 0
  const staleMinutes = fetchedAt && age > STALE_MS ? Math.round(age / 60_000) : null

  return (
    <main>
      <h1>運動中心人數監控</h1>

      <div className="controls">
        <label>
          場館
          <select value={venue} onChange={(e) => setVenue(e.target.value)}>
            {venues.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </label>
        <label>
          日期
          <input
            type="date"
            value={date}
            max={today}
            onChange={(e) => setDate(e.target.value || today)}
          />
        </label>
        {!isToday && (
          <button onClick={() => setDate(today)}>回到今天</button>
        )}
      </div>

      {error && <p className="error">讀取失敗：{error}</p>}

      <section className="cards">
        {latest && Object.entries(latest.areas).map(([area, v]) => (
          <StatCard key={area} area={area} current={v.current} capacity={v.capacity} />
        ))}
      </section>

      {fetchedAt && (
        <p className={staleMinutes === null ? 'updated' : 'updated stale'}>
          最後更新 {fetchedAt.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}
          {staleMinutes !== null && ` ⚠ 已 ${staleMinutes} 分鐘沒有新資料，上方數字不是現在的狀況`}
        </p>
      )}

      <h2>
        {isToday ? '今日' : date} 各時段人數
        {series && <span className="hours"> 營業時間 {series.open_from}–{series.open_to}</span>}
      </h2>
      {series ? <OccupancyChart series={series} /> : <p className="empty">載入中…</p>}
      <p className="note">線段中斷表示該時段沒有採集到資料。</p>

      {venues.length > 0 && (
        <VenueMap venues={venues} selected={venue} onSelect={setVenue} />
      )}
    </main>
  )
}
