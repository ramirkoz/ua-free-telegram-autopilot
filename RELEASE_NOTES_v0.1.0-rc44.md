# UA FREE Telegram Autopilot v0.1.0-rc44

RC44 fixes public RSS/Atom sources that are readable in a normal browser but return HTTP 401/403/429 to the Python source transport.

## Fixed
- Direct RSS/Atom URLs now get a second public-source transport when the normal pinned Python request is access-blocked.
- The fallback tries the operating system `curl` transport first and, when anti-bot protection still blocks it, a guarded headless Edge/Chrome transport.
- SSRF protections are preserved: curl requests and redirects are resolved and verified as public; browser fallback is pinned to the validated source host and all other DNS is blocked.
- Content-type and maximum-size checks remain enforced.
- Existing homepage RSS discovery benefits from the same source fetch transport.
- Added regression coverage and Windows live checks for Ars Technica, Rest of World and Knowable Magazine.

## Preserved
- RC43 channel-editor layout fix.
- RC42 per-channel editorial profiles and operator-defined category weights.
- Existing Data remains compatible; no schema change.

## Upgrade
Unpack RC44 into a fresh folder and copy the complete existing `Data` directory. Do not overlay runtime files.
