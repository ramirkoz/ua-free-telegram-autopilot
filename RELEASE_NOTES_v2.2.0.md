# UA FREE Telegram Autopilot 2.2.0 — Operator Test Prerelease

**Status:** TEST / PRE-RELEASE. This build is offered for operator acceptance, not certified editorial production.

## Changes
- Evidence-first monitoring editorial gates for mixed independent notices and unsupported situation reports.
- Source-span provenance, preliminary claim trace and uncertainty/polarity safeguards.
- Media integrity: block text-only fallback where a Telegram source requires video.
- Exact Telegram message provenance and safe media ownership through explicit reply, album/group ID, or source-provided same-channel post URL.
- Bounded exact-post video retrieval for confirmed same-channel video references.
- Diagnostics for unresolved nearby media without guessing ownership.
- Regression tests on sanitized operator incidents and positive valid-video scenarios.

## Known limitations
- Some public Telegram HTML pages expose no video, reply or album ownership information; these remain blocked for review rather than silently assembled.
- Lexical claim trace runs in diagnostic/shadow mode; full semantic entailment is not implemented.
- The four operator-based replay fixtures are sanitized reconstructions, not raw media-enabled Telegram replays.
- Successful CI/portable build does not establish live editorial acceptance.

## Safe operator testing
1. Back up your complete `Data` directory, especially the database, source settings and encrypted credentials. Never upload the private `Data/secrets.*` files.
2. Stop Autopilot, unpack Windows portable to a **new** empty folder. Keep old 2.1.23 folder for rollback.
3. Copy the preserved `Data` directory into the new portable folder following the existing operator upgrade process. Do not overwrite credentials with sample data.
4. Start in a controlled test window. Review channel 3 «ЗАПОРІЖЖЯ | ГРОМАДИ» for source/video integrity; sample-check channels 1 and 2 for throughput regressions.
5. If blocking or failed media delivery rises sharply, stop 2.2.0 and return to the saved 2.1.23 binary with the backed-up data. Note source URLs, affected IDs, output text, media details and telemetry.

**Acceptance must be judged from real published output, not merely green CI.**
