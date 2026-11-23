import os
import re
import csv
import json
import uuid
import urllib.request
import urllib.error
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(
    page_title="DHRL Race Control Dispatcher",
    page_icon="🏁",
    layout="centered"
)


def get_secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()


SERIES_CONFIG = {
    "Motive Truck Series": {
        "results_webhook": get_secret("WEBHOOK_TRUCKS"),
        "standings_webhook": get_secret("WEBHOOK_TRUCKS_STANDINGS"),
        "standings_msg_id": get_secret("TRUCKS_STANDINGS_MSG_ID", ""),
        "logo_file": "Motive_TruckSeries_Logo.png",
        "banner_file": "Motive_TruckSeries_Logo.png",
        "color": 0xD92525,  # Motive Red
        "standings_title": "🏆 SEASON 2 — MOTIVE TRUCK SERIES STANDINGS"
    },
    "Reno Wraps Series": {
        "results_webhook": get_secret("WEBHOOK_RENO"),
        "standings_webhook": get_secret("WEBHOOK_RENO_STANDINGS"),
        "standings_msg_id": get_secret("RENO_STANDINGS_MSG_ID", ""),
        "logo_file": "Reno_WrapsSeries_Logo.png",
        "banner_file": "Reno_WrapsSeries_Logo.png",
        "color": 0x10B981,  # Reno Green
        "standings_title": "🏆 RENO WRAPS SERIES STANDINGS"
    },
    "DHR Cup Series": {
        "results_webhook": get_secret("WEBHOOK_CUP"),
        "standings_webhook": get_secret("WEBHOOK_CUP_STANDINGS"),
        "standings_msg_id": get_secret("CUP_STANDINGS_MSG_ID", ""),
        "logo_file": "DHR_CupSeries_Logo.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0x2563EB,  # DHR Blue
        "standings_title": "🏆 DHR CUP SERIES STANDINGS"
    },
    "Hosted Results": {
        "results_webhook": get_secret("WEBHOOK_HOSTED"),
        "standings_webhook": "",
        "standings_msg_id": "",
        "logo_file": "DHR_League_Banner31.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0xF59E0B,  # Hosted Amber
        "standings_title": ""
    }
}

HOSTED_BANNER_OPTIONS = {
    "Default League Banner (DHR_League_Banner31.jpg)": "DHR_League_Banner31.jpg",
    "Motive Truck Series (Motive_TruckSeries_Logo.png)": "Motive_TruckSeries_Logo.png",
    "Reno Wraps Series (Reno_WrapsSeries_Logo.png)": "Reno_WrapsSeries_Logo.png",
    "DHR Cup Series (DHR_CupSeries_Logo.png)": "DHR_CupSeries_Logo.png",
}

CAR_EMOJIS = {
    "21": "<:21_redyellow:1566653218182664263>",
    "31": "<:31:1566652973625638932>",
    "77": "<:77:1566653027664793680>",
    "55": "<:55:1566652782562377779>",
    "41": "<:41:1566652901265514586>",
    "13": "<:13:1562378213886267433>",
    "97": "<:97:1566652935096508606>",
    "18": "<:18:1566660026947608636>",
    "12": "<:12:1566653171483545651>",
    "17": "<:17:1566653111584694432>",
    "22": "<:22:1566652856105439413>",
    "9":  "<:9_:1566653069662494813>",
}


def nascar_points(pos: int) -> int:
    if pos == 1:
        return 40
    elif 2 <= pos <= 35:
        return 35 - (pos - 2)
    elif 36 <= pos <= 40:
        return 1
    return 0


def format_car_tag(car_num: str) -> str:
    return CAR_EMOJIS.get(str(car_num), f"#{car_num}")


def parse_lap_time_str(time_val):
    if not time_val:
        return 999999.0
    val = str(time_val).strip()
    try:
        if ":" in val:
            parts = val.split(":")
            return float(parts[0]) * 60 + float(parts[1])
        return float(val)
    except ValueError:
        return 999999.0


