import { Check, Info, RotateCcw, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { filterAndSortRecords, useOutputs } from '../../lib/academyOutputs'
import { combineSeed, drawOptions, hasPool, pickVariants, seededRng } from '../../lib/answerPool'
import type { Quiz } from '../../lib/workspaceApi'
import {
  StudyHead,
  StudyPanel,
  StudySourceReference,
} from './StudySessionChrome'
import { AssessmentPicture } from './AssessmentPicture'
import { showsStemImage } from '../../lib/assessmentVisual'
import { useStudyFullscreen } from './useStudyFullscreen'

// Quiz options are plain strings; correct_answer may be the option text, a
// letter (A/B/C), or a numeric index — handle each.
function optionIsCorrect(quiz: Quiz, option: string, index: number): boolean {
  const answer = (quiz.correct_answer ?? '').trim()
  if (!answer) return false
  if (answer === option) return true
  if (/^[A-Za-z]$/.test(answer) && answer.toUpperCase().charCodeAt(0) - 65 === index) return true
  if (/^\d+$/.test(answer) && Number(answer) === index) return true
  return false
}

export function QuizView({
  sourceId: initialSource = null,
  targetId = null,
}: {
  sourceId?: string | null
  targetId?: string | null
}) {
  const { quizzes } = useWorkspaceData()
  const { sources } = useOutputs()
  const { fullscreen, toggle } = useStudyFullscreen()

  const items = useMemo(
    () =>
      filterAndSortRecords(quizzes, (q) => q.question, {
        search: '',
        sourceId: initialSource,
        sort: 'source',
      }),
    [quizzes, initialSource],
  )

  const [qIndex, setQIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [score, setScore] = useState(0)
  const [finished, setFinished] = useState(false)
  const [sessionSeed, setSessionSeed] = useState(() => Date.now())
  const [allVariants, setAllVariants] = useState(false)
  const targetAppliedRef = useRef<string | null>(null)

  // One draw per question for the session, stable across the variant toggle.
  const draws = useMemo(() => {
    const drawn = new Map<string, ReturnType<typeof drawOptions>>()
    for (const quiz of items) {
      if (!hasPool(quiz.answer_pool)) continue
      drawn.set(
        quiz.id,
        drawOptions(quiz.answer_pool, quiz.subtype ?? quiz.question_type, seededRng(combineSeed(sessionSeed, quiz.id))),
      )
    }
    return drawn
  }, [items, sessionSeed])

  const run = useMemo(() => {
    const chosen = allVariants
      ? items
      : pickVariants(items, seededRng(sessionSeed), targetId ? new Set([targetId]) : new Set())
    return chosen.map((quiz) => {
      const drawn = draws.get(quiz.id)
      return {
        quiz,
        question: drawn?.question ?? quiz.question,
        options: drawn?.options ?? quiz.options,
        correct: drawn ? drawn.correct : null,
      }
    })
  }, [allVariants, draws, items, sessionSeed, targetId])

  // Apply Library / console deep-link focus once the matching question is loaded.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!targetId || run.length === 0) return
    if (targetAppliedRef.current === targetId) return
    const idx = run.findIndex((item) => item.quiz.id === targetId)
    if (idx < 0) return
    setQIndex(idx)
    setSelected(null)
    setScore(0)
    setFinished(false)
    targetAppliedRef.current = targetId
  }, [targetId, run])
  /* eslint-enable react-hooks/set-state-in-effect */

  const resetRun = () => {
    setSessionSeed(Date.now())
    setQIndex(0)
    setSelected(null)
    setScore(0)
    setFinished(false)
  }
  const toggleScope = () => {
    setAllVariants((value) => !value)
    setQIndex(0)
    setSelected(null)
    setScore(0)
    setFinished(false)
  }
  const safeIndex = Math.min(qIndex, Math.max(run.length - 1, 0))
  const current = run[safeIndex]
  const quiz = current?.quiz
  const revealed = selected !== null
  const isLast = safeIndex === run.length - 1
  const optionCorrect = (option: string, index: number) => {
    if (!quiz) return false
    if (current.correct) return current.correct.includes(option)
    return optionIsCorrect(quiz, option, index)
  }

  const choose = (i: number) => {
    if (selected !== null || !current) return
    setSelected(i)
    if (optionCorrect(current.options[i], i)) setScore((s) => s + 1)
  }

  const next = () => {
    if (isLast) {
      setFinished(true)
      return
    }
    setQIndex((i) => i + 1)
    setSelected(null)
  }

  const prev = () => {
    if (safeIndex === 0) return
    setQIndex((i) => i - 1)
    setSelected(null)
  }

  const sourceName = quiz
    ? sources.find((s) => s.id === quiz.source_id)?.name ?? 'Unassigned'
    : 'Unassigned'

  const head = (
    <StudyHead
      eyebrow="Knowledge check"
      title="Quiz"
      description="Answer, review the rationale, and trace each item to its source."
      stats={[
        { value: run.length, label: 'questions' },
        { value: new Set(run.map((item) => item.quiz.source_id ?? '')).size, label: 'sources' },
      ]}
    />
  )

  if (finished) {
    return (
      <section className="study-session">
        {head}
        <div className="quiz quiz--result">
          <p className="quiz__score">
            {score} of {run.length} correct
          </p>
          <p className="quiz__score-note">
            Review the source for any items you missed, then run the quiz again.
          </p>
          <button type="button" className="study__btn" onClick={resetRun}>
            <RotateCcw size={16} /> Restart quiz
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="study-session">
      {head}

      {quiz && current ? (
        <>
          <div className="quiz__scope">
            <button type="button" className="study__btn" onClick={toggleScope}>
              {allVariants ? 'One question per term' : 'Show every variant'}
            </button>
          </div>
          <StudyPanel
            fullscreen={fullscreen}
            onToggleFullscreen={toggle}
            meta={<span className={`pill pill--${quiz.difficulty}`}>{quiz.difficulty}</span>}
            progress={{ current: safeIndex + 1, total: run.length }}
            pager={{
              onPrev: prev,
              onNext: next,
              prevDisabled: safeIndex <= 0,
              // Require an answer before moving forward; the last item leads to results.
              nextDisabled: !revealed,
              label: isLast && revealed ? 'Next: results' : sourceName,
            }}
          >
            <div className="quiz">
              {quiz.visual?.url && showsStemImage(quiz.visual.placement) ? (
                <AssessmentPicture visual={quiz.visual} text={current.question} />
              ) : null}
              <p className="quiz__question">{current.question}</p>
              <div className="quiz__options">
                {current.options.map((opt, i) => {
                  let cls = 'quiz__option'
                  const correct = optionCorrect(opt, i)
                  const showCorrect = revealed && correct
                  const showWrong = revealed && i === selected && !correct
                  if (showCorrect) cls += ' is-correct'
                  else if (showWrong) cls += ' is-wrong'
                  return (
                    <button
                      key={i}
                      type="button"
                      className={cls}
                      disabled={revealed}
                      onClick={() => choose(i)}
                    >
                      <span className="quiz__option-text">{opt}</span>
                      {showCorrect && (
                        <span className="quiz__option-status">
                          <Check size={16} /> Correct
                        </span>
                      )}
                      {showWrong && (
                        <span className="quiz__option-status">
                          <X size={16} /> Incorrect
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
              {revealed && quiz.explanation && (
                <p className="quiz__explain">
                  <Info size={15} /> {quiz.explanation}
                </p>
              )}
            </div>
          </StudyPanel>

          <StudySourceReference sourceId={quiz.source_id ?? null} sourceName={sourceName} />
        </>
      ) : (
        <div className="quiz quiz--result">
          <p className="quiz__score">No questions</p>
          <p className="quiz__score-note">No questions are available for this scope.</p>
        </div>
      )}
    </section>
  )
}
