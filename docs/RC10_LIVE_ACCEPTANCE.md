# RC10 live acceptance — 2026-08-18

## Candidate

UA FREE Telegram Autopilot `0.1.0-rc10`

Windows Portable SHA-256:

`3a6834c20a7d799b1cbde30487a15127973ebf00284b05047f2e3e34baf23e91`

## Operator result

The candidate was run in the real Windows working environment using the existing working `Data`. The operator reported that the application appears to work and explicitly authorized repository synchronization.

Status: **LIVE SMOKE PASS**.

This record intentionally does not claim exhaustive coverage of every provider/API/network edge case. It records the actual operator acceptance required to synchronize the tested RC10 baseline.

## Preserved mechanisms

The accepted RC10 intentionally preserves the RC9 publishing mechanisms: new-before-retry scheduling, retry backoff and cap, Telegram 900/4096 limits, media rejection fallback to the same validated text, no blind retry after an unknown write result, bounded AI Router, production Codex skip, and installed Ollama as the last local fallback without automatic installation/model download.

## Repository gate

The exact synchronized source must pass GitHub CI on Ubuntu/Python 3.12 and Windows/Python 3.11, 3.12 and 3.13 before merge to `main`.