def parse_csv_text(text: str):
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        return [], "", "Unknown Track"

    meta_blob = " ".join(raw_lines[:6]).lower()
    track_name = "Unknown Track"
    if len(raw_lines) > 1 and "Track" in raw_lines[0]:
        meta_row = next(csv.reader([raw_lines[1]]))
        if len(meta_row) > 1:
            track_name = meta_row[1].replace(" - Oval", "").strip()

    header_idx = 0
    for idx, line in enumerate(raw_lines):
        lower = line.lower()
        if ("pos" in lower or "fin" in lower) and ("driver" in lower or "name" in lower or "cust" in lower):
            header_idx = idx
            break

    reader = csv.DictReader(raw_lines[header_idx:])
    drivers = []

    for r in reader:
        norm = {k.strip().lower(): v.strip() for k, v in r.items() if k and v is not None}

        pos = norm.get("fin pos") or norm.get("pos") or norm.get("position") or norm.get("finishing position") or ""
        start_pos = norm.get("start pos") or norm.get("qual pos") or norm.get("starting position") or pos
        car_num = norm.get("car #") or norm.get("car no") or norm.get("car number") or norm.get("car") or "??"
        raw_name = norm.get("driver") or norm.get("name") or norm.get("display name") or norm.get("cust name") or "Unknown"
        clean_name = re.sub(r"\d+$", "", raw_name).strip()

        fast_lap = (
            norm.get("fastest lap time") or norm.get("fastest lap") or
            norm.get("best lap time") or norm.get("best lap") or norm.get("fast lap") or ""
        )
        laps = (
            norm.get("laps complete") or norm.get("laps completed") or
            norm.get("laps comp") or norm.get("comp laps") or norm.get("laps") or "0"
        )
        interval = norm.get("interval") or norm.get("diff") or norm.get("gap") or "--"
        inc = norm.get("inc") or norm.get("incidents") or "0"
        led = norm.get("laps led") or norm.get("led") or "0"

        if pos and str(pos).isdigit():
            drivers.append({
                "pos": int(pos),
                "start_pos": int(start_pos) if str(start_pos).isdigit() else int(pos),
                "car_num": str(car_num).replace("#", "").strip(),
                "name": clean_name,
                "laps": int(laps) if str(laps).isdigit() else 0,
                "interval": str(interval),
                "inc": int(inc.replace("x", "")) if str(inc).replace("x", "").isdigit() else 0,
                "led": int(led) if str(led).isdigit() else 0,
                "fast_lap": str(fast_lap)
            })

    drivers.sort(key=lambda d: d["pos"])
    return drivers, meta_blob, track_name


def parse_json_text(text: str):
    data = json.loads(text)
    meta_blob = ""
    track_name = "Unknown Track"
    race_results = []

    if isinstance(data, dict):
        meta_blob = f"{data.get('session_name', '')} {data.get('league_name', '')}".lower()
        track_name = data.get("track", {}).get("track_name", "Unknown Track").replace(" - Oval", "").strip()
        sessions = data.get("session_results", [])
        race = next((s for s in sessions if s.get("simsession_type_name") == "Race"), None)
        if not race and sessions:
            race = sessions[-1]
        race_results = race.get("results", []) if race else data.get("results", [])
    elif isinstance(data, list):
        race_results = data

    drivers = []
    for idx, d in enumerate(race_results):
        fin_p = d.get("finish_position", idx)
        start_p = d.get("starting_position", fin_p)
        pos = (fin_p + 1) if isinstance(fin_p, int) else (idx + 1)
        start_pos = (start_p + 1) if isinstance(start_p, int) else pos

        car_num = str(d.get("livery", {}).get("car_number", d.get("car_number", d.get("car_num", "??"))))
        raw_name = d.get("display_name") or d.get("name") or d.get("cust_name") or "Unknown"
        clean_name = re.sub(r"\d+$", "", raw_name).strip()
        laps = d.get("laps_complete", d.get("laps", 0))
        inc = d.get("incidents", d.get("inc", 0))
        led = d.get("laps_lead", d.get("laps_led", d.get("led", 0)))
        interval = str(d.get("interval", "--"))

        best_time_raw = d.get("best_lap_time", 0)
        fast_lap_str = f"{best_time_raw / 10000.0:.3f}" if isinstance(best_time_raw, (int, float)) and best_time_raw > 0 else ""

        drivers.append({
            "pos": int(pos),
            "start_pos": int(start_pos),
            "car_num": car_num,
            "name": clean_name,
            "laps": int(laps) if str(laps).isdigit() else 0,
            "interval": interval,
            "inc": int(inc) if str(inc).isdigit() else 0,
            "led": int(led) if str(led).isdigit() else 0,
            "fast_lap": fast_lap_str
        })

    drivers.sort(key=lambda d: d["pos"])
    return drivers, meta_blob, track_name


