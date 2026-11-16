import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import * as d3 from 'd3'
import type { GridCell, Region } from '../api'
import { fmt } from '../api'
import { heatScale, HEAT_STEPS } from '../colors'

type Props = {
  cells: GridCell[]
  region: Region
  variable: 'n' | 'frp'
  drawing: boolean
  onBbox: (bbox: [number, number, number, number]) => void
  gridDeg: number
}

const SA_BOUNDS: L.LatLngBoundsExpression = [
  [-56, -82],
  [13, -34],
]

const cellKey = (lat: number, lon: number, deg: number) => `${Math.floor(lat / deg + 1e-6)}_${Math.floor(lon / deg + 1e-6)}`

/** Leaflet map with a custom canvas layer for 0.1 deg cells and a drag-to-select bbox tool. */
export function MapView({ cells, region, variable, drawing, onBbox, gridDeg }: Props) {
  const divRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const bboxRef = useRef<L.Rectangle | null>(null)
  const dataRef = useRef<{ cells: GridCell[]; variable: 'n' | 'frp'; max: number; index: Map<string, GridCell> }>({
    cells: [],
    variable: 'n',
    max: 1,
    index: new Map(),
  })
  const [hover, setHover] = useState<GridCell | null>(null)
  const max = d3.max(cells, (c) => (variable === 'n' ? c.n : c.frp)) ?? 1

  // --- map + canvas init
  useEffect(() => {
    if (!divRef.current || mapRef.current) return
    const map = L.map(divRef.current, { zoomControl: true, attributionControl: true })
    map.fitBounds(SA_BOUNDS)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors',
      maxZoom: 12,
    }).addTo(map)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 12,
      pane: 'shadowPane',
      opacity: 0.9,
    }).addTo(map)

    const canvas = L.DomUtil.create('canvas', 'leaflet-zoom-hide', map.getPanes().overlayPane) as HTMLCanvasElement
    canvas.style.position = 'absolute'
    canvas.style.pointerEvents = 'none'
    canvasRef.current = canvas

    const redraw = () => {
      const { cells, variable, max } = dataRef.current
      const size = map.getSize()
      const dpr = window.devicePixelRatio || 1
      canvas.width = size.x * dpr
      canvas.height = size.y * dpr
      canvas.style.width = `${size.x}px`
      canvas.style.height = `${size.y}px`
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]))
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, size.x, size.y)
      const heat = heatScale(max)
      const half = gridDeg / 2
      const b = map.getBounds().pad(0.05)
      ctx.globalAlpha = 0.85
      for (const c of cells) {
        const v = variable === 'n' ? c.n : c.frp
        if (v <= 0 || !b.contains([c.lat, c.lon])) continue
        const p1 = map.latLngToContainerPoint([c.lat + half, c.lon - half])
        const p2 = map.latLngToContainerPoint([c.lat - half, c.lon + half])
        const w = Math.max(1.5, p2.x - p1.x)
        const h = Math.max(1.5, p2.y - p1.y)
        ctx.fillStyle = heat(v)
        ctx.fillRect(p1.x, p1.y, w, h)
      }
      ctx.globalAlpha = 1
    }
    map.on('moveend zoomend resize viewreset', redraw)
    ;(map as unknown as { __redraw: () => void }).__redraw = redraw

    map.on('mousemove', (e: L.LeafletMouseEvent) => {
      const c = dataRef.current.index.get(cellKey(e.latlng.lat, e.latlng.lng, gridDeg)) ?? null
      setHover((prev) => (prev === c ? prev : c))
    })
    map.on('mouseout', () => setHover(null))
    mapRef.current = map
    setTimeout(() => map.invalidateSize(), 0)
  }, [gridDeg])

  // --- data updates
  useEffect(() => {
    dataRef.current = {
      cells,
      variable,
      max,
      index: new Map(cells.map((c) => [cellKey(c.lat, c.lon, gridDeg), c])),
    }
    const map = mapRef.current as (L.Map & { __redraw?: () => void }) | null
    map?.__redraw?.()
  }, [cells, variable, max, gridDeg])

  // --- bbox rectangle
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    bboxRef.current?.remove()
    bboxRef.current = null
    if (region.bbox) {
      const [w, s, e, n] = region.bbox
      bboxRef.current = L.rectangle(L.latLngBounds([s, w], [n, e]), {
        renderer: L.svg(),
        color: '#2a78d6',
        weight: 2,
        fill: false,
        dashArray: '4 4',
        interactive: false,
      }).addTo(map)
    }
  }, [region.bbox])

  // --- drawing interaction
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!drawing) {
      map.dragging.enable()
      map.getContainer().style.cursor = ''
      return
    }
    map.dragging.disable()
    map.getContainer().style.cursor = 'crosshair'
    let start: L.LatLng | null = null
    let temp: L.Rectangle | null = null
    const down = (e: L.LeafletMouseEvent) => {
      start = e.latlng
      temp = L.rectangle(L.latLngBounds(start, start), {
        renderer: L.svg(),
        color: '#2a78d6',
        weight: 2,
        fill: true,
        fillOpacity: 0.05,
        interactive: false,
      }).addTo(map)
    }
    const move = (e: L.LeafletMouseEvent) => {
      if (start && temp) temp.setBounds(L.latLngBounds(start, e.latlng))
    }
    const up = (e: L.LeafletMouseEvent) => {
      if (!start) return
      const b = L.latLngBounds(start, e.latlng)
      temp?.remove()
      temp = null
      start = null
      if (b.getNorth() - b.getSouth() > 0.05 && b.getEast() - b.getWest() > 0.05) {
        onBbox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
      }
    }
    map.on('mousedown', down)
    map.on('mousemove', move)
    map.on('mouseup', up)
    return () => {
      map.off('mousedown', down)
      map.off('mousemove', move)
      map.off('mouseup', up)
      temp?.remove()
    }
  }, [drawing, onBbox])

  const unit = variable === 'n' ? 'hotspots' : 'MW'
  return (
    <div className="map-wrap">
      <div ref={divRef} style={{ height: '100%' }} />
      {drawing && <div className="draw-hint">Drag on the map to select an area</div>}
      <div className="map-legend">
        <div>
          {hover
            ? `${hover.lat.toFixed(2)}°, ${hover.lon.toFixed(2)}° — ${fmt(variable === 'n' ? hover.n : hover.frp)} ${unit}`
            : `Harmonized ${variable === 'n' ? 'hotspots' : 'FRP (MW)'} per 0.1° cell`}
        </div>
        <div className="bar" style={{ background: `linear-gradient(90deg, ${HEAT_STEPS.join(',')})` }} />
        <div className="ticks">
          <span>0</span>
          <span>{fmt(max)} (sqrt scale)</span>
        </div>
      </div>
    </div>
  )
}
