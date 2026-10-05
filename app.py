# -*- coding: utf-8 -*-
# ============================================================
#  ربات بیانیه روبیکا — نسخه Webhook (PythonAnywhere)
#  با Flask و دکوراسیون ریست حرفه‌ای
# ============================================================

import json
import time
import os
import re
import requests
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==================== تنظیمات ====================
TOKEN = "CGBACF0SSJCOODBYOPEQEOTPLWXGHUDCMZUANFWHJGXEONZAWLVTEUQCBGRBCQYY"
BASE_URL = f"https://botapi.rubika.ir/v3/{TOKEN}/"
CHANNEL_ID = "c0DWpNh0f6dac3cacd501e096627b5cf"
ADMIN_IDS = ["b0Rqxp0ZUz06e1534a8157da31634872"]

# مسیر فایل‌ها روی PythonAnywhere
BASE_DIR = "/home/alimohammad/rubika-bot-v2/data/"
os.makedirs(BASE_DIR, exist_ok=True)

STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

MUTE_DURATION = 4 * 60
MIN_LINES = 6
REQUEST_TIMEOUT = 15
MAX_PROCESSED = 100000
MAX_STATEMENTS = 2000

# ==================== کشورها ====================
COUNTRIES = {
    "1": "آمریکا", "2": "انگلیس", "3": "شوروی", "4": "ایران",
    "5": "عراق", "6": "چین", "7": "عربستان", "8": "کویت",
    "9": "مصر", "10": "اردن", "11": "سوریه", "12": "لیبی",
    "13": "الجزایر", "14": "ترکیه", "15": "پاکستان", "16": "هند",
    "17": "ژاپن", "18": "آلمان غربی", "19": "ایتالیا", "20": "اسپانیا",
    "21": "لبنان", "22": "فلسطین", "23": "اسرائیل", "24": "کره شمالی",
}

EMOJI = {
    "آمریکا": "🇺🇸", "انگلیس": "🇬🇧", "شوروی": "🇷🇺", "ایران": "🇮🇷",
    "عراق": "🇮🇶", "چین": "🇨🇳", "عربستان": "🇸🇦", "کویت": "🇰🇼",
    "مصر": "🇪🇬", "اردن": "🇯🇴", "سوریه": "🇸🇾", "لیبی": "🇱🇾",
    "الجزایر": "🇩🇿", "ترکیه": "🇹🇷", "پاکستان": "🇵🇰", "هند": "🇮🇳",
    "ژاپن": "🇯🇵", "آلمان غربی": "🇩🇪", "ایتالیا": "🇮🇹", "اسپانیا": "🇪🇸",
    "لبنان": "🇱🇧", "فلسطین": "🇵🇸", "اسرائیل": "🇮🇱", "کره شمالی": "🇰🇵",
}

def tag_of(name):
    return f"📰 خبر فوری {name}"

# ==================== لاگ ====================
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ==================== State ====================
def default_state():
    return {
        "countries": {cid: {"name": name, "owner": None} for cid, name in COUNTRIES.items()},
        "banned": {},
        "muted_until": {},
        "user_country": {},
        "processed_keys": [],
        "statement_map": {},
        "season_active": True,
    }

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            for key, val in default_state().items():
                if key not in state:
                    state[key] = val
            return state
        except Exception as e:
            log(f"⚠️ خطا در خواندن state: {e}")
    return default_state()

def save_state(state):
    try:
        if len(state.get("processed_keys", [])) > MAX_PROCESSED:
            state["processed_keys"] = state["processed_keys"][-MAX_PROCESSED:]
        if len(state.get("statement_map", {})) > MAX_STATEMENTS:
            keys = list(state["statement_map"].keys())
            for k in keys[:-MAX_STATEMENTS]:
                del state["statement_map"][k]

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"❌ خطا در ذخیره state: {e}")

