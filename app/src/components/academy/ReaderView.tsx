import {
  AlertTriangle,
  Bookmark,
  BookmarkCheck,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coffee,
  List,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  X,
} from 'lucide-react'
import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { isAdminAccess } from '../../features/auth/access'
import { useAuth } from '../../features/auth/authContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  buildNarration,
  buildNarrationClips,
  globalsFromDomSelection,
  matchWikiTerms,
  resolveReaderSelection,
  sentenceCueAt,
  type Block,
  type NarrationClip,
  type SpokenWord,
} from '../../lib/readerContent'
import {
  chapterIndexForSeq,
  columnCountFromExtent,
  columnStride,
  globalSpread,
  locateSpread,
  nextUnmeasuredChapter,
  readerProgressLabel,
  seqForSpoken,
  splitReaderChapters,
  spreadPageNumbers,
  spreadsForColumns,
  totalColumns,
  wordBlocksForChapter,
} from '../../lib/readerChapters'
import {
  createReaderLoadSignal,
  isAbortError,
  liveAfterMissingScope,
  loadReaderNarration,
  loadReaderText,
  narrationFailureWarning,
  readReaderCache,
  shouldResumeReaderLoad,
  writeReaderCache,
  type ReaderCacheEntry,
} from '../../lib/readerLoad'
import { defineReaderTerm, type ReaderDefineMode } from '../../lib/readerDefineApi'
import { ApiError } from '../../lib/apiClient'
import { createWikiEntry } from '../../lib/wikiApi'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import type { AcademyPage, AcademyScope } from './types'
import { useIdleChrome } from './useIdleChrome'
import { useReaderFlip } from './useReaderFlip'
import { getNarrationAudioUrl, type NarrationSegment } from '../../lib/sourcesApi'

const SESSION_SECONDS = 25 * 60
// Gap between the two pages of a spread (and between overflow columns). Must
// match the value used in the translate math; we feed it to CSS as a var.
const GAP = 48
// Simulated narration cadence, used when no synthesized audio exists yet.
// Base words-per-minute at 1× playback speed.
const BASE_WPM = 165
// Above this multiplier we warn that comprehension drops off.
const SPEED_WARN_ABOVE = 1.5
const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2] as const

type TocEntry = { title: string; seq: number; sections: { title: string; seq: number }[] }

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

function isEveningNow(): boolean {
  const h = new Date().getHours()
  return h >= 20 || h < 6
}

function isBrowserFullscreen(): boolean {
  return document.fullscreenElement != null
}

type LiveContent = {
  blocks: Block[]
  narration: Map<string, NarrationSegment>
  loading: boolean
  error: string | null
  /** Soft warning when narration timings failed to load (reading still works). */
  narrationWarning: string | null
}

const NO_NARRATION = new Map<string, NarrationSegment>()
const NO_TERMS = new Map<number, string>()
const EMPTY_BLOCKS: Block[] = []

// The offscreen measurer mounts the same blocks so line breaks match the
// visible chapter. Those blocks are not interactive.
function ignoreTermClick(): void {}
const EMPTY_LIVE: LiveContent = {
  blocks: [],
  narration: NO_NARRATION,
  loading: false,
  error: null,
  narrationWarning: null,
}

function liveFromCache(entry: ReaderCacheEntry): LiveContent {
  return {
    blocks: entry.blocks,
    narration: entry.narration,
    loading: false,
    error: null,
    narrationWarning: entry.narrationWarning,
  }
}

function scheduleIdle(callback: () => void): number {
  if (typeof window.requestIdleCallback === 'function') {
    return window.requestIdleCallback(callback)
  }
  return window.setTimeout(callback, 1)
}

function cancelIdle(id: number): void {
  if (typeof window.cancelIdleCallback === 'function') {
    window.cancelIdleCallback(id)
    return
  }
  window.clearTimeout(id)
}

