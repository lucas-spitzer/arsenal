import type { AssessmentVisual } from '../../lib/workspaceApi'
import { cardFace, type CardSide } from '../../lib/assessmentVisual'

export function AssessmentPicture({
  visual,
  text,
}: {
  visual: Pick<AssessmentVisual, 'url' | 'alt'>
  text: string
}) {
  if (!visual.url) return null
  return <img className="study-visual__img" src={visual.url} alt={visual.alt || text} />
}

export function FlashcardFace({
  side,
  text,
  visual,
}: {
  side: CardSide
  text: string
  visual: AssessmentVisual | null | undefined
}) {
  const face = cardFace(side, visual?.placement)
  const bodyClass = `flashcard__body${flashcardLengthModifier(text)}`
  if (!visual?.url || face === 'text') {
    return <span className={bodyClass}>{text}</span>
  }
  if (face === 'image') {
    return <AssessmentPicture visual={visual} text={text} />
  }
  return (
    <span className={`${bodyClass} flashcard__body--beside`}>
      <AssessmentPicture visual={visual} text={text} />
      <span>{text}</span>
    </span>
  )
}

function flashcardLengthModifier(text: string): string {
  if (text.length > 260) return ' flashcard__body--xlong'
  if (text.length > 140) return ' flashcard__body--long'
  return ''
}
