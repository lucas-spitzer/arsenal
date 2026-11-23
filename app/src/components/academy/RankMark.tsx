/** Abstract rank bars. Not official insignia. */

type RankDevice = {
  count: 1 | 2
  metal: 'gold' | 'silver'
}

export function RankMark({ rank, size = 36 }: { rank?: string | null; size?: number }) {
  const device = rankDevice(rank)
  const pair = device.count === 2 ? ' id-plate__bars--pair' : ''
  return (
    <span
      className="id-plate__rank"
      style={{ width: size, height: size }}
      title={rank || 'Rank'}
      aria-hidden
    >
      <span className={`id-plate__bars id-plate__bars--${device.metal}${pair}`}>
        {Array.from({ length: device.count }, (_, index) => (
          <i key={index} />
        ))}
      </span>
    </span>
  )
}

function rankDevice(rank?: string | null): RankDevice {
  const value = (rank || '').replace(/\s+/g, '').toLowerCase()
  if (value.includes('capt') || value.includes('cpt')) return { count: 2, metal: 'silver' }
  if (value.includes('1st') || value.includes('1lt') || value.includes('firstlt')) {
    return { count: 1, metal: 'silver' }
  }
  return { count: 1, metal: 'gold' }
}
