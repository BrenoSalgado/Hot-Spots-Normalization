import { useMemo } from 'react'
import * as d3 from 'd3'
import { fmt, type MonthlyRow, type YearlyRow } from '../api'
import { SERIES } from '../colors'
import { Tooltip, useTooltip } from './Tooltip'

type Props = {
  rows: YearlyRow[]
  monthly: MonthlyRow[]
  variable: 'n' | 'frp'
  selectedYear: number
  onSelectYear: (y: number) => void
}

/** Annual totals, colored by the sensor that produced them; overlap years show the VIIRS-harmonized check. */
export function YearlyBars({ rows, monthly, variable, selectedYear, onSelectYear }: Props) {
  const { tip, show, hide } = useTooltip()
  const value = (r: YearlyRow) => (variable === 'n' ? r.n_harm : r.frp_harm)
  const errByYear = useMemo(() => d3.rollup(monthly, (v) => d3.sum(v, (m) => m.err_abs), (m) => m.year), [monthly])
  const climMean = useMemo(() => d3.mean(rows.filter((r) => r.year <= 2020), value) ?? 0, [rows, variable])

  const width = 560
  const height = 200
  const margin = { top: 10, right: 12, bottom: 24, left: 52 }
  const x = d3.scaleBand<number>().domain(rows.map((r) => r.year)).range([margin.left, width - margin.right]).padding(0.25)
  const yMax = d3.max(rows, (r) => Math.max(value(r), (variable === 'n' ? r.n_viirs_harm : 0) ?? 0)) ?? 1
  const y = d3.scaleLinear().domain([0, yMax * 1.05]).nice().range([height - margin.bottom, margin.top])
  const ticks = y.ticks(4)

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
        {climMean > 0 && (
          <line x1={margin.left} x2={width - margin.right} y1={y(climMean)} y2={y(climMean)} stroke={SERIES.clim} strokeWidth={1.5} />
        )}
        {rows.map((r) => {
          const v = value(r)
          const isModis = r.source === 'MODIS'
          const err = variable === 'n' && !isModis ? errByYear.get(r.year) ?? 0 : 0
          const bx = x(r.year)!
          const bw = x.bandwidth()
          const sel = r.year === selectedYear
          return (
            <g key={r.year} style={{ cursor: 'pointer' }} onClick={() => onSelectYear(r.year)}>
              <rect
                x={bx}
                y={y(v)}
                width={bw}
                height={Math.max(0, y(0) - y(v))}
                rx={3}
                fill={isModis ? SERIES.modis : SERIES.viirs}
                opacity={sel ? 1 : 0.85}
                stroke={sel ? 'var(--text-primary)' : 'none'}
                strokeWidth={sel ? 1 : 0}
              />
              {err > 0 && (
                <line x1={bx + bw / 2} x2={bx + bw / 2} y1={y(v - err)} y2={y(v + err)} stroke="var(--text-primary)" strokeWidth={1} />
              )}
              {variable === 'n' && isModis && r.n_viirs_harm != null && r.n_viirs_harm > 0 && (
                <circle cx={bx + bw / 2} cy={y(r.n_viirs_harm)} r={4} fill={SERIES.viirs} stroke="var(--surface-1)" strokeWidth={2} />
              )}
              <rect
                x={bx - 2}
                y={margin.top}
                width={bw + 4}
                height={height - margin.top - margin.bottom}
                fill="transparent"
                onMouseMove={(e) =>
                  show(
                    e,
                    <div>
                      <b>{r.year}</b> <span className="muted">· {isModis ? 'MODIS observed' : 'VIIRS → MODIS-equivalent'}</span>
                      <br />
                      Hotspots: <b>{fmt(r.n_harm)}</b>
                      {err > 0 && <span className="muted"> ± {fmt(err)}</span>}
                      <br />
                      FRP: {fmt(r.frp_harm)} MW · days with fire: {r.days_with_fire}
                      {isModis && r.n_viirs_harm != null && r.n_viirs_harm > 0 && (
                        <>
                          <br />
                          <span className="muted">
                            Overlap check: VIIRS harmonized {fmt(r.n_viirs_harm)} ({((r.n_viirs_harm / r.n_harm - 1) * 100).toFixed(0)}%)
                            {r.year === 2018 && ' — VIIRS from April only'}
                          </span>
                        </>
                      )}
                    </div>,
                  )
                }
                onMouseLeave={hide}
              />
            </g>
          )
        })}
        {rows.map((r) =>
          r.year % 2 === 0 ? (
            <text key={r.year} x={x(r.year)! + x.bandwidth() / 2} y={height - 8} textAnchor="middle">
              {String(r.year).slice(2)}
            </text>
          ) : null,
        )}
      </svg>
      <div className="legend">
        <span>
          <span className="swatch" style={{ background: SERIES.modis }} /> MODIS observed (Terra + Aqua)
        </span>
        <span>
          <span className="swatch" style={{ background: SERIES.viirs }} /> VIIRS NOAA-20 harmonized to MODIS-equivalent
        </span>
        <span>
          <span className="swatch" style={{ background: SERIES.viirs, borderRadius: 999 }} /> harmonized VIIRS in overlap years (validation)
        </span>
        <span>
          <span className="swatch" style={{ background: SERIES.clim, height: 2 }} /> 2002–2020 mean
        </span>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}
