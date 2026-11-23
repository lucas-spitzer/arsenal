export type CardSide = 'front' | 'back'
export type CardFace = 'text' | 'image' | 'both'

export function cardFace(side: CardSide, placement: string | null | undefined): CardFace {
  if (placement === 'beside') return 'both'
  if (placement === 'front_with_label') return side === 'front' ? 'both' : 'text'
  if (placement === 'front' && side === 'front') return 'image'
  if (placement === 'back' && side === 'back') return 'image'
  return 'text'
}

export function showsStemImage(placement: string | null | undefined): boolean {
  return placement === 'stem'
}

export function stemPicture(
  visual: Record<string, unknown> | null | undefined,
): { url: string; alt: string | null } | null {
  if (!visual) return null
  const url = visual.url
  const placement = visual.placement
  if (typeof url !== 'string' || url.length === 0) return null
  if (!showsStemImage(typeof placement === 'string' ? placement : null)) return null
  const alt = visual.alt
  return { url, alt: typeof alt === 'string' ? alt : null }
}

export function showsSituationImage(placement: string | null | undefined): boolean {
  return placement === 'situation'
}
