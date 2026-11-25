export type RewardBandId = 'champion' | 'podium' | 'top-ten' | 'field'

export interface RewardBand {
  id: RewardBandId
  label: string
  maxRank: number
  reward: string | null
}

export const REWARD_BANDS: readonly RewardBand[] = [
  { id: 'champion', label: '1st', maxRank: 1, reward: 'Academic Champion badge' },
  { id: 'podium', label: 'Top 3', maxRank: 3, reward: 'Alpha Co decals' },
  { id: 'top-ten', label: 'Top 10', maxRank: 10, reward: 'Academic Weapon badge' },
  { id: 'field', label: 'Standings', maxRank: Number.POSITIVE_INFINITY, reward: null },
]

export function rewardBandFor(rank: number): RewardBand {
  return REWARD_BANDS.find((band) => rank <= band.maxRank) ?? REWARD_BANDS[REWARD_BANDS.length - 1]
}

export function groupByRewardBand<T extends { rank: number }>(
  entries: readonly T[],
): { band: RewardBand; entries: T[] }[] {
  return REWARD_BANDS.map((band) => ({
    band,
    entries: entries.filter((entry) => rewardBandFor(entry.rank).id === band.id),
  })).filter((group) => group.entries.length > 0)
}
