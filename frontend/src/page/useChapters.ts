import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Api } from '../api'
import { theme } from '../theme'
import type { BranchView, BranchYear, Chapter, Which } from '../types'

/** Chapters of one life on one branch, fetched lazily in order, re-asked while still being written. */
export function useChapters(api: Api, view: BranchView, which: Which, years: BranchYear[]) {
  const { branch } = view
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [loading, setLoading] = useState(false)
  const generation = useRef(0)
  const key = `${branch.id}:${branch.revision}:${which}:${years.length}`

  // a new branch, a re-simulation or a jump to another life starts the book again
  useEffect(() => {
    generation.current++
    setChapters([])
  }, [key])

  const covered = chapters.length ? chapters[chapters.length - 1].to_at : null
  const nextAt = useMemo(() => {
    if (!years.length) return null
    if (!covered) return years[0].at
    return years.find((y) => y.at > covered)?.at ?? null
  }, [years, covered])

  const loadNext = useCallback(async () => {
    if (!nextAt || loading) return
    const mine = generation.current
    setLoading(true)
    try {
      const c = await api.chapter(branch.id, nextAt, which)
      if (mine === generation.current) setChapters((prev) => (prev.some((x) => x.from_at === c.from_at) ? prev : [...prev, c]))
    } catch {
      /* stays as it is; the next ask tries again */
    } finally {
      setLoading(false)
    }
  }, [api, branch.id, nextAt, which, loading])

  useEffect(() => {
    if (chapters.length === 0) void loadNext()
  }, [chapters.length, loadNext])

  // prose arrives late: ask again for chapters still being written
  useEffect(() => {
    const writing = chapters.filter((c) => c.status === 'writing')
    if (!writing.length) return
    const mine = generation.current
    const timer = setTimeout(async () => {
      const fresh = await Promise.all(writing.map((c) => api.chapter(branch.id, c.from_at, which).catch(() => c)))
      if (mine === generation.current) setChapters((prev) => prev.map((c) => fresh.find((f) => f.from_at === c.from_at) ?? c))
    }, theme.motion.busyPollMs)
    return () => clearTimeout(timer)
  }, [chapters, api, branch.id, which])

  return { chapters, loading, loadNext, done: !nextAt && chapters.length > 0, key }
}

/** The steps a chapter spans, with their index in the branch. */
export const stepsOf = (c: Chapter, years: BranchYear[]) => years.map((y, i) => ({ y, i })).filter(({ y }) => y.at >= c.from_at.slice(0, 10) && y.at <= c.to_at)
