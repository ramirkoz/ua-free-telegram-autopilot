# Autopilot 2.1.23

- Block syntactically broken sentence tails in monitoring-channel final copy before Telegram publication.
- Covers operator-reported Zaporizhzhia traffic fragment “Також проблеми на мостах тех.”
- Existing prepublish quality retry (maximum three attempts) handles recovery or eventual rejection; do not publish broken READY rows.
- Preserve coherent short local traffic news and original newsroom reporting.
- Adds dedicated regression tests. No new source claims are invented by this guard.
- Windows Portable operator LIVE acceptance required after CI and release build.
