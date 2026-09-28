# UA FREE Telegram Autopilot 2.0.0-rc98

Focused candidate based on RC97.

## ПРОДАНО! editorial profile

- Retunes the existing commercial-editorial profile from the operator's manual channel selections rather than generic marketing-trade assumptions.
- Treats the channel as a broad visual/shareable digest: unusual brands and products, technology/AI, pop culture, design, internet phenomena, human behaviour and surprising research can qualify when there is a concrete retellable hook.
- Seeds manual positive examples such as unusual IKEA/Adidas products, AI cat search, MSCHF/Lexus, Aston Martin viral visual, Apple backstage, unusual vehicles/robots, cake CVs and book raves.
- Enables a lower media-first text threshold for the commercial profile so strong video/image-led stories are not discarded merely for having concise source text.
- Tightens rejection of generic retail/martech/search/PR/HR/trade news without novelty, visual payoff, conflict or broad cultural interest.
- Disables a small set of persistently off-profile trade sources in existing commercial-profile Data and raises priority of the strongest existing creative/culture sources. Custom/unknown sources are left untouched.

## Source text cleanup vs media

- Restores the intended meaning of `strip_body_links`: clean body URLs/service lines only.
- The option no longer removes source-owned image/video media during ingest.
- Existing sources with the checkbox enabled keep their cleanup setting and begin receiving media again on fresh collection without manual reconfiguration.

## Monitoring freshness

- Tightens the deterministic live-now gate for first operational strike/impact reports such as `зафіксовано влучання`.
- A first impact notice is rejected unless it contains a concrete settled result such as confirmed counts or completed emergency response.
- Stable aftermath summaries remain eligible.

## Preserved behavior

RC98 preserves RC97 UI responsiveness hardening, telemetry, bounded Telegram adjacent-media stitching, credentials, AI routing, dedupe, anti-slop, learning, publisher, migration and signed updater contracts except for the targeted corrections above.
