import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { colorFor, labelFor, type Series } from './types'

const hhmm = (iso: string) => iso.slice(11, 16)

export default function OccupancyChart({ series }: { series: Series }) {
  // A day before collection started still comes back as a full grid of
  // null buckets, so emptiness means "no non-null value", not "no points".
  const hasData = series.points.some((p) =>
    series.areas.some((a) => p[a] !== null && p[a] !== undefined),
  )
  if (!hasData) {
    return <p className="empty">這一天沒有任何資料。</p>
  }

  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={series.points} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
        <XAxis dataKey="ts" tickFormatter={hhmm} minTickGap={40} fontSize={12} />
        <YAxis allowDecimals={false} fontSize={12} />
        <Tooltip
          labelFormatter={(v) => hhmm(String(v))}
          formatter={(value, name) => [value as number, labelFor(String(name))]}
        />
        <Legend formatter={(v) => labelFor(String(v))} />
        {series.areas.map((area) => (
          <Line
            key={area}
            type="monotone"
            dataKey={area}
            stroke={colorFor(area)}
            strokeWidth={2}
            /* A run of one -- a venue on its first poll, or a reading
               between two gaps -- draws no line segment, so without a dot it
               is invisible. Small enough not to clutter a full day. */
            dot={{ r: 1.5 }}
            /* Gaps must render as gaps. Connecting across missing buckets
               would draw a line that describes data we never collected. */
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
