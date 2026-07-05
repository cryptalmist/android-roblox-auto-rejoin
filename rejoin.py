import json, time, re, subprocess, sys, os, datetime, random

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    import requests

# ── CONFIG ──────────────────────────────────────
DEFAULT_CONFIG = {
    "user_id": 0,
    "place_id": 0,
    "vip_link": "",
    "vng_mode": True,
    "offline_checks_before_rejoin": 3,
    "check_interval_in_game": 20,
    "check_interval_not_in_game": 30,
    "load_wait": 35,
    "force_rejoin_hours": 0,          # 0/None = disabled, e.g. 1.5 = every 90 min
    "webhook_url": "",
    "webhook_message_id_file": "webhook_msg_id.txt",
    "debug": False,
}
CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        json.dump(DEFAULT_CONFIG, open(CONFIG_FILE, "w"), indent=4)
        print("[INFO] config.json created — fill it in and restart.")
        sys.exit(0)
    cfg = json.load(open(CONFIG_FILE))
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg

# ── HELPERS ─────────────────────────────────────
def log(msg): print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}")
def dlog(msg, cfg): cfg.get("debug") and print(f"[DEBUG] {msg}")
def clear(): print("\033[2J\033[H", end="", flush=True)
def package(cfg): return "com.roblox.client.vnggames" if cfg.get("vng_mode") else "com.roblox.client"

# ── ROBLOX API (no auth / public endpoints only) ─
def api_get(url, cfg, **kw):
    try:
        r = requests.get(url, timeout=10, **kw)
        if r.ok: return r.json()
    except Exception as e:
        dlog(f"GET {url}: {e}", cfg)
    return None

def fetch_user_info(cfg):
    d = api_get(f"https://users.roblox.com/v1/users/{cfg.get('user_id')}", cfg)
    if not d: return {}
    return {"display_name": d.get("displayName", "?"), "username": d.get("name", "?"), "user_id": cfg.get("user_id")}

def fetch_presence(cfg):
    try:
        r = requests.post("https://presence.roblox.com/v1/presence/users",
                           json={"userIds": [int(cfg.get("user_id"))]}, timeout=10)
        r.raise_for_status()
        pres = r.json().get("userPresences", [])
        if pres:
            p = pres[0]
            dlog(f"presence={p.get('userPresenceType')} place={p.get('placeId')}", cfg)
            return {
                "in_game": p.get("userPresenceType", 0) == 2,
                "place_id": p.get("placeId"),
                "location": p.get("lastLocation", ""),
                "last_online": (p.get("lastOnline", "")[:19].replace("T", " ") if p.get("lastOnline") else ""),
            }
    except Exception as e:
        dlog(f"fetch_presence: {e}", cfg)
    return {"in_game": False, "place_id": None, "location": "", "last_online": ""}