# ==================== API ====================
def api_call(method, payload=None):
    url = BASE_URL + method
    try:
        r = requests.post(url, json=payload or {}, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            log(f"HTTP {r.status_code} در {method}")
            return None
        return r.json()
    except Exception as e:
        log(f"❌ خطا در {method}: {e}")
        return None

def send_message(chat_id, text, reply_to=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    return api_call("sendMessage", payload)

# ==================== کمکی ====================
def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

def find_country_by_name(name):
    name = name.strip()
    for cid, cname in COUNTRIES.items():
        if cname == name:
            return cid
    return None

def find_country_by_owner(state, user_id):
    uid = str(user_id)
    for cid, info in state["countries"].items():
        if str(info.get("owner")) == uid:
            return cid
    return None

def is_muted(state, user_id):
    uid = str(user_id)
    until = state["muted_until"].get(uid)
    if not until:
        return False
    if time.time() < until:
        return True
    del state["muted_until"][uid]
    return False

def is_banned(state, user_id):
    return str(user_id) in state["banned"]

# ==================== پیام خصوصی ====================
def send_help(user_id, state):
    free = [f"{EMOJI[c['name']]} {c['name']}" for c in state["countries"].values() if not c.get("owner")]
    taken = [f"{EMOJI[c['name']]} {c['name']}" for c in state["countries"].values() if c.get("owner")]
    msg = "📋 راهنمای ربات بیانیه\n\n"
    msg += "برای انتخاب کشور، شماره یا نام کشور را بفرست.\n"
    msg += "بعد از انتخاب، بیانیه‌ات را بفرست (بیشتر از ۵ خط).\n\n"
    msg += f"🟢 کشورهای آزاد ({len(free)}):\n" + ("، ".join(free) if free else "هیچ") + "\n\n"
    msg += f"🔴 کشورهای گرفته‌شده ({len(taken)}):\n" + ("، ".join(taken) if taken else "هیچ")
    send_message(user_id, msg)

def handle_private_message(state, user_id, text, sender_name):
    uid = str(user_id)
    text = (text or "").strip()

    if is_banned(state, uid):
        send_message(user_id, "⛔ شما از ارسال بیانیه محروم شده‌اید.")
        return

    if is_muted(state, uid):
        remaining = int(state["muted_until"][uid] - time.time())
        send_message(user_id, f"🔇 شما تا {remaining} ثانیه دیگر نمی‌توانید بیانیه بفرستید.")
        return

    if text in ("/start", "start", "شروع", "راهنما"):
        send_help(user_id, state)
        return

    current_cid = find_country_by_owner(state, uid)

    if not current_cid:
        cid = text if text in COUNTRIES else find_country_by_name(text)
        if cid:
            if not state["season_active"]:
                send_message(user_id, "❌ سیزن تموم شده. منتظر ریست باشید.")
                return
            info = state["countries"][cid]
            if info.get("owner"):
                send_message(user_id, f"❌ کشور {EMOJI[info['name']]} {info['name']} قبلاً انتخاب شده.")
                return
            info["owner"] = uid
            state["user_country"][uid] = cid
            save_state(state)
            send_message(user_id,
                f"✅ کشور {EMOJI[info['name']]} {info['name']} برای شما ثبت شد.\n"
                f"حالا بیانیه‌ات را بفرست (باید بیشتر از ۵ خط باشد).")
            return
        else:
            send_help(user_id, state)
            return

    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < MIN_LINES:
        send_message(user_id,
            f"❌ بیانیه باید بیشتر از ۵ خط باشد.\nتعداد خطوط فعلی: {len(lines)}")
        return

    info = state["countries"][current_cid]
    header = f"{EMOJI[info['name']]} {tag_of(info['name'])}\n"
    header += f"✍️ فرستنده: {sender_name}\n"
    header += "─" * 20 + "\n"

    result = send_message(CHANNEL_ID, header + text)
    stmt_msg_id = None
    if result:
        data = result.get("data") or {}
        stmt_msg_id = data.get("message_id")

    if stmt_msg_id:
        state["statement_map"][str(stmt_msg_id)] = uid
        save_state(state)
        send_message(user_id, "✅ بیانیه‌ات در کانال منتشر شد.")
        log(f"📤 بیانیه از {uid} | msg_id={stmt_msg_id}")
    else:
        send_message(user_id, "✅ بیانیه‌ات در کانال منتشر شد.")

# ==================== دستورات ادمین ====================
def handle_admin_reply(state, text, reply_to_message_id=None):
    text = (text or "").strip()
    if not text:
        return

    # ---- ریست ----
    if text in ("ریست", "/reset", "reset"):
        reset_season(state)
        
        # پیام ریست توی کانال با دکوراسیون
        reset_msg = "╔═══════════════════════╗\n"
        reset_msg += "║   🔄 𝐒𝐄𝐀𝐒𝐎𝐍 𝐑𝐄𝐒𝐄𝐓   ║\n"
        reset_msg += "╚═══════════════════════╝\n\n"
        reset_msg += "🎖️ **سیزن جدید آغاز شد!**\n\n"
        reset_msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
        reset_msg += "✅ تمامی کشورها **آزاد** شدند.\n"
        reset_msg += "✅ تمامی بن‌ها **لغو** شدند.\n"
        reset_msg += "✅ تمامی پیام‌ها **پاک** شدند.\n\n"
        reset_msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
        reset_msg += "🌍 برای شروع، دستور `/start` را بزنید."
        
        send_message(CHANNEL_ID, reset_msg)
        log("🔄 سیزن ریست شد")
        return

    # ---- خالی کرد (نام کشور) ----
    m = re.match(r"^خالی\s*کرد\s+(.+)$", text)
    if m:
        country_name = m.group(1).strip()
        cid = find_country_by_name(country_name)
        if not cid:
            send_message(CHANNEL_ID, f"❌ کشور «{country_name}» پیدا نشد.")
            return
        info = state["countries"][cid]
        old_owner = info.get("owner")
        info["owner"] = None
        if old_owner and str(old_owner) in state["user_country"]:
            del state["user_country"][str(old_owner)]
        save_state(state)
        send_message(CHANNEL_ID, f"✅ کشور {EMOJI[info['name']]} {info['name']} خالی شد.")
        return

    # ---- بن/آزاد/سکوت ----
    target_msg_id = None
    command = text.strip()
    parts = text.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        target_msg_id = parts[-1]
        command = " ".join(parts[:-1]).strip()
    elif reply_to_message_id:
        target_msg_id = str(reply_to_message_id)

    if not target_msg_id:
        all_msgs = list(state.get("statement_map", {}).keys())
        if not all_msgs:
            send_message(CHANNEL_ID, "⚠️ هیچ بیانیه‌ای ثبت نشده.")
            return
        target_msg_id = all_msgs[-1]

    target_user_id = state.get("statement_map", {}).get(str(target_msg_id))
    if not target_user_id:
        send_message(CHANNEL_ID, f"⚠️ کاربر پیام {target_msg_id} پیدا نشد.")
        return

    if command in ("اخطار", "اخطار ❌", "اخطار❌", "اختار"):
        state["banned"][str(target_user_id)] = True
        save_state(state)
        send_message(CHANNEL_ID, "✅ کاربر برای همیشه از ارسال بیانیه محروم شد.")
        return

    if command in ("آزاد", "آزاد ✅", "آزاد✅"):
        state["banned"].pop(str(target_user_id), None)
        state["muted_until"].pop(str(target_user_id), None)
        save_state(state)
        send_message(CHANNEL_ID, "✅ کاربر آزاد شد.")
        return

    if command in ("اخطار 🔄", "اخطار🔄", "سکوت"):
        state["muted_until"][str(target_user_id)] = time.time() + MUTE_DURATION
        save_state(state)
        send_message(CHANNEL_ID, "✅ کاربر ۴ دقیقه از ارسال بیانیه محروم شد.")
        return

def reset_season(state):
    for cid in state["countries"]:
        state["countries"][cid]["owner"] = None
    state["user_country"] = {}
    state["banned"] = {}
    state["muted_until"] = {}
    state["statement_map"] = {}
    state["season_active"] = True
    save_state(state)

# ==================== پردازش آپدیت ====================
def process_one_update(state, upd):
    upd_type = upd.get("type")
    chat_id = str(upd.get("chat_id") or "")
    update_time = upd.get("update_time") or 0

    if upd_type not in ("NewMessage", "StartedBot"):
        return

    nm = upd.get("new_message") or {}
    mid = nm.get("message_id")
    if mid:
        key = f"{chat_id}:{mid}"
    else:
        key = f"{upd_type}:{chat_id}:{update_time}"

    if key in state.get("processed_keys", []):
        return
    state["processed_keys"].append(key)

    text = nm.get("text") or ""
    sender_id = str(nm.get("sender_id") or "")

    if upd_type == "StartedBot":
        log(f"🚀 StartedBot")
        send_help(chat_id, state)
        return

    log(f"🔎 NewMessage | chat={chat_id[:15]} | text='{text[:50]}'")

    if chat_id == CHANNEL_ID:
        reply_to = nm.get("reply_to_message_id")
        handle_admin_reply(state, text, reply_to)
        return

    if not sender_id:
        return
    sender_name = f"کاربر {sender_id[-6:]}"
    handle_private_message(state, chat_id, text, sender_name)

# ==================== Webhook Endpoints ====================
@app.route("/", methods=["GET"])
def home():
    return "🤖 ربات بیانیه فعال است", 200

@app.route("/receiveUpdate", methods=["POST"])
def receive_update():
    """روبیكا پیام‌ها رو اینجا POST می‌کنه"""
    try:
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"status": "no_data"}), 200

        log(f"📥 دریافت: {json.dumps(data, ensure_ascii=False)[:150]}")

        state = load_state()

        # استخراج update
        if "update" in data:
            upd = data["update"]
        elif "inline_message" in data:
            return jsonify({"status": "OK"}), 200
        else:
            upd = data

        if "type" in upd:
            process_one_update(state, upd)

        save_state(state)

    except Exception as e:
        log(f"❌ خطا در Webhook: {e}")

    return jsonify({"status": "OK"}), 200

# ==================== برای تست محلی ====================
if __name__ == "__main__":
    log("🚀 اجرای محلی روی پورت 5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
