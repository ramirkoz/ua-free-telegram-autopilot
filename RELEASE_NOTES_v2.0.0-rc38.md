# UA FREE Telegram Autopilot v2.0.0-rc38

## CPU-only local AI recovery

RC38 makes the installed Ollama fallback practical on the production notebook (24 GB RAM, no discrete GPU).

- Local health probes allow a cold CPU model up to 90 seconds instead of judging it by cloud-provider timings.
- Local selection/JSON tasks get up to 180 seconds and full writer tasks up to 300 seconds.
- Local output is capped at 768 tokens to keep unattended CPU generation bounded.
- The three channel workers now serialize behind the local provider instead of reporting `provider busy` after two seconds.
- Editorial local fallback combines channel-fit and value scoring in one response when possible.
- A validated local writer draft skips the redundant second local final-edit pass.
- Ollama remains a last-resort fallback behind healthy cloud providers; only one local generation runs at a time.

All RC37 remote update, rollback, Telegram reporting, source attribution and RC36 media fail-closed behavior remain intact.
