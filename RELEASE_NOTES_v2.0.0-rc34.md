# UA FREE Telegram Autopilot v2.0.0-rc34

## Community source context and attribution

RC34 fixes context loss in the `ГРОМАДИ` output lane when a donor post uses generic wording such as “мешканці громади” that only makes sense inside the donor channel.

### What changed

- The existing configured source name (`sources.name`) is now the canonical community name for output channels whose name contains `громад`.
- Writer and final-edit prompts receive that configured community name as mandatory context.
- Deterministic QA rejects a rewrite if the configured community name disappears from the final body.
- The configured source name is treated as source evidence by the factual guard, so the writer can safely introduce the community name even when the original post body itself only says “громада”.
- The publication footer for the communities lane is now `Читати у «<назва джерела>»` and links to the exact canonical original post.
- Community attribution uses only the primary original-post URL; extra evidence URLs do not clutter that footer.
- Other output channels keep the existing `Джерело` / `Джерело N` attribution contract unchanged.
- RC33 actionable-link protection remains independent: registration, application, form, booking, payment, schedule and similar reader-action URLs must still remain in the rewritten body and cannot be replaced by the community footer.
- Caption budgeting reserves space for the longer community footer before AI writing, preventing avoidable Telegram oversize requeues.

### Operator workflow

For donor sources feeding the communities channel, set the source name in the program to the normal human community name, for example `Кушугумська громада`. No extra database field or per-source metadata is required.
