import type { AssessmentVisual } from '../../lib/workspaceApi'
import { cardFace, type CardSide } from '../../lib/assessmentVisual'

export function AssessmentPicture({ visual, text }: { visual: AssessmentVisual; text: string }) {
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
  if (!visual?.url || face === 'text') {
    return <span className="flashcard__body">{text}</span>
  }
  if (face === 'image') {
    return <AssessmentPicture visual={visual} text={text} />
  }
  return (
    <span className="flashcard__body flashcard__body--beside">
      <AssessmentPicture visual={visual} text={text} />
      <span>{text}</span>
    </span>
  )
}
