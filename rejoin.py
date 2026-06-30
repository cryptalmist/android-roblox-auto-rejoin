import json, time, re, subprocess, sys, os, datetime, random

# ── auto install requests ───────────────────────
try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    import requests

# ── default config ──────────────────────────────
DEFAULT_CONFIG = {
    "user": 0,
    "cookie": "",
    "vip_link": "",
    "place_id": "",
    "vng_mode": True,
    "debug": False,
    "clear_logs": True,
    "offline_checks_before_rejoin": 3,
    "check_interval_in_game": 15,
    "check_interval_not_in_game": 30,
    "webhook_url": "",
    "webhook_message_id_file": "webhook_message_id.txt"
}

# ── config ──────────────────────────────────────
def load_config():
    if not os.path.exists("config.json"):
        print("[INFO] Creating default config.json")
        with open("config.json", "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print("[INFO] Edit config.json then restart.")
        sys.exit()
    with open("config.json") as f:
        cfg = json.load(f)
    # fill in any missing keys from defaults
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg

config = load_config()
DEBUG = config.get("debug", False)

def dprint(msg):
    if DEBUG:
        print("[DEBUG]", msg)

# ── terminal clear ──────────────────────────────
def clear_logs():
    if config.get("clear_logs", True):
        print("\033[2J\033[H", end="")

# ── roblox package ──────────────────────────────
def get_package_name():
    return "com.roblox.client.vnggames" if config.get("vng_mode", True) else "com.roblox.client"

# ── session ─────────────────────────────────────
def make_session(cookie=None):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Roblox/WinInet",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    if cookie:
        s.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
    return s

# ── user info ────────────────────────────────────
def get_user_info(user_id, cookie=None):
    session = make_session(cookie)
    info = {}
    try:
        r = session.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=10)
        if r.ok:
            d = r.json()
            info["username"]     = d.get("name", "?")
            info["display_name"] = d.get("displayName", "?")
    except Exception as e:
        dprint(f"User info error: {e}")
    return info

# ── presence check ───────────────────────────────
def is_user_in_game(user_id, cookie=None):
    session = make_session(cookie)
    try:
        r = session.post(
            "https://presence.roblox.com/v1/presence/users",
            json={"userIds": [int(user_id)]},
            timeout=10
        )
        r.raise_for_status()
        pres = r.json().get("userPresences", [])
        if pres:
            p = pres[0]
            ptype      = p.get("userPresenceType", 0)
            place_id   = p.get("placeId")
            game_id    = p.get("gameId")
            location   = p.get("lastLocation", "")
            last_online = p.get("lastOnline", "")[:19].replace("T", " ") if p.get("lastOnline") else ""
            dprint(f"presenceType={ptype} placeId={place_id} gameId={game_id}")
            return ptype == 2, place_id, game_id, location, last_online
        return False, None, None, "", ""
    except Exception as e:
        dprint(f"Presence check error: {e}")
        return False, None, None, "", ""

# ── kill roblox ─────────────────────────────────
def kill_roblox(package):
    try:
        pids = subprocess.getoutput(f"su -c 'pidof {package}'").strip()
        if not pids:
            print("[INFO] Roblox not running")
            return
        for pid in pids.split():
            print(f"[INFO] Killing PID {pid}")
            subprocess.run(f"su -c 'kill -15 {pid}'", shell=True)
            time.sleep(8)
            still = subprocess.getoutput(f"su -c 'pidof {package}'").split()
            if pid in still:
                print("[WARN] Still alive → force kill")
                subprocess.run(f"su -c 'kill -9 {pid}'", shell=True)
                time.sleep(8)
    except Exception as e:
        print("[ERROR] Kill failed:", e)

# ── vip parsing ─────────────────────────────────
def extract_placeid_and_pscode(url):
    match = re.search(r'/games/(\d+)[^?]*\?privateServerLinkCode=([\w-]+)', url)
    if not match:
        raise ValueError("Invalid VIP link format")
    return match.groups()

# ── join ────────────────────────────────────────
def join_vip(link):
    place_id, code = extract_placeid_and_pscode(link)
    uri = f"roblox://placeID={place_id}&LinkCode={code}"
    dprint(f"Launching: {uri}")
    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", uri])

def join_public(place):
    uri = f"roblox://placeID={place}"
    dprint(f"Launching: {uri}")
    subprocess.run(["am", "start", "-a", "android.intent.action.VIEW", "-d", uri])

