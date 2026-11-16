import os
import csv
import json
import uuid
import threading
import urllib.request
import tkinter as tk
from tkinter import filedialog, ttk

BASE_DIR = r"D:\DHR_R-Result_Bot"


def load_env_file(env_path):
    """Simple built-in .env loader (no python-dotenv required)."""
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars


ENV = load_env_file(os.path.join(BASE_DIR, ".env"))

SERIES_CONFIG = {
    "Motive Truck Series": {
        "webhook": ENV.get("WEBHOOK_TRUCKS", ""),
        "logo_file": "Motive_TruckSeries_Logo.png",
        "banner_file": "Motive_TruckSeries_Logo.png",
        "color": 0xD92525  # Motive Red
    },
    "Reno Wraps Series": {
        "webhook": ENV.get("WEBHOOK_RENO", ""),
        "logo_file": "Reno_WrapsSeries_Logo.png",
        "banner_file": "Reno_WrapsSeries_Logo.png",
        "color": 0x10B981  # Reno Green
    },
    "DHR Cup Series": {
        "webhook": ENV.get("WEBHOOK_CUP", ""),
        "logo_file": "DHR_CupSeries_Logo.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0x2563EB  # DHR Blue
    },
    "Hosted Results": {
        "webhook": ENV.get("WEBHOOK_HOSTED", ""),
        "logo_file": "DHR_League.jpg",
        "banner_file": "DHR_League_Banner31.jpg",
        "color": 0xF59E0B  # Hosted Amber/Gold
    }
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


def parse_csv_results(file_path):
    with open(file_path, mode="r", encoding="utf-8-sig", errors="ignore") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    if not raw_lines:
        return []

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
    return drivers


def parse_json_results(file_path):
    with open(file_path, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    race_results = []
    if isinstance(data, dict):
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
    return drivers


def post_discord_multipart(webhook_url, payload_dict, files_list):
    """Sends multipart/form-data with embed JSON + local image attachments using standard urllib."""
    boundary = f"----DHRLBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # Add payload_json part
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="payload_json"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(payload_dict).encode("utf-8"))
    body.extend(b"\r\n")

    # Add file parts
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
            "User-Agent": "DHRL-RaceControl-Dispatcher"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 0, str(e)


class RacePulseDispatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DHR League - Race Result Dispatcher")
        self.root.geometry("540x510")
        self.root.resizable(False, False)
        self.root.configure(bg="#18181b")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TRadiobutton", background="#27272a", foreground="#f4f4f5", font=("Segoe UI", 10, "bold"))

        # Header
        header_frame = tk.Frame(root, bg="#18181b")
        header_frame.pack(pady=(18, 8), padx=20, fill="x")

        tk.Label(
            header_frame,
            text="DRAFT HOUSE RACING LEAGUE",
            font=("Segoe UI", 16, "bold"),
            bg="#18181b",
            fg="#f4f4f5",
        ).pack()

        tk.Label(
            header_frame,
            text="Official Results Dispatcher",
            font=("Segoe UI", 10),
            bg="#18181b",
            fg="#a1a1aa",
        ).pack()

        # Body Card
        body_frame = tk.Frame(root, bg="#27272a", bd=1, relief="ridge")
        body_frame.pack(pady=8, padx=24, fill="both", expand=True)

        # Series Selector (2x2 Grid for 4 Options)
        tk.Label(
            body_frame, text="Target Series / Channel:", font=("Segoe UI", 10, "bold"), bg="#27272a", fg="#e4e4e7"
        ).pack(anchor="w", padx=22, pady=(14, 6))

        self.series_var = tk.StringVar(value="Motive Truck Series")
        series_grid = tk.Frame(body_frame, bg="#27272a")
        series_grid.pack(fill="x", padx=22, pady=(0, 14))

        for idx, s_name in enumerate(SERIES_CONFIG.keys()):
            row_num = idx // 2
            col_num = idx % 2
            ttk.Radiobutton(
                series_grid, text=s_name, variable=self.series_var, value=s_name
            ).grid(row=row_num, column=col_num, sticky="w", padx=(0, 28), pady=3)

        # File Chooser
        tk.Label(
            body_frame, text="Select Result Export File (CSV or JSON):", font=("Segoe UI", 10, "bold"), bg="#27272a", fg="#e4e4e7"
        ).pack(anchor="w", padx=22, pady=(0, 4))

        file_row = tk.Frame(body_frame, bg="#27272a")
        file_row.pack(fill="x", padx=22, pady=(0, 12))

        self.file_path_entry = tk.Entry(
            file_row, font=("Segoe UI", 10), bg="#3f3f46", fg="#ffffff", insertbackground="white", relief="flat"
        )
        self.file_path_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        tk.Button(
            file_row,
            text="Browse...",
            command=self.browse_file,
            bg="#52525b",
            fg="#ffffff",
            activebackground="#71717a",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2"
        ).pack(side="right")

        # Subsession ID
        tk.Label(
            body_frame, text="Subsession ID (Auto-detected or Manual):", font=("Segoe UI", 9), bg="#27272a", fg="#d4d4d8"
        ).pack(anchor="w", padx=22, pady=(0, 4))

        self.sub_id_entry = tk.Entry(
            body_frame, font=("Segoe UI", 10), bg="#3f3f46", fg="#ffffff", insertbackground="white", relief="flat"
        )
        self.sub_id_entry.pack(fill="x", padx=22, ipady=5, pady=(0, 18))

        # Launch Button
        self.dispatch_btn = tk.Button(
            body_frame,
            text="🚦 GREEN GREEN GREEN!",
            command=self.start_dispatch_thread,
            font=("Segoe UI", 12, "bold"),
            bg="#15803d",
            fg="#ffffff",
            activebackground="#166534",
            activeforeground="#ffffff",
            relief="flat",
            pady=10,
            cursor="hand2"
        )
        self.dispatch_btn.pack(fill="x", padx=22, pady=(0, 10))

        # Status Label
        self.status_label = tk.Label(
            body_frame,
            text="Select an export file and target channel to dispatch.",
            font=("Segoe UI", 9),
            bg="#27272a",
            fg="#a1a1aa",
            wraplength=440
        )
        self.status_label.pack(pady=(0, 10))

    def update_status(self, text, color="#a1a1aa"):
        self.status_label.configure(text=text, fg=color)

    def browse_file(self):
        filename = filedialog.askopenfilename(
            initialdir=BASE_DIR,
            title="Select iRacing Race Result File",
            filetypes=(("CSV / JSON files", "*.csv;*.json"), ("All files", "*.*"))
        )
        if filename:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, filename)

            base = os.path.basename(filename)
            for p in base.split("_"):
                if p.isdigit() and len(p) >= 7:
                    self.sub_id_entry.delete(0, tk.END)
                    self.sub_id_entry.insert(0, p)
                    break

    def start_dispatch_thread(self):
        file_path = self.file_path_entry.get().strip().strip('"')
        selected_series = self.series_var.get()
        sub_id = self.sub_id_entry.get().strip() or "Official Event"
        config = SERIES_CONFIG.get(selected_series)

        if not file_path or not os.path.exists(file_path):
            self.update_status("❌ Please select a valid exported CSV or JSON file.", "#ef4444")
            return

        if not config or not config.get("webhook"):
            self.update_status(f"❌ Webhook not found in .env for {selected_series}.", "#ef4444")
            return

        self.dispatch_btn.configure(state="disabled")
        self.update_status("Parsing results and dispatching...", "#3b82f6")

        threading.Thread(
            target=self.process_file,
            args=(file_path, sub_id, selected_series, config),
            daemon=True,
        ).start()

    def process_file(self, file_path, subsession_id, series_name, config):
        try:
            if file_path.lower().endswith(".csv"):
                drivers = parse_csv_results(file_path)
            elif file_path.lower().endswith(".json"):
                drivers = parse_json_results(file_path)
            else:
                self.root.after(0, self.update_status, "❌ File must be a .csv or .json.", "#ef4444")
                return

            if not drivers:
                self.root.after(0, self.update_status, "❌ Could not parse driver results from file.", "#ef4444")
                return

            total_starters = len(drivers)

            # Calculate Awards & Metrics
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

            # Cleanest Driver (Must complete >= 50% distance and > 0 laps)
            leader_laps = max((d["laps"] for d in drivers), default=0)
            finishers = [d for d in drivers if d["laps"] > 0 and d["laps"] >= (leader_laps * 0.50)]
            if finishers:
                min_inc = min(d["inc"] for d in finishers)
                clean_finishers = [d["name"][:14] for d in finishers if d["inc"] == min_inc]
                clean_str = f"{clean_finishers[0]} ({min_inc}x)"
            else:
                clean_str = "None"

            # Standings Table (Strictly <= 42 chars wide AND <= 1000 chars total)
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

            # Resolve Logo & Banner Targets safely
            logo_target = config.get("logo_file", "DHR_League.jpg")
            banner_target = config.get("banner_file", "DHR_League_Banner31.jpg")

            logo_path = os.path.join(BASE_DIR, logo_target)
            if not os.path.exists(logo_path):
                logo_target = "DHR_League.jpg"
                logo_path = os.path.join(BASE_DIR, logo_target)

            banner_path = os.path.join(BASE_DIR, banner_target)
            if not os.path.exists(banner_path):
                banner_target = "DHR_League_Banner31.jpg"
                banner_path = os.path.join(BASE_DIR, banner_target)

            author_obj = {"name": f"Draft House Racing League • {series_name}"}
            if os.path.exists(logo_path):
                author_obj["icon_url"] = f"attachment://{logo_target}"

            embed = {
                "author": author_obj,
                "title": f"🏁 Official Results — Subsession `{subsession_id}`",
                "color": config.get("color", 0xD92525),
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

            status_code, err_text = post_discord_multipart(
                config.get("webhook"), {"embeds": [embed]}, files_list
            )

            if status_code in [200, 204]:
                self.root.after(0, self.update_status, f"🏁 KA-CHOW!! Results dispatched to {series_name}!", "#22c55e")
            else:
                err_snippet = err_text[:90].replace("\n", " ")
                self.root.after(0, self.update_status, f"❌ Discord Error {status_code}: {err_snippet}", "#ef4444")

        except Exception as e:
            self.root.after(0, self.update_status, f"❌ Error: {str(e)[:45]}", "#ef4444")
        finally:
            self.root.after(0, self.dispatch_btn.configure, {"state": "normal"})


if __name__ == "__main__":
    root = tk.Tk()
    app = RacePulseDispatcherApp(root)
    root.mainloop()