// Deep links land here as /app/reader/:sourceId?seg=N where `seg` is the
// segment's stable sequence_index (see api build_reader_link) — never a page
// number, since pages reflow but segment order is immutable.
export function ReaderView({
  sourceId = null,
  seg = null,
  onOpen,
}: {
  sourceId?: string | null
  seg?: number | null
  onOpen?: (page: AcademyPage, scope: AcademyScope) => void
}) {
  const { activeWorkspace } = useWorkspace()
  const { sources, wikiEntries, addWikiEntry, isLoading } = useWorkspaceData()
  const { approvedUser } = useAuth()
  const canEditWiki = isAdminAccess(approvedUser?.role)
  const workspaceId = activeWorkspace?.id ?? null
  const activeSource = sources.find((source) => source.id === sourceId)
  const ebookTitle = activeSource ? sourceDisplayName(activeSource) : 'Ebook'

  const [live, setLive] = useState<LiveContent>(() => {
    if (!sourceId || !workspaceId) return EMPTY_LIVE
    const cached = readReaderCache(workspaceId, sourceId)
    if (cached) return liveFromCache(cached)
    return { ...EMPTY_LIVE, loading: true }
  })
  const [resumeNonce, setResumeNonce] = useState(0)
  const failedWhileHiddenRef = useRef(false)
  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  })

  // Text opens the book. Narration fills in afterward and never puts the
  // opening animation back up. A cached book paints immediately; a refresh
  // keeps those pages on screen. A fetch that dies while the tab is hidden
  // stays in loading so the visible-tab handler can start one new attempt.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!sourceId || !workspaceId) {
      setLive((prev) => liveAfterMissingScope(prev))
      return
    }
    const cached = readReaderCache(workspaceId, sourceId)
    let cancelled = false
    let showedText = cached != null
    let stage: 'text' | 'narration' = 'text'
    const parent = new AbortController()
    const loadSignal = createReaderLoadSignal(parent.signal)
    if (cached) {
      setLive(liveFromCache(cached))
    } else if (liveRef.current.blocks.length === 0) {
      setLive({
        blocks: [],
        narration: NO_NARRATION,
        loading: true,
        error: null,
        narrationWarning: null,
      })
    }

    const remember = (entry: ReaderCacheEntry) => {
      writeReaderCache(workspaceId, sourceId, entry)
    }

    const failOpen = (error: unknown) => {
      if (cancelled || showedText) return
      const message = isAbortError(error)
        ? 'The book took too long to load.'
        : error instanceof Error
          ? error.message
          : 'Failed to load the source.'
      setLive({
        blocks: [],
        narration: NO_NARRATION,
        loading: false,
        error: message,
        narrationWarning: null,
      })
    }

    void loadReaderText(workspaceId, sourceId, loadSignal.signal)
      .then((blocks) => {
        if (cancelled) return
        showedText = true
        stage = 'narration'
        failedWhileHiddenRef.current = false
        const narration = cached?.narration ?? NO_NARRATION
        const narrationWarning = cached?.narrationWarning ?? null
        const entry = { blocks, narration, narrationWarning }
        remember(entry)
        setLive({
          blocks,
          narration,
          loading: false,
          error: null,
          narrationWarning,
        })
        return loadReaderNarration(workspaceId, sourceId, loadSignal.signal)
      })
      .then((narrationResult) => {
        if (cancelled || !narrationResult) return
        setLive((prev) => {
          const entry = {
            blocks: prev.blocks,
            narration: narrationResult.narration,
            narrationWarning: narrationResult.warning,
          }
          remember(entry)
          return { ...prev, ...entry, loading: false, error: null }
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (isAbortError(error) && document.hidden) {
          failedWhileHiddenRef.current = true
          return
        }
        if (stage === 'narration') {
          const warning = narrationFailureWarning(
            isAbortError(error) ? new Error('the request timed out') : error,
          )
          setLive((prev) => {
            if (prev.blocks.length > 0) {
              remember({
                blocks: prev.blocks,
                narration: prev.narration,
                narrationWarning: warning,
              })
            }
            return { ...prev, loading: false, narrationWarning: warning }
          })
          return
        }
        failOpen(error)
      })
      .finally(() => {
        loadSignal.cancelTimer()
      })

    return () => {
      cancelled = true
      parent.abort()
      loadSignal.cancelTimer()
    }
  }, [sourceId, workspaceId, resumeNonce])
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const onVisibility = () => {
      if (
        !shouldResumeReaderLoad({
          visible: document.visibilityState === 'visible',
          loading: liveRef.current.loading,
          failedWhileHidden: failedWhileHiddenRef.current,
        })
      ) {
        return
      }
      failedWhileHiddenRef.current = false
      setResumeNonce((nonce) => nonce + 1)
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const isLive = sourceId != null
  const blocks = useMemo(
    () => (isLive ? live.blocks : EMPTY_BLOCKS),
    [isLive, live.blocks],
  )
  const { wordBlocks, total } = useMemo(() => buildNarration(blocks), [blocks])
  const chapters = useMemo(() => splitReaderChapters(blocks), [blocks])

  const [chapterIndex, setChapterIndex] = useState(0)
  const [localSpread, setLocalSpread] = useState(0)
  const [geometry, setGeometry] = useState<{
    width: number
    height: number
    counts: (number | undefined)[]
  }>({ width: 0, height: 0, counts: [] })
  const [colStride, setColStride] = useState(0)
  const [tocOpen, setTocOpen] = useState(false)
  const [viewportTick, setViewportTick] = useState(0)

  // Persistent bookmark: remembers the reader's spread across sessions, keyed
  // by source. `bookmarkSpread` mirrors the stored value for the button state.
  const bookmarkKey = sourceId ? `arsenal:reader-bookmark:${sourceId}` : null
  const [bookmarkSpread, setBookmarkSpread] = useState<number | null>(null)
  const bookmarkRestoredRef = useRef(false)

  // Narration / audio state. `spoken` is the global index of the reading
  // position (-1 = not started): the first word of the current sentence with
  // audio, or the current word with the simulated cadence. `activeSentence`
  // is the highlighted sentence; it only changes at sentence boundaries.
  const [playing, setPlaying] = useState(false)
  const [spoken, setSpoken] = useState(-1)
  const [activeSentence, setActiveSentence] = useState(-1)
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1)
  const [audioError, setAudioError] = useState<string | null>(null)

  const [remaining, setRemaining] = useState(SESSION_SECONDS)
  const [timerRunning, setTimerRunning] = useState(false)
  const [showBreak, setShowBreak] = useState(false)
  const chimeCtxRef = useRef<AudioContext | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const evening = useMemo(() => isEveningNow(), [])

  // App chrome fades out while reading. Open overlays and a hovered control
  // pin it visible; the printed page furniture (running head, folios, spine)
  // never hides.
  const [hoverChrome, setHoverChrome] = useState(false)

  // Deep-link target. Applied once layout has been measured; highlighted
  // briefly so the reader can see what the link pointed at.
  const [targetSeq, setTargetSeq] = useState<number | null>(null)
  const pendingTargetRef = useRef<number | null>(seg)

  const viewportRef = useRef<HTMLDivElement | null>(null)
  const readerRootRef = useRef<HTMLElement | null>(null)
  const flowRef = useRef<HTMLDivElement | null>(null)
  const measureFlowRef = useRef<HTMLDivElement | null>(null)
  const blockRefs = useRef<Map<number, HTMLElement>>(new Map())
  const measureRefs = useRef<Map<number, HTMLElement>>(new Map())

  // Mirrors of the clamped position so rapid turns in the same frame never
  // read a stale value.
  const chapterIndexRef = useRef(0)
  const localSpreadRef = useRef(0)
  const columnCountsRef = useRef<(number | undefined)[]>([])
  const pendingEdgeRef = useRef<'end' | null>(null)

  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReducedMotion(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const {
    flipTo,
    cancel: cancelFlip,
    isFlipping,
  } = useReaderFlip({ viewportRef, reducedMotion })

  // Reset reading position when switching sources or receiving a new target.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    pendingTargetRef.current = seg
    cancelFlip()
    chapterIndexRef.current = 0
    localSpreadRef.current = 0
    setChapterIndex(0)
    setLocalSpread(0)
    setGeometry({ width: 0, height: 0, counts: [] })
    setPlaying(false)
    setSpoken(-1)
    setActiveSentence(-1)
    setTargetSeq(null)
    bookmarkRestoredRef.current = false
  }, [sourceId, seg, cancelFlip])
  /* eslint-enable react-hooks/set-state-in-effect */

  // Load the stored bookmark for the current source (button-state mirror).
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!bookmarkKey) {
      setBookmarkSpread(null)
      return
    }
    const raw = window.localStorage.getItem(bookmarkKey)
    const val = raw != null ? Number(raw) : NaN
    setBookmarkSpread(Number.isFinite(val) ? val : null)
  }, [bookmarkKey])
  /* eslint-enable react-hooks/set-state-in-effect */

  // --- Wiki term links + selection define -----------------------------------
  // Match canonical wiki entry labels/aliases against the word stream; matched
  // words become tappable links. Free-text selection opens the same popup for
  // wiki hits or contextual/general define assists.
  const columnCounts = useMemo<(number | undefined)[]>(() => {
    if (geometry.counts.length === chapters.length) return geometry.counts
    return Array.from({ length: chapters.length }, () => undefined)
  }, [geometry.counts, chapters.length])
  const visibleChapter = chapters[Math.min(chapterIndex, Math.max(chapters.length - 1, 0))]
  const visibleWordBlocks = useMemo(
    () => wordBlocksForChapter(wordBlocks, visibleChapter),
    [wordBlocks, visibleChapter],
  )
  // Wiki matching walks every word. Limit it to the mounted chapter so the
  // rest of the book is not on the path to the first page.
  const termByWord = useMemo(
    () => matchWikiTerms(visibleWordBlocks, wikiEntries),
    [visibleWordBlocks, wikiEntries],
  )
  const entryById = useMemo(
    () => new Map(wikiEntries.map((entry) => [entry.id, entry])),
    [wikiEntries],
  )

  type DefineContext = {
    prev: string
    current: string
    next: string
    sentence: string
    sourceId: string | null
  }
  type DefinePop =
    | { kind: 'wiki'; entryId: string; left: number; bottom: number }
    | { kind: 'miss'; term: string; left: number; bottom: number; context: DefineContext }
    | {
        kind: 'generated'
        term: string
        left: number
        bottom: number
        mode: ReaderDefineMode
        definition: string
        loading: boolean
        saving: boolean
        error: string | null
        context: DefineContext
      }

  const [definePop, setDefinePop] = useState<DefinePop | null>(null)
  const skipNextSelectionRef = useRef(false)
  const defineEditRef = useRef<HTMLTextAreaElement | null>(null)

  // Anchor the popup's bottom edge just above the selection so it always
  // grows upward (never flips below the word). Coordinates are relative to
  // the reader shell so the overlay can sit above chrome.
  const positionDefinePop = useCallback((target: DOMRect) => {
    const root = readerRootRef.current
    if (!root) return { left: 0, bottom: 0 }
    const rootRect = root.getBoundingClientRect()
    const width = 320
    const left = Math.max(
      8,
      Math.min(target.left - rootRect.left, root.clientWidth - width - 8),
    )
    const selectionTop = target.top - rootRect.top
    const bottom = Math.max(8, root.clientHeight - selectionTop + 8)
    return { left, bottom }
  }, [])

  useLayoutEffect(() => {
    const el = defineEditRef.current
    if (!el || definePop?.kind !== 'generated' || definePop.loading) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [
    definePop?.kind,
    definePop?.kind === 'generated' ? definePop.definition : null,
    definePop?.kind === 'generated' ? definePop.loading : null,
  ])

  const onTermClick = useCallback(
    (entryId: string, target: HTMLElement) => {
      skipNextSelectionRef.current = true
      const { left, bottom } = positionDefinePop(target.getBoundingClientRect())
      setDefinePop({ kind: 'wiki', entryId, left, bottom })
    },
    [positionDefinePop],
  )

  const openSelectionDefine = useCallback(() => {
    if (skipNextSelectionRef.current) {
      skipNextSelectionRef.current = false
      return
    }
    const globals = globalsFromDomSelection(flowRef.current)
    const resolved = resolveReaderSelection(wordBlocks, globals, termByWord)
    if (!resolved) return
    const sel = window.getSelection()
    const rect =
      sel && sel.rangeCount > 0 ? sel.getRangeAt(0).getBoundingClientRect() : null
    if (!rect || (rect.width === 0 && rect.height === 0)) return
    // Prefer the live selection string so the popup shows exactly what the user
    // highlighted (no edge punctuation from whole word spans).
    const highlighted = (sel?.toString() ?? '').replace(/\s+/g, ' ').trim()
    const term = highlighted || resolved.term
    const { left, bottom } = positionDefinePop(rect)
    const context: DefineContext = {
      prev: resolved.neighbors.prev,
      current: resolved.neighbors.current,
      next: resolved.neighbors.next,
      sentence: resolved.sentence,
      sourceId: sourceId ?? null,
    }
    if (resolved.entryId) {
      setDefinePop({ kind: 'wiki', entryId: resolved.entryId, left, bottom })
    } else {
      setDefinePop({ kind: 'miss', term, left, bottom, context })
    }
  }, [wordBlocks, termByWord, positionDefinePop, sourceId])

  const runDefine = useCallback(
    async (mode: ReaderDefineMode) => {
      if (!definePop || definePop.kind === 'wiki' || !workspaceId) return
      const { term, left, bottom, context } = definePop
      setDefinePop({
        kind: 'generated',
        term,
        left,
        bottom,
        mode,
        definition: '',
        loading: true,
        saving: false,
        error: null,
        context,
      })
      try {
        const result = await defineReaderTerm(workspaceId, {
          term,
          mode,
          source_id: context.sourceId,
          sentence: context.sentence,
          prev_paragraph: context.prev,
          current_paragraph: context.current,
          next_paragraph: context.next,
        })
        setDefinePop({
          kind: 'generated',
          term: result.term,
          left,
          bottom,
          mode: result.mode,
          definition: result.definition,
          loading: false,
          saving: false,
          error: null,
          context,
        })
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Define failed.'
        setDefinePop({
          kind: 'generated',
          term,
          left,
          bottom,
          mode,
          definition: '',
          loading: false,
          saving: false,
          error: message,
          context,
        })
      }
    },
    [definePop, workspaceId],
  )

  const saveGeneratedToWiki = useCallback(async () => {
    if (!definePop || definePop.kind !== 'generated' || !workspaceId) return
    if (!definePop.definition.trim()) return
    const { term, left, bottom, mode, definition, context } = definePop
    setDefinePop({ ...definePop, saving: true, error: null })
    try {
      const entry = await createWikiEntry(workspaceId, {
        preferred_label: term,
        definition: definition.trim(),
        entry_kind: 'term',
        importance: 'supporting',
        origin: {
          kind: 'reader_define',
          mode,
          source_id: context.sourceId,
          term,
        },
      })
      addWikiEntry(entry)
      setDefinePop({ kind: 'wiki', entryId: entry.id, left, bottom })
      window.getSelection()?.removeAllRanges()
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : 'Save failed.'
      setDefinePop((prev) =>
        prev && prev.kind === 'generated'
          ? { ...prev, saving: false, error: message }
          : prev,
      )
    }
  }, [definePop, workspaceId, addWikiEntry])

  const wikiPopEntry =
    definePop?.kind === 'wiki' ? entryById.get(definePop.entryId) : undefined

  const { visible: chromeVisible, bind: idleBind } = useIdleChrome({
    pinned: tocOpen || definePop != null || showBreak || hoverChrome,
  })
  const chromeHover = {
    onMouseEnter: () => setHoverChrome(true),
    onMouseLeave: () => setHoverChrome(false),
  }

  const toc = useMemo<TocEntry[]>(() => {
    const entries: TocEntry[] = []
    for (const b of blocks) {
      if (b.kind === 'heading' && b.level === 1) {
        entries.push({ title: b.text, seq: b.seq, sections: [] })
      } else if (b.kind === 'heading' && b.level === 2 && entries.length) {
        entries[entries.length - 1].sections.push({ title: b.text, seq: b.seq })
      }
    }
    return entries
  }, [blocks])

  // --- Pagination measurement ---------------------------------------------
  // The on-screen flow is one chapter. Its column count is measured here.
  // The other chapters are measured one at a time offscreen so the first page
  // does not wait on the rest of the book. column-width only accepts lengths.
  /* eslint-disable react-hooks/set-state-in-effect */
  useLayoutEffect(() => {
    if (chapters.length === 0) {
      setColStride(0)
      return
    }
    const vp = viewportRef.current
    const flow = flowRef.current
    const chapter = visibleChapter
    if (!vp || !flow || !chapter) return
    const width = vp.clientWidth
    const height = vp.clientHeight
    if (width <= 0 || height <= 0) return

    flow.style.columnWidth = `${(width - GAP) / 2}px`
    const stride = columnStride(width, GAP)
    const last = chapter.blocks[chapter.blocks.length - 1]
    const lastEl = blockRefs.current.get(last.seq)
    const lastRight = lastEl ? lastEl.offsetLeft + lastEl.offsetWidth : 0
    const extent = Math.max(flow.scrollWidth, lastRight)
    const columns = columnCountFromExtent(extent, width, GAP)
    setColStride(stride)

    const edgeLocal = pendingEdgeRef.current === 'end' ? spreadsForColumns(columns) - 1 : null
    if (edgeLocal != null) pendingEdgeRef.current = null

    setGeometry((prev) => {
      const sameBox = prev.width === width && prev.height === height
      const counts =
        sameBox && prev.counts.length === chapters.length
          ? prev.counts.slice()
          : Array.from({ length: chapters.length }, () => undefined)
      if (counts[chapter.index] === columns && sameBox) return prev
      counts[chapter.index] = columns
      return { width, height, counts }
    })
    if (edgeLocal != null && edgeLocal !== localSpreadRef.current) {
      localSpreadRef.current = edgeLocal
      setLocalSpread(edgeLocal)
    }
  }, [chapters, visibleChapter, viewportTick])
  /* eslint-enable react-hooks/set-state-in-effect */

  const measureAt = nextUnmeasuredChapter(chapters.length, columnCounts, chapterIndex)
  const measureChapter = measureAt >= 0 ? chapters[measureAt] : undefined

  useEffect(() => {
    if (!measureChapter || geometry.width <= 0 || geometry.height <= 0) return
    let cancelled = false
    const width = geometry.width
    const idle = scheduleIdle(() => {
      if (cancelled) return
      const flow = measureFlowRef.current
      if (!flow) return
      const last = measureChapter.blocks[measureChapter.blocks.length - 1]
      const lastEl = measureRefs.current.get(last.seq)
      const lastRight = lastEl ? lastEl.offsetLeft + lastEl.offsetWidth : 0
      const extent = Math.max(flow.scrollWidth, lastRight)
      const columns = columnCountFromExtent(extent, width, GAP)
      setGeometry((prev) => {
        if (prev.width !== width || prev.counts.length !== chapters.length) return prev
        if (prev.counts[measureChapter.index] === columns) return prev
        const counts = prev.counts.slice()
        counts[measureChapter.index] = columns
        return { ...prev, counts }
      })
    })
    return () => {
      cancelled = true
      cancelIdle(idle)
    }
  }, [measureChapter, geometry.width, geometry.height, chapters.length])

  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    const size = { width: vp.clientWidth, height: vp.clientHeight }
    const ro = new ResizeObserver(() => {
      const width = vp.clientWidth
      const height = vp.clientHeight
      if (width === size.width && height === size.height) return
      size.width = width
      size.height = height
      // Reflow invalidates the flip overlay's frozen page clones.
      cancelFlip()
      setViewportTick((tick) => tick + 1)
    })
    ro.observe(vp)
    return () => ro.disconnect()
  }, [cancelFlip])

  const activeChapterIndex = visibleChapter?.index ?? 0
  const knownColumns = columnCounts[activeChapterIndex]
  const localSpreadCount = knownColumns == null ? 1 : spreadsForColumns(knownColumns)
  const safeLocal = Math.min(localSpread, Math.max(localSpreadCount - 1, 0))
  const spreadIndex = globalSpread(columnCounts, activeChapterIndex, safeLocal)
  const measuredPages = totalColumns(columnCounts)
  const geometryReady = measuredPages != null
  const pageCount = measuredPages ?? knownColumns ?? 0
  const atStart = activeChapterIndex === 0 && safeLocal === 0
  const atEnd =
    chapters.length === 0 ||
    (activeChapterIndex === chapters.length - 1 &&
      knownColumns != null &&
      safeLocal >= localSpreadCount - 1)

  useEffect(() => {
    chapterIndexRef.current = chapterIndex
    localSpreadRef.current = safeLocal
    columnCountsRef.current = columnCounts
  })

  // Every position change funnels through here. 'flip' is only honest for a
  // single page turn inside one chapter. Chapter changes and jumps snap or fade.
  const goToLocal = useCallback(
    (chapter: number, local: number, mode: 'flip' | 'fade' | 'none') => {
      const maxChapter = Math.max(chapters.length - 1, 0)
      const nextChapter = Math.min(Math.max(chapter, 0), maxChapter)
      const nextLocal = Math.max(0, local)
      const currentChapter = chapterIndexRef.current
      const currentLocal = localSpreadRef.current
      if (nextChapter === currentChapter && nextLocal === currentLocal) return
      const sameChapter = nextChapter === currentChapter
      chapterIndexRef.current = nextChapter
      localSpreadRef.current = nextLocal
      setChapterIndex(nextChapter)
      setLocalSpread(nextLocal)
      if (reducedMotion || mode === 'none' || !sameChapter) {
        cancelFlip()
        if (!reducedMotion && mode === 'fade') {
          viewportRef.current?.animate(
            { opacity: [0.25, 1] },
            { duration: 180, easing: 'ease-out' },
          )
        }
        return
      }
      if (mode === 'flip') {
        flipTo(nextLocal > currentLocal ? 1 : -1, currentLocal)
        return
      }
      cancelFlip()
      viewportRef.current?.animate({ opacity: [0.25, 1] }, { duration: 180, easing: 'ease-out' })
    },
    [chapters.length, reducedMotion, cancelFlip, flipTo],
  )

  // Land on the deep-link target once that chapter is mounted and measured.
  useEffect(() => {
    const target = pendingTargetRef.current
    if (target == null || blocks.length === 0) return
    const index = chapterIndexForSeq(chapters, target)
    if (chapterIndexRef.current !== index) {
      goToLocal(index, 0, 'none')
      return
    }
    if (colStride <= 0) return
    const el = blockRefs.current.get(target)
    if (!el) return
    pendingTargetRef.current = null
    const col = Math.round(el.offsetLeft / colStride)
    goToLocal(index, Math.floor(col / 2), 'none')
    setTargetSeq(target)
  }, [colStride, blocks, chapters, chapterIndex, goToLocal])

  // Restore the saved bookmark once enough chapters are measured to know which
  // spread it is. A deep-link target always takes precedence.
  useEffect(() => {
    if (bookmarkRestoredRef.current) return
    if (blocks.length === 0 || !bookmarkKey) return
    if (seg != null) {
      bookmarkRestoredRef.current = true
      return
    }
    const raw = window.localStorage.getItem(bookmarkKey)
    const val = raw != null ? Number(raw) : NaN
    if (!Number.isFinite(val)) {
      bookmarkRestoredRef.current = true
      return
    }
    const location = locateSpread(columnCounts, val)
    if (!location) return
    bookmarkRestoredRef.current = true
    goToLocal(location.chapterIndex, location.localSpread, 'none')
  }, [columnCounts, blocks, seg, bookmarkKey, goToLocal])

  useEffect(() => {
    if (targetSeq == null) return
    const timeout = window.setTimeout(() => setTargetSeq(null), 4000)
    return () => window.clearTimeout(timeout)
  }, [targetSeq])

  useEffect(() => {
    if (!definePop) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDefinePop(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [definePop])

  // --- Navigation ---------------------------------------------------------
  const turn = useCallback(
    (delta: 1 | -1) => {
      setDefinePop(null)
      const currentChapter = chapterIndexRef.current
      const currentLocal = localSpreadRef.current
      const columns = columnCountsRef.current[currentChapter]
      if (columns == null) return
      const spreads = spreadsForColumns(columns)
      const nextLocal = currentLocal + delta
      if (nextLocal >= 0 && nextLocal < spreads) {
        goToLocal(currentChapter, nextLocal, 'flip')
        return
      }
      const nextChapter = currentChapter + delta
      if (nextChapter < 0 || nextChapter >= chapters.length) return
      const nextColumns = columnCountsRef.current[nextChapter]
      if (delta === -1 && nextColumns == null) pendingEdgeRef.current = 'end'
      const landing = delta === 1 || nextColumns == null ? 0 : spreadsForColumns(nextColumns) - 1
      goToLocal(nextChapter, landing, 'fade')
    },
    [chapters.length, goToLocal],
  )

  const jumpToSeq = useCallback(
    (target: number) => {
      pendingTargetRef.current = target
      const index = chapterIndexForSeq(chapters, target)
      if (chapterIndexRef.current !== index) {
        goToLocal(index, 0, 'fade')
      } else if (colStride > 0) {
        const el = blockRefs.current.get(target)
        if (el) {
          const col = Math.round(el.offsetLeft / colStride)
          pendingTargetRef.current = null
          goToLocal(index, Math.floor(col / 2), 'fade')
        }
      }
      setTocOpen(false)
      setDefinePop(null)
    },
    [chapters, colStride, goToLocal],
  )

  // Toggle a bookmark at the current spread. Saving again on the bookmarked
  // page removes it; otherwise the bookmark moves to the current page.
  // The stored value stays a book-wide spread, so it waits until earlier
  // chapters have been measured.
  const toggleBookmark = useCallback(() => {
    if (!bookmarkKey || spreadIndex == null) return
    setBookmarkSpread((prev) => {
      if (prev === spreadIndex) {
        window.localStorage.removeItem(bookmarkKey)
        return null
      }
      window.localStorage.setItem(bookmarkKey, String(spreadIndex))
      return spreadIndex
    })
  }, [bookmarkKey, spreadIndex])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
      // Drop focus off any lingering chrome control (e.g. a footer turn button
      // clicked earlier). Otherwise pressing an arrow flips the page AND enters
      // keyboard modality, so that focused button matches :focus-visible and
      // pins the chrome back open. Blurring keeps an idle reader's chrome hidden.
      const active = document.activeElement as HTMLElement | null
      if (active && active !== document.body) active.blur()
      if (e.key === 'ArrowRight') turn(1)
      else turn(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [turn])

  // --- Narration playback -------------------------------------------------
  // Two engines share `spoken` and `activeSentence`. When synthesized audio
  // exists (narration_segments rows), an HTMLAudioElement plays each chapter
  // clip and sentence start times drive the highlight. Consecutive paragraphs
  // that share an audio_path stay on one file. Otherwise a simulated WPM
  // cadence walks the words (reader-recommendations §6 fallback).
  const tracks = useMemo<NarrationClip[]>(
    () => buildNarrationClips(wordBlocks, live.narration),
    [live.narration, wordBlocks],
  )
  const narratedGlobals = useMemo(
    () => new Set(tracks.flatMap((track) => track.globals)),
    [tracks],
  )
  // Globals are numbered 0..total-1 in reading order, so the array index is the global.
  const sentenceOfGlobal = useMemo(
    () => wordBlocks.flatMap((wb) => wb.words.map((word) => word.sentence)),
    [wordBlocks],
  )
  const hasAudio = isLive && tracks.length > 0

  const spokenRef = useRef(spoken)
  useEffect(() => {
    spokenRef.current = spoken
  }, [spoken])
  const activeSentenceRef = useRef(activeSentence)
  useEffect(() => {
    activeSentenceRef.current = activeSentence
  }, [activeSentence])
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const activeTrackIndexRef = useRef(-1)
  const playTrackRef = useRef<
    ((index: number, seekTo: number | null) => Promise<void>) | null
  >(null)
  const playingRef = useRef(playing)
  const animationFrameRef = useRef<number | null>(null)
  const speedRef = useRef<number>(speed)
  useEffect(() => {
    speedRef.current = speed
  }, [speed])
  const urlCacheRef = useRef(
    new Map<string, { url: string; expiresAt: number }>(),
  )

  useEffect(() => {
    urlCacheRef.current = new Map()
  }, [sourceId])

  // Simulated cadence (no synthesized audio).
  useEffect(() => {
    if (!playing || hasAudio) return
    const msPerWord = 60000 / (BASE_WPM * speed)
    const tick = window.setInterval(() => {
      setSpoken((i) => {
        const next = Math.min(i + 1, total - 1)
        if (i + 1 >= total) setPlaying(false)
        setActiveSentence(sentenceOfGlobal[next] ?? -1)
        return next
      })
    }, msPerWord)
    return () => window.clearInterval(tick)
  }, [playing, speed, total, hasAudio, sentenceOfGlobal])

  // The media element survives pause/resume. Media time is the source of truth;
  // word indexes are only a rendering projection of that clock.
  useEffect(() => {
    if (!hasAudio || !workspaceId || !sourceId) return

    let disposed = false
    const audio = new Audio()
    audio.playbackRate = speedRef.current
    audioRef.current = audio
    activeTrackIndexRef.current = -1

    const fetchUrl = async (clip: NarrationClip): Promise<string> => {
      const cached = urlCacheRef.current.get(clip.audioKey)
      if (cached && cached.expiresAt > Date.now() + 30_000) return cached.url
      const res = await getNarrationAudioUrl(
        workspaceId,
        sourceId,
        clip.fetchNarrationId,
      )
      urlCacheRef.current.set(clip.audioKey, {
        url: res.audio_url,
        expiresAt: Date.now() + res.expires_in * 1000,
      })
      return res.audio_url
    }

    // Called every animation frame; state changes only when the sentence does.
    // The previous sentence stays lit through pauses and while the next clip loads.
    const syncHighlight = () => {
      const track = tracks[activeTrackIndexRef.current]
      if (!track) return
      const cue = sentenceCueAt(track.cues, audio.currentTime)
      if (!cue) return
      if (cue.sentence === activeSentenceRef.current && cue.firstGlobal === spokenRef.current) {
        return
      }
      setActiveSentence(cue.sentence)
      setSpoken(cue.firstGlobal)
    }

    const animate = () => {
      if (disposed || audio.paused || !playingRef.current) {
        animationFrameRef.current = null
        return
      }
      syncHighlight()
      animationFrameRef.current = window.requestAnimationFrame(animate)
    }

    const startAnimation = () => {
      if (animationFrameRef.current == null && !document.hidden) {
        animationFrameRef.current = window.requestAnimationFrame(animate)
      }
    }

    const playIndex = async (index: number, seekTo: number | null) => {
      const track = tracks[index]
      if (disposed) return
      if (!track) {
        // Past the last clip: narration is finished, so clear the highlight.
        const lastTrack = tracks[tracks.length - 1]
        setPlaying(false)
        setActiveSentence(-1)
        if (lastTrack) setSpoken(lastTrack.globals[lastTrack.globals.length - 1])
        return
      }
      activeTrackIndexRef.current = index
      try {
        const url = await fetchUrl(track)
        if (disposed) return
        audio.src = url
        audio.playbackRate = speedRef.current
        const startAt = seekTo ?? 0
        if (audio.readyState < 1) {
          await new Promise<void>((resolve, reject) => {
            const onReady = () => {
              audio.removeEventListener('error', onError)
              resolve()
            }
            const onError = () => {
              audio.removeEventListener('loadedmetadata', onReady)
              reject(new Error('audio load failed'))
            }
            audio.addEventListener('loadedmetadata', onReady, { once: true })
            audio.addEventListener('error', onError, { once: true })
          })
          if (disposed) return
        }
        audio.currentTime = startAt
        syncHighlight()
        if (playingRef.current) await audio.play()
        if (tracks[index + 1]) {
          void fetchUrl(tracks[index + 1]).catch((error: unknown) => {
            if (disposed) return
            setAudioError(
              error instanceof Error
                ? `Couldn’t prefetch the next clip: ${error.message}`
                : 'Couldn’t prefetch the next narration clip.',
            )
          })
        }
      } catch (error: unknown) {
        if (!disposed) {
          setPlaying(false)
          setAudioError(
            error instanceof Error
              ? `Narration playback failed: ${error.message}`
              : 'Narration playback failed.',
          )
        }
      }
    }
    playTrackRef.current = playIndex

    audio.ontimeupdate = syncHighlight
    audio.onplay = startAnimation
    audio.onended = () => {
      void playIndex(activeTrackIndexRef.current + 1, 0)
    }
    const onVisibilityChange = () => {
      syncHighlight()
      if (!document.hidden) startAnimation()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      disposed = true
      document.removeEventListener('visibilitychange', onVisibilityChange)
      if (animationFrameRef.current != null) {
        window.cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
      audio.pause()
      audio.removeAttribute('src')
      playTrackRef.current = null
      activeTrackIndexRef.current = -1
      audioRef.current = null
    }
  }, [hasAudio, tracks, workspaceId, sourceId])

  useEffect(() => {
    playingRef.current = playing
    const audio = audioRef.current
    if (!audio || !hasAudio) return
    if (!playing) {
      audio.pause()
      return
    }
    if (audio.src && !audio.ended) {
      void audio.play().catch((error: unknown) => {
        setPlaying(false)
        setAudioError(
          error instanceof Error
            ? `Narration playback failed: ${error.message}`
            : 'Narration playback failed.',
        )
      })
      return
    }

    const resumeAt = spokenRef.current
    let start = tracks.findIndex((track) => track.globals.includes(resumeAt))
    if (start < 0) {
      start = tracks.findIndex((track) =>
        track.globals.some((global) => global > resumeAt),
      )
    }
    if (start < 0) start = 0
    const track = tracks[start]
    const offset = track?.globals.indexOf(resumeAt) ?? -1
    const seekTo = offset >= 0 ? track.timings[offset].s : 0
    void playTrackRef.current?.(start, seekTo)
  }, [playing, hasAudio, tracks])

  // Speed changes apply to the live audio element without restarting it.
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed
  }, [speed])

  // Keep the spoken word on screen. A chapter change snaps; a single column
  // step inside the chapter flips. Layout effect so the correction lands
  // before paint when the word is already mounted.
  useLayoutEffect(() => {
    if (!playing || spoken < 0 || colStride <= 0) return
    const seq = seqForSpoken(wordBlocks, spoken)
    if (seq < 0) return
    const index = chapterIndexForSeq(chapters, seq)
    if (index !== chapterIndexRef.current) {
      goToLocal(index, 0, 'none')
      return
    }
    const el = blockRefs.current.get(seq)
    if (!el) return
    const targetLocal = Math.floor(Math.round(el.offsetLeft / colStride) / 2)
    if (targetLocal > localSpreadRef.current) {
      const single = targetLocal === localSpreadRef.current + 1
      goToLocal(index, targetLocal, single && !isFlipping() ? 'flip' : 'none')
    }
  }, [spoken, playing, colStride, wordBlocks, chapters, chapterIndex, goToLocal, isFlipping])

  const togglePlay = useCallback(() => {
    if (!playing) setAudioError(null)
    setPlaying((p) => {
      const next = !p
      if (next && spoken + 1 >= total) setSpoken(-1) // restart from top at the end
      return next
    })
  }, [playing, spoken, total])

  const registerBlock = useCallback((seq: number, el: HTMLElement | null) => {
    if (el) blockRefs.current.set(seq, el)
    else blockRefs.current.delete(seq)
  }, [])

  const registerMeasure = useCallback((seq: number, el: HTMLElement | null) => {
    if (el) measureRefs.current.set(seq, el)
    else measureRefs.current.delete(seq)
  }, [])

  const restartNarration = useCallback(() => {
    setPlaying(false)
    setSpoken(-1)
    setActiveSentence(-1)
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      activeTrackIndexRef.current = -1
    }
  }, [])

  // --- Fullscreen ---------------------------------------------------------
  const toggleFullscreen = useCallback(async () => {
    if (fullscreen || isBrowserFullscreen()) {
      if (isBrowserFullscreen()) await document.exitFullscreen()
      else setFullscreen(false)
      return
    }
    try {
      await document.documentElement.requestFullscreen()
    } catch {
      setFullscreen(true)
    }
  }, [fullscreen])

  useEffect(() => {
    const onFullscreenChange = () => setFullscreen(isBrowserFullscreen())
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  useEffect(() => {
    return () => {
      if (document.fullscreenElement) void document.exitFullscreen()
    }
  }, [])

  // A soft two-note chime when the session timer completes. Uses Web Audio so
  // there's no asset to ship; a gentle gain envelope keeps it pleasant.
  const playChime = useCallback(() => {
    try {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return
      const ctx = chimeCtxRef.current ?? new Ctx()
      chimeCtxRef.current = ctx
      if (ctx.state === 'suspended') void ctx.resume()
      const now = ctx.currentTime
      // Two ascending notes (E5 → A5), each a short sine with a soft fade.
      ;[
        { freq: 659.25, at: 0 },
        { freq: 880.0, at: 0.18 },
      ].forEach(({ freq, at }) => {
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.type = 'sine'
        osc.frequency.value = freq
        const start = now + at
        gain.gain.setValueAtTime(0.0001, start)
        gain.gain.exponentialRampToValueAtTime(0.12, start + 0.03)
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.9)
        osc.connect(gain).connect(ctx.destination)
        osc.start(start)
        osc.stop(start + 0.95)
      })
    } catch {
      // Audio is a nicety; ignore environments that block it.
    }
  }, [])

  // --- Session timer ------------------------------------------------------
  useEffect(() => {
    if (showBreak || !timerRunning) return
    const tick = window.setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          playChime()
          setShowBreak(true)
          return 0
        }
        return r - 1
      })
    }, 1000)
    return () => window.clearInterval(tick)
  }, [showBreak, timerRunning, playChime])

  const dismissBreak = (reset: boolean) => {
    setShowBreak(false)
    if (reset) setRemaining(SESSION_SECONDS)
  }

  // --- Render -------------------------------------------------------------
  const runningChapter = visibleChapter?.title ?? ''
  const located = geometryReady
    ? spreadPageNumbers(columnCounts, activeChapterIndex, safeLocal)
    : null
  const leftNum = located?.left ?? (spreadIndex ?? safeLocal) * 2 + 1
  const rightNum =
    located?.right ??
    Math.min((spreadIndex ?? safeLocal) * 2 + 2, Math.max(pageCount, leftNum))

  const opening = (isLive && live.loading) || (!isLive && isLoading)
  const noBook = !isLive && !isLoading
  const emptyState = isLive && !live.loading && !live.error && blocks.length === 0
  const showBook = isLive && !live.loading && live.error == null && !emptyState
  const progressLabel =
    geometryReady && pageCount > 0 ? readerProgressLabel(rightNum, pageCount) : null

  return (
    <section
      ref={readerRootRef}
      className={`reader${evening ? ' reader--warm' : ''}${fullscreen ? ' reader--fullscreen' : ''}${chromeVisible ? '' : ' reader--chrome-hidden'}`}
      {...idleBind}
    >
      <div className="reader__topline" {...chromeHover}>
        <div className="reader__topline-left">
          <button
            type="button"
            className="reader__timer-btn"
            onClick={() => setTocOpen((o) => !o)}
            aria-expanded={tocOpen}
            aria-label="Table of contents"
            title="Contents"
          >
            <List size={14} />
          </button>
          <button
            type="button"
            className={`reader__timer-btn${
              spreadIndex != null && bookmarkSpread === spreadIndex ? ' is-active' : ''
            }`}
            onClick={toggleBookmark}
            disabled={!bookmarkKey || spreadIndex == null}
            aria-pressed={spreadIndex != null && bookmarkSpread === spreadIndex}
            aria-label={
              spreadIndex != null && bookmarkSpread === spreadIndex
                ? 'Remove bookmark'
                : 'Bookmark this page'
            }
            title={
              spreadIndex != null && bookmarkSpread === spreadIndex
                ? 'Remove bookmark'
                : 'Bookmark this page'
            }
          >
            {spreadIndex != null && bookmarkSpread === spreadIndex ? (
              <BookmarkCheck size={14} />
            ) : (
              <Bookmark size={14} />
            )}
          </button>
        </div>
        <div className="reader__session">
          <button
            type="button"
            className="reader__timer-btn"
            onClick={() => void toggleFullscreen()}
            aria-pressed={fullscreen}
            aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <span className="reader__timer" aria-label="Session time remaining">
            <Clock size={14} aria-hidden="true" />
            {formatTime(remaining)}
          </span>
          <button
            type="button"
            className="reader__timer-btn"
            onClick={() => setTimerRunning((r) => !r)}
            aria-label={timerRunning ? 'Pause session timer' : 'Start session timer'}
          >
            {timerRunning ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <button
            type="button"
            className="reader__timer-btn"
            onClick={() => {
              setRemaining(SESSION_SECONDS)
              setTimerRunning(false)
            }}
            aria-label="Reset session timer"
          >
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      <div className="reader__stage">
        <div
          className="reader__book"
          style={{ '--reader-gap': `${GAP}px` } as CSSProperties}
        >
        {showBook && (
          <div className="reader__running-head" aria-hidden="true">
            {runningChapter}
          </div>
        )}
        <div className="reader__viewport" ref={viewportRef}>
          {opening ? (
            <div className="reader__empty reader__opening" role="status">
              <div className="reader__opening-book" aria-hidden="true">
                <span className="reader__opening-cover" />
                <span className="reader__opening-page reader__opening-page--left" />
                <span className="reader__opening-page reader__opening-page--right" />
                <span className="reader__opening-leaf reader__opening-leaf--one" />
                <span className="reader__opening-leaf reader__opening-leaf--two" />
                <span className="reader__opening-spine" />
              </div>
              <p className="reader__empty-title reader__opening-title">{ebookTitle}</p>
              <div className="reader__opening-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            </div>
          ) : live.error && isLive ? (
            <div className="reader__empty" role="alert">
              <p className="reader__empty-title">Couldn't open this source.</p>
              <p className="reader__empty-copy">{live.error}</p>
            </div>
          ) : noBook ? (
            <div className="reader__empty">
              <p className="reader__empty-title">No book yet.</p>
              <p className="reader__empty-copy">
                Favorite a book in the library, or generate an ebook for a source.
              </p>
            </div>
          ) : emptyState ? (
            <div className="reader__empty">
              <p className="reader__empty-title">Nothing to read yet.</p>
              <p className="reader__empty-copy">
                This source hasn't been structured into readable text. Run the production
                pipeline on it from the console, then come back.
              </p>
            </div>
          ) : (
            <>
              <div
                className="reader__flow"
                ref={flowRef}
                onMouseUp={openSelectionDefine}
                onTouchEnd={openSelectionDefine}
                style={
                  {
                    '--reader-spread': safeLocal,
                    '--reader-gap': `${GAP}px`,
                  } as CSSProperties
                }
              >
                {visibleWordBlocks.map(({ block, words }) => (
                  <ReaderBlock
                    key={block.id}
                    block={block}
                    words={words}
                    progress={sentenceProgress(words, activeSentence)}
                    narrated={words.length > 0 && narratedGlobals.has(words[0].global)}
                    chapterStart={false}
                    isTarget={targetSeq != null && block.seq === targetSeq}
                    termByWord={termByWord}
                    onTermClick={onTermClick}
                    registerRef={registerBlock}
                  />
                ))}
              </div>
              {measureChapter && geometry.width > 0 && geometry.height > 0 && (
                <div
                  className="reader__measure"
                  aria-hidden="true"
                  style={{ width: geometry.width, height: geometry.height }}
                >
                  <div
                    ref={measureFlowRef}
                    className="reader__flow"
                    style={
                      {
                        columnWidth: `${(geometry.width - GAP) / 2}px`,
                        '--reader-spread': 0,
                        '--reader-gap': `${GAP}px`,
                      } as CSSProperties
                    }
                  >
                    {wordBlocksForChapter(wordBlocks, measureChapter).map(({ block, words }) => (
                      <ReaderBlock
                        key={block.id}
                        block={block}
                        words={words}
                        progress={-1}
                        narrated={false}
                        chapterStart={false}
                        isTarget={false}
                        termByWord={NO_TERMS}
                        onTermClick={ignoreTermClick}
                        registerRef={registerMeasure}
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {showBook && <div className="reader__spine" aria-hidden="true" />}

          {tocOpen && (
            <>
              <div
                className="reader__toc-backdrop"
                onClick={() => setTocOpen(false)}
                aria-hidden="true"
              />
              <nav className="reader__toc" aria-label="Table of contents">
                <div className="reader__toc-head">
                  <span>Contents</span>
                  <button
                    type="button"
                    className="reader__toc-close"
                    onClick={() => setTocOpen(false)}
                    aria-label="Close contents"
                  >
                    <X size={14} />
                  </button>
                </div>
                {toc.length === 0 && <p className="reader__toc-empty">No chapters.</p>}
                {toc.map((ch) => (
                  <div key={ch.seq} className="reader__toc-chapter-group">
                    <button
                      type="button"
                      className="reader__toc-chapter"
                      onClick={() => jumpToSeq(ch.seq)}
                    >
                      {ch.title}
                    </button>
                    {ch.sections.map((s) => (
                      <button
                        key={s.seq}
                        type="button"
                        className="reader__toc-section"
                        onClick={() => jumpToSeq(s.seq)}
                      >
                        {s.title}
                      </button>
                    ))}
                  </div>
                ))}
              </nav>
            </>
          )}
        </div>
        {showBook && (
          <>
            <span className="reader__folio reader__folio--left" aria-hidden="true">
              {leftNum}
            </span>
            {rightNum > leftNum && (
              <span className="reader__folio reader__folio--right" aria-hidden="true">
                {rightNum}
              </span>
            )}
          </>
        )}
        </div>
        <button
          type="button"
          className="reader__zone reader__zone--prev"
          onClick={() => turn(-1)}
          disabled={atStart}
          aria-label="Previous page"
        >
          <ChevronLeft size={22} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="reader__zone reader__zone--next"
          onClick={() => turn(1)}
          disabled={atEnd}
          aria-label="Next page"
        >
          <ChevronRight size={22} aria-hidden="true" />
        </button>
      </div>

      <div className="reader__footer" {...chromeHover}>
        <div className="reader__player">
          <button
            type="button"
            className="reader__turn"
            onClick={togglePlay}
            aria-label={playing ? 'Pause narration' : 'Play narration'}
          >
            {playing ? <Pause size={20} /> : <Play size={20} />}
          </button>
          <button
            type="button"
            className="reader__timer-btn"
            onClick={restartNarration}
            aria-label="Restart narration"
            title="Restart narration"
          >
            <RotateCcw size={14} />
          </button>
          <span className="reader__timer" aria-label="Narration">
            <Volume2 size={14} aria-hidden="true" />
            {spoken < 0
              ? hasAudio
                ? 'Audio narration'
                : 'Narration'
              : `${Math.min(spoken + 1, total)} / ${total} words`}
          </span>
          <label className="reader__speed">
            <span className="reader__speed-label">Speed</span>
            <select
              className="reader__speed-select"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value) as (typeof SPEEDS)[number])}
              aria-label="Narration speed"
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="reader__pager">
          <button
            type="button"
            className="reader__turn"
            onClick={() => turn(-1)}
            disabled={atStart}
            aria-label="Previous pages"
          >
            <ChevronLeft size={22} />
          </button>
          <span className="reader__pageinfo" aria-label="Progress through the book">
            {pageCount > 0
              ? geometryReady
                ? `${progressLabel} · ${pageCount} pages`
                : `Page ${leftNum}`
              : 'No content'}
          </span>
          <button
            type="button"
            className="reader__turn"
            onClick={() => turn(1)}
            disabled={atEnd}
            aria-label="Next pages"
          >
            <ChevronRight size={22} />
          </button>
        </div>
        {speed > SPEED_WARN_ABOVE && (
          <p className="reader__speed-warn" role="status">
            <AlertTriangle size={14} aria-hidden="true" />
            High speeds boost coverage but reduce retention — slow down for material you need to
            remember.
          </p>
        )}
        {(live.narrationWarning || audioError) && (
          <p className="reader__audio-error" role="alert">
            <AlertTriangle size={14} aria-hidden="true" />
            {audioError ?? live.narrationWarning}
          </p>
        )}
      </div>

      {showBreak && (
        <div className="reader__break" role="dialog" aria-label="Break reminder">
          <div className="reader__break-card">
            <Coffee size={28} aria-hidden="true" />
            <h3 className="reader__break-title">Nice work.</h3>
            <p className="reader__break-copy">
              Take a 5-minute break away from the screen. Stepping away helps your memory
              consolidate what you just read.
            </p>
            <div className="reader__break-actions">
              <button
                type="button"
                className="reader__break-btn reader__break-btn--primary"
                onClick={() => dismissBreak(false)}
              >
                Start break
              </button>
              <button type="button" className="reader__break-btn" onClick={() => dismissBreak(true)}>
                Keep reading
              </button>
            </div>
          </div>
        </div>
      )}

      {definePop && (
        <>
          <div
            className="reader__term-backdrop"
            onClick={() => setDefinePop(null)}
            aria-hidden="true"
          />
          <aside
            className="reader__term-pop"
            style={{ left: definePop.left, bottom: definePop.bottom, top: 'auto' }}
            role="dialog"
            aria-label={
              definePop.kind === 'wiki'
                ? `Definition of ${wikiPopEntry?.preferred_label ?? 'term'}`
                : `Define ${definePop.term}`
            }
          >
            {definePop.kind === 'wiki' && wikiPopEntry && (
              <>
                <div className="reader__term-head">
                  <span className="reader__term-label">{wikiPopEntry.preferred_label}</span>
                  <button
                    type="button"
                    className="reader__toc-close"
                    onClick={() => setDefinePop(null)}
                    aria-label="Close definition"
                  >
                    <X size={14} />
                  </button>
                </div>
                <span className="reader__term-provenance">From wiki</span>
                <p className="reader__term-definition">{wikiPopEntry.definition}</p>
                {onOpen && sourceId && (
                  <button
                    type="button"
                    className="reader__term-discuss"
                    onClick={() => {
                      setDefinePop(null)
                      onOpen('discussions', { sourceId, targetId: null, projectId: null })
                    }}
                  >
                    Discuss with assistant
                  </button>
                )}
              </>
            )}

            {definePop.kind === 'miss' && (
              <>
                <div className="reader__term-head">
                  <span className="reader__term-label">{definePop.term}</span>
                  <button
                    type="button"
                    className="reader__toc-close"
                    onClick={() => setDefinePop(null)}
                    aria-label="Close definition"
                  >
                    <X size={14} />
                  </button>
                </div>
                <p className="reader__term-hint">Not in the wiki yet.</p>
                <div className="reader__term-actions">
                  <button
                    type="button"
                    className="reader__term-action reader__term-action--primary"
                    onClick={() => void runDefine('contextual')}
                    disabled={!workspaceId}
                  >
                    Contextual definition
                  </button>
                  <button
                    type="button"
                    className="reader__term-action"
                    onClick={() => void runDefine('general')}
                    disabled={!workspaceId}
                  >
                    General definition
                  </button>
                </div>
              </>
            )}

            {definePop.kind === 'generated' && (
              <>
                <div className="reader__term-head">
                  <span className="reader__term-label">{definePop.term}</span>
                  <button
                    type="button"
                    className="reader__toc-close"
                    onClick={() => setDefinePop(null)}
                    aria-label="Close definition"
                  >
                    <X size={14} />
                  </button>
                </div>
                <span className="reader__term-provenance">
                  {definePop.mode === 'contextual'
                    ? 'From nearby paragraphs'
                    : 'General definition'}
                </span>
                {definePop.loading ? (
                  <div
                    className="reader__term-generating"
                    aria-live="polite"
                    aria-busy="true"
                  >
                    <div className="reader__term-ink" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </div>
                    <p className="reader__term-hint reader__term-hint--pulse">
                      Composing definition…
                    </p>
                  </div>
                ) : (
                  <textarea
                    ref={defineEditRef}
                    className="reader__term-edit reader__term-edit--reveal"
                    value={definePop.definition}
                    rows={1}
                    readOnly={!canEditWiki}
                    onChange={(event) =>
                      setDefinePop({
                        ...definePop,
                        definition: event.target.value,
                      })
                    }
                  />
                )}
                {definePop.error && (
                  <p className="reader__term-error" role="alert">
                    {definePop.error}
                  </p>
                )}
                <div className="reader__term-actions">
                  {canEditWiki ? (
                    <button
                      type="button"
                      className="reader__term-action reader__term-action--primary"
                      onClick={() => void saveGeneratedToWiki()}
                      disabled={
                        definePop.loading ||
                        definePop.saving ||
                        !definePop.definition.trim() ||
                        !workspaceId
                      }
                    >
                      {definePop.saving ? 'Saving…' : 'Add to wiki'}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="reader__term-action"
                    onClick={() => setDefinePop(null)}
                    disabled={definePop.saving}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </aside>
        </>
      )}
    </section>
  )
}

// A block's narration progress: the active sentence when it is in this block,
// ALL_READ once narration has passed the block, -1 before it reaches the block.
// Blocks away from the active sentence keep the same value, so memo skips them.
const ALL_READ = Number.POSITIVE_INFINITY

function sentenceProgress(words: SpokenWord[], activeSentence: number): number {
  if (activeSentence < 0 || words.length === 0) return -1
  if (activeSentence > words[words.length - 1].sentence) return ALL_READ
  if (activeSentence < words[0].sentence) return -1
  return activeSentence
}

const ReaderBlock = memo(function ReaderBlock({
  block,
  words,
  progress,
  narrated,
  chapterStart,
  isTarget,
  termByWord,
  onTermClick,
  registerRef,
}: {
  block: Block
  words: SpokenWord[]
  progress: number
  narrated: boolean
  chapterStart: boolean
  isTarget: boolean
  termByWord: Map<number, string>
  onTermClick: (entryId: string, target: HTMLElement) => void
  registerRef: (seq: number, el: HTMLElement | null) => void
}) {
  const cls = `${chapterStart ? ' reader__chapter-start' : ''}${isTarget ? ' is-target' : ''}`
  const ref = (el: HTMLElement | null) => registerRef(block.seq, el)
  if (block.kind === 'heading') {
    if (block.level === 1)
      return (
        <h1 ref={ref} className={`reader__h1${cls}`} data-segment-id={block.id}>
          {block.text}
        </h1>
      )
    return (
      <h2 ref={ref} className={`reader__h2${cls}`} data-segment-id={block.id}>
        {block.text}
      </h2>
    )
  }
  const variantCls = block.variant ? ` reader__para--${block.variant}` : ''

  const sentences: { sentence: number; words: SpokenWord[] }[] = []
  for (const word of words) {
    const last = sentences[sentences.length - 1]
    if (last && last.sentence === word.sentence) last.words.push(word)
    else sentences.push({ sentence: word.sentence, words: [word] })
  }

  const sentenceClass = (sentence: number) => {
    if (sentence === progress) return 'reader__sentence reader__band'
    if (narrated && sentence < progress) return 'reader__sentence is-read'
    return 'reader__sentence'
  }

  const renderWord = (word: SpokenWord) => {
    const style = `${word.em ? ' is-em' : ''}${word.strong ? ' is-strong' : ''}`
    const termId = termByWord.get(word.global)
    if (termId) {
      return (
        <span key={word.global} className={`reader__word${style}`} data-global={word.global}>
          <button
            type="button"
            className="reader__term"
            onClick={(event) => {
              event.stopPropagation()
              onTermClick(termId, event.currentTarget)
            }}
          >
            {word.text}
          </button>{' '}
        </span>
      )
    }
    return (
      <span key={word.global} className={`reader__word${style}`} data-global={word.global}>
        {word.text}{' '}
      </span>
    )
  }

  return (
    <p ref={ref} className={`reader__para${variantCls}${cls}`} data-segment-id={block.id}>
      {sentences.map(({ sentence, words: sentenceWords }) => (
        <span key={sentence} className={sentenceClass(sentence)} data-sentence={sentence}>
          {sentenceWords.map(renderWord)}
        </span>
      ))}
    </p>
  )
})
