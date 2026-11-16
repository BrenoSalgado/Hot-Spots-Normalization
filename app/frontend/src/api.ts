export type Region = { country: string; bbox: [number, number, number, number] | null }

export type Meta = {
  date_min: string
  date_max: string
  countries: string[]
  grid_deg: number
  modis_until: string
  viirs_from: string
  validation: string
}

export type MonthlyRow = {
  year: number
  month: number
  n_harm: number
  frp_harm: number
  n_modis: number | null
  n_viirs: number | null
  n_viirs_harm: number | null
  source: string
  err_abs: number
  clim_mean: number
  clim_sd: number | null
  clim_median: number
  anomaly: number
  zscore: number | null
}

export type YearlyRow = {
  year: number
  n_harm: number
  frp_harm: number
  n_modis: number | null
  n_viirs: number | null
  n_viirs_harm: number | null
  source: string
  days_with_fire: number
}

export type CalendarRow = {
  acq_date: string
  n_harm: number
  frp_harm: number
  source: string
  clim_mean: number
}

export type GridCell = { lat: number; lon: number; n: number; frp: number }

export function regionParams(r: Region): URLSearchParams {
  const p = new URLSearchParams()
  if (r.bbox) p.set('bbox', r.bbox.map((v) => v.toFixed(3)).join(','))
  else if (r.country) p.set('country', r.country)
  return p
}

async function get<T>(path: string, params: URLSearchParams): Promise<T> {
  const res = await fetch(`/api/${path}?${params.toString()}`)
  if (!res.ok) throw new Error(`${path}: ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  meta: () => get<Meta>('meta', new URLSearchParams()),
  monthly: (r: Region) => get<MonthlyRow[]>('monthly', regionParams(r)),
  yearly: (r: Region) => get<YearlyRow[]>('yearly', regionParams(r)),
  calendar: (r: Region, year: number) => {
    const p = regionParams(r)
    p.set('year', String(year))
    return get<CalendarRow[]>('calendar', p)
  },
  grid: (r: Region, start: string, end: string, limit = 30000) => {
    const p = regionParams(r)
    p.set('start', start)
    p.set('end', end)
    p.set('limit', String(limit))
    return get<GridCell[]>('grid', p)
  },
  exportUrl: (r: Region, level: 'daily' | 'monthly' | 'cells', start?: string, end?: string) => {
    const p = regionParams(r)
    p.set('level', level)
    if (start) p.set('start', start)
    if (end) p.set('end', end)
    return `/api/export.csv?${p.toString()}`
  },
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function regionLabel(r: Region): string {
  if (r.bbox) {
    const [w, s, e, n] = r.bbox
    return `Area ${s.toFixed(1)}°,${w.toFixed(1)}° → ${n.toFixed(1)}°,${e.toFixed(1)}°`
  }
  return r.country === 'all' ? 'South America' : r.country.replace(/_/g, ' ')
}

export const fmt = (v: number | null | undefined, digits = 0): string =>
  v == null || Number.isNaN(v) ? '–' : v.toLocaleString('en-US', { maximumFractionDigits: digits })
