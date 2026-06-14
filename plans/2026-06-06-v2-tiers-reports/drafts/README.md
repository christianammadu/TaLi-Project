<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# `drafts/` — ready-to-drop artifacts

Files in this directory are **artifacts the plan produced that are meant to land into the actual codebase / asset tree at a specific work-package boundary.** They are *not* themselves part of the spine — they're outputs the plan curated that downstream work consumes.

## When to put something here

Use `drafts/` when:

1. **The plan needed to design the exact shape of a file** (a schema, a config, an API surface, a piece of copy) and getting it right *was* part of the planning work, not the implementation work.
2. **The file is consumed at a specific WP boundary** that you can name in `01-plan.md` and `05-tracking.md`. (Studio's `drafts/schema.ts` is consumed at WP-02 § Schema; the WP brief says "start from `drafts/schema.ts`.")
3. **The file would be wasted effort to re-derive** during implementation. If a subagent could re-create it in 10 minutes from the spec, it doesn't belong here.

## When NOT to put something here

- **General reference content** → that's `02-research-external.md` or `03-research-internal.md`.
- **Visual mockups** → those are `designs/` (produced by `groundwork design`).
- **Code that's already merged** → delete from drafts/ once it's landed; the file's job is done.
- **Speculation / placeholder code** that doesn't have a specific consumer named yet → it'll rot. Either name the consumer (a WP) or move it to a sub-plan that documents *why* you wrote it.

## Conventions

### Header

Every draft file starts with a structured header. For lifted-from-elsewhere drafts, follow studio's pattern (`plans/studio/drafts/schema.ts`) — four blocks:

```ts
/**
 * <project> — <thing> v1 (DRAFT — destined for <final-path>)
 *
 * LIFTED-FROM:
 *   <source-path>
 *   (<byte-equivalence note, if applicable — "byte-identical with <other source>">)
 *
 * Lifted base: <comma-list of what was copied verbatim from the source>
 *
 * Modifications from the lift:
 *   - Renamed <X> → <Y> at the boundary (because <reason>)
 *   - Dropped <Z> (because <reason — e.g. "composition-engine-specific">)
 *   - Extended with: <new fields>, <new types>, <new constraints> (Round N)
 *   - <other delta>
 *
 * Round-by-round changes:
 *   - Round 2: <what changed>
 *   - Round 7: <what changed>
 */
```

For built-fresh drafts (no source), use the shorter form:

```ts
// DRAFT-FOR: ikenga-pkgs/packages/apps/studio/shared/schema.ts (WP-02)
// Built fresh in Round N — see 01-plan.md §Schema.
```

### Rules of thumb

- **One file = one consumer** unless explicitly noted. Co-locating multiple consumers' drafts makes the WP brief harder to write.
- **Updates while implementing**: if the consumer needs the draft to change before landing, edit the draft here — the WP brief should say "draft is the source of truth until landing." Round-by-round changes go in the header's `Round-by-round changes` section so a future maintainer can see the evolution.
- **Once landed**: either delete the draft (history lives in git + the WP commit) or replace `DRAFT-FOR:` with `LANDED-AS:` + a path. The skill's `.groundwork.json` doesn't track drafts directly; the consumer WP's status (`done`) implicitly closes them.

## What's here

| File | Consumer (WP) | Header / status |
|---|---|---|
| _e.g._ `schema.ts` | _e.g._ WP-02 (Schema) | DRAFT-FOR · landed → delete after merge |

Update this table by hand as drafts are added or land.
