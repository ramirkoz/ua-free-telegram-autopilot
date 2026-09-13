# UA FREE Telegram Autopilot V2.0.0-rc25

## Packaging fix

- Rebuilt the Windows portable as a slim deterministic runtime instead of copying the entire GitHub Actions Python installation.
- Keeps the signed Python launcher, Tk/Tcl GUI runtime, standard library, pip, and only the declared production dependencies.
- Keeps bundled OpenAI Codex 0.147.0 so the application remains ready to use after extraction.
- Removes test-only packages, runner tooling, caches, bytecode and unused Python development files from the portable.
- Adds a release-size guard so an accidentally bloated Windows portable fails CI instead of being published.
- Preserves all RC24 application behavior; this release changes packaging and release hygiene only.
- Removes obsolete RC18 verification staging from the active branch.
