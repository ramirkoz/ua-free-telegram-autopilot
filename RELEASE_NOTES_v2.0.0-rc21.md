# UA FREE Telegram Autopilot V2.0.0-rc21

## Дистанційний нагляд і оновлення

- Google Drive supervisor feed залишається основним транспортом телеметрії: `status.json`, `incident.json`, `recent_events.json`, agent journal/hourly report та update state.
- Під час старту supervisor перевіряє вже збережений `mirror_dir`, а autodiscovery віддає перевагу існуючому активному feed з telemetry-файлами, а не випадковій порожній папці з такою самою назвою.
- `set_expected_running()` більше не будує важкий snapshot на Tk thread. Він лише змінює intended state і будить supervisor thread, тому Start/Stop не мають морозити GUI.
- Update helper спочатку бере підписаний update overlay з локально синхронізованої Supervisor/Google Drive папки та перевіряє точний SHA-256. GitHub URL лишається тільки fallback.
- Workflow update overlay генерує `release_manifest.json` з exact version/SHA/source commit і прикладає manifest + overlay як Actions artifact для віддаленого агента.

## UI / shutdown

- Start/Stop intended-state snapshot винесений з Tk thread.
- Supervisor wake-up робить remote status майже миттєвим без синхронних SQLite/media queries у GUI.
- Під час Stop UI heartbeat залишається живим, а remote feed показує `expected_running=false` і фактичні lingering workers/collectors окремо.

## Медіа

- Збережені RC20 правила: EDITORIAL = максимум одне релевантне медіа; MONITORING = лише медіа точного Telegram `data-post`, без сусідніх постів, avatar/logo/reply/forward/link-preview chrome.
