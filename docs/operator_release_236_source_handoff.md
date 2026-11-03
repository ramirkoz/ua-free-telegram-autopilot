# Autopilot v2.3.6 — verified four-way synchronization (2026-11-03)

**Status:** GitHub **main 2.3.6**, official Windows GitHub release **v2.3.6**, Google Drive official asset mirror **completed**, ProductVault canonical record **updated**. Operator LIVE installation/Telegram delivery still requires acceptance; synchronization success is not a claim that the user has installed 2.3.6.

## Canonical code
- Branch `sync/20261103-exact-operator-236`, PR [#270](https://github.com/ramirkoz/ua-free-telegram-autopilot/pull/270), squash merge into main `37516cec9cbc726d96aa1137f1457d8903eb50db`.
- Imported **194 actual operator Source ZIP files**, individual Git SHA-1 compared to the original ZIP: **194/194 exact**, zero mismatches. Kept original Git history and 69 dormant legacy root `rc*.py` for historical context; release build excludes them.
- 4/4 PR CI jobs green (Ubuntu 3.12 and Windows 3.11/3.12/3.13). Legacy tests that assumed superseded behavior were aligned with the actual 2.3.6 operator build; tested code itself was not rewritten to emulate old release.
- Versions: `VERSION.txt`, `PUBLIC_VERSION.txt`, `V2_VERSION.txt`, and active package all **2.3.6**.
- Official GitHub Windows release workflow [#41624485165](https://github.com/ramirkoz/ua-free-telegram-autopilot/actions/runs/41624485165) finished **success**, including tests, Windows GUI smoke, signer checks, Defender and artifact integrity.

## Official GitHub release and matching Drive mirror
- GitHub: https://github.com/ramirkoz/ua-free-telegram-autopilot/releases/tag/v2.3.6 (published 2026-11-03).
- Official Google Drive folder: https://drive.google.com/drive/folders/1O14xcRXwNN3LIRmY9plMUNGB2-wAizTX under `UA FREE Telegram Autopilot — Project Vault`.
- Windows Portable: **36,243,970 bytes**, SHA256 `1dba73798b86876c8f5660f7568bb8ccc8f66d49997b73e92e3d1539b8094b39`, Drive ID `1DAYdmxE3-psFB5Fy9nc3OD8oqT9JCLFA`.
- Source ZIP: **1,188,312 bytes**, SHA256 `b9d63deed5f7ee4404901bc3048655f90ab0eac011d6411be582730e7bfc1d68`, Drive ID `14ViqEYNvkHAGctAUAyTsMxRae-tf__rS`.
- SHA256SUMS: **234 bytes**, Drive ID `1b9Bw7mJw_Qk5jdbFnbB6KsV4XHskDJsJ`.
- Drive mirrors **exact binary assets extracted from the successful GitHub release workflow**. The GitHub artifact ZIP CRC, extracted file hashes and checksum-file contents were verified before Drive upload; Drive reported exact matching sizes.

## Distinction: original local candidate is preserved, not confused with official release
- The previous locally assembled Portable (29,444,571 B, SHA256 `8ab47dd33eb6c3da19c7c69d10b98674a14cb1e83fc5c0c22884d321faab3f01`) and local Source (749,308 B, SHA256 `6d60e5dc42ef7ba5a38ff213c9bbfae1bb453c2b0256b7a1ad110022c743d829`) remain in the Drive subfolder `LOCAL_RC — operator build 2.3.6` and persistent ChatGPT Library. These are **not byte-identical** to official CI assets. Use the parent Drive folder's main files or GitHub Release for the officially verified build.
- Original `Data`, operator keys, old SQLite, source history, Telegram UNKNOWN/receipts and 45/30/5 cadence were not bundled/altered. New install uses the **built-in first-run importer** (select old 2.3.5 folder, don't copy Data manually).
- Unverified item remains: actual operator LIVE 2.3.6 traffic and first publish after installation.

## Product definition
CTRL+UA and ПРОДАНО! editorial calibration from 200 operator labels; targeted `ГРОМАДИ` duplicate, claim and schedule integrity corrections; Trend Hunter FeedBurner identity fix. Canonical policy and learning set in `ramirkoz/ProductVault/01_PRODUCT/AUTOPILOT/`.
