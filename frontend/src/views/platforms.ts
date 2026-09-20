// The accounts a person can choose to have Hereafter learn from.

export type Platform = 'github' | 'linkedin' | 'instagram'

export const PLATFORMS: { key: Platform; label: string }[] = [
  { key: 'github', label: 'GitHub' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'instagram', label: 'Instagram' },
]
