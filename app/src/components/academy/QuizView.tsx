import { Check, Info, RotateCcw, X } from 'lucide-react'
import { useMemo, useState } from 'react'
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
import { showsStemImage } from '../../lib/assessmentVisual'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import { useLessons } from '../../lib/useLessons'
import { AssessmentPicture } from './AssessmentPicture'
import { StudyHead, StudyPanel, StudySourceReference } from './StudySessionChrome'
import { useStudyFullscreen } from './useStudyFullscreen'

type Mode = 'full_practice' | 'subject'
type Miss = { quizId: string; question: string; selected: string; answer: string }

export function QuizView(_legacyLibraryScope?: {
  sourceId?: string | null
  targetId?: string | null
  projectId?: string | null
  batchKey?: string | null
}) {
  void _legacyLibraryScope
  const { activeWorkspace } = useWorkspace()
  const { quizzes, sources } = useWorkspaceData()
  const { lessons } = useLessons(activeWorkspace?.id ?? null)
  const { setLifetimeAp } = useAtlas()
  const { fullscreen, toggle } = useStudyFullscreen()

  const [mode, setMode] = useState<Mode>('full_practice')
  const [subjectKind, setSubjectKind] = useState<SubjectKind>('source')
  const [subjectId, setSubjectId] = useState('')
  const [attempt, setAttempt] = useState<ExamAttempt | null>(null)
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [feedback, setFeedback] = useState<AnswerSubmitResult | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)
  const [misses, setMisses] = useState<Miss[]>([])
  const [apGained, setApGained] = useState(0)
  const [masteredCount, setMasteredCount] = useState(0)
  const [floatLabel, setFloatLabel] = useState<string | null>(null)

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

  const questions = attempt?.questions ?? []
  const current: ExamQuestion | null = questions[index] ?? null
  const revealed = selected !== null && feedback !== null
  const isLast = index >= questions.length - 1

  const begin = async () => {
    if (!activeWorkspace) return
    setError(null)
    setFinished(false)
    setMisses([])
    setApGained(0)
    setMasteredCount(0)
    setFeedback(null)
    setSelected(null)
    setIndex(0)
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

  const choose = async (optionIndex: number) => {
    if (!activeWorkspace || !attempt || !current || selected !== null || submitting) return
    setSubmitting(true)
    setSelected(optionIndex)
    try {
      const result = await submitExamAnswer(activeWorkspace.id, attempt.id, {
        quiz_id: current.quiz_id,
        question: current.question,
        options: current.options,
        selected_index: optionIndex,
      })
      setFeedback(result)
      setLifetimeAp(result.lifetime_ap)
      setApGained((value) => value + result.points_total)
      if (result.newly_mastered) setMasteredCount((value) => value + 1)
      if (result.points_total > 0) {
        setFloatLabel(result.newly_mastered ? `Mastered · +${result.points_total} AP` : `+${result.points_total} AP`)
        window.setTimeout(() => setFloatLabel(null), 900)
      }
      if (!result.correct) {
        setMisses((rows) => [
          ...rows,
          {
            quizId: current.quiz_id,
            question: current.question,
            selected: current.options[optionIndex] ?? '',
            answer: result.right_answer,
          },
        ])
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not submit that answer.')
      setSelected(null)
    } finally {
      setSubmitting(false)
    }
  }

  const next = async () => {
    if (!revealed || !activeWorkspace || !attempt) return
    if (isLast) {
      try {
        const done = await completeExam(activeWorkspace.id, attempt.id)
        setAttempt(done)
        setFinished(true)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Could not finish the exam.')
      }
      return
    }
    setIndex((value) => value + 1)
    setSelected(null)
    setFeedback(null)
  }

  const reset = () => {
    setAttempt(null)
    setFinished(false)
    setIndex(0)
    setSelected(null)
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

      <div className="study-stage">
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
                    value={subjectId ? `${subjectKind}:${subjectId}` : ''}
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
                disabled={mode === 'subject' && !subjectId}
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
                onPrev: () => undefined,
                onNext: () => void next(),
                prevDisabled: true,
                nextDisabled: !revealed,
                label: isLast && revealed ? 'Finish' : current.subject_name || 'Next',
              }}
            >
              <div className="quiz quiz--prompt" style={{ position: 'relative' }}>
                {floatLabel ? (
                  <span className={`ap-float${feedback?.newly_mastered ? ' ap-float--mastery' : ''}`}>
                    {floatLabel}
                  </span>
                ) : null}
                {feedback?.newly_mastered ? (
                  <p className="ap-mastery-banner">Concept mastered · +3 bonus</p>
                ) : null}
                {current.visual &&
                typeof current.visual.url === 'string' &&
                showsStemImage(String(current.visual.placement ?? '')) ? (
                  <AssessmentPicture
                    visual={current.visual as { url: string; placement?: string | null }}
                    text={current.question}
                  />
                ) : null}
                <p className="quiz__question">{current.question}</p>
                <div className="quiz__options">
                  {current.options.map((opt, optionIndex) => {
                    let cls = 'quiz__option'
                    const isCorrect = revealed && feedback?.right_answer === opt
                    const isWrong = revealed && optionIndex === selected && !feedback?.correct
                    if (isCorrect) cls += ' is-correct'
                    else if (isWrong) cls += ' is-wrong'
                    return (
                      <button
                        key={`${current.quiz_id}-${optionIndex}`}
                        type="button"
                        className={cls}
                        disabled={revealed || submitting}
                        onClick={() => void choose(optionIndex)}
                      >
                        <span className="quiz__option-text">{opt}</span>
                        {isCorrect ? (
                          <span className="quiz__option-status">
                            <Check size={16} /> Correct
                          </span>
                        ) : null}
                        {isWrong ? (
                          <span className="quiz__option-status">
                            <X size={16} /> Incorrect
                          </span>
                        ) : null}
                      </button>
                    )
                  })}
                </div>
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
