import { describe, expect, it, vi } from 'vitest'
import { onPageReturn } from './refreshOnReturn'

function fakePage() {
  const win = new EventTarget()
  const doc = Object.assign(new EventTarget(), { visibilityState: 'visible' as DocumentVisibilityState })
  return { win, doc, targets: { window: win, document: doc } }
}

describe('onPageReturn', () => {
  it('fires when the window regains focus', () => {
    const { win, targets } = fakePage()
    const onReturn = vi.fn()
    onPageReturn(onReturn, targets)

    win.dispatchEvent(new Event('focus'))

    expect(onReturn).toHaveBeenCalledTimes(1)
  })

  it('fires when the tab becomes visible, not when it is hidden', () => {
    const { doc, targets } = fakePage()
    const onReturn = vi.fn()
    onPageReturn(onReturn, targets)

    doc.visibilityState = 'hidden'
    doc.dispatchEvent(new Event('visibilitychange'))
    expect(onReturn).not.toHaveBeenCalled()

    doc.visibilityState = 'visible'
    doc.dispatchEvent(new Event('visibilitychange'))
    expect(onReturn).toHaveBeenCalledTimes(1)
  })

  it('stops listening after unsubscribe', () => {
    const { win, doc, targets } = fakePage()
    const onReturn = vi.fn()
    const unsubscribe = onPageReturn(onReturn, targets)

    unsubscribe()
    win.dispatchEvent(new Event('focus'))
    doc.dispatchEvent(new Event('visibilitychange'))

    expect(onReturn).not.toHaveBeenCalled()
  })
})
