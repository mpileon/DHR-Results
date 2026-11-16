import os
import csv
import json
import uuid
import urllib.request
import urllib.error
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(
    page_title="DHRL Results Dispatcher",
    page_icon="🏁",
    layout="centered"
)


def get_secret(key: str, default: str = "") -> str:
    """Reads from Streamlit Cloud Secrets first, falling back to environment variables."""
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()


SERIES_CONFIG = {
    "Motive Truck Series": {
        "webhook": get_secret("WEBHOOK_TRUCKS"),
        "logo_file": "Motive_TruckSeries_Logo.png",
        "banner_file": "Motive_TruckSeries_Logo.png",
        "color": 0xD92525  # Motive Red
    },
    "Reno Wraps Series": {
        "webhook": get_secret("WEBHOOK_RENO"),
        "logo_file": "Reno_WrapsSeries_Logo.png",
        "banner_file": "Reno_WrapsSeries_Logo.png",
        "color": 0x10B981  # Reno Green
    },
    "DHR Cup Series": {
        "webhook": get_secret("WEBHOOK_CUP"),
        "logo_file": "DHR_CupSeries_Logo.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0x2563EB  # DHR Blue
    },
    "Hosted Results": {
        "webhook": get_secret("WEBHOOK_HOSTED"),
        "logo_file": "DHR_League_Banner31.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0xF59E0B  # Hosted Amber
    }
}

HOSTED_BANNER_OPTIONS = {
    "Default League Banner (DHR_League_Banner31.jpg)": "DHR_League_Banner31.jpg",
    "Motive Truck Series (Motive_TruckSeries_Logo.png)": "Motive_TruckSeries_Logo.png",
    "Reno Wraps Series (Reno_WrapsSeries_Logo.png)": "Reno_WrapsSeries_Logo.png",
    "DHR Cup Series (DHR_CupSeries_Logo.png)": "DHR_CupSeries_Logo.png",
}


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
        return [], ""

    meta_blob = " ".join(raw_lines[:6]).lower()

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
        name = norm.get("driver") or norm.get("name") or norm.get("display name") or norm.get("cust name") or "Unknown"

        fast_lap = (
            norm.get("fastest lap time") or
            norm.get("fastest lap") or
            norm.get("best lap time") or
            norm.get("best lap") or
            norm.get("fast lap") or
            ""
        )
        laps = (
            norm.get("laps complete") or
            norm.get("laps completed") or
            norm.get("laps comp") or
            norm.get("comp laps") or
            norm.get("laps") or
            "0"
        )
        interval = norm.get("interval") or norm.get("diff") or norm.get("gap") or "--"
        inc = norm.get("inc") or norm.get("incidents") or "0"
        led = norm.get("laps led") or norm.get("led") or "0"

        if pos and str(pos).isdigit():
            drivers.append({
                "pos": int(pos),
                "start_pos": int(start_pos) if str(start_pos).isdigit() else int(pos),
                "car_num": str(car_num).replace("#", ""),
                "name": str(name),
                "laps": int(laps) if str(laps).isdigit() else 0,
                "interval": str(interval),
                "inc": int(inc.replace("x", "")) if str(inc).replace("x", "").isdigit() else 0,
                "led": int(led) if str(led).isdigit() else 0,
                "fast_lap": str(fast_lap)
            })

    drivers.sort(key=lambda d: d["pos"])
    return drivers, meta_blob


def parse_json_text(text: str):
    data = json.loads(text)
    meta_blob = ""
    race_results = []

    if isinstance(data, dict):
        meta_blob = f"{data.get('session_name', '')} {data.get('league_name', '')}".lower()
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
        name = d.get("display_name") or d.get("name") or d.get("cust_name") or "Unknown"
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
            "name": name,
            "laps": int(laps) if str(laps).isdigit() else 0,
            "interval": interval,
            "inc": int(inc) if str(inc).isdigit() else 0,
            "led": int(led) if str(led).isdigit() else 0,
            "fast_lap": fast_lap_str
        })

    drivers.sort(key=lambda d: d["pos"])
    return drivers, meta_blob


def parse_any_payload(raw_text: str):
    """Auto-detects whether raw text is JSON or CSV and parses it."""
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
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, str(e)


# --- UI HEADER ---
st.title("🏁 DRAFT HOUSE RACING LEAGUE")
st.caption("Cloud Race Results Dispatcher • Season 2")

# Optional Staff PIN Gate (Set STAFF_PIN in Streamlit Secrets)
required_pin = get_secret("STAFF_PIN")
if required_pin:
    entered_pin = st.text_input("🔒 DHRL Staff Passcode", type="password", placeholder="Enter staff PIN to unlock...")
    if entered_pin != required_pin:
        st.info("Enter the DHRL Staff Passcode to access the dispatcher.")
        st.stop()

selected_series = st.radio(
    "Target Series / Discord Channel:",
    options=list(SERIES_CONFIG.keys()),
    horizontal=True
)

# --- INPUT TABS: DRAG-AND-DROP FILE vs PASTE RAW TEXT ---
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
        height=200,
        placeholder='Start Time,Track,Series,Hosted Session Name\n"2026-11-16T00:00:35Z","Texas Motor Speedway - Oval",...',
        key="raw_text_input"
    )
    if pasted_text.strip() and not raw_input_text:
        raw_input_text = pasted_text

if raw_input_text.strip():
    try:
        drivers, meta_blob = parse_any_payload(raw_input_text)
    except Exception as parse_err:
        st.error(f"❌ Error reading CSV/JSON data: {parse_err}")
        st.stop()

    subsession_id = st.text_input("Subsession ID:", value=detected_sub_id)

    # Hosted Results Banner Picker (auto-detected + manual override)
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

    if not drivers:
        st.error("❌ Could not parse any driver results from that input. Check that the header row is included.")
        st.stop()

    # Calculate Awards & Metrics
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

    # Build Monospace Standings Table
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

    with st.expander("📋 Preview Discord Embed Content", expanded=True):
        st.markdown(f"**Title:** 🏁 Official Results — Subsession `{subsession_id}`")
        st.markdown(awards_content)
        st.markdown(standings_block)

    if st.button("🚦 GREEN GREEN GREEN!", type="primary", use_container_width=True):
        config = SERIES_CONFIG[selected_series]
        webhook_url = config.get("webhook", "")

        if not webhook_url:
            st.error(f"❌ Missing webhook secret for {selected_series} in Streamlit Secrets!")
            st.stop()

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

        with st.spinner(f"Dispatching results to {selected_series}..."):
            status_code, err_text = post_discord_multipart(webhook_url, {"embeds": [embed]}, files_list)

        if status_code in (200, 204):
            st.success(f"🏁 KA-CHOW!! Results dispatched to **{selected_series}**!")
        else:
            st.error(f"❌ Discord Error {status_code}: {err_text[:150]}")