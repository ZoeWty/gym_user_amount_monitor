import { createContext, useContext } from 'react'

export const LANGS = { zh: '繁體中文', en: 'English' } as const
export type Lang = keyof typeof LANGS

const STORAGE_KEY = 'gym-monitor-lang'

/** Remembered choice, else the browser's preference, else Chinese. */
export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'zh' || saved === 'en') return saved
  } catch {
    // private window, blocked storage, thumbnail capture -- fall through
  }
  return navigator.language?.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export function rememberLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // the choice still applies to this session, it just will not persist
  }
}

const zh = {
  htmlLang: 'zh-Hant',
  /** Locale for toLocaleString; venue clocks are always Taipei regardless. */
  locale: 'zh-TW',

  title: '運動中心人數監控',
  language: '語言',
  venue: '場館',
  date: '日期',
  backToToday: '回到今天',
  loadFailed: (msg: string) => `讀取失敗：${msg}`,
  lastUpdated: (when: string) => `最後更新 ${when}`,
  stale: (mins: number) =>
    ` ⚠ 已 ${mins} 分鐘沒有新資料，上方數字不是現在的狀況`,
  chartHeading: (day: string) => `${day} 各時段人數`,
  today: '今日',
  openHours: (from: string, to: string) => ` 營業時間 ${from}–${to}`,
  loading: '載入中…',
  gapNote: '線段中斷表示該時段沒有採集到資料。',
  noDataThatDay: '這一天沒有任何資料。',

  usage: (pct: number) => `使用率 ${pct}%`,
  usageAria: (area: string, pct: number) => `${area}使用率 ${pct}%`,

  mapHeading: '場館地圖',
  mapLegend: '綠 <34% · 黃 <67% · 紅 較擁擠',
  useMyLocation: '使用我的位置',
  relocate: '重新定位',
  locationStaysHere: '位置只留在這台裝置，不會送到後端',
  geoUnsupported: '這個瀏覽器不支援定位',
  geoDenied: '已拒絕定位，地圖顯示全部場館',
  geoFailed: (msg: string) => `無法取得位置：${msg}`,
  distanceAbout: (km: string) => `距離約 ${km} km`,
  noDataNow: '目前沒有資料',
  yourLocation: '你的位置',
  nearestToYou: '離你最近：',

  areas: { gym: '健身房', swim: '游泳池', ice: '冰宮' } as Record<string, string>,
  /** Venue display names, keyed by id. Upstream only sends Chinese. */
  venues: {} as Record<string, string>,
}

export type Strings = typeof zh

const en: Strings = {
  htmlLang: 'en',
  locale: 'en-GB',

  title: 'Sports Centre Occupancy',
  language: 'Language',
  venue: 'Venue',
  date: 'Date',
  backToToday: 'Back to today',
  loadFailed: (msg: string) => `Could not load: ${msg}`,
  lastUpdated: (when: string) => `Last updated ${when}`,
  stale: (mins: number) =>
    ` ⚠ No new data for ${mins} min — the numbers above are not current`,
  chartHeading: (day: string) => `${day} by time of day`,
  today: 'Today',
  openHours: (from: string, to: string) => ` Open ${from}–${to}`,
  loading: 'Loading…',
  gapNote: 'A break in the line means no data was collected then.',
  noDataThatDay: 'No data for this day.',

  usage: (pct: number) => `${pct}% full`,
  usageAria: (area: string, pct: number) => `${area} ${pct}% full`,

  mapHeading: 'Venue map',
  mapLegend: 'green <34% · amber <67% · red busier',
  useMyLocation: 'Use my location',
  relocate: 'Update location',
  locationStaysHere: 'Your location stays on this device and is never sent to the server',
  geoUnsupported: 'This browser does not support geolocation',
  geoDenied: 'Location denied — showing every venue',
  geoFailed: (msg: string) => `Could not get your location: ${msg}`,
  distanceAbout: (km: string) => `about ${km} km away`,
  noDataNow: 'No data right now',
  yourLocation: 'You are here',
  nearestToYou: 'Nearest to you: ',

  areas: { gym: 'Gym', swim: 'Pool', ice: 'Ice rink' },
  // Taipei's own romanisation of the twelve district names.
  venues: {
    btsc: 'Beitou Sports Centre',
    dasc: "Da'an Sports Centre",
    dtsc: 'Datong Sports Centre',
    jjsc: 'Zhongzheng Sports Centre',
    ngsc: 'Nangang Sports Centre',
    nhsc: 'Neihu Sports Centre',
    slsc: 'Shilin Sports Centre',
    sssc: 'Songshan Sports Centre',
    whsc: 'Wanhua Sports Centre',
    wssc: 'Wenshan Sports Centre',
    xysc: 'Xinyi Sports Centre',
    zssc: 'Zhongshan Sports Centre',
  },
}

const ALL: Record<Lang, Strings> = { zh, en }

export const LangContext = createContext<Lang>('zh')

export function useStrings(): Strings {
  return ALL[useContext(LangContext)]
}

/** Area label, falling back to the raw key for an area we have not named. */
export function areaLabel(s: Strings, area: string): string {
  return s.areas[area] ?? area
}

/** Venue label. Chinese uses the name upstream sent; English uses our map,
 *  falling back to that same Chinese name for a venue we have not romanised. */
export function venueLabel(s: Strings, id: string, upstreamName: string): string {
  return s.venues[id] ?? upstreamName
}
