interface FoundryLoaderProps {
  label: string
  size?: 'sm' | 'lg'
}

function Cartridge({ x }: { x: number }) {
  return (
    <g className="as-console__loader-cartridge">
      <path d={`M ${x - 4.5} 37 Q ${x - 4} 29 ${x} 23 Q ${x + 4} 29 ${x + 4.5} 37 Z`} />
      <path d={`M ${x - 5} 38 H ${x + 5} V 67 H ${x - 5} Z`} />
      <path d={`M ${x - 6} 67 H ${x + 6} V 72 H ${x - 6} Z`} />
    </g>
  )
}

export function FoundryLoader({ label, size = 'lg' }: FoundryLoaderProps) {
  return (
    <div className={`as-console__loader as-console__loader--${size}`} role="status" aria-live="polite">
      <span className="as-console__loader-mark" aria-hidden="true">
        <svg viewBox="0 0 100 100" focusable="false">
          <circle className="as-console__loader-ring-track" cx="50" cy="50" r="43" />
          <circle className="as-console__loader-ring-progress" cx="50" cy="50" r="43" />
          <Cartridge x={35} />
          <Cartridge x={50} />
          <Cartridge x={65} />
        </svg>
      </span>
      <span className="as-console__loader-label">{label}</span>
    </div>
  )
}
