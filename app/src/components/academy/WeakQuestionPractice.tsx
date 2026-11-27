import { ArrowLeft, Check, Info, Send, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useAtlas } from '../../features/atlas/atlasContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { combineSeed, drawOptions, hasPool, seededRng } from '../../lib/answerPool'
import { showsStemImage } from '../../lib/assessmentVisual'
import { submitPracticeAnswer, type AnswerSubmitResult } from '../../lib/atlasApi'
import type { Quiz } from '../../lib/workspaceApi'
import { AssessmentPicture } from './AssessmentPicture'
import { ChoiceOptions } from './ChoiceOptions'
import { answerLabels, isMultipleSelect } from './choiceOptions'
import { CORRECT_BURST_MS, CorrectBurst } from './CorrectBurst'

function isShortAnswerQuiz(quiz: Quiz): boolean {
  return (quiz.subtype ?? quiz.question_type) === 'short_answer'
}

function optionIsCorrect(quiz: Quiz, option: string, index: number): boolean {
  const answer = (quiz.correct_answer ?? '').trim()
  if (!answer) return false
  if (answer === option) return true
  if (/^[A-Za-z]$/.test(answer) && answer.toUpperCase().charCodeAt(0) - 65 === index) return true
  if (/^\d+$/.test(answer) && Number(answer) === index) return true
  return false
}

function drawQuestion(quiz: Quiz, seed: number): { question: string; options: string[]; correct: string[] | null } {
  if (isShortAnswerQuiz(quiz) || !hasPool(quiz.answer_pool)) {
    return { question: quiz.question, options: quiz.options, correct: null }
  }
  const result = drawOptions(
    quiz.answer_pool,
    quiz.subtype ?? quiz.question_type,
    seededRng(combineSeed(seed, quiz.id)),
  )
  return {
    question: result.question ?? quiz.question,
    options: result.options,
    correct: result.correct,
  }
}

