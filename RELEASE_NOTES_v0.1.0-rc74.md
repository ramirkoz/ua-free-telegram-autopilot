# UA FREE Telegram Autopilot v0.1.0-rc74

## Universal runtime cleanup

RC74 removes legacy active layers that inferred channel families or imposed hidden pacing rules. The runtime contract is now explicit:

- universal mechanisms stay under the hood: collection, dedupe/clustering, Fact Guard, language/media infrastructure, QA, scheduling engine, monitoring/editorial branching and universal Editorial Value;
- channel-specific language direction, timing, editorial policy, prompts, media behavior and editorial weights come only from that channel's saved settings;
- channel names are not routing rules and are not used to infer editorial taste.

## Throughput fix

The RC67 pre-queue dedupe is now deterministic and non-blocking. It no longer waits on AI providers before a story may enter the editorial pipeline. AI/network delays in pre-clustering therefore cannot silently starve one channel while another continues to publish.

## Language isolation

Per-channel language direction is now re-established inside background preparation workers and publication calls. This fixes the context loss introduced by parallel RC67 workers and prevents one channel's language mode from leaking into another.

Changing a channel language direction or channel policy invalidates queued READY/new/retry drafts for that channel so the new settings are applied immediately instead of reusing stale generated text.

## Media cleanup

Media filtering is channel-neutral. The engine hard-rejects only technical/non-editorial noise such as trackers, ad-network assets, favicons, sprites and avatars. Editorial concepts such as advertising, promotion or commercial activity are no longer hidden engine-level rejection terms; relevance is decided by the channel policy.

Source labels follow the configured output language (`Джерело/Джерела` or `Source/Sources`).

## Retired active layers

RC62, RC63 and RC64 remain in repository history for compatibility/reference but are no longer installed in the production runtime because they contained channel-family inference and hard-coded pacing behavior.
