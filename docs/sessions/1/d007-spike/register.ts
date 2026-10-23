import type { Register } from 'claude-code'

const LOG = '<scratch>/probe-out/spike.log'
let fired = false

async function log($: any, line: string): Promise<void> {
  const prev = (await $.fs.exists(LOG)) ? await $.fs.read(LOG) : ''
  await $.fs.write(LOG, `${prev}${new Date().toISOString()} ${line}\n`)
}

export const register: Register = on => {
  on('turn.complete', async ($, e, next) => {
    const out = await next(e)
    if (e.agentId !== undefined || fired) return out
    fired = true
    const strategy = (await $.fs.read('.spike-strategy')).trim()
    await log($, `turn.complete main; strategy=${strategy}; session=${await $.session.id()}`)
    $.clock.after(4000, async () => {
      try {
        let r: unknown
        if (strategy === 'submit-clear') r = await $.prompt.submit({ text: '/clear' })
        else if (strategy === 'submit-clear-asuser') r = await $.prompt.submit({ text: '/clear', asUser: true })
        else if (strategy === 'submit-compact') r = await $.prompt.submit({ text: '/compact' })
        else if (strategy === 'submit-compact-asuser') r = await $.prompt.submit({ text: '/compact', asUser: true })
        else if (strategy === 'command-clear') r = await $.command.run({ command: 'clear' })
        else if (strategy === 'command-compact') r = await $.command.run({ command: 'compact' })
        else if (strategy === 'session-compact') r = await $.session.compact({ instructions: 'keep the plan' })
        await log($, `${strategy} resolved: ${JSON.stringify(r).slice(0, 300)}; session now=${await $.session.id()}`)
      } catch (err) {
        await log($, `${strategy} rejected: ${String(err).slice(0, 300)}`)
      }
    })
    return out
  })

  on('prompt.submit', async ($, e, next) => {
    await log($, `prompt.submit origin=${JSON.stringify(e.origin)} command=${JSON.stringify((e as any).command)} text=${e.text.slice(0, 40)}`)
    return next(e)
  })
}
