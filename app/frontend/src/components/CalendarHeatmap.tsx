import { useMemo } from 'react'
import * as d3 from 'd3'
import { fmt, type CalendarRow } from '../api'
import { heatScale, zColor } from '../colors'
import { Tooltip, useTooltip } from './Tooltip'

type Props = { rows: CalendarRow[]; year: number; mode: 'value' | 'anomaly'; variable: 'n' | 'frp' }

const DOW = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']

/** GitHub-style day calendar for a single year. */
export function CalendarHeatmap({ rows, year, mode, variable }: Props) {
  const { tip, show, hide } = useTooltip()
  const byDate = useMemo(() => new Map(rows.map((r) => [r.acq_date, r])), [rows])
  const value = (r: CalendarRow) => (variable === 'n' ? r.n_harm : r.frp_harm)
  const max = useMemo(() => d3.quantile(rows.map(value).sort(d3.ascending), 0.98) ?? 1, [rows, variable])
  const heat = heatScale(max)

  const days = useMemo(() => d3.timeDays(new Date(year, 0, 1), new Date(year + 1, 0, 1)), [year])
  const first = new Date(year, 0, 1)
  const weekIndex = (d: Date) => d3.timeMonday.count(d3.timeMonday(first), d)
  const dow = (d: Date) => (d.getDay() + 6) % 7
  const cell = 13
  const margin = { top: 18, left: 30 }
  const weeks = weekIndex(days[days.length - 1]) + 1
  const width = margin.left + weeks * cell + 4
  const height = margin.top + 7 * cell + 4

  const monthStarts = d3.timeMonths(new Date(year, 0, 1), new Date(year + 1, 0, 1))

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ maxWidth: width }}>
        {monthStarts.map((m) => (
          <text key={+m} x={margin.left + weekIndex(m) * cell} y={12}>
            {d3.timeFormat('%b')(m)}
          </text>
        ))}
        {DOW.map((d, i) => (
          <text key={i} x={margin.left - 6} y={margin.top + i * cell + 10} textAnchor="end" style={{ fontSize: 9 }}>
            {d}
          </text>
        ))}
        {days.map((d) => {
          const key = d3.timeFormat('%Y-%m-%d')(d)
          const r = byDate.get(key)
          const v = r ? value(r) : 0
          let fill = '#f6f5f2'
          if (mode === 'value') fill = heat(v)
          else if (variable === 'n') {
            // anomaly as ratio to daily climatology, mapped to pseudo-z: log2(ratio)
            const clim = r?.clim_mean ?? 0
            const z = clim > 0 || v > 0 ? Math.log2((v + 1) / (clim + 1)) : null
            fill = zColor(z == null ? null : z * 1.5)
          }
          return (
            <rect
              key={key}
              x={margin.left + weekIndex(d) * cell + 1}
              y={margin.top + dow(d) * cell + 1}
              width={cell - 2}
              height={cell - 2}
              rx={2}
              fill={fill}
              onMouseMove={(e) =>
                show(
                  e,
                  <div>
                    <b>{d3.timeFormat('%a %d %b %Y')(d)}</b>
                    {r && <span className="muted"> · {r.source === 'MODIS' ? 'MODIS' : 'VIIRS → MODIS-eq.'}</span>}
                    <br />
                    Hotspots: <b>{fmt(r?.n_harm ?? 0)}</b> · FRP {fmt(r?.frp_harm ?? 0)} MW
                    <br />
                    <span className="muted">Daily climatology 2002–2020: {fmt(r?.clim_mean ?? 0, 1)}</span>
                  </div>,
                )
              }
              onMouseLeave={hide}
            />
          )
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  )
}
