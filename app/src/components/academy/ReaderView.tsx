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
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { useWorkspace } from '../../features/workspace/workspaceContext'
import { useWorkspaceData } from '../../features/workspace/workspaceDataContext'
import {
  MOCK_BLOCKS,
  buildBlocks,
  buildNarration,
  buildNarrationClips,
  globalsFromDomSelection,
  matchWikiTerms,
  resolveReaderSelection,
  timingIndexAt,
  type Block,
  type NarrationClip,
  type SpokenWord,
} from '../../lib/readerContent'
import { defineReaderTerm, type ReaderDefineMode } from '../../lib/readerDefineApi'
import { ApiError } from '../../lib/apiClient'
import { createWikiEntry } from '../../lib/wikiApi'
import { sourceDisplayName } from '../../lib/sourceDisplay'
import type { AcademyPage, AcademyScope } from './types'
import { useIdleChrome } from './useIdleChrome'
import { useReaderFlip } from './useReaderFlip'
import {
  getNarrationAudioUrl,
  listAllSourceSegments,
  listSourceChapters,
  listSourceNarration,
  type NarrationSegment,
} from '../../lib/sourcesApi'

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
  const { sources, wikiEntries, addWikiEntry } = useWorkspaceData()
  const workspaceId = activeWorkspace?.id ?? null
  const activeSource = sources.find((source) => source.id === sourceId)
  const ebookTitle = activeSource ? sourceDisplayName(activeSource) : 'Ebook'

  const [live, setLive] = useState<LiveContent>({
    blocks: [],
    narration: NO_NARRATION,
    loading: false,
    error: null,
    narrationWarning: null,
  })

  // Fetch is keyed on (workspace, source); the sync setLive puts the viewport
  // into its loading state for the whole request, same pattern as the
  // measurement effect below. Narration is optional — a failure there never
  // blocks reading, but we surface a soft warning instead of silent fallback.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!sourceId || !workspaceId) return
    let cancelled = false
    setLive({
      blocks: [],
      narration: NO_NARRATION,
      loading: true,
      error: null,
      narrationWarning: null,
    })
    Promise.all([
      listAllSourceSegments(workspaceId, sourceId),
      listSourceChapters(workspaceId, sourceId),
      listSourceNarration(workspaceId, sourceId).then(
        (rows) => ({ rows, warning: null as string | null }),
        (error: unknown) => ({
          rows: [] as NarrationSegment[],
          warning:
            error instanceof Error
              ? `Couldn’t load narration audio (${error.message}). Using estimated pacing.`
              : 'Couldn’t load narration audio. Using estimated pacing.',
        }),
      ),
    ])
      .then(([segments, chapters, narrationResult]) => {
        if (cancelled) return
        const narration = new Map<string, NarrationSegment>()
        for (const row of narrationResult.rows) {
          if (row.words.length > 0) narration.set(row.segment_id, row)
        }
        setLive({
          blocks: buildBlocks(segments, chapters),
          narration,
          loading: false,
          error: null,
          narrationWarning: narrationResult.warning,
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Failed to load the source.'
        setLive({
          blocks: [],
          narration: NO_NARRATION,
          loading: false,
          error: message,
          narrationWarning: null,
        })
      })
    return () => {
      cancelled = true
    }
  }, [sourceId, workspaceId])
  /* eslint-enable react-hooks/set-state-in-effect */

  const isLive = sourceId != null
  const blocks = isLive ? live.blocks : MOCK_BLOCKS
  const { wordBlocks, total } = useMemo(() => buildNarration(blocks), [blocks])

  const [spread, setSpread] = useState(0)
  const [spreadCount, setSpreadCount] = useState(1)
  const [pageCount, setPageCount] = useState(1)
  const [colStride, setColStride] = useState(0)
  const [chapterCols, setChapterCols] = useState<{ col: number; title: string }[]>([])
  const [tocOpen, setTocOpen] = useState(false)
  const [viewportTick, setViewportTick] = useState(0)

  // Persistent bookmark: remembers the reader's spread across sessions, keyed
  // by source. `bookmarkSpread` mirrors the stored value for the button state.
  const bookmarkKey = sourceId ? `arsenal:reader-bookmark:${sourceId}` : null
  const [bookmarkSpread, setBookmarkSpread] = useState<number | null>(null)
  const bookmarkRestoredRef = useRef(false)

  // Narration / audio state. `spoken` is the global index of the word currently
  // being read (-1 = not started). Playback is a simulated cadence until the
  // narration stage's synthesized audio is wired in; speed scales the WPM.
  const [playing, setPlaying] = useState(false)
  const [spoken, setSpoken] = useState(-1)
  const [activeSpoken, setActiveSpoken] = useState(-1)
  const [preciseHighlight, setPreciseHighlight] = useState(false)
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
  const blockRefs = useRef<Map<number, HTMLElement>>(new Map())

  // Mirror of the (clamped) spread for event handlers, so rapid successive
  // turns in the same frame never read a stale value.
  const spreadRef = useRef(0)

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
    spreadRef.current = 0
    setSpread(0)
    setPlaying(false)
    setSpoken(-1)
    setActiveSpoken(-1)
    setPreciseHighlight(false)
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
  const termByWord = useMemo(
    () => matchWikiTerms(wordBlocks, wikiEntries),
    [wordBlocks, wikiEntries],
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
  // The browser lays the stream into fixed-height columns (two visible per
  // spread); we only measure how many columns/spreads exist and where chapter
  // starts land, for nav + the running header. Recomputed on resize.
  /* eslint-disable react-hooks/set-state-in-effect */
  useLayoutEffect(() => {
    if (blocks.length === 0) {
      setSpreadCount(1)
      setPageCount(1)
      setColStride(0)
      setChapterCols([])
      return
    }
    const vp = viewportRef.current
    const flow = flowRef.current
    if (!vp || !flow) return
    const width = vp.clientWidth
    if (width <= 0) return

    // column-width only accepts lengths (percentage calc() is invalid CSS and
    // gets dropped), so the two-page column width must be set in pixels here,
    // before the column extent below is measured.
    flow.style.columnWidth = `${(width - GAP) / 2}px`

    const stride = (width + GAP) / 2 // one column + one gap
    const lastEl = blockRefs.current.get(blocks[blocks.length - 1].seq)
    const lastRight = lastEl ? lastEl.offsetLeft + lastEl.offsetWidth : 0
    const extent = Math.max(flow.scrollWidth, lastRight)
    const totalColumns = Math.max(1, Math.round((extent + GAP) / stride))
    const spreads = Math.max(1, Math.ceil(totalColumns / 2))

    const cols: { col: number; title: string }[] = []
    for (const b of blocks) {
      if (!b.isChapterStart) continue
      const el = blockRefs.current.get(b.seq)
      if (!el) continue
      cols.push({ col: Math.round(el.offsetLeft / stride), title: b.chapterTitle })
    }

    setColStride(stride)
    setPageCount(totalColumns)
    setSpreadCount(spreads)
    setChapterCols(cols)
  }, [blocks, viewportTick])
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    const ro = new ResizeObserver(() => {
      // Reflow invalidates the flip overlay's frozen page clones.
      cancelFlip()
      setViewportTick((t) => t + 1)
    })
    ro.observe(vp)
    return () => ro.disconnect()
  }, [cancelFlip])

  const lastSpread = Math.max(spreadCount - 1, 0)
  const safeSpread = Math.min(spread, lastSpread)

  useEffect(() => {
    spreadRef.current = safeSpread
  })

  // Every spread change funnels through here; `mode` picks the motion.
  // 'flip' is only honest for single-page turns — jumps use 'fade' (a short
  // opacity dip) or 'none' (instant snap). Reduced motion always snaps.
  const goToSpread = useCallback(
    (target: number, mode: 'flip' | 'fade' | 'none') => {
      const clamped = Math.min(Math.max(target, 0), lastSpread)
      const current = spreadRef.current
      if (clamped === current) return
      spreadRef.current = clamped
      setSpread(clamped)
      if (reducedMotion || mode === 'none') {
        cancelFlip()
        return
      }
      if (mode === 'flip') {
        flipTo(clamped > current ? 1 : -1, current)
      } else {
        cancelFlip()
        viewportRef.current?.animate({ opacity: [0.25, 1] }, { duration: 180, easing: 'ease-out' })
      }
    },
    [lastSpread, reducedMotion, cancelFlip, flipTo],
  )

  // Land on the deep-link target once columns have been measured.
  useEffect(() => {
    const target = pendingTargetRef.current
    if (target == null || colStride <= 0 || blocks.length === 0) return
    const el = blockRefs.current.get(target)
    pendingTargetRef.current = null
    if (!el) return
    const col = Math.round(el.offsetLeft / colStride)
    goToSpread(Math.floor(col / 2), 'none')
    setTargetSeq(target)
  }, [colStride, blocks, goToSpread])

  // Restore the saved bookmark once columns are measured. A deep-link target
  // (opening to a specific segment) always takes precedence. Reads storage
  // directly to avoid racing the async bookmark-state load.
  useEffect(() => {
    if (bookmarkRestoredRef.current) return
    if (colStride <= 0 || blocks.length === 0) return
    bookmarkRestoredRef.current = true
    if (seg != null || !bookmarkKey) return
    const raw = window.localStorage.getItem(bookmarkKey)
    const val = raw != null ? Number(raw) : NaN
    if (Number.isFinite(val)) goToSpread(val, 'none')
  }, [colStride, blocks, seg, bookmarkKey, goToSpread])

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
      goToSpread(spreadRef.current + delta, 'flip')
    },
    [goToSpread],
  )

  const jumpToSeq = useCallback(
    (target: number) => {
      const el = blockRefs.current.get(target)
      if (el && colStride > 0) {
        const col = Math.round(el.offsetLeft / colStride)
        goToSpread(Math.floor(col / 2), 'fade')
      }
      setTocOpen(false)
      setDefinePop(null)
    },
    [colStride, goToSpread],
  )

  // Toggle a bookmark at the current spread. Saving again on the bookmarked
  // page removes it; otherwise the bookmark moves to the current page.
  const toggleBookmark = useCallback(() => {
    if (!bookmarkKey) return
    setBookmarkSpread((prev) => {
      if (prev === safeSpread) {
        window.localStorage.removeItem(bookmarkKey)
        return null
      }
      window.localStorage.setItem(bookmarkKey, String(safeSpread))
      return safeSpread
    })
  }, [bookmarkKey, safeSpread])

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
  // Two engines share the `spoken` index. When synthesized audio exists
  // (narration_segments rows), an HTMLAudioElement plays each chapter clip
  // and word timings drive the highlight. Consecutive paragraphs that share
  // an audio_path stay on one file. Otherwise a simulated WPM cadence walks
  // the words (reader-recommendations §6 fallback).
  const tracks = useMemo<NarrationClip[]>(
    () => buildNarrationClips(wordBlocks, live.narration),
    [live.narration, wordBlocks],
  )
  const narratedGlobals = useMemo(
    () => new Set(tracks.flatMap((track) => track.globals)),
    [tracks],
  )
  const hasAudio = isLive && tracks.length > 0
  const hasEstimatedAlignment = tracks.some(
    (track) => track.alignmentSource === 'estimated',
  )

  const spokenRef = useRef(spoken)
  useEffect(() => {
    spokenRef.current = spoken
  }, [spoken])
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
        if (i + 1 >= total) {
          setPlaying(false)
          setActiveSpoken(total - 1)
          return total - 1
        }
        const next = i + 1
        setPreciseHighlight(false)
        setActiveSpoken(next)
        return next
      })
    }, msPerWord)
    return () => window.clearInterval(tick)
  }, [playing, speed, total, hasAudio])

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

    const syncHighlight = () => {
      const track = tracks[activeTrackIndexRef.current]
      if (!track) return
      const index = timingIndexAt(track.timings, audio.currentTime)
      if (index < 0) {
        setActiveSpoken(-1)
        return
      }
      const global = track.globals[index]
      setSpoken((current) => (current === global ? current : global))
      setPreciseHighlight(track.alignmentSource !== 'estimated')
      setActiveSpoken(
        audio.currentTime < track.timings[index].e ? global : -1,
      )
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
      if (!track || disposed) {
        if (!disposed) setPlaying(false)
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
      setActiveSpoken(-1)
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

  // Keep the spoken word on screen: when narration crosses into a column beyond
  // the current spread, turn the page to follow it.
  useEffect(() => {
    if (!playing || spoken < 0 || colStride <= 0) return
    let seq = -1
    for (const wb of wordBlocks) {
      const hit = wb.words.find((w) => w.global === spoken)
      if (hit) {
        seq = hit.seq
        break
      }
    }
    if (seq < 0) return
    const el = blockRefs.current.get(seq)
    if (!el) return
    const targetSpread = Math.floor(Math.round(el.offsetLeft / colStride) / 2)
    if (targetSpread > spreadRef.current) {
      // Turn the page like the user would, but never cut short a flip the
      // user started, and don't fake a flip across a multi-spread jump.
      const single = targetSpread === spreadRef.current + 1
      goToSpread(targetSpread, single && !isFlipping() ? 'flip' : 'none')
    }
  }, [spoken, playing, colStride, wordBlocks, goToSpread, isFlipping])

  const togglePlay = useCallback(() => {
    if (!playing) setAudioError(null)
    setPlaying((p) => {
      const next = !p
      if (next && spoken + 1 >= total) setSpoken(-1) // restart from top at the end
      return next
    })
  }, [playing, spoken, total])

  const restartNarration = useCallback(() => {
    setPlaying(false)
    setSpoken(-1)
    setActiveSpoken(-1)
    setPreciseHighlight(false)
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      activeTrackIndexRef.current = -1
    }
  }, [])

  // The active sentence, used to draw the soft "reading band" ahead of the word.
  const speakingSentence = useMemo(() => {
    if (activeSpoken < 0) return -1
    for (const wb of wordBlocks) {
      const hit = wb.words.find((w) => w.global === activeSpoken)
      if (hit) return hit.sentence
    }
    return -1
  }, [activeSpoken, wordBlocks])

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
  let runningChapter = ''
  const leftCol = safeSpread * 2
  for (const c of chapterCols) {
    if (c.col <= leftCol) runningChapter = c.title
    else break
  }

  const leftNum = safeSpread * 2 + 1
  const rightNum = Math.min(safeSpread * 2 + 2, pageCount)

  const emptyState = isLive && !live.loading && !live.error && blocks.length === 0
  const showBook = !(isLive && (live.loading || live.error != null)) && !emptyState
  const progressPct = pageCount > 0 ? Math.round((rightNum / pageCount) * 100) : 0

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
              bookmarkSpread === safeSpread ? ' is-active' : ''
            }`}
            onClick={toggleBookmark}
            disabled={!bookmarkKey}
            aria-pressed={bookmarkSpread === safeSpread}
            aria-label={
              bookmarkSpread === safeSpread ? 'Remove bookmark' : 'Bookmark this page'
            }
            title={bookmarkSpread === safeSpread ? 'Remove bookmark' : 'Bookmark this page'}
          >
            {bookmarkSpread === safeSpread ? (
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
          {live.loading && isLive ? (
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
          ) : emptyState ? (
            <div className="reader__empty">
              <p className="reader__empty-title">Nothing to read yet.</p>
              <p className="reader__empty-copy">
                This source hasn't been structured into readable text. Run the production
                pipeline on it from the console, then come back.
              </p>
            </div>
          ) : (
            <div
              className="reader__flow"
              ref={flowRef}
              onMouseUp={openSelectionDefine}
              onTouchEnd={openSelectionDefine}
              style={
                {
                  '--reader-spread': safeSpread,
                  '--reader-gap': `${GAP}px`,
                } as CSSProperties
              }
            >
              {wordBlocks.map(({ block, words }, i) => (
                <ReaderBlock
                  key={block.id}
                  block={block}
                  words={words}
                  spoken={spoken}
                  activeSpoken={activeSpoken}
                  preciseHighlight={preciseHighlight}
                  narratedGlobals={narratedGlobals}
                  speakingSentence={speakingSentence}
                  chapterStart={block.isChapterStart && i > 0}
                  isTarget={targetSeq != null && block.seq === targetSeq}
                  termByWord={termByWord}
                  onTermClick={onTermClick}
                  registerRef={(el) => {
                    if (el) blockRefs.current.set(block.seq, el)
                    else blockRefs.current.delete(block.seq)
                  }}
                />
              ))}
            </div>
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
          disabled={safeSpread === 0}
          aria-label="Previous page"
        >
          <ChevronLeft size={22} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="reader__zone reader__zone--next"
          onClick={() => turn(1)}
          disabled={safeSpread >= lastSpread}
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
                ? hasEstimatedAlignment
                  ? 'Audio narration · sentence sync'
                  : 'Audio narration'
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
            disabled={safeSpread === 0}
            aria-label="Previous pages"
          >
            <ChevronLeft size={22} />
          </button>
          <span className="reader__pageinfo" aria-label="Progress through the book">
            {pageCount > 0 ? `${progressPct}% · ${pageCount} pages` : 'No content'}
          </span>
          <button
            type="button"
            className="reader__turn"
            onClick={() => turn(1)}
            disabled={safeSpread >= lastSpread}
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
                      onOpen('discussions', { sourceId, targetId: null })
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

function ReaderBlock({
  block,
  words,
  spoken,
  activeSpoken,
  preciseHighlight,
  narratedGlobals,
  speakingSentence,
  chapterStart,
  isTarget,
  termByWord,
  onTermClick,
  registerRef,
}: {
  block: Block
  words: SpokenWord[]
  spoken: number
  activeSpoken: number
  preciseHighlight: boolean
  narratedGlobals: Set<number>
  speakingSentence: number
  chapterStart: boolean
  isTarget: boolean
  termByWord: Map<number, string>
  onTermClick: (entryId: string, target: HTMLElement) => void
  registerRef: (el: HTMLElement | null) => void
}) {
  const cls = `${chapterStart ? ' reader__chapter-start' : ''}${isTarget ? ' is-target' : ''}`
  if (block.kind === 'heading') {
    if (block.level === 1)
      return (
        <h1 ref={registerRef} className={`reader__h1${cls}`} data-segment-id={block.id}>
          {block.text}
        </h1>
      )
    return (
      <h2 ref={registerRef} className={`reader__h2${cls}`} data-segment-id={block.id}>
        {block.text}
      </h2>
    )
  }
  const variantCls = block.variant ? ` reader__para--${block.variant}` : ''
  return (
    <p ref={registerRef} className={`reader__para${variantCls}${cls}`} data-segment-id={block.id}>
      {words.map((w) => {
        const state =
          preciseHighlight && w.global === activeSpoken
            ? ' is-speaking'
            : w.global < spoken && narratedGlobals.has(w.global)
              ? ' is-read'
              : w.sentence === speakingSentence
                ? ' is-band'
                : ''
        const style = `${w.em ? ' is-em' : ''}${w.strong ? ' is-strong' : ''}`
        const termId = termByWord.get(w.global)
        if (termId) {
          return (
            <span
              key={w.global}
              className={`reader__word${state}${style}`}
              data-global={w.global}
            >
              <button
                type="button"
                className="reader__term"
                onClick={(e) => {
                  e.stopPropagation()
                  onTermClick(termId, e.currentTarget)
                }}
              >
                {w.text}
              </button>{' '}
            </span>
          )
        }
        return (
          <span
            key={w.global}
            className={`reader__word${state}${style}`}
            data-global={w.global}
          >
            {w.text}{' '}
          </span>
        )
      })}
    </p>
  )
}
