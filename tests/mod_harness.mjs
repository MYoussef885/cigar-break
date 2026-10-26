// Runs mods/auto.ts's turn.complete handler once, against a fake `$`, and
// prints what it did as JSON: {"commands": [...], "toasts": [...]}.
//
//   node tests/mod_harness.mjs <cigar home> <session id> [reason] [agent id]
//
// The fake `$` covers only what the mod uses. Clock callbacks run right after
// the handler returns, so a scheduled /clear shows up in "commands".
import { access, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'

const [cigarHome, sessionId, reason = 'answer', agentId] = process.argv.slice(2)
const here = dirname(fileURLToPath(import.meta.url))
const { register } = await import(pathToFileURL(join(here, '..', 'mods', 'auto.ts')).href)

const commands = []
const toasts = []
const later = []
const env = { HOME: '/nonexistent-home', CIGAR_HOME: cigarHome }
const $ = {
  env: { get: async name => env[name] },
  session: { id: async () => sessionId },
  fs: {
    exists: async path => access(path).then(() => true, () => false),
    read: async path => readFile(path, 'utf8'),
    write: async (path, text) => writeFile(path, text),
  },
  clock: { after: (ms, fn) => later.push(fn) },
  command: { run: async ({ command }) => commands.push(command) },
  ui: { toast: text => toasts.push(text) },
}

let handler
register((event, fn) => {
  if (event === 'turn.complete') handler = fn
})
const e = { reason, agentId: agentId || undefined }
await handler($, e, async ev => ev)
for (const fn of later) await fn()
process.stdout.write(JSON.stringify({ commands, toasts }) + '\n')
