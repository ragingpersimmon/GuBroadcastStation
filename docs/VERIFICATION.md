# Verification engine

Gu publishes only what passes `gbs/verify/checker.verify()`. Order of work per edition (`gbs rundown`):

1. **Cluster**: reports on one event are grouped, even when headlines are worded differently (shared names + words).
2. **Corroborate**: count independent organisations, meaning distinct ownership groups in `config/source_registry.json`.
   - BBC News and BBC Sport are one group.
   - Unknown outlets (weight 0) can't confirm.
   - Official sources (UN, NASA) need a news organisation alongside them.
   - Reports more than 72 h apart don't corroborate each other.
   - Fewer than `GBS_MIN_SOURCES` (2) → held back.
3. **Cross-check facts**: figures and names in 2+ independent reports are confirmed. Single-source figures are passed to the writer as "do NOT use".
4. **Write**: the local LLM writes Gu's own headline and read from the confirmed material. The prompt never sees outlet names.
5. **Gate** (up to 3 drafts, with the checker's feedback each time). A draft is rejected if any of these hold:
   - It shares a run of 6+ words with any source title or summary.
   - It reuses a source headline.
   - It uses loaded language.
   - It uses a single-source figure.
6. **Publish**: only rows with `rewritten=1` are ever shown. Stories written before the engine existed stay hidden.
   - Each story page shows "How this story was verified": counts and pass/fail only.
   - Sources are never named.

No rewriter (LLM down) → nothing new publishes; the site keeps what was already verified.

Ops: `gbs doctor` reports:
- rewriter status and model
- live and silent feeds
- outlets missing from the registry
- 24-hour published/held counts and the top reasons stories were held

Adding a feed: add the outlet to `config/source_registry.json` with its ownership group, or its stories can never confirm anything.
