import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { filterAndSortRecords, useOutputs } from '../../lib/academyOutputs'
import {
  StudyHead,
  StudyPanel,
  StudySourceReference,
} from './StudySessionChrome'
import { FlashcardFace } from './AssessmentPicture'
import { useStudyFullscreen } from './useStudyFullscreen'

export function FlashcardsView({
  sourceId: initialSource = null,
  targetId = null,
}: {
  sourceId?: string | null
  targetId?: string | null
}) {
  const { flashcards } = useWorkspaceData()
  const { sources } = useOutputs()
  const { fullscreen, toggle } = useStudyFullscreen()

  const cards = useMemo(
    () =>
      filterAndSortRecords(flashcards, (c) => `${c.front} ${c.back}`, {
        search: '',
        sourceId: initialSource,
        sort: 'source',
      }),
    [flashcards, initialSource],
  )

  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const targetAppliedRef = useRef<string | null>(null)

  // Apply Library deep-link focus once the matching card is in the loaded list.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!targetId || cards.length === 0) return
    if (targetAppliedRef.current === targetId) return
    const idx = cards.findIndex((c) => c.id === targetId)
    if (idx < 0) return
    setIndex(idx)
    setFlipped(false)
    targetAppliedRef.current = targetId
  }, [targetId, cards])
  /* eslint-enable react-hooks/set-state-in-effect */

  const safeIndex = Math.min(index, Math.max(cards.length - 1, 0))
  const card = cards[safeIndex]

  const go = (delta: number) => {
    if (cards.length === 0) return
    setFlipped(false)
    setIndex((i) => (Math.min(i, cards.length - 1) + delta + cards.length) % cards.length)
  }

  // Arrow keys page through the deck, matching the pager (no wrap-around).
  // Ignored while typing in a form control so other inputs keep arrow behavior.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.isContentEditable ||
          ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
      ) {
        return
      }
      if (event.key === 'ArrowLeft' && safeIndex > 0) {
        event.preventDefault()
        go(-1)
      } else if (event.key === 'ArrowRight' && safeIndex < cards.length - 1) {
        event.preventDefault()
        go(1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const sourceName = card
    ? sources.find((s) => s.id === card.source_id)?.name ?? 'Unassigned'
    : 'Unassigned'

  return (
    <section className="study-session">
      <StudyHead
        eyebrow="Recall practice"
        title="Flashcard review"
        description="Work a focused queue and assess recall as you go."
        stats={[
          { value: cards.length, label: 'cards' },
          { value: new Set(cards.map((c) => c.source_id ?? '')).size, label: 'sources' },
        ]}
      />

      {card ? (
        <>
          <StudyPanel
            fullscreen={fullscreen}
            onToggleFullscreen={toggle}
            meta={<span className={`pill pill--${card.difficulty}`}>{card.difficulty}</span>}
            progress={{ current: safeIndex + 1, total: cards.length }}
            pager={{
              onPrev: () => go(-1),
              onNext: () => go(1),
              prevDisabled: safeIndex <= 0,
              nextDisabled: safeIndex >= cards.length - 1,
              label: sourceName,
            }}
          >
            <button
              type="button"
              className={`flashcard${flipped ? ' is-flipped' : ''}`}
              onClick={() => setFlipped((f) => !f)}
            >
              <span className="flashcard__side">
                {flipped ? 'Back · tap to flip' : 'Front · tap to flip'}
              </span>
              <FlashcardFace
                side={flipped ? 'back' : 'front'}
                text={flipped ? card.back : card.front}
                visual={card.visual}
              />
            </button>
          </StudyPanel>

          <StudySourceReference sourceId={card.source_id ?? null} sourceName={sourceName} />
        </>
      ) : (
        <div className="quiz quiz--result">
          <p className="quiz__score">No flashcards</p>
          <p className="quiz__score-note">No flashcards are available for this scope.</p>
        </div>
      )}
    </section>
  )
}
