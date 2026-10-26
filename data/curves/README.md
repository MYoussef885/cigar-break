# Shared curves

Each file here is one developer's anonymous curve for one model, shared with `cigar share` and accepted by a maintainer (D-015). Files live at `data/curves/<model>/<issue number>.json`; `scripts/ingest_curves.py` writes them from issues labelled `curve-accepted`.

A curve holds aggregates only. It contains no paths, project names, code, prompts or user identifiers, and the same allowlist check runs when it is shared and when it is ingested (`cigar.share.problems`).

## Schema (`schema_version: 1`)

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | Always `1` for this layout |
| `cigar_version` | string | The Cigar version that built the payload |
| `harness` | string | `claude-code`, or `other` for agents that report through `record_event` or `cigar.track` |
| `model` | string | The model ID as the agent reported it, for example `claude-sonnet-5-5` |
| `window` | string | The session's context window label: `200k` or `1m` (D-026) |
| `sessions` | int | Sessions behind this curve |
| `events` | int | Main-agent tool calls behind this curve |
| `buckets` | list | One entry per 10k-token bucket: `{lo, hi, events, weight}` |
| `knee` | int or null | The learned knee in tokens, or `null` if none was found |
| `confidence` | string | `low`, `medium` or `high` (architecture §9) |
| `default_knee` | int | Cigar's starting knee for this model and window (D-017) |

In a bucket, `lo` and `hi` are context sizes in tokens (`hi = lo + 10000`), `events` is the number of tool calls made at that context size, and `weight` is their summed signal weight: failures 1.0, repeated calls 0.8, re-reads 0.5, undone edits 1.0, failed checks 0.7. The bucket's signal rate is `weight / events`.

Example:

```json
{
  "schema_version": 1,
  "cigar_version": "0.1.0",
  "harness": "claude-code",
  "model": "claude-sonnet-5-5",
  "window": "200k",
  "sessions": 23,
  "events": 2841,
  "buckets": [
    {"lo": 30000, "hi": 40000, "events": 212, "weight": 15.4},
    {"lo": 40000, "hi": 50000, "events": 301, "weight": 22.9}
  ],
  "knee": 110000,
  "confidence": "high",
  "default_knee": 100000
}
```

Buckets with few events may be dropped when a payload is too long for a prefilled issue URL.
