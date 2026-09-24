import { useEffect, useState } from 'react'
import OccupancyChart from './OccupancyChart'
import StatCard from './StatCard'
import type { Latest, Series, Venue } from './types'

/** Today's date in Taipei, as YYYY-MM-DD, regardless of the browser's zone. */
const taipeiToday = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei' }).format(new Date())

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export default function App() {
  const [venues, setVenues] = useState<Venue[]>([])
  const [venue, setVenue] = useState<string>('')
  const [date, setDate] = useState<string>(taipeiToday())
  const [latest, setLatest] = useState<Latest | null>(null)
  const [series, setSeries] = useState<Series | null>(null)
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

  // Live numbers. Only poll while looking at today -- a past day cannot change.
  useEffect(() => {
    if (!venue) return
    let cancelled = false
    const load = () =>
      getJSON<Latest>(`/api/latest?venue=${venue}`)
        .then((d) => !cancelled && setLatest(d))
        .catch((e) => !cancelled && setError(String(e)))
    load()
    if (!isToday) return () => { cancelled = true }
    // 60s matches how often upstream itself refreshes; faster gains nothing.
    const id = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [venue, isToday])

  useEffect(() => {
    if (!venue) return
    let cancelled = false
    getJSON<Series>(`/api/series?venue=${venue}&date=${date}`)
      .then((d) => !cancelled && setSeries(d))
      .catch((e) => !cancelled && setError(String(e)))
    return () => { cancelled = true }
  }, [venue, date])

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

      {latest?.fetched_at && (
        <p className="updated">
          最後更新 {new Date(latest.fetched_at).toLocaleString('zh-TW', {
            timeZone: 'Asia/Taipei',
          })}
        </p>
      )}

      <h2>
        {isToday ? '今日' : date} 各時段人數
        {series && <span className="hours"> 營業時間 {series.open_from}–{series.open_to}</span>}
      </h2>
      {series ? <OccupancyChart series={series} /> : <p className="empty">載入中…</p>}
      <p className="note">線段中斷表示該時段沒有採集到資料。</p>
    </main>
  )
}
