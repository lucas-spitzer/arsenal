import { buildBlocks, pickNarrationSet, type Block } from './readerContent'
import {
  listAllSourceSegments,
  listSourceChapters,
  listSourceNarration,
  type NarrationSegment,
} from './sourcesApi'

export const READER_LOAD_TIMEOUT_MS = 20_000

export type ReaderCacheEntry = {
  blocks: Block[]
  narration: Map<string, NarrationSegment>
  narrationWarning: string | null
}

const readerCache = new Map<string, ReaderCacheEntry>()

export function readerCacheKey(workspaceId: string, sourceId: string): string {
  return `${workspaceId}:${sourceId}`
}

export function readReaderCache(workspaceId: string, sourceId: string): ReaderCacheEntry | null {
  return readerCache.get(readerCacheKey(workspaceId, sourceId)) ?? null
}

export function writeReaderCache(
  workspaceId: string,
  sourceId: string,
  entry: ReaderCacheEntry,
): void {
  readerCache.set(readerCacheKey(workspaceId, sourceId), entry)
}

export function clearReaderCache(): void {
  readerCache.clear()
}

export function narrationMapFromRows(rows: NarrationSegment[]): Map<string, NarrationSegment> {
  const narration = new Map<string, NarrationSegment>()
  const timed = rows.filter((row) => row.words.length > 0)
  for (const row of pickNarrationSet(timed)) {
    narration.set(row.segment_id, row)
  }
  return narration
}

export function narrationFailureWarning(error: unknown): string {
  return error instanceof Error
    ? `Couldn’t load narration audio (${error.message}). Using estimated pacing.`
    : 'Couldn’t load narration audio. Using estimated pacing.'
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  )
}

/** A load that lost its workspace or source must not stay on the opening animation. */
export function liveAfterMissingScope<T extends { loading: boolean }>(live: T): T {
  if (!live.loading) return live
  return { ...live, loading: false }
}

export function shouldResumeReaderLoad(state: {
  visible: boolean
  loading: boolean
  failedWhileHidden: boolean
}): boolean {
  return state.visible && (state.loading || state.failedWhileHidden)
}

export function combineAbortSignals(signals: readonly AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  const onAbort = () => controller.abort()
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort()
      return controller.signal
    }
    signal.addEventListener('abort', onAbort, { once: true })
  }
  return controller.signal
}

export function createReaderLoadSignal(
  parent: AbortSignal,
  timeoutMs = READER_LOAD_TIMEOUT_MS,
): { signal: AbortSignal; cancelTimer: () => void; didTimeOut: () => boolean } {
  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), timeoutMs)
  return {
    signal: combineAbortSignals([parent, timeout.signal]),
    cancelTimer: () => clearTimeout(timer),
    didTimeOut: () => timeout.signal.aborted && !parent.aborted,
  }
}

export async function loadReaderText(
  workspaceId: string,
  sourceId: string,
  signal: AbortSignal,
): Promise<Block[]> {
  const [segments, chapters] = await Promise.all([
    listAllSourceSegments(workspaceId, sourceId, { signal }),
    listSourceChapters(workspaceId, sourceId, { signal }),
  ])
  return buildBlocks(segments, chapters)
}

export async function loadReaderNarration(
  workspaceId: string,
  sourceId: string,
  signal: AbortSignal,
): Promise<{ narration: Map<string, NarrationSegment>; warning: string | null }> {
  try {
    const rows = await listSourceNarration(workspaceId, sourceId, { signal })
    return { narration: narrationMapFromRows(rows), warning: null }
  } catch (error: unknown) {
    if (isAbortError(error)) throw error
    return { narration: new Map(), warning: narrationFailureWarning(error) }
  }
}

/**
 * Publish text as soon as segments and chapters arrive. Narration is optional
 * and must not hold the opening state.
 */
export async function loadReaderDocument(options: {
  loadText: (signal: AbortSignal) => Promise<Block[]>
  loadNarration: (
    signal: AbortSignal,
  ) => Promise<{ narration: Map<string, NarrationSegment>; warning: string | null }>
  onText: (blocks: Block[]) => void
  onNarration: (result: { narration: Map<string, NarrationSegment>; warning: string | null }) => void
  signal: AbortSignal
}): Promise<void> {
  const blocks = await options.loadText(options.signal)
  if (options.signal.aborted) return
  options.onText(blocks)
  const narration = await options.loadNarration(options.signal)
  if (options.signal.aborted) return
  options.onNarration(narration)
}
