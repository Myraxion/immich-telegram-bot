# Native Telegram Localization Support

We introduce multi-language reply localization supporting English (`en`), Chinese (`zh`), Japanese (`ja`), and Russian (`ru`) resolved dynamically from Telegram sender language preferences.

Previously, all user-facing bot messages (system help, start guide, error alerts, and upload status summaries) were hardcoded in Russian inside `bot.py`. Non-Russian speakers received incomprehensible feedback, and language selection was inflexible.

By implementing a lightweight localization catalog (`i18n.py`) and integrating with Telegram's native `from_user.language_code`:
- Incoming messages resolve the sender's primary language subtag (e.g. `zh-Hans`, `zh-CN` -> `zh`, `en-US` -> `en`, `ja` -> `ja`, `ru` -> `ru`).
- Senders with unknown or missing language codes fall back gracefully to `DEFAULT_LANGUAGE` (configurable via environment, defaulting to `en`).
- Multi-message media groups resolve localization based on the leading message sender preference.
- All translations remain in-code within a type-safe, dictionary-backed module, avoiding external compilation tooling (GNU gettext / Babel) or complex stateful `/lang` command flows in compliance with the KISS principle.
