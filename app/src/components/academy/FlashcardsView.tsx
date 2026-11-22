import { Check, Info, Shuffle, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { filterAndSortRecords } from '../../lib/academyOutputs'
import { combineSeed, drawOptions, hasPool, seededRng } from '../../lib/answerPool'
import { showsStemImage } from '../../lib/assessmentVisual'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import { isWikiTermQuiz } from '../../lib/assessmentOrigin'
import type { Flashcard, Quiz } from '../../lib/workspaceApi'
import {
  StudyHead,
  StudyPanel,
  StudySourceReference,
} from './StudySessionChrome'
import { AssessmentPicture, FlashcardFace } from './AssessmentPicture'
import { useStudyFullscreen } from './useStudyFullscreen'

type PracticeMode = 'flashcards' | 'questions'

function shuffleOrder(length: number, seed: number): number[] {
  const order = Array.from({ length }, (_, index) => index)
  const rng = seededRng(seed)
  for (let i = order.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1))
    ;[order[i], order[j]] = [order[j]!, order[i]!]
  }
  return order
}

function optionIsCorrect(quiz: Quiz, option: string, index: number): boolean {
  const answer = (quiz.correct_answer ?? '').trim()
  if (!answer) return false
  if (answer === option) return true
  if (/^[A-Za-z]$/.test(answer) && answer.toUpperCase().charCodeAt(0) - 65 === index) return true
  if (/^\d+$/.test(answer) && Number(answer) === index) return true
  return false
}

