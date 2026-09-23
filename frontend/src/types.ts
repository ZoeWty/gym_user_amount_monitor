export type Venue = { id: string; name: string }

export type Latest = {
  venue: string
  fetched_at: string | null
  areas: Record<string, { current: number; capacity: number; ts: string }>
}

export type SeriesPoint = { ts: string } & Record<string, string | number | null>

export type Series = {
  venue: string
  date: string
  areas: string[]
  points: SeriesPoint[]
}

/** Upstream area keys are stable; anything unknown falls back to its raw id. */
export const AREA_LABEL: Record<string, string> = {
  gym: '健身房',
  swim: '游泳池',
  ice: '冰宮',
}

export const AREA_COLOR: Record<string, string> = {
  gym: '#2563eb',
  swim: '#0d9488',
  ice: '#c026d3',
}

export const labelFor = (area: string) => AREA_LABEL[area] ?? area
export const colorFor = (area: string) => AREA_COLOR[area] ?? '#64748b'
