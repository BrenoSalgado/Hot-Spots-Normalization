import { useCallback, useEffect, useMemo, useState } from 'react'
import * as d3 from 'd3'
import { api, fmt, regionLabel, type CalendarRow, type GridCell, type Meta, type MonthlyRow, type Region, type YearlyRow } from './api'
import { MapView } from './components/MapView'
import { YearMonthHeatmap } from './components/YearMonthHeatmap'
import { CalendarHeatmap } from './components/CalendarHeatmap'
import { YearlyBars } from './components/YearlyBars'
import { ClimatologyChart } from './components/ClimatologyChart'
import { SERIES } from './colors'

type Variable = 'n' | 'frp'
type Mode = 'value' | 'anomaly'

type Validation = Record<string, Record<string, number | string | boolean>>
type ModelInfo = { selected: string; metric: string; region: string; by_month: boolean; f_all: number; block_deg: number; overlap: string[] }

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [region, setRegion] = useState<Region>({ country: 'all', bbox: null })
  const [year, setYear] = useState(2024)
  const [variable, setVariable] = useState<Variable>('n')
  const [mode, setMode] = useState<Mode>('value')
  const [drawing, setDrawing] = useState(false)

  const [monthly, setMonthly] = useState<MonthlyRow[]>([])
  const [yearly, setYearly] = useState<YearlyRow[]>([])
  const [calendar, setCalendar] = useState<CalendarRow[]>([])
  const [cells, setCells] = useState<GridCell[]>([])
  const [loading, setLoading] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(String(e)))
  }, [])

  const track = useCallback(<T,>(p: Promise<T>) => {
    setLoading((n) => n + 1)
    return p.finally(() => setLoading((n) => n - 1))
  }, [])

  useEffect(() => {
    setError(null)
    track(Promise.all([api.monthly(region), api.yearly(region)]))
      .then(([m, y]) => {
        setMonthly(m)
        setYearly(y)
      })
      .catch((e) => setError(String(e)))
  }, [region, track])

  useEffect(() => {
    track(api.calendar(region, year)).then(setCalendar).catch((e) => setError(String(e)))
    track(api.grid(region, `${year}-01-01`, `${year}-12-31`)).then(setCells).catch((e) => setError(String(e)))
  }, [region, year, track])

  const onBbox = useCallback((bbox: [number, number, number, number]) => {
    setRegion({ country: 'all', bbox })
    setDrawing(false)
  }, [])

  const years = useMemo(() => yearly.map((r) => r.year), [yearly])
  const yearRow = yearly.find((r) => r.year === year)
  const yearMonths = monthly.filter((r) => r.year === year)
  const yearErr = d3.sum(yearMonths, (r) => r.err_abs)
  const climYear = d3.mean(yearly.filter((r) => r.year <= 2020), (r) => (variable === 'n' ? r.n_harm : r.frp_harm)) ?? 0
  const peak = yearMonths.length ? yearMonths.reduce((a, b) => (b.n_harm > a.n_harm ? b : a)) : null
  const rank = useMemo(() => {
    const sorted = [...yearly].sort((a, b) => b.n_harm - a.n_harm)
    return sorted.findIndex((r) => r.year === year) + 1
  }, [yearly, year])

  const validation = useMemo<Validation | null>(() => {
    if (!meta) return null
    try {
      return JSON.parse(meta.validation) as Validation
    } catch {
      return null
    }
  }, [meta])
  const model = (meta as (Meta & { model?: ModelInfo }) | null)?.model

  return (
    <div className="app">
      <header className="topbar">
        <h1>Harmonized Burning Activity Calendar</h1>
        <span className="sub">MODIS (2002–2020) + VIIRS NOAA-20 (2018–2025) · one consistent hotspot time series · South America</span>
        <span className="spacer" />
        <span className="pill">
          <span className="swatch" style={{ background: SERIES.modis }} /> MODIS observed
        </span>
        <span className="pill">
          <span className="swatch" style={{ background: SERIES.viirs }} /> VIIRS → MODIS-equivalent
        </span>
        {loading > 0 && <span className="loading">loading…</span>}
      </header>

      <aside className="sidebar">
        <div className="control">
          <label>Region</label>
          <select
            value={region.bbox ? '__bbox' : region.country}
            onChange={(e) => {
              if (e.target.value !== '__bbox') setRegion({ country: e.target.value, bbox: null })
            }}
          >
            <option value="all">South America (all countries)</option>
            {meta?.countries.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, ' ')}
              </option>
            ))}
            {region.bbox && <option value="__bbox">Custom area</option>}
          </select>
          <div className="btn-row" style={{ marginTop: 6 }}>
            <button className={`btn ${drawing ? 'active' : ''}`} onClick={() => setDrawing((d) => !d)}>
              {drawing ? 'Cancel drawing' : 'Draw area on map'}
            </button>
            {region.bbox && (
              <button className="btn" onClick={() => setRegion({ country: 'all', bbox: null })}>
                Clear area
              </button>
            )}
          </div>
          {region.bbox && <div className="hint" style={{ marginTop: 4 }}>{regionLabel(region)}</div>}
        </div>

        <div className="control">
          <label>Year in focus</label>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {(years.length ? years : d3.range(2002, 2026)).map((y) => (
              <option key={y} value={y}>
                {y} {y <= 2020 ? '· MODIS' : '· VIIRS → MODIS-eq.'}
              </option>
            ))}
          </select>
        </div>

        <div className="control">
          <label>Variable</label>
          <div className="seg">
            <button className={variable === 'n' ? 'active' : ''} onClick={() => setVariable('n')}>
              Hotspots
            </button>
            <button className={variable === 'frp' ? 'active' : ''} onClick={() => setVariable('frp')}>
              FRP (MW)
            </button>
          </div>
        </div>

        <div className="control">
          <label>Calendar coloring</label>
          <div className="seg">
            <button className={mode === 'value' ? 'active' : ''} onClick={() => setMode('value')}>
              Activity
            </button>
            <button className={mode === 'anomaly' ? 'active' : ''} onClick={() => setMode('anomaly')} disabled={variable === 'frp'}>
              Anomaly
            </button>
          </div>
          <div className="hint" style={{ marginTop: 4 }}>Anomaly = departure from the 2002–2020 climatology of the same month (σ units).</div>
        </div>

        <div className="control">
          <label>Download analytics (CSV)</label>
          <div className="btn-row">
            <a className="btn" href={api.exportUrl(region, 'daily')} download>
              Daily series
            </a>
            <a className="btn" href={api.exportUrl(region, 'monthly')} download>
              Monthly
            </a>
            <a className="btn" href={api.exportUrl(region, 'cells', `${year}-01-01`, `${year}-12-31`)} download>
              Cells {year}
            </a>
          </div>
          <div className="hint" style={{ marginTop: 4 }}>Columns include harmonized values, raw MODIS and VIIRS counts, and the source sensor.</div>
        </div>

        <details className="method">
          <summary>Method &amp; validation</summary>
          <p>
            VIIRS 375 m detections are converted to MODIS-equivalent hotspots with a linear factor fitted in the overlap window
            ({model?.overlap?.[0] ?? '2018-04-01'} → {model?.overlap?.[1] ?? '2020-12-31'}). Factors are estimated per{' '}
            {model?.region === 'block' ? `${model.block_deg}° block` : model?.region ?? 'region'}
            {model?.by_month ? ' and month of year' : ''}, shrunk toward the continental value ({model ? model.f_all.toFixed(3) : '…'} MODIS hotspots per VIIRS
            pixel) where data are sparse. Model chosen by leave-one-year-out cross-validation.
          </p>
          {validation && (
            <table>
              <thead>
                <tr>
                  <th>model</th>
                  <th>R² cell·month</th>
                  <th>NRMSE country·month</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(validation)
                  .sort((a, b) => Number(a[1].mean_rank) - Number(b[1].mean_rank))
                  .map(([name, v]) => (
                    <tr key={name} style={{ fontWeight: name === model?.selected ? 600 : 400 }}>
                      <td>{name}</td>
                      <td>{Number(v.cellmonth_r2).toFixed(3)}</td>
                      <td>{Number(v.ctrymonth_nrmse).toFixed(3)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
          <p>
            Data: NASA FIRMS country archives, MODIS C6.1 (Terra + Aqua) and VIIRS NOAA-20 (JPSS-1). Dates are UTC. Cells are {meta?.grid_deg ?? 0.1}°.
          </p>
        </details>
      </aside>

      <main className="content">
        {error && <div className="card wide error">{error}</div>}

        <div className="card wide">
          <div className="stats">
            <div className="stat">
              <div className="k">{regionLabel(region)} · {year}</div>
              <div className="v">{fmt(yearRow ? (variable === 'n' ? yearRow.n_harm : yearRow.frp_harm) : null)}</div>
              <div className="d">
                {variable === 'n' ? 'harmonized hotspots' : 'MW total FRP'}
                {yearRow && yearRow.source !== 'MODIS' && variable === 'n' && ` ± ${fmt(yearErr)}`}
                {yearRow && ` · ${yearRow.source === 'MODIS' ? 'MODIS observed' : 'VIIRS → MODIS-eq.'}`}
              </div>
            </div>
            <div className="stat">
              <div className="k">vs 2002–2020 mean</div>
              <div className="v" style={{ color: yearRow && (variable === 'n' ? yearRow.n_harm : yearRow.frp_harm) > climYear ? SERIES.viirs : SERIES.modis }}>
                {yearRow && climYear > 0 ? `${(((variable === 'n' ? yearRow.n_harm : yearRow.frp_harm) / climYear - 1) * 100).toFixed(0)}%` : '–'}
              </div>
              <div className="d">mean {fmt(climYear)} per year</div>
            </div>
            <div className="stat">
              <div className="k">Rank of {year}</div>
              <div className="v">{rank ? `#${rank}` : '–'}</div>
              <div className="d">of {yearly.length} years, by hotspots</div>
            </div>
            <div className="stat">
              <div className="k">Peak month</div>
              <div className="v">{peak ? d3.timeFormat('%b')(new Date(peak.year, peak.month - 1, 1)) : '–'}</div>
              <div className="d">{peak ? `${fmt(peak.n_harm)} hotspots · ${peak.zscore != null ? (peak.zscore >= 0 ? '+' : '') + peak.zscore.toFixed(1) + ' σ' : ''}` : ''}</div>
            </div>
          </div>
        </div>

        <div className="card wide">
          <div className="card-head">
            <h2>Burning activity calendar</h2>
            <p className="desc">Years × months, 2002–2025. Rows up to 2020 are MODIS observations; later rows are VIIRS converted to MODIS-equivalent units. Click a row to focus a year.</p>
          </div>
          <YearMonthHeatmap rows={monthly} mode={mode} variable={variable} selectedYear={year} onSelectYear={setYear} />
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Where it burned in {year}</h2>
            <p className="desc">Harmonized {variable === 'n' ? 'hotspots' : 'FRP'} per 0.1° cell. Drag with the draw tool to analyze any area.</p>
          </div>
          <MapView cells={cells} region={region} variable={variable} drawing={drawing} onBbox={onBbox} gridDeg={meta?.grid_deg ?? 0.1} />
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Day by day, {year}</h2>
            <p className="desc">Daily harmonized activity; hover for the daily climatology.</p>
          </div>
          <CalendarHeatmap rows={calendar} year={year} mode={mode} variable={variable} />
          <div style={{ height: 8 }} />
          <div className="card-head">
            <h2>Seasonal cycle</h2>
            <p className="desc">{year} against the 2002–2020 monthly climatology.</p>
          </div>
          <ClimatologyChart rows={monthly} variable={variable} year={year} />
        </div>

        <div className="card wide">
          <div className="card-head">
            <h2>Annual totals, 2002–2025</h2>
            <p className="desc">Whiskers show the harmonization uncertainty (cross-validated error). Dots in 2018–2020 show what harmonized VIIRS gives against observed MODIS.</p>
          </div>
          <YearlyBars rows={yearly} monthly={monthly} variable={variable} selectedYear={year} onSelectYear={setYear} />
        </div>
      </main>
    </div>
  )
}
