import type { Register } from 'claude-code'

// Cigar auto mode (D-007, D-021, D-026). While the mode is `auto`, the Python
// hook writes <CIGAR_HOME>/auto/<session id>.json with state "ready" and the
// handoff's path, but only once a handoff is saved for the session. At the end
// of that turn this module runs /clear, and Cigar's SessionStart hook restores
// the handoff and says so in one line. No marker, or a marker without a
// handoff, means no clear: a nudge alone never resets. Anything unexpected
// leaves the session alone.

const CLEAR_DELAY_MS = 1000

async function markerPath($: any, sessionId: string): Promise<string | undefined> {
  const homeDir = await $.env.get('HOME')
  let cigarHome = await $.env.get('CIGAR_HOME')
  if (cigarHome && cigarHome.startsWith('~') && homeDir) cigarHome = homeDir + cigarHome.slice(1)
  if (!cigarHome && homeDir) cigarHome = `${homeDir}/.cigar`
  return cigarHome ? `${cigarHome}/auto/${sessionId}.json` : undefined
}

async function takeReadyMarker($: any): Promise<boolean> {
  const path = await markerPath($, await $.session.id())
  if (!path || !(await $.fs.exists(path))) return false
  const marker = JSON.parse(await $.fs.read(path))
  if (marker.state !== 'ready') return false
  if (typeof marker.handoff !== 'string' || !marker.handoff) return false
  await $.fs.write(path, JSON.stringify({ ...marker, state: 'fired' }))
  return true
}

export const register: Register = on => {
  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    if (e.agentId !== undefined || e.reason !== 'answer') return out
    try {
      if (await takeReadyMarker($)) {
        $.clock.after(CLEAR_DELAY_MS, async () => {
          await $.command.run({ command: 'clear' })
        })
      }
    } catch {
      // Fail open: never disturb the session.
    }
    return out
  })
}
