import { MessageCircle, MessagesSquare, Plus, Send, Trash2, X } from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import {
  createThread,
  deleteThread,
  getThread,
  listThreads,
  sendThreadMessage,
  updateThread,
  type DiscussionMessage,
  type DiscussionSubmode,
  type DiscussionThread,
} from '../../lib/assistantApi'
import { ChatRichText } from './ChatRichText'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import { useOutputs } from '../../lib/academyOutputs'
import { discussionSections } from '../../lib/discussionPrompts'
import { useLessons } from '../../lib/useLessons'
import {
  StudyHead,
  StudyLessonReference,
  StudyPanel,
  StudySourceReference,
} from './StudySessionChrome'
import { useStudyFullscreen } from './useStudyFullscreen'

const DEFAULT_SEED_PROMPT =
  'Ask any question and receive thought-provoking responses with canonical references to the wiki.'

/* Discussions are persisted conversation threads. A side panel (opened from
   the conversations icon in the panel bar) lists existing threads and lets the
   academy start a new one, either free-form or seeded from a knowledge-base
   prompt. */

export function DiscussionsView({
  sourceId: initialSource = null,
  threadId: initialThreadId = null,
}: {
  sourceId?: string | null
  /** Thread to open on arrival, e.g. one created by "Discuss this class". */
  threadId?: string | null
}) {
  const { approvedUser } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const canChooseStyle = isAdminAccess(approvedUser?.role)
  const { wikiEntries } = useWorkspaceData()
  const { sources } = useOutputs()
  const { fullscreen, toggle } = useStudyFullscreen()

  const sections = useMemo(
    () => discussionSections(wikiEntries, initialSource),
    [wikiEntries, initialSource],
  )
  const prompts = useMemo(() => sections.flatMap((section) => section.prompts), [sections])

  const [threads, setThreads] = useState<DiscussionThread[]>([])
  const [threadsLoaded, setThreadsLoaded] = useState(false)
  const [activeThread, setActiveThread] = useState<DiscussionThread | null>(null)
  const [messages, setMessages] = useState<DiscussionMessage[]>([])
  const [panelOpen, setPanelOpen] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [animatingMessageId, setAnimatingMessageId] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  const scrollLogToBottom = () => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }

  const workspaceId = activeWorkspace?.id ?? null

  // Load persisted threads whenever the active workspace changes.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!workspaceId) return
    let cancelled = false
    setThreadsLoaded(false)
    listThreads(workspaceId)
      .then((rows) => {
        if (cancelled) return
        setThreads(rows)
        setThreadsLoaded(true)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not load conversations.')
        setThreadsLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])
  /* eslint-enable react-hooks/set-state-in-effect */

  const openedInitialRef = useRef<string | null>(null)
  useEffect(() => {
    if (!workspaceId || !initialThreadId || openedInitialRef.current === initialThreadId) return
    openedInitialRef.current = initialThreadId
    let cancelled = false
    getThread(workspaceId, initialThreadId)
      .then((detail) => {
        if (cancelled) return
        setActiveThread(detail)
        setMessages(detail.messages)
        setThreads((rows) => (rows.some((row) => row.id === detail.id) ? rows : [detail, ...rows]))
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load the conversation.')
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, initialThreadId])

  const { lessons } = useLessons(workspaceId)
  const threadLesson = activeThread?.lesson_id
    ? lessons.find((lesson) => lesson.id === activeThread.lesson_id) ?? null
    : null

  useEffect(() => {
    scrollLogToBottom()
  }, [messages, sending])

  const openThread = async (thread: DiscussionThread) => {
    if (!workspaceId) return
    setError(null)
    setPanelOpen(false)
    setActiveThread(thread)
    setMessages([])
    setAnimatingMessageId(null)
    try {
      const detail = await getThread(workspaceId, thread.id)
      setActiveThread(detail)
      setMessages(detail.messages)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the conversation.')
    }
  }

  const submitMessage = async (threadId: string, text: string) => {
    if (!workspaceId) return
    setDraft('')
    setError(null)
    setSending(true)
    const optimistic: DiscussionMessage = {
      id: `pending-${Date.now()}`,
      thread_id: threadId,
      role: 'user',
      content: text,
      citations: [],
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, optimistic])
    try {
      const response = await sendThreadMessage(workspaceId, threadId, text)
      setAnimatingMessageId(response.assistant_message.id)
      setMessages((current) => [
        ...current.filter((message) => message.id !== optimistic.id),
        response.user_message,
        response.assistant_message,
      ])
      setThreads((rows) => {
        const updated = rows.find((row) => row.id === threadId)
        if (!updated) return rows
        const bumped = { ...updated, updated_at: new Date().toISOString() }
        return [bumped, ...rows.filter((row) => row.id !== threadId)]
      })
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id))
      setDraft(text)
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setSending(false)
    }
  }

  const startThread = async (options: {
    title: string
    sourceId?: string | null
    wikiEntryId?: string | null
  }) => {
    if (!workspaceId || creating) return
    setCreating(true)
    setError(null)
    const wikiEntryId = options.wikiEntryId ?? null
    try {
      const detail = await createThread(workspaceId, {
        title: options.title,
        submode: canChooseStyle ? (activeThread?.submode ?? 'tbs') : 'tbs',
        source_id: options.sourceId ?? null,
        wiki_entry_id: wikiEntryId,
        // An ELO question is the tutor's opener, filled in on the server from the
        // stored entry. seed_prompt is only the blank-thread welcome.
        seed_prompt: wikiEntryId ? null : DEFAULT_SEED_PROMPT,
      })
      setThreads((rows) => [detail, ...rows])
      setActiveThread(detail)
      setMessages(detail.messages)
      setNewTitle('')
      setPanelOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the conversation.')
    } finally {
      setCreating(false)
    }
  }

  const removeThread = async (thread: DiscussionThread) => {
    if (!workspaceId) return
    try {
      await deleteThread(workspaceId, thread.id)
      setThreads((rows) => rows.filter((row) => row.id !== thread.id))
      if (activeThread?.id === thread.id) {
        setActiveThread(null)
        setMessages([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the conversation.')
    }
  }

  const setSubmode = async (submode: DiscussionSubmode) => {
    if (!activeThread || !workspaceId || activeThread.submode === submode) return
    const previous = activeThread
    setActiveThread({ ...activeThread, submode })
    try {
      const updated = await updateThread(workspaceId, activeThread.id, { submode })
      setThreads((rows) => rows.map((row) => (row.id === updated.id ? updated : row)))
    } catch (err) {
      setActiveThread(previous)
      setError(err instanceof Error ? err.message : 'Could not update discussion style.')
    }
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending || !activeThread || !workspaceId) return
    await submitMessage(activeThread.id, text)
  }

  const submode = canChooseStyle ? (activeThread?.submode ?? 'tbs') : 'tbs'
  const sourceName = activeThread?.source_id
    ? sources.find((source) => source.id === activeThread.source_id)?.name ?? 'Unassigned'
    : null

  return (
    <section className="study-session">
      <StudyHead
        eyebrow="Guided inquiry"
        title="Discussion room"
        description="Develop an argument through source-grounded conversations."
        stats={[{ value: threads.length, label: 'threads' }]}
      />

      <StudyPanel
        fullscreen={fullscreen}
        onToggleFullscreen={toggle}
        meta={
          <>
            <button
              type="button"
              className="disc-threads__toggle"
              onClick={() => setPanelOpen((open) => !open)}
              aria-expanded={panelOpen}
              aria-label="Conversations"
              title="Conversations"
            >
              <MessagesSquare size={16} />
            </button>
            <span className="study-session__panel-title">
              {activeThread ? activeThread.title : 'No conversation selected'}
            </span>
          </>
        }
        center={
          activeThread && canChooseStyle ? (
            <div className="disc__seg" role="group" aria-label="Discussion style">
              <button
                type="button"
                className={`disc__seg-btn${submode === 'tbs' ? ' is-active' : ''}`}
                onClick={() => setSubmode('tbs')}
                aria-pressed={submode === 'tbs'}
              >
                TBS
              </button>
              <button
                type="button"
                className={`disc__seg-btn${submode === 'socratic' ? ' is-active' : ''}`}
                onClick={() => setSubmode('socratic')}
                aria-pressed={submode === 'socratic'}
              >
                Socratic
              </button>
              <button
                type="button"
                className={`disc__seg-btn${submode === 'euclidean' ? ' is-active' : ''}`}
                onClick={() => setSubmode('euclidean')}
                aria-pressed={submode === 'euclidean'}
              >
                Euclidean
              </button>
            </div>
          ) : undefined
        }
      >
        {activeThread ? (
          <div className="chat">
            <div className="chat__log" ref={logRef}>
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`chat__msg chat__msg--${message.role === 'assistant' ? 'ai' : 'user'}`}
                >
                  <span className="chat__role">
                    {message.role === 'assistant' ? 'Tutor' : 'You'}
                  </span>
                  <ChatRichText
                    text={message.content}
                    citations={message.citations}
                    animate={message.id === animatingMessageId}
                    onProgress={scrollLogToBottom}
                    onDone={() => setAnimatingMessageId(null)}
                  />
                </div>
              ))}
              {sending && (
                <div className="chat__msg chat__msg--ai">
                  <span className="chat__role">Tutor</span>
                  <span className="chat__thinking" aria-label="Tutor is thinking">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              )}
            </div>

            {error && <p className="chat__error">{error}</p>}

            <form className="chat__compose" onSubmit={send}>
              <input
                className="chat__input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={messagePlaceholder(submode, Boolean(activeThread.wiki_entry_id))}
                aria-label="Your message"
                disabled={sending}
              />
              <button type="submit" className="chat__send" disabled={!draft.trim() || sending}>
                <Send size={16} /> Send
              </button>
            </form>
          </div>
        ) : (
          <div className="disc-starters">
            {!threadsLoaded ? (
              <p className="disc__sub">Loading conversations…</p>
            ) : (
              <>
                {sections.length > 0 ? (
                  sections.map((section) => (
                    <Fragment key={section.key}>
                      <div className="disc__label">
                        <h3>{section.title}</h3>
                        <span className="disc__label-line" aria-hidden />
                      </div>
                      <div className="disc__grid">
                        {section.prompts.map((prompt) => (
                          <button
                            key={prompt.key}
                            type="button"
                            className="disc__prompt"
                            disabled={creating}
                            onClick={() =>
                              void startThread({
                                title: prompt.title,
                                wikiEntryId: prompt.key,
                                sourceId: prompt.sourceId,
                              })
                            }
                          >
                            <MessageCircle size={16} aria-hidden />
                            {prompt.title}
                          </button>
                        ))}
                      </div>
                    </Fragment>
                  ))
                ) : (
                  <p className="disc__sub">
                    ELOs from a knowledge upload appear here. Begin your own conversation below.
                  </p>
                )}

                <div className="disc__own">
                  <div className="disc__label">
                    <h3>Start your own</h3>
                    <span className="disc__label-line" aria-hidden />
                  </div>
                  <form
                    className="disc__field"
                    onSubmit={(e) => {
                      e.preventDefault()
                      const title = newTitle.trim()
                      if (title) void startThread({ title, sourceId: initialSource })
                    }}
                  >
                    <input
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      placeholder="What would you like to discuss?"
                      aria-label="New conversation topic"
                      disabled={creating}
                    />
                    <button type="submit" className="disc__start" disabled={!newTitle.trim() || creating}>
                      <MessagesSquare size={16} /> Start
                    </button>
                  </form>
                </div>
              </>
            )}
            {error && <p className="chat__error">{error}</p>}
          </div>
        )}

        {panelOpen && (
          <>
            <div
              className="disc-threads__backdrop"
              onClick={() => setPanelOpen(false)}
              aria-hidden
            />
            <aside className="disc-threads" aria-label="Conversations">
              <div className="disc-threads__head">
                <span>Conversations</span>
                <button
                  type="button"
                  className="disc-threads__close"
                  onClick={() => setPanelOpen(false)}
                  aria-label="Close conversations"
                >
                  <X size={15} />
                </button>
              </div>

              <form
                className="disc-threads__new"
                onSubmit={(e) => {
                  e.preventDefault()
                  const title = newTitle.trim()
                  if (title) void startThread({ title, sourceId: initialSource })
                }}
              >
                <input
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="Start a new conversation…"
                  aria-label="New conversation topic"
                  disabled={creating}
                />
                <button type="submit" disabled={!newTitle.trim() || creating} aria-label="Start conversation">
                  <Plus size={15} />
                </button>
              </form>

              {threads.length > 0 && (
                <div className="disc-threads__list">
                  {threads.map((thread) => (
                    <div
                      key={thread.id}
                      className={`disc-threads__item${activeThread?.id === thread.id ? ' is-active' : ''}`}
                    >
                      <button
                        type="button"
                        className="disc-threads__item-open"
                        onClick={() => void openThread(thread)}
                      >
                        <span className="disc-threads__item-title">{thread.title}</span>
                        <span className="disc-threads__item-meta">
                          {formatRelativeTime(thread.updated_at)}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="disc-threads__item-delete"
                        onClick={() => void removeThread(thread)}
                        aria-label={`Delete "${thread.title}"`}
                        title="Delete conversation"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {prompts.length > 0 && (
                <div className="disc-threads__suggestions">
                  <span className="disc-threads__section-label">Suggested topics</span>
                  {prompts.map((prompt) => (
                    <button
                      key={prompt.key}
                      type="button"
                      className="disc-threads__suggestion"
                      disabled={creating}
                      onClick={() =>
                        void startThread({
                          title: prompt.title,
                          wikiEntryId: prompt.key,
                          sourceId: prompt.sourceId,
                        })
                      }
                    >
                      {prompt.title}
                    </button>
                  ))}
                </div>
              )}
            </aside>
          </>
        )}
      </StudyPanel>

      {activeThread?.source_id && sourceName && (
        <StudySourceReference sourceId={activeThread.source_id} sourceName={sourceName} />
      )}
      {threadLesson && <StudyLessonReference lesson={threadLesson} />}
    </section>
  )
}

function messagePlaceholder(submode: DiscussionSubmode, checkingAnswer: boolean): string {
  if (checkingAnswer) return 'Write your answer…'
  switch (submode) {
    case 'tbs':
      return 'Ask about a concept…'
    case 'socratic':
      return 'Share your thinking…'
    case 'euclidean':
      return 'Ask a question…'
    default: {
      const exhaustive: never = submode
      return exhaustive
    }
  }
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