def parse_any_payload(raw_text: str):
    stripped = raw_text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_json_text(stripped)
    return parse_csv_text(raw_text)


def detect_hosted_banner(meta_blob: str) -> str:
    if "truck" in meta_blob or "motive" in meta_blob:
        return "Motive Truck Series (Motive_TruckSeries_Logo.png)"
    if "reno" in meta_blob or "xfinity" in meta_blob or "o'reilly" in meta_blob:
        return "Reno Wraps Series (Reno_WrapsSeries_Logo.png)"
    if "cup" in meta_blob or "next gen" in meta_blob:
        return "DHR Cup Series (DHR_CupSeries_Logo.png)"
    return "Default League Banner (DHR_League_Banner31.jpg)"


def fetch_discord_standings_message(webhook_url: str, message_id: str):
    """Fetches an existing webhook message from Discord so standings persist in Discord itself."""
    if not webhook_url or not message_id:
        return None
    url = f"{webhook_url.rstrip('/')}/messages/{message_id.strip()}"
    req = urllib.request.Request(url, headers={"User-Agent": "DHRL-RaceControl-CloudDispatcher"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            embeds = data.get("embeds", [])
            if embeds:
                return embeds[0].get("description", "")
    except Exception:
        return None
    return None


def parse_existing_standings_text(desc_text: str):
    """Parses driver rows and race winners out of an existing Discord Standings embed."""
    drivers_state = {}
    winners_blocks = []

    if not desc_text:
        return drivers_state, winners_blocks

    parts = desc_text.split("🏁 **Season 2 Race Winners**")
    if len(parts) == 1:
        parts = desc_text.split("🏁 **Race Winners**")

    table_part = parts[0]
    winners_part = parts[1] if len(parts) > 1 else ""

    for line in table_part.splitlines():
        line = line.strip()
        # Matches: "1 | #82 **Chris James** | 1 | 1 | **40**" or custom emoji "<:13:123> **Name**"
        m = re.match(
            r"^\d+\s*\|\s*(?:<:[a-zA-Z0-9_~]+:\d+>|#?(\w+))\s*\*\*(.+?)\*\*\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*\*\*(\d+)\*\*",
            line
        )
        if m:
            car_num, name, wins, starts, pts = m.groups()
            emoji_match = re.search(r"<:([a-zA-Z0-9_~]+):\d+>", line)
            resolved_car = emoji_match.group(1).split("_")[0] if emoji_match else (car_num or "??")
            drivers_state[name.strip()] = {
                "car_num": resolved_car,
                "wins": int(wins),
                "starts": int(starts),
                "pts": int(pts)
            }

    if winners_part:
        blocks = [b.strip() for b in winners_part.strip().split("\n\n") if b.strip() and "Pending" not in b]
        winners_blocks.extend(blocks)

    return drivers_state, winners_blocks


def post_discord_multipart(webhook_url, payload_dict, files_list):
    boundary = f"----DHRLBoundary{uuid.uuid4().hex}"
    body = bytearray()

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="payload_json"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(payload_dict).encode("utf-8"))
    body.extend(b"\r\n")

    for idx, (filename, file_path, mime_type) in enumerate(files_list):
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="files[{idx}]"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        webhook_url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "DHRL-RaceControl-CloudDispatcher"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, str(e)


def send_json_webhook(webhook_url: str, payload_dict: dict, edit_message_id: str = ""):
    """Posts a new message (with ?wait=true to return its Message ID) or edits an existing one."""
    if edit_message_id.strip():
        url = f"{webhook_url.rstrip('/')}/messages/{edit_message_id.strip()}"
        method = "PATCH"
    else:
        sep = "&" if "?" in webhook_url else "?"
        url = f"{webhook_url}{sep}wait=true"
        method = "POST"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload_dict).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DHRL-RaceControl-CloudDispatcher"
        },
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_resp = resp.read().decode("utf-8", errors="ignore")
            msg_id = ""
            if raw_resp:
                try:
                    msg_id = json.loads(raw_resp).get("id", "")
                except Exception:
                    pass
            return resp.status, msg_id, ""
    except urllib.error.HTTPError as e:
        return e.code, "", e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, "", str(e)


