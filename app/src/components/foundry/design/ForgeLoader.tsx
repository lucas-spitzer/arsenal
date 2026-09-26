interface ForgeLoaderProps {
  label: string
  size?: 'sm' | 'lg'
}

const DEPTH = 5

/** Each frame renders a smaller copy of itself; the nested rotation is the animation. */
function ForgeFrame({ depth }: { depth: number }) {
  return (
    <span className={`dsn-forge__frame dsn-forge__frame--${depth % 2 === 0 ? 'scarlet' : 'gold'}`}>
      {depth > 1 ? <ForgeFrame depth={depth - 1} /> : <span className="dsn-forge__core" />}
    </span>
  )
}

export function ForgeLoader({ label, size = 'lg' }: ForgeLoaderProps) {
  return (
    <div className={`dsn-forge dsn-forge--${size}`} role="status" aria-live="polite">
      <span className="dsn-forge__mark" aria-hidden="true">
        <ForgeFrame depth={DEPTH} />
      </span>
      <span className="dsn-forge__label">{label}</span>
    </div>
  )
}