# ── GAME LAUNCH ─────────────────────────────────
def force_stop(cfg):
    pkg = package(cfg)
    log(f"Force stopping {pkg}")
    subprocess.run(f"su -c 'am force-stop {pkg}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

def launch(cfg):
    vip, place = cfg.get("vip_link", 0), cfg.get("place_id", 0)
    if vip:
        m = re.search(r'/games/(\d+)[^?]*\?privateServerLinkCode=([\w-]+)', vip)
        if not m: return log("[ERROR] Invalid vip_link format")
        uri = f"roblox://placeID={m[1]}&LinkCode={m[2]}"
        log(f"Joining VIP → place {m[1]}")
    elif place:
        uri = f"roblox://placeID={place}"
        log(f"Joining public → place {place}")
    else:
        return log("[ERROR] No place_id or vip_link in config")

    dlog(f"URI: {uri}", cfg)
    subprocess.run(["am", "start", "-n", "com.roblox.client/com.roblox.client.startup.ActivitySplash"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", uri],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def rejoin(cfg):
    force_stop(cfg)
    launch(cfg)
    wait = int(cfg.get("load_wait", 35))
    log(f"Waiting {wait}s for game to load...")
    time.sleep(wait)

# ── WEBHOOK ─────────────────────────────────────
def send_webhook(cfg, presence, user_info):
    url = cfg.get("webhook_url", "").strip()
    if not url: return
    id_file  = cfg.get("webhook_message_id_file", "webhook_msg_id.txt")
    in_game  = presence.get("in_game", False)
    username = user_info.get("username", str(cfg.get("user_id")))
    now      = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    desc = f"**User:** {username}\n**Status:** {'🟢 In Game' if in_game else '🔴 Offline'}"
    if in_game and presence.get("location"): desc += f"\n**Location:** {presence['location']}"
    if in_game and presence.get("place_id"): desc += f"\n**Place ID:** {presence['place_id']}"

    payload = {"embeds": [{
        "title": "Roblox Auto Rejoin", "description": desc,
        "color": 0x00FF00 if in_game else 0xFF0000,
        "footer": {"text": f"Last checked: {now}"},
    }]}

    try:
        msg_id = open(id_file).read().strip() if os.path.exists(id_file) else None
        if msg_id:
            r = requests.patch(f"{url}/messages/{msg_id}", json=payload, timeout=10)
            if r.status_code in (200, 204): return
            os.remove(id_file)
        r = requests.post(url + "?wait=true", json=payload, timeout=10)
        if r.ok:
            open(id_file, "w").write(r.json()["id"])
    except Exception as e:
        dlog(f"webhook: {e}", cfg)

# ── DISPLAY ─────────────────────────────────────
def print_status(cfg, presence, user_info, offline_counter, limit, next_force_in):
    clear()
    W, now = 42, datetime.datetime.now().strftime("%H:%M:%S")
    print("=" * W)
    print("        Roblox Auto Rejoin")
    print("=" * W)
    if user_info:
        print(f"  Name     : {user_info.get('display_name', '?')}")
        print(f"  Username : @{user_info.get('username', '?')}")
        print(f"  ID       : {user_info.get('user_id', '?')}")
    else:
        print(f"  ID       : {cfg.get('user_id')}")
    print("-" * W)

    in_game = presence.get("in_game", False)
    print(f"  Time     : {now}")
    print(f"  Status   : {'🟢 In Game' if in_game else '🔴 Not In Game'}")
    if in_game:
        if presence.get("location"): print(f"  Location : {presence['location']}")
        if presence.get("place_id"): print(f"  Place ID : {presence['place_id']}")
    else:
        if presence.get("last_online"): print(f"  Last On  : {presence['last_online']}")
        print(f"  Offline  : {offline_counter+1} / {limit}")

    if next_force_in is not None:
        print(f"  Next forced rejoin in : {next_force_in/60:.1f} min")
    print("=" * W)

# ── MAIN ────────────────────────────────────────
def main():
    cfg = load_config()
    user_info = fetch_user_info(cfg)

    clear()
    log("Roblox Auto Rejoin starting...")
    if user_info:
        log(f"Account: {user_info['display_name']} (@{user_info['username']})")

    offline_counter, user_info_ticker = 0, 0
    last_rejoin = time.time()

    while True:
        cfg   = load_config()
        limit = int(cfg.get("offline_checks_before_rejoin", 3))
        force_hours = float(cfg.get("force_rejoin_hours") or 0)

        user_info_ticker += 1
        if user_info_ticker >= 30 or not user_info:
            user_info, user_info_ticker = fetch_user_info(cfg), 0

        presence = fetch_presence(cfg)

        next_force_in = None
        if force_hours > 0:
            next_force_in = max(0, force_hours * 3600 - (time.time() - last_rejoin))

        print_status(cfg, presence, user_info, offline_counter, limit, next_force_in)
        send_webhook(cfg, presence, user_info)

        # ── forced periodic rejoin, regardless of presence ──
        if force_hours > 0 and (time.time() - last_rejoin) >= force_hours * 3600:
            log(f"Forced rejoin timer hit ({force_hours}h) — rejoining")
            rejoin(cfg)
            offline_counter, last_rejoin = 0, time.time()
            continue

        if presence["in_game"]:
            offline_counter = 0
            time.sleep(int(cfg.get("check_interval_in_game", 20)) + random.uniform(0, 3))
        else:
            offline_counter += 1
            if offline_counter >= limit:
                log(f"Offline {offline_counter}x in a row — rejoining")
                rejoin(cfg)
                offline_counter, last_rejoin = 0, time.time()
            else:
                time.sleep(int(cfg.get("check_interval_not_in_game", 30)) + random.uniform(0, 2))

if __name__ == "__main__":
    main()
