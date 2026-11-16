import { useMemo } from 'react'
import * as d3 from 'd3'
import { MONTHS, fmt, type MonthlyRow } from '../api'
import { heatScale, zColor, HEAT_STEPS, DIVERGING } from '../colors'
import { Tooltip, useTooltip } from './Tooltip'

type Props = {
  rows: MonthlyRow[]
  mode: 'value' | 'anomaly'
  variable: 'n' | 'frp'
  selectedYear: number
  onSelectYear: (y: number) => void
}

/** The burning-activity calendar: years as rows, months as columns. */
export function YearMonthHeatmap({ rows, mode, variable, selectedYear, onSelectYear }: Props) {
  const { tip, show, hide } = useTooltip()
  const years = useMemo(() => Array.from(new Set(rows.map((r) => r.year))).sort(), [rows])
  const byKey = useMemo(() => new Map(rows.map((r) => [`${r.year}-${r.month}`, r])), [rows])
  const value = (r: MonthlyRow) => (variable === 'n' ? r.n_harm : r.frp_harm)
  const max = useMemo(() => d3.max(rows, value) ?? 1, [rows, variable])
  const heat = heatScale(max)

  const margin = { top: 22, right: 110, bottom: 6, left: 44 }
  const cellW = 44
  const cellH = 17
  const width = margin.left + 12 * cellW + margin.right
  const height = margin.top + years.length * cellH + margin.bottom

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ maxWidth: width }}>
        {MONTHS.map((m, i) => (
          <text key={m} x={margin.left + i * cellW + cellW / 2} y={14} textAnchor="middle">
            {m}
          </text>
        ))}
        {years.map((y, yi) => {
          const yPos = margin.top + yi * cellH
          const sel = y === selectedYear
          const src = byKey.get(`${y}-1`)?.source ?? byKey.get(`${y}-12`)?.source
          return (
            <g key={y}>
              <text
                x={margin.left - 6}
                y={yPos + cellH / 2 + 4}
                textAnchor="end"
                style={{ fill: sel ? 'var(--text-primary)' : undefined, fontWeight: sel ? 600 : 400, cursor: 'pointer' }}
                onClick={() => onSelectYear(y)}
              >
                {y}
              </text>
              {MONTHS.map((_, mi) => {
                const r = byKey.get(`${y}-${mi + 1}`)
                const v = r ? value(r) : 0
                const fill = !r ? '#f6f5f2' : mode === 'value' ? heat(v) : zColor(variable === 'n' ? r.zscore : null)
                return (
                  <rect
                    key={mi}
                    x={margin.left + mi * cellW + 1}
                    y={yPos + 1}
                    width={cellW - 2}
                    height={cellH - 2}
                    rx={2}
                    fill={fill}
                    stroke={sel ? 'var(--text-primary)' : 'none'}
                    strokeWidth={sel ? 0.8 : 0}
                    style={{ cursor: 'pointer' }}
                    onClick={() => onSelectYear(y)}
                    onMouseMove={(e) =>
                      show(
                        e,
                        r ? (
                          <div>
                            <b>
                              {MONTHS[mi]} {y}
                            </b>{' '}
                            <span className="muted">· {r.source === 'MODIS' ? 'MODIS observed' : 'VIIRS → MODIS-eq.'}</span>
                            <br />
                            Hotspots: <b>{fmt(r.n_harm)}</b>
                            {r.source !== 'MODIS' && <span className="muted"> ± {fmt(r.err_abs)}</span>}
                            <br />
                            FRP: {fmt(r.frp_harm)} MW
                            <br />
                            <span className="muted">
                              Climatology 2002–2020: {fmt(r.clim_mean)} · anomaly {r.anomaly >= 0 ? '+' : ''}
                              {fmt(r.anomaly)} ({r.zscore != null ? (r.zscore >= 0 ? '+' : '') + r.zscore.toFixed(1) + ' σ' : '–'})
                            </span>
                            {r.n_modis != null && r.n_viirs_harm != null && (
                              <>
                                <br />
                                <span className="muted">
                                  Overlap check — MODIS {fmt(r.n_modis)} vs VIIRS harmonized {fmt(r.n_viirs_harm)}
                                </span>
                              </>
                            )}
                          </div>
                        ) : (
                          <span className="muted">no data</span>
                        ),
                      )
                    }
                    onMouseLeave={hide}
                  />
                )
              })}
              <text x={margin.left + 12 * cellW + 8} y={yPos + cellH / 2 + 4} style={{ fontSize: 10 }}>
                {src === 'MODIS' ? (y >= 2018 ? 'MODIS · overlap' : 'MODIS') : 'VIIRS → MODIS-eq.'}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="legend">
        {mode === 'value' ? (
          <span>
            <span className="muted">0</span>
            <span
              style={{
                width: 120,
                height: 8,
                borderRadius: 2,
                background: `linear-gradient(90deg, ${HEAT_STEPS.join(',')})`,
                display: 'inline-block',
              }}
            />
            <span className="muted">{fmt(max)} {variable === 'n' ? 'hotspots/month' : 'MW/month'} (sqrt scale)</span>
          </span>
        ) : (
          <span>
            <span className="muted">−3σ below normal</span>
            <span
              style={{
                width: 120,
                height: 8,
                borderRadius: 2,
                background: `linear-gradient(90deg, ${DIVERGING.join(',')})`,
                display: 'inline-block',
              }}
            />
            <span className="muted">+3σ above normal (vs 2002–2020 monthly climatology)</span>
          </span>
        )}
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}
