# UA FREE Telegram Autopilot v2.0.0-rc77

- Added encrypted Meta/Facebook credentials in the global Facebook tab: App ID, App Secret, User Access Token and Graph API version.
- Facebook Pages can be discovered from the User Access Token or added/edited manually; Page Access Tokens remain in encrypted secrets.secure.
- Every channel now has a Facebook tab with checkboxes for the available Pages. The channel database stores only selected Page IDs, never Facebook tokens.
- After a successful Telegram publication, selected Facebook Pages receive an automatic link post using the final Telegram text.
- Facebook attribution points to the already-published Telegram post: `Джерело: https://t.me/.../<message_id>`.
- Facebook delivery has its own durable queue/retry state. A Facebook failure never rolls back or republishes the Telegram post.
- Public @channels and Telegram -100 channel IDs are converted to usable Telegram post links when possible.
- RC76 source-attribution rules, RC75 language/short-post safeguards and RC74 Anti-Slop/UI fixes are preserved.