# --- UI HEADER ---
st.title("🏁 DRAFT HOUSE RACING LEAGUE")
st.caption("Cloud Race Control • Official Results & Championship Standings")

required_pin = get_secret("STAFF_PIN")
if required_pin:
    entered_pin = st.text_input("🔒 DHRL Staff Passcode", type="password", placeholder="Enter staff PIN to unlock...")
    if entered_pin != required_pin:
        st.info("Enter the DHRL Staff Passcode to access Race Control.")
        st.stop()

selected_series = st.radio(
    "Target Series / Discord Channel:",
    options=list(SERIES_CONFIG.keys()),
    horizontal=True
)

tab_upload, tab_paste = st.tabs([
    "📁 Drag & Drop CSV / JSON File",
    "📋 Paste Raw CSV / JSON Text"
])

raw_input_text = ""
detected_sub_id = "Official Event"

with tab_upload:
    uploaded_file = st.file_uploader(
        "Drag the CSV/JSON file here (or click Browse files)",
        type=["csv", "json"],
        key="file_uploader_input"
    )
    if uploaded_file is not None:
        raw_input_text = uploaded_file.getvalue().decode("utf-8-sig", errors="ignore")
        for part in uploaded_file.name.split("_"):
            if part.isdigit() and len(part) >= 7:
                detected_sub_id = part
                break

with tab_paste:
    pasted_text = st.text_area(
        "Paste raw CSV or JSON text directly below:",
        height=180,
        placeholder='Start Time,Track,Series,Hosted Session Name\n"2026-11-16T00:00:35Z","Texas Motor Speedway - Oval",...',
        key="raw_text_input"
    )
    if pasted_text.strip() and not raw_input_text:
        raw_input_text = pasted_text

