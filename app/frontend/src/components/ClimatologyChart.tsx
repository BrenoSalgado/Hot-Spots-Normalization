import { useMemo } from 'react'
import * as d3 from 'd3'
import { MONTHS, fmt, type MonthlyRow } from '../api'
import { SERIES } from '../colors'
import { Tooltip, useTooltip } from './Tooltip'

type Props = { rows: MonthlyRow[]; variable: 'n' | 'frp'; year: number }

/** Seasonal cycle: 2002-2020 climatology band vs the selected year. */
export function ClimatologyChart({ rows, variable, year }: Props) {
  const { tip, show, hide } = useTooltip()
  const value = (r: MonthlyRow) => (variable === 'n' ? r.n_harm : r.frp_harm)
  const clim = useMemo(() => {
    const base = rows.filter((r) => r.year >= 2002 && r.year <= 2020)
    return d3.range(1, 13).map((m) => {
      const vals = base.filter((r) => r.month === m).map(value)
      return {
        month: m,
        mean: d3.mean(vals) ?? 0,
        lo: d3.quantile(vals.sort(d3.ascending), 0.1) ?? 0,
        hi: d3.quantile(vals, 0.9) ?? 0,
        max: d3.max(vals) ?? 0,
      }
    })
  }, [rows, variable])
  const sel = useMemo(() => rows.filter((r) => r.year === year).sort((a, b) => a.month - b.month), [rows, year])
  const src = sel[0]?.source
  const color = src === 'MODIS' ? SERIES.modis : SERIES.viirs

  const width = 560
  const height = 200
  const margin = { top: 10, right: 12, bottom: 24, left: 52 }
  const x = d3.scalePoint<number>().domain(d3.range(1, 13)).range([margin.left, width - margin.right]).padding(0.5)
  const yMax = Math.max(d3.max(clim, (c) => c.hi) ?? 0, d3.max(sel, value) ?? 0, 1)
  const y = d3.scaleLinear().domain([0, yMax * 1.05]).nice().range([height - margin.bottom, margin.top])
  const ticks = y.ticks(4)
  const area = d3.area<(typeof clim)[number]>().x((c) => x(c.month)!).y0((c) => y(c.lo)).y1((c) => y(c.hi)).curve(d3.curveMonotoneX)
  const lineMean = d3.line<(typeof clim)[number]>().x((c) => x(c.month)!).y((c) => y(c.mean)).curve(d3.curveMonotoneX)
  const lineSel = d3.line<MonthlyRow>().x((r) => x(r.month)!).y((r) => y(value(r))).curve(d3.curveMonotoneX)

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={margin.left} x2={width - margin.right} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        {ticks.map((t) => (
          <text key={t} x={margin.left - 6} y={y(t) + 4} textAnchor="end">
            {d3.format('~s')(t)}
          </text>
        ))}
        <path d={area(clim) ?? ''} fill={SERIES.clim} opacity={0.35} />
        <path d={lineMean(clim) ?? ''} fill="none" stroke={SERIES.clim} strokeWidth={2} />
        <path d={lineSel(sel) ?? ''} fill="none" stroke={color} strokeWidth={2} />
        {sel.map((r) => (
          <circle
            key={r.month}
            cx={x(r.month)}
            cy={y(value(r))}
            r={4}
            fill={color}
            stroke="var(--surface-1)"
            strokeWidth={2}
            onMouseMove={(e) => {
              const c = clim[r.month - 1]
              show(
                e,
                <div>
                  <b>
                    {MONTHS[r.month - 1]} {r.year}
                  </b>
                  <br />
                  {year}: <b>{fmt(value(r))}</b> {r.source !== 'MODIS' && <span className="muted">± {fmt(r.err_abs)}</span>}
                  <br />
                  <span className="muted">
                    2002–2020: mean {fmt(c.mean)}, P10–P90 {fmt(c.lo)}–{fmt(c.hi)}, max {fmt(c.max)}
                  </span>
                </div>,
              )
            }}
            onMouseLeave={hide}
          />
        ))}
        {MONTHS.map((m, i) => (
          <text key={m} x={x(i + 1)} y={height - 8} textAnchor="middle">
            {m}
          </text>
        ))}
      </svg>
      <div className="legend">
        <span>
          <span className="swatch" style={{ background: color }} /> {year} {src === 'MODIS' ? '(MODIS)' : '(VIIRS → MODIS-eq.)'}
        </span>
        <span>
          <span className="swatch" style={{ background: SERIES.clim }} /> 2002–2020 mean and P10–P90 band
        </span>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}
