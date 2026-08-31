# UA FREE Telegram Autopilot v0.1.0-rc59

RC59 replaces channel-specific editorial routing with a universal per-channel policy engine.

## Universal ChannelPolicy

The engine no longer recognizes or routes by specific channel names, channel types, marketing/science keywords in the channel profile, or article-derived channel kinds.

Every channel now stores its own `ChannelPolicy` in SQLite. The same universal selector and writer are used for every channel.

Per-channel settings include:

- channel purpose / mission;
- target audience;
- what to select;
- what to reject;
- writing structure;
- tone and style;
- manual positive and negative examples;
- extra editorial rules;
- optional extra selector prompt;
- optional extra writer prompt;
- media policy: required / preferred / optional;
- preferred post length.

Existing `editorial_profile` text is migrated into the new policy for compatibility. New channels can be added and fully configured without code changes.

## Reaction learning

- 👍 is a positive topic signal.
- 👎 is a negative topic signal and can temporarily suppress very close stories.
- 🔥 is style-only and never increases topic affinity.
- editor signals are isolated by `channel_id` and have priority over audience performance;
- audience reactions/views/forwards/replies remain a softer secondary signal;
- the selector receives recent positive/negative topic examples semantically, without hardcoded topic taxonomies;
- the writer receives only 🔥 style examples.

## Publication safety

RC59 adds a global refusal/meta-output blocker. Text such as `Вибачте, я не можу підготувати пост...`, channel-fit explanations, or other AI service commentary cannot become a Telegram publication.

If the universal selector is unavailable or returns invalid output, the material fails closed and is not published.

## Settings UX

Channel editing now includes separate tabs for:

- Basic settings;
- Mission;
- Selection;
- Writing;
- Examples;
- Advanced prompts.

The editor can display the actual generated AI instruction and test a policy against a sample story before allowing it into autopilot.

## Upgrade

Extract RC59 into a new folder and copy the complete `Data` directory from RC58. On first start RC59 creates the `channel_policies` table and migrates each existing channel's legacy editorial profile into its own policy row.

After upgrade, review the editorial policy of each channel before leaving unattended autopilot enabled.
