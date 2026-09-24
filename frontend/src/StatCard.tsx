import { areaLabel, useStrings } from './i18n'
import { colorFor } from './types'

type Props = {
  area: string
  current: number
  capacity: number
}

export default function StatCard({ area, current, capacity }: Props) {
  const s = useStrings()
  const label = areaLabel(s, area)
  const pct = capacity > 0 ? Math.round((current / capacity) * 100) : null
  const color = colorFor(area)

  return (
    <div className="card">
      <div className="card-title" style={{ color }}>
        {label}
      </div>
      <div className="card-number">
        {current}
        <span className="card-capacity"> / {capacity}</span>
      </div>
      {pct !== null && (
        <>
          <div
            className="meter"
            role="meter"
            aria-valuenow={current}
            aria-valuemin={0}
            aria-valuemax={capacity}
            aria-label={s.usageAria(label, pct)}
          >
            <div
              className="meter-fill"
              style={{ width: `${Math.min(pct, 100)}%`, background: color }}
            />
          </div>
          <div className="card-pct">{s.usage(pct)}</div>
        </>
      )}
    </div>
  )
}
