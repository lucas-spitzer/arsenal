import { Check, Info, RotateCcw, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { filterAndSortRecords, useOutputs } from '../../lib/academyOutputs'
import { combineSeed, drawOptions, hasPool, pickVariants, seededRng } from '../../lib/answerPool'
import {
  batchesForSource,
  defaultQuizBatch,
  listQuizBatches,
  quizBatchSources,
  type QuizBatch,
} from '../../lib/quizBatches'
import {
  createQuizResult,
  type QuizResult,
  type QuizResultDraft,
  type QuizResultDraftAnswer,
} from '../../lib/quizResultsApi'
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

interface DrawnQuiz {
  quiz: Quiz
  question: string
  options: string[]
  correct: string[] | null
}

interface QuizMiss {
  quizId: string
  question: string
  selected: string
  answer: string
}

interface QuizOutcome {
  correct: number
  total: number
  misses: QuizMiss[]
  pending: boolean
  saveError: string | null
  canRetry: boolean
}

function optionIsRight(item: DrawnQuiz, option: string, index: number): boolean {
  if (item.correct) return item.correct.includes(option)
  return optionIsCorrect(item.quiz, option, index)
}

function gradeRun(run: DrawnQuiz[], answers: Record<string, number>) {
  let correct = 0
  const misses: QuizMiss[] = []
  const submissions: QuizResultDraftAnswer[] = []
  let complete = true
  for (const item of run) {
    const selectedIndex = answers[item.quiz.id]
    if (selectedIndex == null || selectedIndex < 0 || selectedIndex >= item.options.length) {
      complete = false
      continue
    }
    const selected = item.options[selectedIndex] ?? ''
    const right = item.options.find((option, index) => optionIsRight(item, option, index)) ?? ''
    const isCorrect = optionIsRight(item, selected, selectedIndex)
    if (isCorrect) correct += 1
    else misses.push({ quizId: item.quiz.id, question: item.question, selected, answer: right })
    submissions.push({
      quiz_id: item.quiz.id,
      question: item.question,
      options: item.options,
      selected_index: selectedIndex,
    })
  }
  return { correct, total: run.length, misses, submissions, complete: complete && submissions.length === run.length }
}

function missesFromResult(result: QuizResult): QuizMiss[] {
  return result.answers
    .filter((answer) => !answer.correct)
    .map((answer) => ({
      quizId: answer.quiz_id,
      question: answer.question,
      selected: answer.selected,
      answer: answer.answer,
    }))
}

export function QuizView({
  sourceId: initialSource = null,
  targetId = null,
  projectId = null,
  batchKey = null,
}: {
  sourceId?: string | null
  targetId?: string | null
  projectId?: string | null
  batchKey?: string | null
}) {
  const { activeWorkspace } = useWorkspace()
  const { quizzes, knowledgeRunTitles } = useWorkspaceData()
  const { sources } = useOutputs()
  const { fullscreen, toggle } = useStudyFullscreen()
  const batches = listQuizBatches(
    quizzes,
    knowledgeRunTitles,
    (sourceId) => sources.find((source) => source.id === sourceId)?.name ?? 'Unassigned',
  )
  const [pickedKey, setPickedKey] = useState<string | null>(null)
  const batch =
    batches.find((item) => item.key === pickedKey) ??
    defaultQuizBatch(batches, { sourceId: initialSource, projectId, batchKey })
  const sourceChoices = quizBatchSources(batches)
  const batchChoices = batch ? batchesForSource(batches, batch.sourceKey) : []

  const items = batch
    ? filterAndSortRecords(
        quizzes.filter(
          (quiz) =>
            (quiz.source_id ?? null) === batch.sourceId &&
            (quiz.knowledge_project_id ?? null) === batch.projectId,
        ),
        (quiz) => quiz.question,
        { search: '', sourceId: null, sort: 'source' },
      )
    : []

  const [qIndex, setQIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [finished, setFinished] = useState(false)
  const [outcome, setOutcome] = useState<QuizOutcome | null>(null)
  const [sessionSeed, setSessionSeed] = useState(() => Date.now())
  const [allVariants, setAllVariants] = useState(false)
  const targetAppliedRef = useRef<string | null>(null)
  const finishStarted = useRef(false)
  const pendingSave = useRef<QuizResultDraft | null>(null)
  const saveGeneration = useRef(0)

  const draws = new Map<string, ReturnType<typeof drawOptions>>()
  for (const quiz of items) {
    if (!hasPool(quiz.answer_pool)) continue
    draws.set(
      quiz.id,
      drawOptions(quiz.answer_pool, quiz.subtype ?? quiz.question_type, seededRng(combineSeed(sessionSeed, quiz.id))),
    )
  }

  const chosen = allVariants
    ? items
    : pickVariants(items, seededRng(sessionSeed), targetId ? new Set([targetId]) : new Set())
  const run = chosen.map((quiz) => {
    const drawn = draws.get(quiz.id)
    return {
      quiz,
      question: drawn?.question ?? quiz.question,
      options: drawn?.options ?? quiz.options,
      correct: drawn ? drawn.correct : null,
    }
  })

  const resetRun = () => {
    saveGeneration.current += 1
    finishStarted.current = false
    pendingSave.current = null
    setSessionSeed((seed) => seed + 1)
    setQIndex(0)
    setSelected(null)
    setAnswers({})
    setFinished(false)
    setOutcome(null)
  }
  const chooseBatch = (next: QuizBatch | undefined) => {
    if (!next || next.key === batch?.key) return
    setPickedKey(next.key)
    resetRun()
  }
  const toggleScope = () => {
    setAllVariants((value) => !value)
    resetRun()
  }

  // Apply a deep link once the matching question is in this batch.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!targetId || run.length === 0) return
    if (targetAppliedRef.current === targetId) return
    const idx = run.findIndex((item) => item.quiz.id === targetId)
    if (idx < 0) return
    setQIndex(idx)
    setSelected(null)
    targetAppliedRef.current = targetId
  }, [targetId, run])
  /* eslint-enable react-hooks/set-state-in-effect */

  const safeIndex = Math.min(qIndex, Math.max(run.length - 1, 0))
  const current = run[safeIndex]
  const quiz = current?.quiz
  const revealed = selected !== null
  const isLast = safeIndex === run.length - 1
  const optionCorrect = (option: string, index: number) => {
    if (!current) return false
    return optionIsRight(current, option, index)
  }

  const choose = (index: number) => {
    if (selected !== null || !current) return
    setSelected(index)
    setAnswers((prev) => ({ ...prev, [current.quiz.id]: index }))
  }

  const persist = async (draft: QuizResultDraft) => {
    const generation = saveGeneration.current
    if (!activeWorkspace) {
      setOutcome((prev) =>
        prev ? { ...prev, pending: false, saveError: 'This score was not saved.', canRetry: false } : prev,
      )
      return
    }
    setOutcome((prev) => (prev ? { ...prev, pending: true, saveError: null, canRetry: false } : prev))
    try {
      const saved = await createQuizResult(activeWorkspace.id, draft)
      if (saveGeneration.current !== generation) return
      pendingSave.current = null
      setOutcome({
        correct: saved.correct_count,
        total: saved.question_count,
        misses: missesFromResult(saved),
        pending: false,
        saveError: null,
        canRetry: false,
      })
    } catch {
      if (saveGeneration.current !== generation) return
      setOutcome((prev) =>
        prev ? { ...prev, pending: false, saveError: 'This score was not saved.', canRetry: true } : prev,
      )
    }
  }

  const finish = () => {
    if (finishStarted.current || !batch) return
    const graded = gradeRun(run, { ...answers, ...(current && selected != null ? { [current.quiz.id]: selected } : {}) })
    finishStarted.current = true
    setFinished(true)
    setOutcome({
      correct: graded.correct,
      total: graded.total,
      misses: graded.misses,
      pending: graded.complete,
      saveError: graded.complete ? null : 'This score was not saved.',
      canRetry: false,
    })
    if (!graded.complete || graded.submissions.length === 0) return
    const draft: QuizResultDraft = {
      knowledge_project_id: batch.projectId,
      source_id: batch.sourceId,
      scope: allVariants ? 'every_variant' : 'one_per_term',
      answers: graded.submissions,
    }
    pendingSave.current = draft
    void persist(draft)
  }

  const next = () => {
    if (isLast) {
      finish()
      return
    }
    setQIndex((index) => index + 1)
    setSelected(null)
  }

  const prev = () => {
    if (safeIndex === 0) return
    setQIndex((index) => index - 1)
    setSelected(null)
  }

  const sourceName = quiz
    ? (sources.find((source) => source.id === quiz.source_id)?.name ?? 'Unassigned')
    : (batch?.sourceName ?? 'Unassigned')

  const picks = sourceChoices.length > 0 && batch ? (
    <div className="quiz__picks">
      <label className="lib__select">
        <span className="lib__select-label">Source</span>
        <select
          value={batch.sourceKey}
          onChange={(event) => {
            const inSource = batches.filter((item) => item.sourceKey === event.target.value)
            chooseBatch(defaultQuizBatch(inSource, {}) ?? undefined)
          }}
          aria-label="Quiz source"
        >
          {sourceChoices.map((source) => (
            <option key={source.sourceKey || 'unassigned'} value={source.sourceKey}>
              {source.sourceName}
            </option>
          ))}
        </select>
      </label>
      <label className="lib__select">
        <span className="lib__select-label">Batch</span>
        <select
          value={batch.key}
          onChange={(event) => chooseBatch(batchChoices.find((item) => item.key === event.target.value))}
          aria-label="Quiz batch"
        >
          {batchChoices.map((item) => (
            <option key={item.key} value={item.key}>
              {item.title} ({item.questionCount})
            </option>
          ))}
        </select>
      </label>
    </div>
  ) : null

  const head = (
    <StudyHead
      eyebrow="Knowledge check"
      title="Quiz"
      description="Answer, review the rationale, and trace each item to its source."
      stats={[
        { value: run.length, label: 'questions' },
        { value: batch?.title ?? 'No batch', label: 'batch' },
      ]}
    />
  )

  return (
    <section className="study-session">
      {head}
      {picks}

      {finished && outcome ? (
        <div className="quiz quiz--result">
          <p className="quiz__score">
            {outcome.correct} of {outcome.total} correct
          </p>
          <p className="quiz__score-note">{batch?.title ?? 'Quiz'}</p>
          {outcome.misses.length > 0 ? (
            <ul className="quiz__misses">
              {outcome.misses.map((miss) => (
                <li key={miss.quizId}>
                  <p className="quiz__miss-question">{miss.question}</p>
                  <p>
                    You picked {miss.selected}. The answer is {miss.answer}.
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="quiz__score-note">Every question was correct.</p>
          )}
          {outcome.pending ? <p className="quiz__score-note">Saving this result.</p> : null}
          {outcome.saveError ? <p className="quiz__score-note">{outcome.saveError}</p> : null}
          {outcome.canRetry ? (
            <button
              type="button"
              className="study__btn"
              onClick={() => {
                const draft = pendingSave.current
                if (draft) void persist(draft)
              }}
            >
              Save this result
            </button>
          ) : null}
          <button type="button" className="study__btn" onClick={resetRun}>
            <RotateCcw size={16} /> Restart quiz
          </button>
        </div>
      ) : quiz && current ? (
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
              nextDisabled: !revealed,
              label: isLast && revealed ? 'Next: results' : (batch?.title ?? sourceName),
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
          <p className="quiz__score-note">No questions are available for this batch.</p>
        </div>
      )}
    </section>
  )
}
