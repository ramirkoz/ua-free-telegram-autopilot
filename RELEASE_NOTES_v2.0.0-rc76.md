# UA FREE Telegram Autopilot v2.0.0-rc76

- Named-source footer remains enabled for every source configured as named attribution.
- In-body source attribution is conditional: only source names containing the literal word «громада» are required/allowed as source context in rewrite prompts.
- Non-community sources are no longer introduced in body as «за інформацією…», «… повідомляє/інформує/пише» or similar redundant attribution; the system footer is sufficient.
- Source/article URLs are no longer treated as protected actionable facts merely because they appear in a Telegram source post.
- Reader-action links remain protected and are restored when needed.
- Monitoring QA rejects non-actionable source/article URLs in the body when they would duplicate the footer.
- RC75 dynamic short-post length, trusted final editing and grammar QA are preserved, together with RC74 Anti-Slop/paragraph/corruption and V2 Windows editing fixes.
- No source-specific hardcoding added.
