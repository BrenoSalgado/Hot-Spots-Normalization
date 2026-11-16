import * as d3 from 'd3'

// Sequential: one hue (orange, series 2), light -> dark. Lightest step recedes toward the surface.
export const HEAT_STEPS = ['#fdeee6', '#f9cdb6', '#f5ab86', '#ee8558', '#eb6834', '#c24c1e', '#8f3412', '#5a2009']
export const heatInterpolator = d3.piecewise(d3.interpolateLab, HEAT_STEPS)

/** sqrt-scaled sequential scale for counts */
export function heatScale(max: number) {
  const s = d3.scaleSqrt().domain([0, Math.max(max, 1)]).range([0, 1]).clamp(true)
  return (v: number) => (v <= 0 ? HEAT_STEPS[0] : heatInterpolator(0.12 + 0.88 * s(v)))
}

// Diverging: blue (below normal) <-> neutral gray <-> orange (above normal)
export const DIVERGING = ['#1c5cab', '#2a78d6', '#86b6ef', '#d9d8d3', '#f5ab86', '#eb6834', '#a23a14']
export const divergingInterpolator = d3.piecewise(d3.interpolateLab, DIVERGING)

/** z-score to color, clamped to +-3 */
export function zColor(z: number | null | undefined) {
  if (z == null || Number.isNaN(z)) return '#f1f0ec'
  const t = (Math.max(-3, Math.min(3, z)) + 3) / 6
  return divergingInterpolator(t)
}

export const SERIES = {
  modis: '#2a78d6',
  viirs: '#eb6834',
  viirsRaw: '#eda100',
  clim: '#c3c2b7',
}
