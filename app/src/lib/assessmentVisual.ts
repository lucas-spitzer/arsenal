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

export function showsSituationImage(placement: string | null | undefined): boolean {
  return placement === 'situation'
}
