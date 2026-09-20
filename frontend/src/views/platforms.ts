// The accounts a person can choose to have Hereafter learn from.

export type Platform = 'github' | 'linkedin' | 'instagram' | 'site'

// Hardcoded for now: choosing an account points Hereafter at this profile. `url` is absent where none is set.
export const PLATFORMS: { key: Platform; label: string; url?: string }[] = [
  { key: 'github', label: 'GitHub', url: 'https://github.com/archangelinux' },
  { key: 'linkedin', label: 'LinkedIn', url: 'https://www.linkedin.com/in/angelinabai/' },
  { key: 'instagram', label: 'Instagram', url: 'https://www.instagram.com/mthr.angie/' },
  { key: 'site', label: 'Personal website', url: 'https://archangelinux.vercel.app/' },
]