export function WeakQuestionPractice({
  quiz,
  stem,
  subjectName,
  onBack,
}: {
  quiz: Quiz | null
  stem: string
  subjectName: string
  onBack: () => void
}) {
  const { activeWorkspace } = useWorkspace()
  const { setLifetimeAp } = useAtlas()
  const [seed] = useState(() => Math.floor(Math.random() * 0x7fffffff))
  const [picked, setPicked] = useState<number[]>([])
  const [result, setResult] = useState<AnswerSubmitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [responseDraft, setResponseDraft] = useState('')
  const [floatLabel, setFloatLabel] = useState<string | null>(null)
  const burstTimer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(burstTimer.current), [])

  const drawn = useMemo(() => (quiz ? drawQuestion(quiz, seed) : null), [quiz, seed])
  const shortAnswer = quiz ? isShortAnswerQuiz(quiz) : false
  const multiple = quiz ? isMultipleSelect(quiz.subtype ?? quiz.question_type) : false
  const revealed = result !== null

  const applyScore = (next: AnswerSubmitResult) => {
    setResult(next)
    setLifetimeAp(next.lifetime_ap)
    if (next.correct) {
      setFloatLabel(next.points_total > 0 ? `+${next.points_total} AP` : '')
      window.clearTimeout(burstTimer.current)
      burstTimer.current = window.setTimeout(() => setFloatLabel(null), CORRECT_BURST_MS)
    }
  }

  const choose = (optionIndex: number) => {
    if (!quiz || !drawn || !activeWorkspace || revealed || submitting || multiple) return
    setPicked([optionIndex])
    setSubmitting(true)
    setError(null)
    void submitPracticeAnswer(activeWorkspace.id, {
      quiz_id: quiz.id,
      question: drawn.question,
      options: drawn.options,
      selected_index: optionIndex,
    })
      .then(applyScore)
      .catch((caught: unknown) => {
        setPicked([])
        setError(caught instanceof Error ? caught.message : 'Could not submit that answer.')
      })
      .finally(() => setSubmitting(false))
  }

  const togglePicked = (optionIndex: number) => {
    if (revealed || submitting) return
    setPicked((current) =>
      current.includes(optionIndex) ? current.filter((index) => index !== optionIndex) : [...current, optionIndex],
    )
  }

  const checkSelection = () => {
    if (!quiz || !drawn || !activeWorkspace || picked.length === 0 || revealed || submitting) return
    setSubmitting(true)
    setError(null)
    void submitPracticeAnswer(activeWorkspace.id, {
      quiz_id: quiz.id,
      question: drawn.question,
      options: drawn.options,
      selected_indices: picked,
    })
      .then(applyScore)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Could not submit that answer.')
      })
      .finally(() => setSubmitting(false))
  }

  const submitShortAnswer = (event: FormEvent) => {
    event.preventDefault()
    const text = responseDraft.trim()
    if (!quiz || !drawn || !activeWorkspace || !text || submitting || revealed) return
    setSubmitting(true)
    setError(null)
    void submitPracticeAnswer(activeWorkspace.id, {
      quiz_id: quiz.id,
      question: drawn.question,
      response: text,
    })
      .then(applyScore)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Could not grade that answer.')
      })
      .finally(() => setSubmitting(false))
  }

  const fromServer = result ? answerLabels(result.correct_options, result.right_answer) : []
  const correctOptions =
    fromServer.length > 0
      ? fromServer
      : result && quiz && drawn
        ? drawn.options.filter((option, optionIndex) =>
            drawn.correct && drawn.correct.length > 0
              ? drawn.correct.includes(option)
              : optionIsCorrect(quiz, option, optionIndex),
          )
        : []

  const explanation = result?.explanation || quiz?.explanation || ''

  return (
    <div className="anl__practice-view">
      <div className="anl__practice-bar">
        <button type="button" className="study__btn" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
        <p className="anl__note">{subjectName}</p>
      </div>

      {!quiz || !drawn ? (
        <div className="anl__question">
          <p className="quiz__question">{stem}</p>
          <p className="anl__note">Question unavailable.</p>
        </div>
      ) : (
        <div className="anl__question quiz">
          {floatLabel !== null && result ? (
            <CorrectBurst label={floatLabel} mastery={result.newly_mastered} />
          ) : null}
          {result?.newly_mastered ? <p className="ap-mastery-banner">Concept mastered · +3 bonus</p> : null}
          {quiz.visual?.url && showsStemImage(quiz.visual.placement) ? (
            <AssessmentPicture visual={quiz.visual} text={drawn.question} />
          ) : null}
          <p className="quiz__question">{drawn.question}</p>
          {shortAnswer ? (
            <form className="quiz__short-answer" onSubmit={submitShortAnswer}>
              <label className="lib__select">
                <span className="lib__select-label">Your answer</span>
                <textarea
                  className="as-wiki__input"
                  rows={4}
                  value={responseDraft}
                  disabled={revealed || submitting}
                  onChange={(event) => setResponseDraft(event.target.value)}
                  placeholder="Write a short answer"
                />
              </label>
              {result ? (
                <p className={`quiz__short-verdict${result.correct ? ' is-correct' : ' is-wrong'}`}>
                  {result.correct ? (
                    <>
                      <Check size={16} /> Pass
                    </>
                  ) : (
                    <>
                      <X size={16} /> Needs work
                    </>
                  )}
                </p>
              ) : null}
              {result?.feedback ? <p className="quiz__explain">{result.feedback}</p> : null}
              {error ? <p className="quiz__score-note">{error}</p> : null}
              {!revealed ? (
                <button type="submit" className="study__btn" disabled={submitting || !responseDraft.trim()}>
                  <Send size={16} /> {submitting ? 'Grading…' : 'Submit answer'}
                </button>
              ) : null}
            </form>
          ) : (
            <ChoiceOptions
              options={drawn.options}
              multiple={multiple}
              picked={picked}
              revealed={revealed}
              submitting={submitting}
              correctOptions={correctOptions}
              onPick={multiple ? togglePicked : choose}
              onCheck={checkSelection}
            />
          )}
          {error && !shortAnswer ? <p className="quiz__score-note">{error}</p> : null}
          {revealed && explanation ? (
            <p className="quiz__explain">
              <Info size={15} /> {explanation}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}
