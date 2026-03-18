from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, make_response, session
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import os
import uuid
import requests
import time

TZ = ZoneInfo(os.getenv("TZ", "America/Costa_Rica"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "cambia_esto_en_render")

# =========================
# CONFIGURACIÓN MAESTRA
# =========================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "cambia_verify_token")
DOMINIO = os.getenv("DOMINIO", "https://barberia-app-1.onrender.com")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 1. Definición de los 3 Barberos (Punto #2 y #4)
BARBEROS = {
    "1": {"nombre": "Sebastian", "telefono": "50660840460", "clave": "Barberia2026!"},
    "2": {"nombre": "Barbero 2", "telefono": "50600000000", "clave": "Barbero2Pass"},
    "3": {"nombre": "Barbero 3", "telefono": "50600000000", "clave": "Barbero3Pass"}
}

# 2. Servicios con Duración (Punto #1: Sin colchón fijo, duración real)
SERVICIOS_DATA = {
    "Corte de cabello": {"precio": 5000, "duracion": 30},
    "Corte + barba": {"precio": 7000, "duracion": 60},
    "Solo barba": {"precio": 5000, "duracion": 30},
    "Solo cejas": {"precio": 2000, "duracion": 15},
}

# =========================
# HELPERS
# =========================
def enviar_whatsapp(to_numero, mensaje):
    if not WHATSAPP_TOKEN: return False
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_numero, "type": "text", "text": {"body": mensaje}}
    try:
        r = requests.post(url, headers=headers, json=data, timeout=10)
        return r.status_code < 400
    except: return False

def _now_cr():
    return datetime.now(TZ)

def _supabase_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

# =========================
# RUTAS APP
# =========================

@app.route("/", methods=["GET", "POST"])
def index():
    cliente_id = request.args.get("cliente_id") or request.cookies.get("cliente_id") or str(uuid.uuid4())
    hoy_dt = _now_cr()

    if request.method == "POST":
        cliente = request.form.get("cliente", "").strip()
        b_id = request.form.get("barbero_id")
        serv_nom = request.form.get("servicio")
        fecha = request.form.get("fecha")
        hora = request.form.get("hora")
        
        b_info = BARBEROS.get(b_id, BARBEROS["1"])
        precio = SERVICIOS_DATA[serv_nom]["precio"]

        # Guardar en Supabase
        url = f"{SUPABASE_URL}/rest/v1/citas"
        body = {
            "cliente": cliente,
            "cliente_id": cliente_id,
            "barbero": b_info["nombre"],
            "servicio": serv_nom,
            "precio": precio,
            "fecha": fecha,
            "hora": hora
        }
        requests.post(url, headers=_supabase_headers(), json=body)

        # Notificación al barbero elegido (Punto #3)
        msg_barbero = f"💈 Nueva cita agendada\n\nCliente: {cliente}\nServicio: {serv_nom}\nFecha: {fecha}\nHora: {hora}"
        enviar_whatsapp(b_info["telefono"], msg_barbero)

        flash("Cita agendada exitosamente")
        resp = make_response(redirect(url_for("index", cliente_id=cliente_id)))
        resp.set_cookie("cliente_id", cliente_id, max_age=31536000)
        return resp

    return render_template("index.html", 
                           barberos=BARBEROS, 
                           servicios=SERVICIOS_DATA, 
                           cliente_id=cliente_id, 
                           hoy_iso=hoy_dt.strftime("%Y-%m-%d"))

@app.route("/horas")
def horas():
    fecha = request.args.get("fecha")
    b_id = request.args.get("barbero_id")
    serv_nom = request.args.get("servicio")

    if not all([fecha, b_id, serv_nom]): return jsonify([])

    b_nom = BARBEROS.get(b_id, {}).get("nombre", "Sebastian")
    duracion_nueva = SERVICIOS_DATA.get(serv_nom, {"duracion": 30})["duracion"]

    # Consultar ocupados en Supabase
    url = f"{SUPABASE_URL}/rest/v1/citas?barbero=eq.{b_nom}&fecha=eq.{fecha}&servicio=neq.CITA%20CANCELADA"
    res = requests.get(url, headers=_supabase_headers()).json()
    
    ocupados = []
    for c in res:
        h_ini = datetime.strptime(c['hora'], "%I:%M%p")
        # Duración de la cita existente
        d_ocu = SERVICIOS_DATA.get(c['servicio'], {"duracion": 30})["duracion"]
        h_fin = h_ini + timedelta(minutes=d_ocu)
        ocupados.append((h_ini.time(), h_fin.time()))

    disponibles = []
    curr = datetime.strptime("09:00am", "%I:%M%p")
    fin_jornada = datetime.strptime("07:30pm", "%I:%M%p")

    while curr + timedelta(minutes=duracion_nueva) <= fin_jornada:
        ini_p = curr.time()
        fin_p = (curr + timedelta(minutes=duracion_nueva)).time()
        
        es_valido = True
        for o_ini, o_fin in ocupados:
            if not (fin_p <= o_ini or ini_p >= o_fin):
                es_valido = False
                break
        
        if es_valido:
            disponibles.append(curr.strftime("%I:%M%p").lower())
        
        curr += timedelta(minutes=15)

    return jsonify(disponibles)

# Webhook para respuesta automática
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Token incorrecto", 403
    return "ok", 200

if __name__ == "__main__":
    app.run(debug=True)





