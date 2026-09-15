import { useMemo, useState } from 'react'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { formatDate } from '../../lib/foundryFormat'
import type { AcademyPage, AcademyScope } from '../academy/types'
import { FoundryViewToggle } from './FoundryViewToggle'
import { ErrorBanner } from './ErrorBanner'
import type { FoundryView } from './types'

function AssessmentCardFoot({
  createdAt,
  difficulty,
  onOpen,
}: {
  createdAt: string
  difficulty: string
  onOpen: () => void
}) {
  return (
    <div className="as-console__artifact-foot">
      <span className="seg">{formatDate(createdAt)}</span>
      <span className="seg">{difficulty}</span>
      <span className="seg">
        <button
          type="button"
          className="as-console__statepill as-state--download"
          onClick={onOpen}
        >
          Open
        </button>
      </span>
    </div>
  )
}

export function FoundryAssessments({
  onOpen,
}: {
  onOpen: (page: AcademyPage, scope: AcademyScope) => void
}) {
  const { flashcards, quizzes, scenarios, isLoading, error } = useWorkspaceData()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<FoundryView>('grid')

  const totalCount = flashcards.length + quizzes.length + scenarios.length

  const filteredFlashcards = useMemo(() => {
    const q = query.toLowerCase()
    return flashcards.filter(
      (card) => card.front.toLowerCase().includes(q) || card.back.toLowerCase().includes(q),
    )
  }, [flashcards, query])

  const filteredQuizzes = useMemo(() => {
    const q = query.toLowerCase()
    return quizzes.filter((quiz) => quiz.question.toLowerCase().includes(q))
  }, [quizzes, query])

  const filteredScenarios = useMemo(() => {
    const q = query.toLowerCase()
    return scenarios.filter(
      (scenario) =>
        scenario.title.toLowerCase().includes(q) || scenario.prompt.toLowerCase().includes(q),
    )
  }, [scenarios, query])

  const filteredCount =
    filteredFlashcards.length + filteredQuizzes.length + filteredScenarios.length

  return (
    <>
      <header className="as-console__header">
        <div>
          <div className="as-console__eyebrow">Assessment Bank</div>
          <h2>QnGen Outputs</h2>
        </div>
        <FoundryViewToggle view={view} onChange={setView} />
      </header>
      <div className="as-console__scroll">
        {error ? <ErrorBanner message={error} /> : null}
        <div className="as-console__searchbar">
          <span style={{ color: '#6f828b' }}>⌕</span>
          <input
            placeholder="Search flashcards, quizzes, and scenarios…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span className="as-count">{filteredCount} items</span>
        </div>
        {isLoading && totalCount === 0 ? (
          <div className="as-console__empty">Loading assessments…</div>
        ) : totalCount === 0 ? (
          <div className="as-console__empty">
            No assessments yet. Upload a source, run Wiki Knowledge (and review
            targets) from OPS, then open entries in Academy Library.
          </div>
        ) : (
          <>
            {filteredFlashcards.length > 0 ? (
              <section className="as-console__panel" style={{ marginBottom: 'var(--space-5)' }}>
                <div className="as-console__panel-head">
                  <h3>Flashcards</h3>
                  <span className="as-count">{filteredFlashcards.length}</span>
                </div>
                {view === 'list' ? (
                  <table className="as-console__table">
                    <thead>
                      <tr>
                        <th>Front</th>
                        <th>Back</th>
                        <th>Subtype</th>
                        <th>Difficulty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredFlashcards.map((card) => (
                        <tr key={card.id}>
                          <td>{card.front}</td>
                          <td>{card.back}</td>
                          <td>{card.subtype ?? 'basic'}</td>
                          <td>{card.difficulty}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="as-console__sources">
                    {filteredFlashcards.map((card) => (
                      <div className="as-console__panel as-console__artifact-card" key={card.id} style={{ padding: 18 }}>
                        <div style={{ fontWeight: 600, color: '#fff' }}>{card.front}</div>
                        <p style={{ fontSize: '0.84rem', color: '#b6c4cb', marginTop: 8 }}>{card.back}</p>
                        <div className="as-console__card-fill" aria-hidden="true" />
                        <AssessmentCardFoot
                          createdAt={card.created_at}
                          difficulty={card.difficulty}
                          onOpen={() =>
                            onOpen('flashcards', {
                              sourceId: card.source_id ?? null,
                              targetId: card.id,
                            })
                          }
                        />
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {filteredQuizzes.length > 0 ? (
              <section className="as-console__panel" style={{ marginBottom: 'var(--space-5)' }}>
                <div className="as-console__panel-head">
                  <h3>Quizzes</h3>
                  <span className="as-count">{filteredQuizzes.length}</span>
                </div>
                {view === 'list' ? (
                  <table className="as-console__table">
                    <thead>
                      <tr>
                        <th>Question</th>
                        <th>Type</th>
                        <th>Difficulty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredQuizzes.map((quiz) => (
                        <tr key={quiz.id}>
                          <td>{quiz.question}</td>
                          <td>{quiz.subtype ?? quiz.question_type}</td>
                          <td>{quiz.difficulty}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="as-console__sources">
                    {filteredQuizzes.map((quiz) => (
                      <div className="as-console__panel as-console__artifact-card" key={quiz.id} style={{ padding: 18 }}>
                        <div style={{ fontWeight: 600, color: '#fff' }}>{quiz.question}</div>
                        <p style={{ fontSize: '0.84rem', color: '#b6c4cb', marginTop: 8 }}>
                          {quiz.explanation ?? quiz.correct_answer}
                        </p>
                        <div className="as-console__card-fill" aria-hidden="true" />
                        <AssessmentCardFoot
                          createdAt={quiz.created_at}
                          difficulty={quiz.difficulty}
                          onOpen={() =>
                            onOpen('quiz', {
                              sourceId: quiz.source_id ?? null,
                              targetId: quiz.id,
                            })
                          }
                        />
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {filteredScenarios.length > 0 ? (
              <section className="as-console__panel">
                <div className="as-console__panel-head">
                  <h3>Scenarios</h3>
                  <span className="as-count">{filteredScenarios.length}</span>
                </div>
                {view === 'list' ? (
                  <table className="as-console__table">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Prompt</th>
                        <th>Subtype</th>
                        <th>Difficulty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredScenarios.map((scenario) => (
                        <tr key={scenario.id}>
                          <td>{scenario.title}</td>
                          <td>{scenario.prompt}</td>
                          <td>{scenario.subtype ?? 'decision_prompt'}</td>
                          <td>{scenario.difficulty}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="as-console__sources">
                    {filteredScenarios.map((scenario) => (
                      <div className="as-console__panel as-console__artifact-card" key={scenario.id} style={{ padding: 18 }}>
                        <div style={{ fontWeight: 600, color: '#fff' }}>{scenario.title}</div>
                        <p style={{ fontSize: '0.84rem', color: '#b6c4cb', marginTop: 8 }}>{scenario.prompt}</p>
                        <div className="as-console__card-fill" aria-hidden="true" />
                        <AssessmentCardFoot
                          createdAt={scenario.created_at}
                          difficulty={scenario.difficulty}
                          onOpen={() =>
                            onOpen('scenarios', {
                              sourceId: scenario.source_id ?? null,
                              targetId: scenario.id,
                            })
                          }
                        />
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {filteredCount === 0 && query ? (
              <div className="as-console__empty">No assessments match your search.</div>
            ) : null}
          </>
        )}
      </div>
    </>
  )
}
