type ReturnTargets = {
  window: Pick<Window, 'addEventListener' | 'removeEventListener'>
  document: Pick<Document, 'addEventListener' | 'removeEventListener' | 'visibilityState'>
}

/**
 * Calls `onReturn` when the user comes back to the page: the window regains
 * focus or the tab becomes visible again. Returns the unsubscribe function.
 */
export function onPageReturn(
  onReturn: () => void,
  targets: ReturnTargets = { window, document },
): () => void {
  const onVisibility = () => {
    if (targets.document.visibilityState === 'visible') onReturn()
  }
  targets.window.addEventListener('focus', onReturn)
  targets.document.addEventListener('visibilitychange', onVisibility)
  return () => {
    targets.window.removeEventListener('focus', onReturn)
    targets.document.removeEventListener('visibilitychange', onVisibility)
  }
}
