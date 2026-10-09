import { ChevronLeft, ChevronRight, Shuffle, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { drawOptions, emptyPool, hasPool, type AnswerPool } from '../../../lib/answerPool'
import { cardFace } from '../../../lib/assessmentVisual'
import {
  deleteKnowledgeItem,
  duplicateKnowledgeItem,
  deletePlanVisual,
  generateKnowledgeBatch,
  generateKnowledgeVariants,
  makeKnowledgeFlashcards,
  saveKnowledgeFlashcard,
  saveKnowledgeQuestion,
  saveKnowledgeScenario,
  updateKnowledgePlan,
  updateKnowledgeProject,
  uploadPlanVisual,
  type ItemKind,
  type KnowledgeEntry,
  type KnowledgeProjectDetail,
  type KnowledgeQuestion,
  type KnowledgeScenario,
} from '../../../lib/knowledgeApi'

export type DesignStep = 'flashcards' | 'questions' | 'scenarios'

const STEPS: { value: DesignStep; label: string }[] = [
  { value: 'flashcards', label: 'Flashcards' },
  { value: 'questions', label: 'Questions' },
  { value: 'scenarios', label: 'Scenarios' },
]
const CARD_LAYOUTS = [
  { value: 'label_description', label: 'Label and description' },
  { value: 'image_label', label: 'Image and label' },
  { value: 'image_label_description', label: 'Image, label, and description' },
] as const
const QUESTION_FORMATS = [
  { value: 'multiple_choice', label: 'Multiple choice' },
  { value: 'true_false_correction', label: 'True or false, with a correction' },
  { value: 'multiple_select', label: 'Multiple select' },
] as const
const SCENARIO_FORMATS = [
  { value: 'decision_prompt', label: 'Decision' },
  { value: 'rubric_response', label: 'Rubric response' },
] as const
const BLOOM_LEVELS = [
  { value: '', label: 'Any level' },
  { value: 'remember', label: 'Remember' },
  { value: 'understand', label: 'Understand' },
  { value: 'apply', label: 'Apply' },
  { value: 'analyze', label: 'Analyze' },
] as const
const DIFFICULTIES = ['easy', 'medium', 'hard'] as const
const IMAGE_LAYOUTS = new Set(['image_label', 'image_label_description'])
const PLACEMENT_FOR_LAYOUT: Record<string, string> = {
  image_label: 'front',
  image_label_description: 'front_with_label',
}

type Option = { readonly value: string; readonly label: string }
/** Run a project mutation, report failures, and resolve true when it succeeded. */
type Act = (task: () => Promise<KnowledgeProjectDetail>, fallback: string) => Promise<boolean>

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

function categoryOf(entry: KnowledgeEntry): string {
  return entry.category?.trim() || 'Uncategorized'
}

function isDone(entry: KnowledgeEntry, step: DesignStep): boolean {
  if (step === 'flashcards') return entry.flashcard !== null
  if (step === 'questions') return entry.questions.length > 0
  return entry.scenarios.length > 0
}

function description(entry: KnowledgeEntry): string {
  const definition = entry.definition.trim()
  const significance = entry.significance?.trim() ?? ''
  if (definition && significance) return `${definition}\n\n${significance}`
  return definition || significance
}

function defaultSides(entry: KnowledgeEntry): { front: string; back: string } {
  if (entry.layout === 'image_label') return { front: entry.preferred_label, back: entry.preferred_label }
  return { front: entry.preferred_label, back: description(entry) }
}

export function KnowledgeComposer({
  project,
  onChange,
  onError,
}: {
  project: KnowledgeProjectDetail
  onChange: (project: KnowledgeProjectDetail) => void
  onError: (message: string) => void
}) {
  const [step, setStep] = useState<DesignStep>('flashcards')
  const [index, setIndex] = useState(0)
  const [isBusy, setIsBusy] = useState(false)
  const [showBatch, setShowBatch] = useState(false)

  const entries = useMemo(
    () =>
      [...project.entries].sort(
        (a, b) =>
          categoryOf(a).localeCompare(categoryOf(b)) || a.preferred_label.localeCompare(b.preferred_label),
      ),
    [project.entries],
  )
  const safeIndex = Math.min(index, Math.max(entries.length - 1, 0))
  const entry = entries[safeIndex]
  const doneCount = entries.filter((row) => isDone(row, step)).length

  const act: Act = async (task, fallback) => {
    setIsBusy(true)
    try {
      onChange(await task())
      return true
    } catch (caught) {
      onError(errorMessage(caught, fallback))
      return false
    } finally {
      setIsBusy(false)
    }
  }

  const goTo = (next: number) => setIndex(Math.max(0, Math.min(entries.length - 1, next)))

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      if (event.key === '[') goTo(safeIndex - 1)
      if (event.key === ']') goTo(safeIndex + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (!entry) {
    return <p className="dsn-hint">No entries were written.</p>
  }

  const categories = [...new Set(entries.map(categoryOf))]
  const category = categoryOf(entry)
  const kind: ItemKind | null = step === 'questions' ? 'question' : step === 'scenarios' ? 'scenario' : null

  return (
    <div className="kcomp">
      <div className="kcomp__top">
        <div className="kproj-switch" role="tablist" aria-label="Design steps">
          {STEPS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={step === option.value}
              className={step === option.value ? 'is-active' : ''}
              onClick={() => {
                setStep(option.value)
                setShowBatch(false)
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="kcomp__top-actions">
          {step === 'flashcards' ? (
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              disabled={isBusy || !entries.some((row) => row.enabled)}
              onClick={() => void act(() => makeKnowledgeFlashcards(project.id), 'Could not make the flashcards.')}
            >
              Make all flashcards
            </button>
          ) : (
            <button
              type="button"
              className="as-console__cta as-console__cta--ghost"
              aria-expanded={showBatch}
              onClick={() => setShowBatch((value) => !value)}
            >
              Batch this category
            </button>
          )}
        </div>
      </div>

      {kind && showBatch ? (
        <BatchPanel
          key={`${kind}-${category}`}
          kind={kind}
          category={category}
          count={entries.filter((row) => categoryOf(row) === category).length}
          busy={isBusy}
          onGenerate={(input) => act(() => generateKnowledgeBatch(project.id, input), 'Could not generate this batch.')}
        />
      ) : null}

      <header className="kcomp__head">
        <div className="kcomp__title">
          <h3>{entry.preferred_label}</h3>
          <span className="kproj-entry__meta">
            {entry.entry_kind} · {entry.importance} · {category}
            {isDone(entry, step) ? ' · saved' : ''}
          </span>
        </div>
        <nav className="kcomp__nav" aria-label="Entries">
          <button type="button" className="kcomp__nav-btn" onClick={() => goTo(safeIndex - 1)} disabled={safeIndex === 0}>
            <ChevronLeft size={16} /> Previous
          </button>
          <label className="kcomp__jump">
            <span className="kcomp__count">
              {safeIndex + 1} of {entries.length} · {doneCount} saved
            </span>
            <select
              className="as-wiki__input kproj-select"
              value={entry.plan_id}
              aria-label="Jump to entry"
              onChange={(event) => goTo(entries.findIndex((row) => row.plan_id === event.target.value))}
            >
              {categories.map((group) => (
                <optgroup key={group} label={group}>
                  {entries
                    .filter((row) => categoryOf(row) === group)
                    .map((row) => (
                      <option key={row.plan_id} value={row.plan_id}>
                        {isDone(row, step) ? '● ' : '○ '}
                        {row.preferred_label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="kcomp__nav-btn"
            onClick={() => goTo(safeIndex + 1)}
            disabled={safeIndex >= entries.length - 1}
          >
            Next <ChevronRight size={16} />
          </button>
        </nav>
      </header>

      <div className="kcomp__grid">
        <SourcePane entry={entry} />
        {step === 'flashcards' ? (
          <FlashcardPass key={entry.plan_id} projectId={project.id} entry={entry} busy={isBusy} act={act} />
        ) : step === 'questions' ? (
          <QuestionPass key={entry.plan_id} project={project} entry={entry} busy={isBusy} act={act} />
        ) : (
          <ScenarioPass key={entry.plan_id} project={project} entry={entry} busy={isBusy} act={act} />
        )}
      </div>
    </div>
  )
}

function SourcePane({ entry }: { entry: KnowledgeEntry }) {
  return (
    <section className="kcomp__pane kcomp__source" aria-label="Source material">
      <h4 className="kcomp__pane-title">Source</h4>
      <p>{entry.definition}</p>
      {entry.significance ? <p>{entry.significance}</p> : null}
      {entry.entry_kind === 'list' && entry.items.length ? (
        <ol className="kproj-entry__items">
          {entry.items.map((item) => (
            <li key={item.name}>
              {item.name}
              {item.details ? ` — ${item.details}` : ''}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="kcomp__field">
      <span>{label}</span>
      {children}
    </label>
  )
}

function Select({
  value,
  options,
  onChange,
  disabled,
}: {
  value: string
  options: readonly Option[]
  onChange: (value: string) => void
  disabled?: boolean
}) {
  return (
    <select className="as-wiki__input kproj-select" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

// ---------------------------------------------------------------------------
// Flashcards pass
// ---------------------------------------------------------------------------

function FlashcardPass({
  projectId,
  entry,
  busy,
  act,
}: {
  projectId: string
  entry: KnowledgeEntry
  busy: boolean
  act: Act
}) {
  const initial = entry.flashcard ?? defaultSides(entry)
  const [front, setFront] = useState(initial.front)
  const [back, setBack] = useState(initial.back)
  const [alt, setAlt] = useState(entry.visual?.alt ?? '')
  const needsImage = IMAGE_LAYOUTS.has(entry.layout)
  const placement = PLACEMENT_FOR_LAYOUT[entry.layout]

  const upload = (file: File) =>
    void act(
      () => uploadPlanVisual(projectId, entry.plan_id, { file, kind: 'diagram', placement: placement ?? 'back', alt }),
      'Could not upload the image.',
    )

  return (
    <>
      <section className="kcomp__pane kcomp__item" aria-label="Flashcard">
        <h4 className="kcomp__pane-title">Card</h4>
        <div className="kcomp__faces">
          <CardFacePreview side="front" text={front} placement={needsImage ? placement : null} visual={entry.visual} label={entry.preferred_label} />
          <CardFacePreview side="back" text={back} placement={needsImage ? placement : null} visual={entry.visual} label={entry.preferred_label} />
        </div>
        <Field label="Front">
          <textarea className="as-wiki__input" rows={2} value={front} onChange={(event) => setFront(event.target.value)} />
        </Field>
        <Field label="Back">
          <textarea className="as-wiki__input" rows={5} value={back} onChange={(event) => setBack(event.target.value)} />
        </Field>
        <div className="kcomp__actions">
          <button
            type="button"
            className="as-console__cta"
            disabled={busy || !front.trim() || !back.trim()}
            onClick={() => void act(() => saveKnowledgeFlashcard(projectId, entry.plan_id, { front, back }), 'Could not save the card.')}
          >
            {entry.flashcard ? 'Save card' : 'Make card'}
          </button>
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            disabled={busy}
            onClick={() => {
              const sides = defaultSides(entry)
              setFront(sides.front)
              setBack(sides.back)
            }}
          >
            Reset to wiki text
          </button>
        </div>
      </section>

      <section className="kcomp__pane kcomp__controls" aria-label="Card settings">
        <h4 className="kcomp__pane-title">Settings</h4>
        <label className="kcomp__check">
          <input
            type="checkbox"
            checked={entry.enabled}
            disabled={busy}
            onChange={(event) =>
              void act(() => updateKnowledgePlan(projectId, entry.plan_id, { enabled: event.target.checked }), 'Could not update the card.')
            }
          />
          Include in "Make all flashcards"
        </label>
        <Field label="Layout">
          <Select
            value={entry.layout}
            options={CARD_LAYOUTS}
            disabled={busy}
            onChange={(layout) => void act(() => updateKnowledgePlan(projectId, entry.plan_id, { layout }), 'Could not update the layout.')}
          />
        </Field>
        <Field label="Alt text">
          <input className="as-wiki__input" value={alt} onChange={(event) => setAlt(event.target.value)} placeholder="Optional" />
        </Field>
        <Field label={entry.visual ? 'Replace image' : 'Image'}>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) upload(file)
            }}
          />
        </Field>
        {entry.visual ? (
          <button
            type="button"
            className="as-console__cta as-console__cta--ghost"
            disabled={busy}
            onClick={() => void act(() => deletePlanVisual(projectId, entry.plan_id), 'Could not remove the image.')}
          >
            Remove image
          </button>
        ) : null}
        {needsImage && !entry.visual ? <p className="dsn-hint">This layout needs an image before the card can be made.</p> : null}
      </section>
    </>
  )
}

function CardFacePreview({
  side,
  text,
  placement,
  visual,
  label,
}: {
  side: 'front' | 'back'
  text: string
  placement: string | null | undefined
  visual: KnowledgeEntry['visual']
  label: string
}) {
  const face = placement ? cardFace(side, placement) : 'text'
  const showImage = face !== 'text' && visual?.url
  const showText = face !== 'image' || !visual?.url
  return (
    <div className="kcomp__face">
      <span className="kcomp__face-label">{side}</span>
      {showImage ? <img src={visual.url ?? undefined} alt={visual.alt || label} /> : null}
      {showText ? <p>{text || '—'}</p> : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared generation controls (questions and scenarios)
// ---------------------------------------------------------------------------

function GenerateControls({
  project,
  entry,
  kind,
  busy,
  act,
}: {
  project: KnowledgeProjectDetail
  entry: KnowledgeEntry
  kind: ItemKind
  busy: boolean
  act: Act
}) {
  const formats: readonly Option[] = kind === 'question' ? QUESTION_FORMATS : SCENARIO_FORMATS
  const category = categoryOf(entry)
  const [count, setCount] = useState(kind === 'question' ? 3 : 1)
  const [mix, setMix] = useState<'same' | 'spread'>(kind === 'question' ? 'spread' : 'same')
  const [format, setFormat] = useState<string>(formats[0].value)
  const [bloom, setBloom] = useState('')
  const [instructions, setInstructions] = useState(entry.instructions)
  const [categoryNote, setCategoryNote] = useState(project.batch_instructions?.[category] ?? '')
  const maxCount = kind === 'question' ? 5 : 3

  return (
    <section className="kcomp__pane kcomp__controls" aria-label="Generation settings">
      <h4 className="kcomp__pane-title">Generate</h4>
      <div className="kcomp__row">
        <Field label="How many">
          <input
            className="as-wiki__input"
            type="number"
            min={1}
            max={maxCount}
            value={count}
            onChange={(event) => setCount(Math.max(1, Math.min(maxCount, Number(event.target.value) || 1)))}
          />
        </Field>
        {kind === 'question' ? (
          <Field label="Mix">
            <Select
              value={mix}
              options={[
                { value: 'spread', label: 'Spread formats and levels' },
                { value: 'same', label: 'Same format and level' },
              ]}
              onChange={(value) => setMix(value === 'spread' ? 'spread' : 'same')}
            />
          </Field>
        ) : null}
      </div>
      {kind === 'scenario' || mix === 'same' ? (
        <div className="kcomp__row">
          <Field label="Format">
            <Select value={format} options={formats} onChange={setFormat} />
          </Field>
          <Field label="Cognitive level">
            <Select value={bloom} options={BLOOM_LEVELS} onChange={setBloom} />
          </Field>
        </div>
      ) : (
        <p className="dsn-hint">Spread rotates multiple choice, true/false, and multiple select across remember, understand, and apply.</p>
      )}
      <Field label="Instructions for this entry">
        <textarea
          className="as-wiki__input"
          rows={3}
          value={instructions}
          placeholder="Optional. What to probe, what to avoid."
          onChange={(event) => setInstructions(event.target.value)}
          onBlur={() => {
            if (instructions.trim() === entry.instructions.trim()) return
            void act(() => updateKnowledgePlan(project.id, entry.plan_id, { instructions }), 'Could not save the instructions.')
          }}
        />
      </Field>
      <Field label={`Instructions for ${category}`}>
        <textarea
          className="as-wiki__input"
          rows={3}
          value={categoryNote}
          placeholder="Optional. Applies to every entry in this category."
          onChange={(event) => setCategoryNote(event.target.value)}
          onBlur={() => {
            if (categoryNote.trim() === (project.batch_instructions?.[category] ?? '').trim()) return
            void act(
              () => updateKnowledgeProject(project.id, { batch_instructions: { [category]: categoryNote } }),
              'Could not save the category instructions.',
            )
          }}
        />
      </Field>
      <button
        type="button"
        className="as-console__cta"
        disabled={busy}
        onClick={() =>
          void act(
            () =>
              generateKnowledgeVariants(project.id, {
                kind,
                wiki_entry_id: entry.wiki_entry_id,
                format,
                count,
                mix: kind === 'question' ? mix : 'same',
                bloom_level: bloom,
                instructions,
              }),
            `Could not generate ${kind}s.`,
          )
        }
      >
        {busy ? 'Generating…' : `Generate ${count} ${kind}${count === 1 ? '' : 's'}`}
      </button>
    </section>
  )
}

function BatchPanel({
  kind,
  category,
  count,
  busy,
  onGenerate,
}: {
  kind: ItemKind
  category: string
  count: number
  busy: boolean
  onGenerate: (input: Parameters<typeof generateKnowledgeBatch>[1]) => Promise<boolean>
}) {
  const formats: readonly Option[] = kind === 'question' ? QUESTION_FORMATS : SCENARIO_FORMATS
  const [perEntry, setPerEntry] = useState(1)
  const [format, setFormat] = useState<string>(formats[0].value)
  const [bloom, setBloom] = useState('')
  const [mode, setMode] = useState<'append' | 'replace'>('append')
  const [instructions, setInstructions] = useState('')

  return (
    <section className="kcomp__batch" aria-label="Category batch">
      <div className="kcomp__batch-head">
        <strong>{category}</strong>
        <span className="kproj-entry__meta">{count} entries</span>
      </div>
      <div className="kcomp__row">
        <Field label="Per entry">
          <input
            className="as-wiki__input"
            type="number"
            min={1}
            max={3}
            value={perEntry}
            onChange={(event) => setPerEntry(Math.max(1, Math.min(3, Number(event.target.value) || 1)))}
          />
        </Field>
        <Field label="Format">
          <Select value={format} options={formats} onChange={setFormat} />
        </Field>
        <Field label="Cognitive level">
          <Select value={bloom} options={BLOOM_LEVELS} onChange={setBloom} />
        </Field>
        <Field label="Existing items">
          <Select
            value={mode}
            options={[
              { value: 'append', label: 'Keep and add' },
              { value: 'replace', label: 'Replace' },
            ]}
            onChange={(value) => setMode(value === 'replace' ? 'replace' : 'append')}
          />
        </Field>
      </div>
      <Field label="Instructions">
        <textarea
          className="as-wiki__input"
          rows={2}
          value={instructions}
          placeholder="Optional. What this batch should emphasize."
          onChange={(event) => setInstructions(event.target.value)}
        />
      </Field>
      <button
        type="button"
        className="as-console__cta"
        disabled={busy}
        onClick={() => void onGenerate({ kind, category, format, instructions, per_entry: perEntry, bloom_level: bloom, mode })}
      >
        {busy ? 'Generating…' : `Generate for ${category}`}
      </button>
    </section>
  )
}

function VariantStrip({
  count,
  active,
  onSelect,
  onAdd,
  onDuplicate,
  onDelete,
  busy,
  noun,
}: {
  count: number
  active: number
  onSelect: (index: number) => void
  onAdd: () => void
  onDuplicate: () => void
  onDelete: () => void
  busy: boolean
  noun: string
}) {
  if (count === 0) return null
  return (
    <div className="kcomp__variants" role="tablist" aria-label={`${noun} variants`}>
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          type="button"
          role="tab"
          aria-selected={i === active}
          className={i === active ? 'kcomp__variant is-active' : 'kcomp__variant'}
          onClick={() => onSelect(i)}
        >
          {i + 1}
        </button>
      ))}
      <span className="kcomp__count">
        Variant {active + 1} of {count}
      </span>
      <button type="button" className="kcomp__text-btn" disabled={busy} onClick={onAdd}>
        Add
      </button>
      <button type="button" className="kcomp__text-btn" disabled={busy} onClick={onDuplicate}>
        Duplicate
      </button>
      <button type="button" className="kcomp__icon-btn" aria-label={`Delete this ${noun}`} disabled={busy} onClick={onDelete}>
        <Trash2 size={15} />
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Questions pass
// ---------------------------------------------------------------------------

function QuestionPass({
  project,
  entry,
  busy,
  act,
}: {
  project: KnowledgeProjectDetail
  entry: KnowledgeEntry
  busy: boolean
  act: Act
}) {
  const [active, setActive] = useState(0)
  const variants = entry.questions
  const safeActive = Math.min(active, Math.max(variants.length - 1, 0))
  const question = variants[safeActive]

  return (
    <>
      <section className="kcomp__pane kcomp__item" aria-label="Question">
        <h4 className="kcomp__pane-title">Question</h4>
        <VariantStrip
          count={variants.length}
          active={safeActive}
          onSelect={setActive}
          busy={busy}
          noun="question"
          onAdd={() =>
            void act(
              () =>
                generateKnowledgeVariants(project.id, {
                  kind: 'question',
                  wiki_entry_id: entry.wiki_entry_id,
                  format: question?.subtype || 'multiple_choice',
                  count: 1,
                  mix: 'same',
                  bloom_level: question?.bloom_level || '',
                  instructions: entry.instructions,
                }),
              'Could not add a question.',
            )
          }
          onDuplicate={() => {
            if (!question) return
            void act(() => duplicateKnowledgeItem(project.id, question.plan_id), 'Could not duplicate the question.')
          }}
          onDelete={() => {
            if (!question) return
            void act(() => deleteKnowledgeItem(project.id, question.plan_id), 'Could not delete the question.')
            setActive(Math.max(0, safeActive - 1))
          }}
        />
        {question ? (
          <QuestionEditor key={question.plan_id} projectId={project.id} question={question} busy={busy} act={act} />
        ) : (
          <p className="dsn-hint">No questions yet for {entry.preferred_label}. Generate some on the right, or batch the category.</p>
        )}
      </section>
      <GenerateControls project={project} entry={entry} kind="question" busy={busy} act={act} />
    </>
  )
}

interface QuestionDraft {
  question: string
  format: string
  bloom: string
  difficulty: string
  explanation: string
  pool: AnswerPool
}

function questionDraft(question: KnowledgeQuestion): QuestionDraft {
  const saved = question.draft as Partial<QuestionDraft> | null
  const pool = hasPool(question.answer_pool)
    ? question.answer_pool
    : {
        correct: question.correct_answer ? [question.correct_answer] : [],
        distractors: question.options.filter((option) => option !== question.correct_answer).map((text) => ({ text, misconception: '' })),
        show_count: Math.max(2, question.options.length || 4),
      }
  return {
    question: saved?.question ?? question.question,
    format: saved?.format ?? question.subtype,
    bloom: saved?.bloom ?? question.bloom_level ?? '',
    difficulty: saved?.difficulty ?? question.difficulty,
    explanation: saved?.explanation ?? question.explanation ?? '',
    pool: saved?.pool ?? pool,
  }
}

/** Persist unsaved edits to the plan when the editor unmounts (navigation). */
function useDraftOnUnmount<T>(projectId: string, planId: string, draft: T, dirty: boolean) {
  const latest = useRef({ draft, dirty })
  latest.current = { draft, dirty }
  useEffect(
    () => () => {
      if (!latest.current.dirty) return
      void updateKnowledgePlan(projectId, planId, { draft: latest.current.draft as Record<string, unknown> }).catch(() => undefined)
    },
    [projectId, planId],
  )
}

function QuestionEditor({
  projectId,
  question,
  busy,
  act,
}: {
  projectId: string
  question: KnowledgeQuestion
  busy: boolean
  act: Act
}) {
  const [draft, setDraft] = useState<QuestionDraft>(() => questionDraft(question))
  const [dirty, setDirty] = useState(question.draft !== null)
  const [preview, setPreview] = useState<{ options: string[]; correct: string[]; question: string | null } | null>(null)
  useDraftOnUnmount(projectId, question.plan_id, draft, dirty)

  const update = (patch: Partial<QuestionDraft>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDirty(true)
    setPreview(null)
  }
  const isTrueFalse = draft.format === 'true_false_correction'

  return (
    <div className="kcomp__editor">
      {dirty ? <span className="kcomp__dirty">Unsaved edits</span> : null}
      <Field label={isTrueFalse ? 'Statement shown by default' : 'Question'}>
        <textarea className="as-wiki__input" rows={3} value={draft.question} onChange={(event) => update({ question: event.target.value })} />
      </Field>
      <div className="kcomp__row">
        <Field label="Format">
          <Select value={draft.format} options={QUESTION_FORMATS} onChange={(format) => update({ format })} />
        </Field>
        <Field label="Cognitive level">
          <Select value={draft.bloom} options={BLOOM_LEVELS} onChange={(bloom) => update({ bloom })} />
        </Field>
        <Field label="Difficulty">
          <Select
            value={draft.difficulty}
            options={DIFFICULTIES.map((value) => ({ value, label: value }))}
            onChange={(difficulty) => update({ difficulty })}
          />
        </Field>
      </div>
      <AnswerPoolEditor pool={draft.pool} trueFalse={isTrueFalse} onChange={(pool) => update({ pool })} />
      <Field label="Explanation">
        <textarea className="as-wiki__input" rows={3} value={draft.explanation} onChange={(event) => update({ explanation: event.target.value })} />
      </Field>
      {preview ? (
        <div className="kcomp__preview" aria-live="polite">
          <span className="kproj-entry__meta">Sample draw</span>
          {preview.question ? <p>{preview.question}</p> : null}
          <ol>
            {preview.options.map((option) => (
              <li key={option} className={preview.correct.includes(option) ? 'is-correct' : ''}>
                {option}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <div className="kcomp__actions">
        <button
          type="button"
          className="as-console__cta"
          disabled={busy}
          onClick={() =>
            void act(
              () =>
                saveKnowledgeQuestion(projectId, question.plan_id, {
                  question: draft.question,
                  format: draft.format,
                  answer_pool: draft.pool,
                  explanation: draft.explanation || null,
                  difficulty: draft.difficulty,
                  bloom_level: draft.bloom || null,
                }),
              'Could not save the question.',
            ).then((saved) => {
              if (saved) setDirty(false)
            })
          }
        >
          Save question
        </button>
        <button type="button" className="as-console__cta as-console__cta--ghost" onClick={() => setPreview(drawOptions(draft.pool, draft.format))}>
          <Shuffle size={15} /> Preview draw
        </button>
      </div>
    </div>
  )
}

function AnswerPoolEditor({
  pool,
  trueFalse,
  onChange,
}: {
  pool: AnswerPool
  trueFalse: boolean
  onChange: (pool: AnswerPool) => void
}) {
  const safe = pool ?? emptyPool()
  const setCorrect = (correct: string[]) => onChange({ ...safe, correct })
  const setDistractors = (distractors: AnswerPool['distractors']) => onChange({ ...safe, distractors })

  return (
    <div className="kcomp__pool">
      <div className="kcomp__pool-group">
        <div className="kcomp__pool-head">
          <span className="kcomp__pool-title">{trueFalse ? 'True statements' : 'Correct answers'}</span>
          <span className="dsn-hint">{trueFalse ? 'Any can be shown as the statement.' : 'One is drawn each time. Each must stand alone.'}</span>
        </div>
        {safe.correct.map((text, i) => (
          <div key={i} className="kcomp__pool-row">
            <input
              className="as-wiki__input"
              value={text}
              onChange={(event) => setCorrect(safe.correct.map((row, j) => (j === i ? event.target.value : row)))}
            />
            <button
              type="button"
              className="kcomp__icon-btn"
              aria-label="Remove correct answer"
              onClick={() => setCorrect(safe.correct.filter((_, j) => j !== i))}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button type="button" className="kcomp__add" onClick={() => setCorrect([...safe.correct, ''])}>
          + Add {trueFalse ? 'true statement' : 'phrasing'}
        </button>
      </div>

      <div className="kcomp__pool-group">
        <div className="kcomp__pool-head">
          <span className="kcomp__pool-title">{trueFalse ? 'False statements' : 'Distractors'}</span>
          <span className="dsn-hint">
            {trueFalse ? 'Note holds the correction.' : `${Math.max(0, safe.show_count - 1)} are drawn with the answer. Note why a learner would pick it.`}
          </span>
        </div>
        {safe.distractors.map((row, i) => (
          <div key={i} className="kcomp__pool-row kcomp__pool-row--distractor">
            <input
              className="as-wiki__input"
              value={row.text}
              placeholder="Wrong option"
              onChange={(event) => setDistractors(safe.distractors.map((d, j) => (j === i ? { ...d, text: event.target.value } : d)))}
            />
            <input
              className="as-wiki__input"
              value={row.misconception ?? ''}
              placeholder={trueFalse ? 'Correction' : 'Misconception'}
              onChange={(event) =>
                setDistractors(safe.distractors.map((d, j) => (j === i ? { ...d, misconception: event.target.value } : d)))
              }
            />
            <button
              type="button"
              className="kcomp__text-btn"
              title="Move to correct answers"
              onClick={() =>
                onChange({
                  ...safe,
                  correct: [...safe.correct, row.text],
                  distractors: safe.distractors.filter((_, j) => j !== i),
                })
              }
            >
              {trueFalse ? 'Is true' : 'Is correct'}
            </button>
            <button
              type="button"
              className="kcomp__icon-btn"
              aria-label="Remove distractor"
              onClick={() => setDistractors(safe.distractors.filter((_, j) => j !== i))}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button type="button" className="kcomp__add" onClick={() => setDistractors([...safe.distractors, { text: '', misconception: '' }])}>
          + Add {trueFalse ? 'false statement' : 'distractor'}
        </button>
      </div>

      {!trueFalse ? (
        <Field label="Options shown">
          <input
            className="as-wiki__input kcomp__narrow"
            type="number"
            min={2}
            max={8}
            value={safe.show_count}
            onChange={(event) => onChange({ ...safe, show_count: Math.max(2, Math.min(8, Number(event.target.value) || 4)) })}
          />
        </Field>
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Scenarios pass
// ---------------------------------------------------------------------------

function ScenarioPass({
  project,
  entry,
  busy,
  act,
}: {
  project: KnowledgeProjectDetail
  entry: KnowledgeEntry
  busy: boolean
  act: Act
}) {
  const [active, setActive] = useState(0)
  const variants = entry.scenarios
  const safeActive = Math.min(active, Math.max(variants.length - 1, 0))
  const scenario = variants[safeActive]

  return (
    <>
      <section className="kcomp__pane kcomp__item" aria-label="Scenario">
        <h4 className="kcomp__pane-title">Scenario</h4>
        <VariantStrip
          count={variants.length}
          active={safeActive}
          onSelect={setActive}
          busy={busy}
          noun="scenario"
          onAdd={() =>
            void act(
              () =>
                generateKnowledgeVariants(project.id, {
                  kind: 'scenario',
                  wiki_entry_id: entry.wiki_entry_id,
                  format: scenario?.subtype || 'decision_prompt',
                  count: 1,
                  mix: 'same',
                  bloom_level: scenario?.bloom_level || '',
                  instructions: entry.instructions,
                }),
              'Could not add a scenario.',
            )
          }
          onDuplicate={() => {
            if (!scenario) return
            void act(() => duplicateKnowledgeItem(project.id, scenario.plan_id), 'Could not duplicate the scenario.')
          }}
          onDelete={() => {
            if (!scenario) return
            void act(() => deleteKnowledgeItem(project.id, scenario.plan_id), 'Could not delete the scenario.')
            setActive(Math.max(0, safeActive - 1))
          }}
        />
        {scenario ? (
          <ScenarioEditor key={scenario.plan_id} projectId={project.id} scenario={scenario} busy={busy} act={act} />
        ) : (
          <p className="dsn-hint">No scenarios yet for {entry.preferred_label}. Generate some on the right, or batch the category.</p>
        )}
      </section>
      <GenerateControls project={project} entry={entry} kind="scenario" busy={busy} act={act} />
    </>
  )
}

interface ScenarioDraft {
  title: string
  context: string
  prompt: string
  criteria: string
  format: string
  bloom: string
  difficulty: string
}

function scenarioDraft(scenario: KnowledgeScenario): ScenarioDraft {
  const saved = scenario.draft as Partial<ScenarioDraft> | null
  return {
    title: saved?.title ?? scenario.title,
    context: saved?.context ?? scenario.context ?? '',
    prompt: saved?.prompt ?? scenario.prompt,
    criteria: saved?.criteria ?? scenario.evaluation_criteria.join('\n'),
    format: saved?.format ?? scenario.subtype,
    bloom: saved?.bloom ?? scenario.bloom_level ?? '',
    difficulty: saved?.difficulty ?? scenario.difficulty,
  }
}

function ScenarioEditor({
  projectId,
  scenario,
  busy,
  act,
}: {
  projectId: string
  scenario: KnowledgeScenario
  busy: boolean
  act: Act
}) {
  const [draft, setDraft] = useState<ScenarioDraft>(() => scenarioDraft(scenario))
  const [dirty, setDirty] = useState(scenario.draft !== null)
  useDraftOnUnmount(projectId, scenario.plan_id, draft, dirty)

  const update = (patch: Partial<ScenarioDraft>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDirty(true)
  }

  return (
    <div className="kcomp__editor">
      {dirty ? <span className="kcomp__dirty">Unsaved edits</span> : null}
      <Field label="Title">
        <input className="as-wiki__input" value={draft.title} onChange={(event) => update({ title: event.target.value })} />
      </Field>
      <Field label="Situation">
        <textarea className="as-wiki__input" rows={4} value={draft.context} onChange={(event) => update({ context: event.target.value })} />
      </Field>
      <Field label="Decision prompt">
        <textarea className="as-wiki__input" rows={3} value={draft.prompt} onChange={(event) => update({ prompt: event.target.value })} />
      </Field>
      <Field label="Evaluation criteria, one per line">
        <textarea className="as-wiki__input" rows={4} value={draft.criteria} onChange={(event) => update({ criteria: event.target.value })} />
      </Field>
      <div className="kcomp__row">
        <Field label="Format">
          <Select value={draft.format} options={SCENARIO_FORMATS} onChange={(format) => update({ format })} />
        </Field>
        <Field label="Cognitive level">
          <Select value={draft.bloom} options={BLOOM_LEVELS} onChange={(bloom) => update({ bloom })} />
        </Field>
        <Field label="Difficulty">
          <Select
            value={draft.difficulty}
            options={DIFFICULTIES.map((value) => ({ value, label: value }))}
            onChange={(difficulty) => update({ difficulty })}
          />
        </Field>
      </div>
      <div className="kcomp__actions">
        <button
          type="button"
          className="as-console__cta"
          disabled={busy}
          onClick={() =>
            void act(
              () =>
                saveKnowledgeScenario(projectId, scenario.plan_id, {
                  title: draft.title,
                  prompt: draft.prompt,
                  context: draft.context || null,
                  evaluation_criteria: draft.criteria.split('\n').map((line) => line.trim()).filter(Boolean),
                  format: draft.format,
                  difficulty: draft.difficulty,
                  bloom_level: draft.bloom || null,
                }),
              'Could not save the scenario.',
            ).then((saved) => {
              if (saved) setDirty(false)
            })
          }
        >
          Save scenario
        </button>
      </div>
    </div>
  )
}
