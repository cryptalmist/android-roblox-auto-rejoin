
# Roblox Auto-Rejoin

This script automatically monitors a Roblox account's in-game status and rejoins a VIP server if the account goes offline. It also updates a Discord webhook message with the current status.

---

## 📦 Features

- Auto-check if user is in-game.
- Auto-launch VIP server link when not in-game.
- Works with both **Global Roblox** and **Vietnam Roblox** (via `vng_mode` toggle).
- Sends status updates to a **Discord webhook**.
- Can update existing webhook message (instead of spamming new ones).
- Configurable intervals and debug output.

---

## 📝 Config.json Example

```json
{
  "user": "184",
  "vip_link": "https://www.roblox.com/games/234234/?privateServerLinkCode=xxxxxx",
  "check_interval_in_game": 15,
  "check_interval_not_in_game": 30,

  "webhook_url": "https://discord.com/api/webhooks/xxxxxx/xxxxxx",
  "webhook_message_id_file": "~/msgid.txt",
  "roproxy": "roproxy.com",
  "vng_mode": true,
  "debug": true
}
```

---

## ⚙️ Config Fields

| Field | Type | Description |
|-------|------|-------------|
| `user` | string | Roblox user ID to monitor |
| `vip_link` | string | Full VIP server link (from Roblox website) |
| `check_interval_in_game` | int | Seconds to wait between checks when user is in-game |
| `check_interval_not_in_game` | int | Seconds to wait between checks when user is not in-game |
| `webhook_url` | string | Discord webhook URL |
| `webhook_message_id_file` | string | Path to store webhook message ID (use `~/file.txt` for home dir) |
| `roproxy` | string | Proxy domain for Roblox API (default: roproxy.com) |
| `debug` | bool | Enable debug prints if `true` |
| `vng_mode` | bool | Use Vietnam Roblox client if `true`, global client if `false` |

chat gpidi ski bi di so sigma
