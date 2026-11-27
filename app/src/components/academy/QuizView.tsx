import { Info, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useAtlas } from '../../features/atlas/atlasContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  completeExam,
  startExam,
  submitExamAnswer,
  type AnswerSubmitResult,
  type ExamAttempt,
  type ExamQuestion,
  type SubjectKind,
} from '../../lib/atlasApi'
import { stemPicture } from '../../lib/assessmentVisual'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import { useLessons } from '../../lib/useLessons'
import { AssessmentPicture } from './AssessmentPicture'
import { ChoiceOptions } from './ChoiceOptions.tsx'
import { answerLabels, isMultipleSelect, listPhrase } from './choiceOptions'
import { CORRECT_BURST_MS, CorrectBurst } from './CorrectBurst'
import { quizLaunchFromScope } from './types'
import { StudyHead, StudyPanel, StudySourceReference } from './StudySessionChrome'
import { useStudyFullscreen } from './useStudyFullscreen'

type Mode = 'full_practice' | 'subject'
type Miss = { quizId: string; question: string; selected: string; answer: string }
type Answered = { picked: number[]; feedback: AnswerSubmitResult }

export function QuizView({
  sourceId = null,
  lessonId = null,
}: {
  sourceId?: string | null
  lessonId?: string | null
}) {
  const { activeWorkspace } = useWorkspace()
  const { quizzes, sources } = useWorkspaceData()
  const { lessons } = useLessons(activeWorkspace?.id ?? null)
  const { setLifetimeAp } = useAtlas()
  const { fullscreen, toggle } = useStudyFullscreen()

  const [launch] = useState(() => quizLaunchFromScope({ sourceId, lessonId }))
  const [mode, setMode] = useState<Mode>(launch.mode)
  const [subjectKind, setSubjectKind] = useState<SubjectKind>(launch.subjectKind)
  const [subjectId, setSubjectId] = useState(launch.subjectId)
  const [attempt, setAttempt] = useState<ExamAttempt | null>(null)
  const [index, setIndex] = useState(0)
  const [picked, setPicked] = useState<number[]>([])
  const [feedback, setFeedback] = useState<AnswerSubmitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)
  const [misses, setMisses] = useState<Miss[]>([])
  const [apGained, setApGained] = useState(0)
  const [masteredCount, setMasteredCount] = useState(0)
  const [floatLabel, setFloatLabel] = useState<string | null>(null)
  const [answered, setAnswered] = useState<Record<number, Answered>>({})
  const burstTimer = useRef<number | undefined>(undefined)
  const finishing = useRef(false)

  useEffect(() => () => window.clearTimeout(burstTimer.current), [])

  const subjectOptions = useMemo(() => {
    const sourceOpts = sources.map((source) => ({
      kind: 'source' as const,
      id: source.id,
      name: sourceDisplayName(source),
      count: quizzes.filter((quiz) => quiz.source_id === source.id && !quiz.lesson_id).length,
    }))
    const lessonOpts = lessons.map((lesson) => ({
      kind: 'lesson' as const,
      id: lesson.id,
      name: lesson.title,
      count: quizzes.filter((quiz) => quiz.lesson_id === lesson.id).length,
    }))
    return [...sourceOpts, ...lessonOpts].filter((row) => row.count >= 10)
  }, [sources, lessons, quizzes])
  const subjectReady = subjectOptions.some((row) => row.kind === subjectKind && row.id === subjectId)

  const questions = attempt?.questions ?? []
  const current: ExamQuestion | null = questions[index] ?? null
  const picture = current ? stemPicture(current.visual) : null
  const multiple = isMultipleSelect(current?.subtype)
  const revealed = feedback !== null
  const isLast = index >= questions.length - 1

  const begin = async () => {
    if (!activeWorkspace) return
    setError(null)
    setFinished(false)
    setMisses([])
    setApGained(0)
    setMasteredCount(0)
    setFeedback(null)
    setPicked([])
    setIndex(0)
    setAnswered({})
    try {
      const next = await startExam(activeWorkspace.id, {
        exam_type: mode,
        subject_kind: mode === 'subject' ? subjectKind : null,
        subject_id: mode === 'subject' ? subjectId || null : null,
      })
      setAttempt(next)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not start the exam.')
    }
  }

  const submitChoice = async (indices: number[]) => {
    if (!activeWorkspace || !attempt || !current || feedback !== null || submitting) return
    const choosingSeveral = isMultipleSelect(current.subtype)
    setSubmitting(true)
    setPicked(indices)
    setError(null)
    try {
      const result = await submitExamAnswer(activeWorkspace.id, attempt.id, {
        quiz_id: current.quiz_id,
        question: current.question,
        options: current.options,
        ...(choosingSeveral ? { selected_indices: indices } : { selected_index: indices[0] ?? 0 }),
      })
      setFeedback(result)
      setAnswered((rows) => ({ ...rows, [index]: { picked: indices, feedback: result } }))
      setLifetimeAp(result.lifetime_ap)
      setApGained((value) => value + result.points_total)
      if (result.newly_mastered) setMasteredCount((value) => value + 1)
      if (result.correct) {
        setFloatLabel(result.points_total > 0 ? `+${result.points_total} AP` : '')
        window.clearTimeout(burstTimer.current)
        burstTimer.current = window.setTimeout(() => setFloatLabel(null), CORRECT_BURST_MS)
      }
      if (!result.correct) {
        const selectedLabels = indices.map((optionIndex) => current.options[optionIndex] ?? '').filter(Boolean)
        setMisses((rows) => [
          ...rows,
          {
            quizId: current.quiz_id,
            question: current.question,
            selected: listPhrase(selectedLabels),
            answer: listPhrase(answerLabels(result.correct_options, result.right_answer)),
          },
        ])
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not submit that answer.')
      if (!choosingSeveral) setPicked([])
    } finally {
      setSubmitting(false)
    }
  }

  const choose = (optionIndex: number) => {
    if (!current || feedback !== null || submitting) return
    if (isMultipleSelect(current.subtype)) {
      setPicked((currentPicked) =>
        currentPicked.includes(optionIndex)
          ? currentPicked.filter((index) => index !== optionIndex)
          : [...currentPicked, optionIndex],
      )
      return
    }
    void submitChoice([optionIndex])
  }

  const showQuestion = (target: number) => {
    const saved = answered[target]
    window.clearTimeout(burstTimer.current)
    setFloatLabel(null)
    setIndex(target)
    setPicked(saved?.picked ?? [])
    setFeedback(saved?.feedback ?? null)
  }

  const next = async () => {
    if (!revealed || !activeWorkspace || !attempt || submitting) return
    if (isLast) {
      if (finishing.current) return
      finishing.current = true
      try {
        const done = await completeExam(activeWorkspace.id, attempt.id)
        setAttempt(done)
        setFinished(true)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Could not finish the exam.')
      } finally {
        finishing.current = false
      }
      return
    }
    showQuestion(index + 1)
  }

  const prev = () => {
    if (index <= 0 || submitting) return
    showQuestion(index - 1)
  }

  // Arrow keys page through the exam like the pager. Ignored while typing in a form control.
  useEffect(() => {
    if (!attempt || finished) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return
      event.preventDefault()
      if (event.key === 'ArrowLeft') prev()
      else void next()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  const reset = () => {
    setAttempt(null)
    setFinished(false)
    setIndex(0)
    setAnswered({})
    setPicked([])
    setFeedback(null)
    setMisses([])
    setApGained(0)
    setMasteredCount(0)
    setError(null)
  }

  return (
    <section className="study-session study-session--practice">
      <StudyHead
        eyebrow="Knowledge check"
        title="Quiz"
        description="A full exam draws thirty questions. Subject exams draw ten from one source or class."
      />

      <div className="study-stage study-stage--wide">
        {!attempt ? (
          <div className="quiz__launch">
            <div className="quiz__launch-copy">
              <h2>Choose a graded practice exam</h2>
            </div>
            <div className="quiz__picks quiz__picks--launch">
              <div className="disc__seg quiz__launch-seg" role="group" aria-label="Exam mode">
                <button
                  type="button"
                  className={`disc__seg-btn${mode === 'full_practice' ? ' is-active' : ''}`}
                  onClick={() => setMode('full_practice')}
                >
                  Full Exam (30)
                </button>
                <button
                  type="button"
                  className={`disc__seg-btn${mode === 'subject' ? ' is-active' : ''}`}
                  onClick={() => setMode('subject')}
                >
                  Subject Exam (10)
                </button>
              </div>
              {mode === 'subject' ? (
                <label className="lib__select lib__select--wide">
                  <span className="lib__select-label">Subject</span>
                  <select
                    value={subjectReady ? `${subjectKind}:${subjectId}` : ''}
                    onChange={(event) => {
                      const [kind, id] = event.target.value.split(':')
                      if (kind === 'source' || kind === 'lesson') {
                        setSubjectKind(kind)
                        setSubjectId(id ?? '')
                      }
                    }}
                  >
                    <option value="">Select a source or class</option>
                    {subjectOptions.map((row) => (
                      <option key={`${row.kind}:${row.id}`} value={`${row.kind}:${row.id}`}>
                        {row.name} ({row.count})
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                type="button"
                className="study__btn study__btn--primary quiz__launch-cta"
                onClick={() => void begin()}
                disabled={mode === 'subject' && !subjectReady}
              >
                Start exam
              </button>
              {error ? <p className="quiz__score-note">{error}</p> : null}
            </div>
          </div>
        ) : null}

        {attempt && finished ? (
          <div className="quiz quiz--result quiz--result-center">
            <p className="quiz__score">
              {attempt.correct_count} of {attempt.question_count} correct
            </p>
            <p className="quiz__score-note">
              +{apGained} AP
              {masteredCount > 0 ? ` · ${masteredCount} newly mastered` : ''}
            </p>
            {misses.length > 0 ? (
              <ul className="quiz__misses">
                {misses.map((miss) => (
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
            <button type="button" className="study__btn" onClick={reset}>
              <RotateCcw size={16} /> New exam
            </button>
          </div>
        ) : null}

        {attempt && !finished && current ? (
          <>
            <StudyPanel
              fullscreen={fullscreen}
              onToggleFullscreen={toggle}
              meta={
                <span className="pill">
                  {attempt.exam_type === 'full_practice' ? 'Full Exam' : attempt.subject_name || 'Subject'}
                </span>
              }
              progress={{ current: index + 1, total: questions.length }}
              pager={{
                onPrev: prev,
                onNext: () => void next(),
                prevDisabled: index <= 0 || submitting,
                nextDisabled: !revealed,
                label: isLast && revealed ? 'Finish' : current.subject_name || 'Next',
              }}
            >
              <div className="quiz quiz--prompt" style={{ position: 'relative' }}>
                {floatLabel !== null ? (
                  <CorrectBurst key={current.quiz_id} label={floatLabel} mastery={Boolean(feedback?.newly_mastered)} />
                ) : null}
                {feedback?.newly_mastered ? (
                  <p className="ap-mastery-banner">Concept mastered · +3 bonus</p>
                ) : null}
                {picture ? <AssessmentPicture visual={picture} text={current.question} /> : null}
                <p className="quiz__question">{current.question}</p>
                <ChoiceOptions
                  options={current.options}
                  multiple={multiple}
                  picked={picked}
                  revealed={revealed}
                  submitting={submitting}
                  correctOptions={answerLabels(feedback?.correct_options, feedback?.right_answer)}
                  onPick={choose}
                  onCheck={() => void submitChoice(picked)}
                />
                {revealed && feedback?.explanation ? (
                  <p className="quiz__explain">
                    <Info size={15} /> {feedback.explanation}
                  </p>
                ) : null}
                {error ? <p className="quiz__score-note">{error}</p> : null}
              </div>
            </StudyPanel>
            <StudySourceReference
              sourceId={current.subject_kind === 'source' ? (current.subject_id ?? null) : null}
              sourceName={current.subject_name ?? 'Subject'}
            />
          </>
        ) : null}
      </div>
    </section>
  )
}