export function FlashcardsView({
  sourceId: initialSource = null,
  targetId = null,
  projectId = null,
}: {
  sourceId?: string | null
  targetId?: string | null
  projectId?: string | null
}) {
  const { flashcards, quizzes, sources: workspaceSources } = useWorkspaceData()
  const { fullscreen, toggle } = useStudyFullscreen()

  const [mode, setMode] = useState<PracticeMode>('flashcards')
  const [sourceId, setSourceId] = useState<string | null>(initialSource)
  const [sourceProp, setSourceProp] = useState(initialSource)
  const [shuffleSeed, setShuffleSeed] = useState(() => Date.now())
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [questionSeed, setQuestionSeed] = useState(() => Date.now())
  const targetAppliedRef = useRef<string | null>(null)

  // Follow Library deep-link source changes without an effect.
  if (initialSource !== sourceProp) {
    setSourceProp(initialSource)
    setSourceId(initialSource)
    setIndex(0)
    setFlipped(false)
    setSelected(null)
  }

  const sources = useMemo(() => {
    const byId = new Map(workspaceSources.map((source) => [source.id, source]))
    const labelOf = (id: string) => {
      const source = byId.get(id)
      return source ? sourceDisplayName(source) : 'Unassigned'
    }
    const seen = new Map<string, string>()
    for (const card of flashcards) {
      if (!card.source_id || seen.has(card.source_id)) continue
      seen.set(card.source_id, labelOf(card.source_id))
    }
    for (const quiz of quizzes) {
      if (!isWikiTermQuiz(quiz) || !quiz.source_id || seen.has(quiz.source_id)) continue
      seen.set(quiz.source_id, labelOf(quiz.source_id))
    }
    return [...seen.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [flashcards, quizzes, workspaceSources])

  const filteredCards = useMemo(
    () =>
      filterAndSortRecords(flashcards, (card) => `${card.front} ${card.back}`, {
        search: '',
        sourceId,
        sort: 'source',
        projectId,
      }),
    [flashcards, sourceId, projectId],
  )

  const cardOrder = useMemo(
    () => shuffleOrder(filteredCards.length, shuffleSeed),
    [filteredCards.length, shuffleSeed],
  )

  const cards = useMemo(
    () => cardOrder.map((i) => filteredCards[i]).filter((card): card is Flashcard => Boolean(card)),
    [cardOrder, filteredCards],
  )

  const termQuestions = useMemo(
    () =>
      filterAndSortRecords(
        quizzes.filter((quiz) => isWikiTermQuiz(quiz)),
        (quiz) => quiz.question,
        { search: '', sourceId, sort: 'source', projectId },
      ),
    [quizzes, sourceId, projectId],
  )

  const questionOrder = useMemo(
    () => shuffleOrder(termQuestions.length, questionSeed),
    [termQuestions.length, questionSeed],
  )

  const orderedQuestions = useMemo(
    () => questionOrder.map((i) => termQuestions[i]).filter((quiz): quiz is Quiz => Boolean(quiz)),
    [questionOrder, termQuestions],
  )

  // Apply Library deep-link focus once the matching card is in the loaded list.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!targetId || cards.length === 0 || mode !== 'flashcards') return
    if (targetAppliedRef.current === targetId) return
    const idx = cards.findIndex((card) => card.id === targetId)
    if (idx < 0) return
    setIndex(idx)
    setFlipped(false)
    targetAppliedRef.current = targetId
  }, [targetId, cards, mode])
  /* eslint-enable react-hooks/set-state-in-effect */

  const deck = mode === 'flashcards' ? cards : orderedQuestions
  const safeIndex = Math.min(index, Math.max(deck.length - 1, 0))
  const card = mode === 'flashcards' ? cards[safeIndex] : undefined
  const quiz = mode === 'questions' ? orderedQuestions[safeIndex] : undefined

  const drawn = useMemo(() => {
    if (!quiz) return null
    if (!hasPool(quiz.answer_pool)) {
      return {
        question: quiz.question,
        options: quiz.options,
        correct: null as string[] | null,
      }
    }
    const result = drawOptions(
      quiz.answer_pool,
      quiz.subtype ?? quiz.question_type,
      seededRng(combineSeed(questionSeed, quiz.id)),
    )
    return {
      question: result.question ?? quiz.question,
      options: result.options,
      correct: result.correct,
    }
  }, [quiz, questionSeed])

  const resetPosition = () => {
    setIndex(0)
    setFlipped(false)
    setSelected(null)
  }

  const setPracticeMode = (next: PracticeMode) => {
    if (next === mode) return
    setMode(next)
    resetPosition()
  }

  const changeSource = (next: string | null) => {
    setSourceId(next)
    resetPosition()
  }

  const shuffleDeck = () => {
    if (mode === 'flashcards') setShuffleSeed((seed) => seed + 1)
    else setQuestionSeed((seed) => seed + 1)
    resetPosition()
  }

  const go = (delta: number) => {
    if (deck.length === 0) return
    setFlipped(false)
    setSelected(null)
    setIndex((i) => (Math.min(i, deck.length - 1) + delta + deck.length) % deck.length)
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
      } else if (event.key === 'ArrowRight' && safeIndex < deck.length - 1) {
        event.preventDefault()
        go(1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const activeSourceId = card?.source_id ?? quiz?.source_id ?? null
  const sourceName = activeSourceId
    ? sources.find((source) => source.id === activeSourceId)?.name ?? 'Unassigned'
    : 'Unassigned'

  const optionCorrect = (option: string, optionIndex: number) => {
    if (!quiz || !drawn) return false
    if (drawn.correct) return drawn.correct.includes(option)
    return optionIsCorrect(quiz, option, optionIndex)
  }

  const revealed = selected !== null

  const choose = (optionIndex: number) => {
    if (selected !== null) return
    setSelected(optionIndex)
  }

  const nextQuestion = () => {
    if (!revealed) return
    if (safeIndex >= deck.length - 1) {
      shuffleDeck()
      return
    }
    go(1)
  }

  const toolbar = (
    <div className="quiz__picks">
      <div className="lib__chips" role="group" aria-label="Practice mode">
        <button
          type="button"
          className={`lib__chip${mode === 'flashcards' ? ' is-active' : ''}`}
          onClick={() => setPracticeMode('flashcards')}
        >
          Flashcards
        </button>
        <button
          type="button"
          className={`lib__chip${mode === 'questions' ? ' is-active' : ''}`}
          onClick={() => setPracticeMode('questions')}
        >
          Questions
        </button>
      </div>
      <label className="lib__select">
        <span className="lib__select-label">Source</span>
        <select
          value={sourceId ?? ''}
          onChange={(event) => changeSource(event.target.value || null)}
          aria-label="Filter by source"
        >
          <option value="">All</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.name}
            </option>
          ))}
        </select>
      </label>
      {mode === 'flashcards' ? (
        <button type="button" className="study__btn" onClick={shuffleDeck} disabled={cards.length < 2}>
          <Shuffle size={16} /> Shuffle
        </button>
      ) : null}
    </div>
  )

  return (
    <section className="study-session">
      <StudyHead
        eyebrow="Recall practice"
        title="Flashcard review"
        description={
          mode === 'flashcards'
            ? 'Flip through key terms and check the definition on the back.'
            : 'Answer randomized questions on key terms from this library.'
        }
        stats={[
          {
            value: mode === 'flashcards' ? cards.length : orderedQuestions.length,
            label: mode === 'flashcards' ? 'cards' : 'questions',
          },
          {
            value: new Set(
              (mode === 'flashcards' ? cards : orderedQuestions).map((item) => item.source_id ?? ''),
            ).size,
            label: 'sources',
          },
        ]}
      />

      {toolbar}

      {mode === 'flashcards' && card ? (
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
              onClick={() => setFlipped((value) => !value)}
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
      ) : null}

      {mode === 'questions' && quiz && drawn ? (
        <>
          <StudyPanel
            fullscreen={fullscreen}
            onToggleFullscreen={toggle}
            meta={<span className={`pill pill--${quiz.difficulty}`}>{quiz.difficulty}</span>}
            progress={{ current: safeIndex + 1, total: orderedQuestions.length }}
            pager={{
              onPrev: () => go(-1),
              onNext: nextQuestion,
              prevDisabled: safeIndex <= 0,
              nextDisabled: !revealed,
              label: revealed && safeIndex >= orderedQuestions.length - 1 ? 'Shuffle again' : sourceName,
            }}
          >
            <div className="quiz">
              {quiz.visual?.url && showsStemImage(quiz.visual.placement) ? (
                <AssessmentPicture visual={quiz.visual} text={drawn.question} />
              ) : null}
              <p className="quiz__question">{drawn.question}</p>
              <div className="quiz__options">
                {drawn.options.map((option, optionIndex) => {
                  let cls = 'quiz__option'
                  const correct = optionCorrect(option, optionIndex)
                  const showCorrect = revealed && correct
                  const showWrong = revealed && optionIndex === selected && !correct
                  if (showCorrect) cls += ' is-correct'
                  else if (showWrong) cls += ' is-wrong'
                  return (
                    <button
                      key={optionIndex}
                      type="button"
                      className={cls}
                      disabled={revealed}
                      onClick={() => choose(optionIndex)}
                    >
                      <span className="quiz__option-text">{option}</span>
                      {showCorrect ? (
                        <span className="quiz__option-status">
                          <Check size={16} /> Correct
                        </span>
                      ) : null}
                      {showWrong ? (
                        <span className="quiz__option-status">
                          <X size={16} /> Incorrect
                        </span>
                      ) : null}
                    </button>
                  )
                })}
              </div>
              {revealed && quiz.explanation ? (
                <p className="quiz__explain">
                  <Info size={15} /> {quiz.explanation}
                </p>
              ) : null}
            </div>
          </StudyPanel>

          <StudySourceReference sourceId={quiz.source_id ?? null} sourceName={sourceName} />
        </>
      ) : null}

      {mode === 'flashcards' && !card ? (
        <div className="quiz quiz--result">
          <p className="quiz__score">No flashcards</p>
          <p className="quiz__score-note">No flashcards are available for this scope.</p>
        </div>
      ) : null}

      {mode === 'questions' && !quiz ? (
        <div className="quiz quiz--result">
          <p className="quiz__score">No questions</p>
          <p className="quiz__score-note">No term questions are available for this scope.</p>
        </div>
      ) : null}
    </section>
  )
}