def rejoin():
    package = get_package_name()
    kill_roblox(package)
    time.sleep(8)

    vip = config.get("vip_link", "")
    place = config.get("place_id", "")

    if vip:
        print("[INFO] Joining VIP server")
        join_vip(vip)
    elif place:
        print("[INFO] Joining public server")
        join_public(place)
    else:
        print("[ERROR] No vip_link or place_id set in config.json")

# ── webhook ─────────────────────────────────────
def send_or_update_webhook(cfg, in_game, place_id=None):
    webhook = cfg.get("webhook_url", "")
    if not webhook:
        return

    file = cfg.get("webhook_message_id_file", "webhook_message_id.txt")
    last = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    desc = f"**User:** {cfg.get('user')}\n**Status:** {'🟢 In Game' if in_game else '🔴 Offline'}"
    if in_game and place_id:
        desc += f"\n**Place ID:** {place_id}"

    embed = {
        "title": "Roblox Auto Rejoin",
        "description": desc,
        "color": 0x00FF00 if in_game else 0xFF0000,
        "footer": {"text": f"Last checked: {last}"}
    }

    try:
        if os.path.exists(file):
            with open(file) as f:
                msg_id = f.read().strip()
            r = requests.patch(f"{webhook}/messages/{msg_id}", json={"embeds": [embed]}, timeout=10)
            if r.status_code not in (200, 204):
                os.remove(file)

        if not os.path.exists(file):
            r = requests.post(webhook + "?wait=true", json={"embeds": [embed]}, timeout=10)
            if r.ok:
                with open(file, "w") as f:
                    f.write(r.json()["id"])
    except Exception as e:
        dprint(f"Webhook error: {e}")

# ── status display ───────────────────────────────
def print_status(offline_counter, limit, in_game, place_id, game_id, location, last_online, user_info):
    clear_logs()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    W = 40
    print("=" * W)
    print("       Roblox Auto Rejoin")
    print("=" * W)

    # account info
    if user_info:
        print(f"  Display Name : {user_info.get('display_name', '?')}")
        print(f"  Username     : {user_info.get('username', '?')}")
        print(f"  User ID      : {config.get('user')}")
    else:
        print(f"  User ID      : {config.get('user')}")

    print("-" * W)

    # presence
    print(f"  Time         : {now}")
    print(f"  VNG Mode     : {config.get('vng_mode')}")
    print(f"  Status       : {'🟢 In Game' if in_game else '🔴 Not In Game'}")

    if in_game:
        if location:
            print(f"  Location     : {location}")
        if place_id:
            print(f"  Place ID     : {place_id}")
        if game_id:
            print(f"  Game ID      : {game_id}")
    else:
        if last_online:
            print(f"  Last Online  : {last_online}")
        print(f"  Offline Ctr  : {offline_counter} / {limit}")

    print("=" * W)

# ── main loop ───────────────────────────────────
def main_loop():
    global config, DEBUG
    offline_counter = 0
    user_info = {}

    while True:
        config = load_config()
        DEBUG = config.get("debug", False)

        user   = str(config.get("user"))
        cookie = config.get("cookie", "") or None
        delay_in  = int(config.get("check_interval_in_game", 15))
        delay_out = int(config.get("check_interval_not_in_game", 30))
        limit     = int(config.get("offline_checks_before_rejoin", 3))

        # refresh user info every ~5 minutes (every 20 ticks at 15s)
        if not user_info or offline_counter % 20 == 0:
            user_info = get_user_info(user, cookie)

        in_game, place_id, game_id, location, last_online = is_user_in_game(user, cookie)

        print_status(offline_counter, limit, in_game, place_id, game_id, location, last_online, user_info)
        send_or_update_webhook(config, in_game, place_id)

        if in_game:
            offline_counter = 0
            time.sleep(delay_in + random.uniform(0, 2))
        else:
            offline_counter += 1
            if offline_counter >= limit:
                print(f"[INFO] Offline limit reached ({limit}) → rejoining")
                rejoin()
                offline_counter = 0
                time.sleep(delay_out + random.uniform(1, 3))
            else:
                time.sleep(delay_out)

# ── start ───────────────────────────────────────
if __name__ == "__main__":
    clear_logs()
    print("[INFO] Starting Roblox Auto Rejoin...")
    time.sleep(1)
    main_loop()
