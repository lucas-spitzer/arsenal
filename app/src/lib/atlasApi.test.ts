import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./apiClient', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from './apiClient'
import { getLeaderboard } from './atlasApi'

const request = vi.mocked(apiRequest)

beforeEach(() => {
  request.mockReset()
})

describe('getLeaderboard', () => {
  it('skips the HTTP cache so every load shows current standings', async () => {
    request.mockResolvedValueOnce({ entries: [] })

    await getLeaderboard('workspace-1')

    expect(request).toHaveBeenCalledWith('/workspaces/workspace-1/atlas/leaderboard', { cache: 'no-store' })
  })
})