if raw_input_text.strip():
    try:
        drivers, meta_blob, detected_track = parse_any_payload(raw_input_text)
    except Exception as parse_err:
        st.error(f"❌ Error reading CSV/JSON data: {parse_err}")
        st.stop()

    if not drivers:
        st.error("❌ Could not parse any driver results from that input.")
        st.stop()

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        subsession_id = st.text_input("Subsession ID:", value=detected_sub_id)
    with col_meta2:
        track_display = st.text_input("Track Name:", value=detected_track)

    chosen_hosted_banner = None
    if selected_series == "Hosted Results":
        default_banner_label = detect_hosted_banner(meta_blob)
        banner_keys = list(HOSTED_BANNER_OPTIONS.keys())
        chosen_label = st.selectbox(
            "Hosted Results Bottom Banner:",
            options=banner_keys,
            index=banner_keys.index(default_banner_label)
        )
        chosen_hosted_banner = HOSTED_BANNER_OPTIONS[chosen_label]

    # --- COMPUTE RACE RESULTS & AWARDS ---
    total_starters = len(drivers)
    for d in drivers:
        d["pos_diff"] = d["start_pos"] - d["pos"]

    hard_charger = max(drivers, key=lambda d: d["pos_diff"], default=None)
    biggest_drop = min(drivers, key=lambda d: d["pos_diff"], default=None)

    hc_name = hard_charger["name"][:15] if hard_charger else "None"
    hc_gain = f"+{hard_charger['pos_diff']}" if hard_charger and hard_charger["pos_diff"] > 0 else "0"

    bd_name = biggest_drop["name"][:15] if biggest_drop else "None"
    bd_loss = f"{biggest_drop['pos_diff']}" if biggest_drop and biggest_drop["pos_diff"] < 0 else "0"

    most_led = max(drivers, key=lambda d: d["led"], default=None)
    led_name = most_led["name"][:15] if most_led else "None"
    led_count = most_led["led"] if most_led else 0

    fast_candidates = [d for d in drivers if d.get("fast_lap") and parse_lap_time_str(d["fast_lap"]) < 999999.0]
    if fast_candidates:
        fast_driver = min(fast_candidates, key=lambda d: parse_lap_time_str(d["fast_lap"]))
        fast_str = f"{fast_driver['fast_lap']} ({fast_driver['name'][:12]})"
    else:
        fast_str = "N/A"

    p2 = drivers[1] if len(drivers) > 1 else None
    mov_str = p2["interval"] if p2 else "N/A"
    if mov_str.startswith("-"):
        mov_str = f"+{mov_str.lstrip('-')}"
    if not mov_str.endswith("s") and "." in mov_str:
        mov_str = f"{mov_str}s"

    leader_laps = max((d["laps"] for d in drivers), default=0)
    finishers = [d for d in drivers if d["laps"] > 0 and d["laps"] >= (leader_laps * 0.50)]
    if finishers:
        min_inc = min(d["inc"] for d in finishers)
        clean_finishers = [d["name"][:14] for d in finishers if d["inc"] == min_inc]
        clean_str = f"{clean_finishers[0]} ({min_inc}x)"
    else:
        clean_str = "None"

    header_lines = ["```text", "P   #   DRIVER            LAPS  INTERVAL  INC", "-" * 43]
    row_lines = []
    char_count = sum(len(x) + 1 for x in header_lines) + 10

    for idx, d in enumerate(drivers):
        pos = str(d["pos"])
        num = str(d["car_num"])
        name = str(d["name"])[:16]
        laps = str(d["laps"])
        raw_int = str(d["interval"]).strip()

        if pos == "1" or raw_int in ["0.000", "-00.000", "0", ""]:
            interval = "WINNER"
        elif raw_int.endswith("L") or "lap" in raw_int.lower():
            interval = raw_int.replace(" ", "")
        elif raw_int.replace(".", "").replace("-", "").isdigit():
            interval = f"+{raw_int.lstrip('-')}s"[:8]
        else:
            interval = raw_int[:8]

        inc = f"{d['inc']}x"
        row_str = f"{pos:<3} #{num:<3} {name:<17} {laps:<5} {interval:<9} {inc}"

        if char_count + len(row_str) + 35 > 1000:
            remaining = len(drivers) - idx
            row_lines.append(f"... +{remaining} more drivers")
            break

        row_lines.append(row_str)
        char_count += len(row_str) + 1

    standings_block = "\n".join(header_lines + row_lines + ["```"])

    starters_content = f"> 🟢 **{total_starters} Drivers** took the green flag."
    awards_content = (
        f"> ⚡ **Hard Charger:** {hc_name} (`{hc_gain}`)\n"
        f"> 👑 **Most Laps Led:** {led_name} (`{led_count} laps`)\n"
        f"> 🔻 **Biggest Drop:** {bd_name} (`{bd_loss}`)\n"
        f"> ⏱️ **Fastest Lap:** `{fast_str}`\n"
        f"> ⏱️ **Margin of Victory:** `{mov_str}`\n"
        f"> 🛡️ **Cleanest Driver:** {clean_str}"
    )

    # --- SECTION 1: RACE RESULTS ---
    st.divider()
    st.subheader("1️⃣ Official Race Results")

    with st.expander("📋 Preview Race Results Embed", expanded=False):
        st.markdown(f"**Title:** 🏁 Official Results — Subsession `{subsession_id}`")
        st.markdown(awards_content)
        st.markdown(standings_block)

    def dispatch_results():
        config = SERIES_CONFIG[selected_series]
        webhook_url = config.get("results_webhook", "")
        if not webhook_url:
            st.error(f"❌ Missing results webhook for {selected_series} in Streamlit Secrets!")
            return False

        logo_target = config["logo_file"]
        banner_target = chosen_hosted_banner if chosen_hosted_banner else config["banner_file"]

        logo_path = os.path.join(BASE_DIR, logo_target)
        if not os.path.exists(logo_path):
            logo_target = "DHR_League_Banner31.jpg"
            logo_path = os.path.join(BASE_DIR, logo_target)

        banner_path = os.path.join(BASE_DIR, banner_target)
        if not os.path.exists(banner_path):
            banner_target = "DHR_League_Banner31.jpg"
            banner_path = os.path.join(BASE_DIR, banner_target)

        author_obj = {"name": f"Draft House Racing League • {selected_series}"}
        if os.path.exists(logo_path):
            author_obj["icon_url"] = f"attachment://{logo_target}"

        embed = {
            "author": author_obj,
            "title": f"🏁 Official Results — Subsession `{subsession_id}`",
            "color": config["color"],
            "fields": [
                {"name": "🏁 Field Starters", "value": starters_content[:1024], "inline": False},
                {"name": "🏆 Race Awards & Highlights", "value": awards_content[:1024], "inline": False},
                {"name": "📋 Official Standings", "value": standings_block[:1024], "inline": False},
            ],
            "footer": {"text": "Draft House Racing League • Official Session Results"},
        }

        if os.path.exists(banner_path):
            embed["image"] = {"url": f"attachment://{banner_target}"}

        def get_mime(fname):
            return "image/png" if fname.lower().endswith(".png") else "image/jpeg"

        files_list = []
        if logo_target == banner_target:
            if os.path.exists(logo_path):
                files_list.append((logo_target, logo_path, get_mime(logo_target)))
        else:
            if os.path.exists(logo_path):
                files_list.append((logo_target, logo_path, get_mime(logo_target)))
            if os.path.exists(banner_path):
                files_list.append((banner_target, banner_path, get_mime(banner_target)))

        status_code, err_text = post_discord_multipart(webhook_url, {"embeds": [embed]}, files_list)
        if status_code in (200, 204):
            st.success(f"🏁 KA-CHOW!! Race Results dispatched to **{selected_series}**!")
            return True
        else:
            st.error(f"❌ Discord Error {status_code}: {err_text[:150]}")
            return False

    if st.button("🚦 Post Race Results Only", use_container_width=True):
        with st.spinner("Dispatching Race Results..."):
            dispatch_results()

    # --- SECTION 2: CHAMPIONSHIP STANDINGS (FOR SERIES RACES) ---
    config = SERIES_CONFIG[selected_series]
    standings_webhook = config.get("standings_webhook", "")

    if standings_webhook:
        st.divider()
        st.subheader(f"2️⃣ {selected_series} Standings Update")

        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            existing_msg_id = st.text_input(
                "Existing Discord Standings Message ID (leave blank for Race 1 / new post):",
                value=config.get("standings_msg_id", ""),
                help="Right-click the pinned Standings post in Discord -> Copy Message ID. Leave blank on Race 1 to create a fresh post!"
            )
        with col_s2:
            score_zero_laps = st.checkbox(
                "Award points to 0-lap DNS?",
                value=True,
                help="Checked = P14 with 0 laps still receives 23 pts. Unchecked = 0 pts."
            )

        # Fetch prior standings from Discord if Message ID is provided
        prior_desc = fetch_discord_standings_message(standings_webhook, existing_msg_id) if existing_msg_id.strip() else ""
        if existing_msg_id.strip() and prior_desc is None:
            st.warning("⚠️ Could not fetch that Message ID from Discord—starting calculation from a fresh 0-point slate unless you paste prior standings below.")

        with st.expander("🛠️ Advanced: View / Paste Prior Standings Text (Optional)", expanded=False):
            manual_prior = st.text_area(
                "Auto-loaded from Discord Message ID above (or paste prior standings text here):",
                value=prior_desc or "",
                height=140
            )

        base_drivers, base_winners = parse_existing_standings_text(manual_prior)
        race_num = len(base_winners) + 1
        race_label = st.text_input("Race Label for Winners List:", value=f"Race {race_num} — {track_display}")

        # Merge current race points into base_drivers
        updated_drivers = {k: dict(v) for k, v in base_drivers.items()}
        winner_entry = None

        for d in drivers:
            name = d["name"]
            if name not in updated_drivers:
                updated_drivers[name] = {
                    "car_num": d["car_num"],
                    "wins": 0,
                    "starts": 0,
                    "pts": 0,
                    "best_fin": 99
                }

            pts_earned = 0 if (d["laps"] == 0 and not score_zero_laps) else nascar_points(d["pos"])
            updated_drivers[name]["car_num"] = d["car_num"]
            updated_drivers[name]["starts"] += 1
            updated_drivers[name]["pts"] += pts_earned
            updated_drivers[name]["last_fin"] = d["pos"]

            if d["pos"] == 1:
                updated_drivers[name]["wins"] += 1
                tag = format_car_tag(d["car_num"])
                winner_entry = f"🏆 **{race_label}**\n{tag} {name}"

        sorted_drivers = sorted(
            updated_drivers.items(),
            key=lambda x: (-x[1]["pts"], -x[1]["wins"], x[1].get("last_fin", 99), x[1]["starts"])
        )

        # --- CRISP MONOSPACED STANDINGS TABLE (Never wraps in Discord) ---
        table_lines = [
            "```text",
            "POS  #    DRIVER             W  S   PTS",
            "-" * 41
        ]
        for idx, (d_name, d_info) in enumerate(sorted_drivers, 1):
            c_num = f"#{d_info['car_num']}"
            clean_d = d_name[:17]
            wins_s = str(d_info["wins"])
            starts_s = str(d_info["starts"])
            pts_s = str(d_info["pts"])
            table_lines.append(f"{idx:<4} {c_num:<4} {clean_d:<18} {wins_s:<2} {starts_s:<3} {pts_s}")
        table_lines.append("```")

        winners_lines = ["\n🏁 **Season 2 Race Winners**\n"]
        for wb in base_winners:
            # Ensure clean two-line spacing per winner
            clean_wb = wb.replace(" 🏆", "\n\n🏆").strip()
            winners_lines.append(f"{clean_wb}\n")
        if winner_entry:
            winners_lines.append(winner_entry)

        final_standings_desc = "\n".join(table_lines + winners_lines).strip()

        with st.expander("📊 Preview Updated Championship Standings", expanded=True):
            st.markdown(final_standings_desc)

        update_in_place = st.checkbox(
            "Edit existing Discord standings post in-place (uncheck to post a brand-new message)",
            value=bool(existing_msg_id.strip())
        )

        def dispatch_standings():
            embed_payload = {
                "embeds": [
                    {
                        "author": {"name": f"Draft House Racing League • {selected_series}"},
                        "title": config["standings_title"],
                        "description": final_standings_desc[:4096],
                        "color": config["color"],
                        "footer": {"text": "Draft House Racing League • Season 2 Official Points"}
                    }
                ]
            }
            target_edit_id = existing_msg_id.strip() if update_in_place else ""
            s_code, new_msg_id, err = send_json_webhook(standings_webhook, embed_payload, target_edit_id)
            if s_code in (200, 204):
                st.success(f"🏆 Standings updated in **{selected_series}**!")
                if new_msg_id and not target_edit_id:
                    st.info(f"📌 **New Standings Message ID:** `{new_msg_id}` — Save this in Streamlit Secrets as `TRUCKS_STANDINGS_MSG_ID = \"{new_msg_id}\"` so next week's race automatically adds onto these points!")
                return True
            else:
                st.error(f"❌ Standings Dispatch Error {s_code}: {err[:150]}")
                return False

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🏆 Post Standings Only", use_container_width=True):
                with st.spinner("Updating Standings..."):
                    dispatch_standings()
        with col_btn2:
            if st.button("🚀 FINISH RACE CONTROL (Post BOTH Results + Standings)", type="primary", use_container_width=True):
                with st.spinner("Dispatching Results & Standings..."):
                    ok1 = dispatch_results()
                    ok2 = dispatch_standings()
                    if ok1 and ok2:
                        st.balloons()
