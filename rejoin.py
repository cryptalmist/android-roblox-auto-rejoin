import json, time, re, subprocess, sys, os, datetime

try:
    import requests
except ImportError:
    print("Module 'requests' not found. Auto-installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    import requests
time.sleep(1)

def load_config():
    with open("config.json") as f:
        return json.load(f)

config = load_config()

# global debug flag
DEBUG = config.get("debug", False)

def dprint(msg):
    """Print only if debug enabled"""
    if DEBUG:
        print(f"[DEBUG] {msg}")

def clear_logs():
    subprocess.run("clear", shell=True)

def get_package_name():
    """Return package based on vng_mode"""
    return "com.roblox.client.vnggames" if config.get("vng_mode", True) else "com.roblox.client"

def kill_roblox(package):
    try:
        pid = subprocess.getoutput(f"su -c 'pidof {package}'").strip()
        if pid:
            print(f"[INFO] Roblox running with PID {pid} → Killing it")
            subprocess.run(f"su -c 'kill -9 {pid}'", shell=True, check=True)
            print("[INFO] Roblox killed successfully")
        else:
            print("[INFO] Roblox is not running")
    except Exception as e:
        print(f"[ERROR] Failed to kill Roblox: {e}")

def extract_placeid_and_pscode(url):
    match = re.search(r'/games/(\d+)[^?]*\?privateServerLinkCode=([\w-]+)', url)
    if not match:
        raise ValueError("Invalid VIP link format")
    return match.groups()

def is_user_in_game(user_id, presence_endpoint):
    resp = requests.post(presence_endpoint, json={"userIds": [int(user_id)]})
    resp.raise_for_status()
    pres = resp.json().get("userPresences", [])
    return bool(pres and pres[0].get("userPresenceType") == 2)

def send_or_update_webhook(config, in_game):
    WEBHOOK_URL = config.get("webhook_url", "")
    if not WEBHOOK_URL:
        return

    WEBHOOK_MESSAGE_ID_FILE = os.path.expanduser(config.get("webhook_message_id_file", "webhook_message_id.txt"))

    last_update = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vip_link = config["vip_link"]
    embed = {
        "title": "Roblox Auto-Rejoin Status",
        "description": (
            f"**User:** {config['user']}\n"
            f"**Status:** {'In Game ✅' if in_game else 'Not In Game ❌'}\n"
            f"**VIP Link:** [Click to Join]({vip_link})"
        ),
        "color": 0x00ff00 if in_game else 0xff0000,
        "footer": {"text": f"Last Update: {last_update}"}
    }

    # edit existing message if file exists
    if os.path.exists(WEBHOOK_MESSAGE_ID_FILE):
        with open(WEBHOOK_MESSAGE_ID_FILE) as f:
            message_id = f.read().strip()
        r = requests.patch(f"{WEBHOOK_URL}/messages/{message_id}", json={"embeds": [embed]})
        dprint(f"PATCH status: {r.status_code} text: {r.text}")
        if r.status_code not in (200, 204):
            print("[WARN] Failed to edit message, will send new one next time")
            os.remove(WEBHOOK_MESSAGE_ID_FILE)

    # send a new one if no file
    if not os.path.exists(WEBHOOK_MESSAGE_ID_FILE):
        r = requests.post(WEBHOOK_URL + "?wait=true", json={"embeds": [embed]})
        dprint(f"POST status: {r.status_code} text: {r.text}")
        if r.ok:
            message_id = r.json()["id"]
            with open(WEBHOOK_MESSAGE_ID_FILE, "w") as f:
                f.write(message_id)
            print(f"[INFO] Saved new message id: {message_id}")
        else:
            print("[ERROR] Failed to send webhook:", r.text)

def rejoin_vip(vip_link):
    package = get_package_name()
    kill_roblox(package)
    time.sleep(2)
    place_id, link_code = extract_placeid_and_pscode(vip_link)
    print(f"[INFO] Launching VIP link → PlaceID: {place_id}, LinkCode: {link_code}")
    subprocess.run([
        "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", f"roblox://placeID={place_id}&LinkCode={link_code}"
    ], check=True)

def main_loop():
    global config, DEBUG
    while True:
        config = load_config()
        DEBUG = config.get("debug", False)

        USER = str(config["user"])
        VIP_LINK = config["vip_link"]
        DELAY_IN_GAME = int(config.get("check_interval_in_game", 15))
        DELAY_NOT_IN_GAME = int(config.get("check_interval_not_in_game", 30))
        ROPROXY = config.get("roproxy", "roproxy.com")
        PRESENCE_ENDPOINT = f"https://presence.{ROPROXY}/v1/presence/users"

        clear_logs()
        print("=== Roblox Auto-Rejoin Script ===")
        print(f"[INFO] Using package: {get_package_name()}")

        try:
            in_game = is_user_in_game(USER, PRESENCE_ENDPOINT)
        except Exception as e:
            print(f"[ERROR] Could not check user status: {e}")
            time.sleep(10)
            continue

        send_or_update_webhook(config, in_game)

        if in_game:
            print(f"[INFO] User {USER} is IN game → waiting {DELAY_IN_GAME}s")
            time.sleep(DELAY_IN_GAME)
        else:
            print(f"[INFO] User {USER} is NOT in game → launching VIP link and waiting {DELAY_NOT_IN_GAME}s")
            try:
                rejoin_vip(VIP_LINK)
            except Exception as e:
                print(f"[ERROR] Failed to launch VIP link: {e}")
            time.sleep(DELAY_NOT_IN_GAME)

if __name__ == "__main__":
    clear_logs()
    print("Starting auto-rejoin loop…")
    time.sleep(1)
    main_loop()
