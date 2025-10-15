
import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader

SHEET_ID = os.environ.get("SHEET_ID")
SHEET_NAME = os.environ.get("SHEET_NAME", "Foglio1")
SECURITY_TOKEN = os.environ.get("SECURITY_TOKEN", "")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "service_account.json")

CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

app = Flask(__name__)
CORS(app)

def _load_gs_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if GOOGLE_CREDENTIALS_JSON:
        info = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
    elif os.path.exists(GOOGLE_CREDENTIALS_FILE):
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    else:
        raise RuntimeError("Missing Google credentials")
    return gspread.authorize(creds)

def _cloudinary_setup():
    if CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=CLOUDINARY_URL, secure=True)
    elif CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )
    else:
        raise RuntimeError("Missing Cloudinary credentials")

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/list")
def list_rows():
    gc = _load_gs_client()
    sh = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    values = sh.get_all_values()
    if not values or len(values) < 2:
        return jsonify({"rows": []})
    header = [h.strip().lower() for h in values[0]]
    rows = []
    for r_i, row in enumerate(values[1:], start=2):
        try:
            idx = {h:i for i,h in enumerate(header)}
            rid = row[idx.get("id", -1)] if idx.get("id", -1) >= 0 else ""
            if not rid:
                continue
            item = {
                "id": rid,
                "agente": row[idx.get("agente", -1)] if idx.get("agente", -1) >= 0 else "",
                "negozio": row[idx.get("negozio", -1)] if idx.get("negozio", -1) >= 0 else "",
                "data": row[idx.get("data", -1)] if idx.get("data", -1) >= 0 else "",
                "createdAtIso": row[idx.get("createdatiso", -1)] if idx.get("createdatiso", -1) >= 0 else "",
                "photoUrls": json.loads(row[idx.get("photourls (json)", -1)] or "[]") if idx.get("photourls (json)", -1) >= 0 else [],
                "sheetRowUrl": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#range=A{r_i}",
            }
            rows.append(item)
        except Exception:
            continue
    return jsonify({"rows": rows})

@app.post("/add")
def add_row():
    if SECURITY_TOKEN and request.form.get("token") != SECURITY_TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    agente = request.form.get("agente", "").strip()
    negozio = request.form.get("negozio", "").strip()
    data_pass = request.form.get("data", "").strip()
    created = datetime.utcnow().isoformat()

    _cloudinary_setup()
    photo_urls = []
    for key in request.files:
        file = request.files[key]
        if not file or not getattr(file, "filename", ""):
            continue
        up = cloudinary.uploader.upload(file, folder="crm-agenti", resource_type="image")
        photo_urls.append(up.get("secure_url"))

    gc = _load_gs_client()
    sh = gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    rid = f"R-{datetime.utcnow().strftime('%y%m%d%H%M%S')}"
    sh.append_row([rid, agente, negozio, data_pass, created, json.dumps(photo_urls), ""], value_input_option="USER_ENTERED")

    return jsonify({"ok": True, "item": {"id": rid, "agente": agente, "negozio": negozio, "data": data_pass, "createdAtIso": created, "photoUrls": photo_urls}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
