import { useCallback, useState, type ReactNode } from 'react'

export type TipState = { x: number; y: number; content: ReactNode } | null

export function useTooltip() {
  const [tip, setTip] = useState<TipState>(null)
  const show = useCallback((e: { clientX: number; clientY: number }, content: ReactNode) => {
    setTip({ x: e.clientX, y: e.clientY, content })
  }, [])
  const hide = useCallback(() => setTip(null), [])
  return { tip, show, hide }
}

export function Tooltip({ tip }: { tip: TipState }) {
  if (!tip) return null
  const left = Math.min(tip.x + 12, window.innerWidth - 260)
  const top = Math.min(tip.y + 12, window.innerHeight - 120)
  return (
    <div className="tooltip" style={{ left, top }}>
      {tip.content}
    </div>
  )
}
