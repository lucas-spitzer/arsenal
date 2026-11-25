import { describe, expect, it } from 'vitest'
import { groupByRewardBand, rewardBandFor } from './leaderboardRewards'

const board = (count: number) => Array.from({ length: count }, (_, index) => ({ rank: index + 1 }))

describe('rewardBandFor', () => {
  it('places each cut line at 1, 3, and 10', () => {
    expect(rewardBandFor(1).id).toBe('champion')
    expect(rewardBandFor(2).id).toBe('podium')
    expect(rewardBandFor(3).id).toBe('podium')
    expect(rewardBandFor(4).id).toBe('top-ten')
    expect(rewardBandFor(10).id).toBe('top-ten')
    expect(rewardBandFor(11).id).toBe('field')
  })
})

describe('groupByRewardBand', () => {
  it('splits a full board into four groups', () => {
    const groups = groupByRewardBand(board(12))
    expect(groups.map((group) => [group.band.id, group.entries.map((entry) => entry.rank)])).toEqual([
      ['champion', [1]],
      ['podium', [2, 3]],
      ['top-ten', [4, 5, 6, 7, 8, 9, 10]],
      ['field', [11, 12]],
    ])
  })

  it('only returns bands that have rows', () => {
    const groups = groupByRewardBand(board(2))
    expect(groups.map((group) => group.band.id)).toEqual(['champion', 'podium'])
  })

  it('returns nothing for an empty board', () => {
    expect(groupByRewardBand([])).toEqual([])
  })
})
