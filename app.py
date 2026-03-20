from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, make_response
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import uuid
import requests
import threading
import time

TZ = ZoneInfo("America/Costa_Rica")
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "secret_key_123")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "barberia123")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# WhatsApp Cloud API
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

# Barberos estáticos con info básica
BARBEROS = {
    "1": {"nombre": "Sebastian", "telefono": "50672314147"},
    "2": {"nombre": "Barbero 2", "telefono": "50600000000"},
    "3": {"nombre": "Barbero 3", "telefono": "50600000000"}
}

# Inicializar barberos en Supabase
def inicializar_barberos():
    """Crear registros de barberos en Supabase si no existen"""
    try:
        for b_id, info in BARBEROS.items():
            # Verificar si el barbero ya existe
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/barberos?id=eq.{b_id}",
                headers=_headers()
            )
            if res.status_code == 200 and res.json():
                continue  # Ya existe
            
            # Crear nuevo barbero
            data = {
                "id": int(b_id),
                "nombre": info["nombre"],
                "activo": True,
                "disponible_hoy": True,
                "created_at": datetime.now(TZ).isoformat()
            }
            requests.post(
                f"{SUPABASE_URL}/rest/v1/barberos",
                headers=_headers(),
                json=data
            )
        print("Barberos inicializados correctamente")
    except Exception as e:
        print(f"Error inicializando barberos: {e}")

SERVICIOS = {
    "Corte de cabello": {"precio": 5000, "duracion": 30},
    "Corte + barba": {"precio": 7000, "duracion": 60},
    "Cejas": {"precio": 2000, "duracion": 15},
}

MESES_2026 = {
    "01": "Enero",
    "02": "Febrero",
    "03": "Marzo",
    "04": "Abril",
    "05": "Mayo",
    "06": "Junio",
    "07": "Julio",
    "08": "Agosto",
    "09": "Septiembre",
    "10": "Octubre",
    "11": "Noviembre",
    "12": "Diciembre",
}

# ============ FUNCIONES AUXILIARES ============

def obtener_barbero_info(barbero_id):
    """Obtener información del barbero desde Supabase"""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/barberos?id=eq.{barbero_id}",
            headers=_headers()
        )
        if res.status_code == 200:
            data = res.json()
            if data:
                return data[0]
    except:
        pass
    return None


def barbero_disponible_hoy(barbero_id):
    """Verificar si el barbero está disponible hoy"""
    barbero = obtener_barbero_info(barbero_id)
    if not barbero:
        return False
    
    activo = barbero.get("activo", False)
    disponible_hoy = barbero.get("disponible_hoy", False)
    
    return activo and disponible_hoy


def obtener_todos_barberos():
    """Obtener info de todos los barberos desde Supabase"""
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/barberos?order=id.asc",
            headers=_headers()
        )
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


def normalizar_numero_cr(numero):
    numero = str(numero).strip().replace(" ", "").replace("-", "").replace("+", "")
    if numero.startswith("506"):
        return numero
    return f"506{numero}"


def enviar_whatsapp_texto(numero, mensaje):
    try:
        if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
            print("WhatsApp no configurado en variables de entorno.")
            return None

        numero = normalizar_numero_cr(numero)

        url = f"https://graph.facebook.com/v23.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"body": mensaje}
        }
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }

        r = requests.post(url, headers=headers, json=payload, timeout=20)
        print("WHATSAPP STATUS:", r.status_code)
        print("WHATSAPP RESPUESTA:", r.text)
        return r
    except Exception as e:
        print("Error enviando WhatsApp:", e)
        return None


def obtener_citas_barbero_fecha(barbero_id, fecha):
    url = f"{SUPABASE_URL}/rest/v1/citas?barbero_id=eq.{barbero_id}&fecha=eq.{fecha}&order=hora.asc"
    res = requests.get(url, headers=_headers())
    try:
        data = res.json()
        return data if isinstance(data, list) else []
    except:
        return []


def obtener_todas_citas_barbero(barbero_id):
    url = f"{SUPABASE_URL}/rest/v1/citas?barbero_id=eq.{barbero_id}&order=fecha.asc,hora.asc"
    res = requests.get(url, headers=_headers())
    try:
        data = res.json()
        return data if isinstance(data, list) else []
    except:
        return []


def obtener_cita_por_id(cita_id):
    url = f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita_id}"
    res = requests.get(url, headers=_headers())
    try:
        data = res.json()
        if isinstance(data, list) and data:
            return data[0]
    except:
        pass
    return None


def calcular_precio(servicio):
    return SERVICIOS.get(servicio, {}).get("precio", 0)


def calcular_duracion(servicio):
    return SERVICIOS.get(servicio, {}).get("duracion", 30)


def hora_choque(hora_nueva, duracion_nueva, hora_existente, duracion_existente):
    inicio_nueva = datetime.strptime(hora_nueva.upper(), "%I:%M%p")
    fin_nueva = inicio_nueva + timedelta(minutes=duracion_nueva)

    inicio_existente = datetime.strptime(hora_existente, "%H:%M:%S")
    fin_existente = inicio_existente + timedelta(minutes=duracion_existente)

    return inicio_nueva < fin_existente and fin_nueva > inicio_existente


def formatear_hora(hora_db):
    try:
        return datetime.strptime(str(hora_db), "%H:%M:%S").strftime("%I:%M %p")
    except:
        return str(hora_db)


@app.route("/")
def index():
    hoy = datetime.now(TZ).strftime("%Y-%m-%d")
    c_id = request.cookies.get("cliente_id") or str(uuid.uuid4())

    # Obtener barberos desde Supabase
    barberos_info = obtener_todos_barberos()
    
    # Filtrar solo barberos activos y disponibles hoy
    barberos_disponibles = {}
    for barbero in barberos_info:
        bid = str(barbero.get("id"))
        if barbero.get("activo") and barbero.get("disponible_hoy"):
            # Obtener nombre del diccionario BARBEROS
            nombre = BARBEROS.get(bid, {}).get("nombre", barbero.get("nombre", "Barbero"))
            barberos_disponibles[bid] = {"nombre": nombre, "telefono": BARBEROS.get(bid, {}).get("telefono", "")}
    
    # Si no hay barberos disponibles, mostrar mensaje
    if not barberos_disponibles:
        barberos_disponibles = BARBEROS  # Fallback al diccionario original si hay problema

    resp = make_response(
        render_template(
            "index.html",
            barberos=barberos_disponibles,
            servicios=SERVICIOS,
            hoy_iso=hoy,
            cliente_id=c_id
        )
    )
    resp.set_cookie("cliente_id", c_id, max_age=31536000)
    return resp


@app.route("/", methods=["POST"])
def agendar():
    try:
        cliente = request.form.get("cliente", "").strip()
        cliente_telefono = request.form.get("cliente_telefono", "").strip()
        barbero_id = request.form.get("barbero_id", "").strip()
        servicio = request.form.get("servicio", "").strip()
        fecha = request.form.get("fecha", "").strip()
        hora = request.form.get("hora", "").strip()

        if not cliente or not cliente_telefono or not barbero_id or not servicio or not fecha or not hora:
            flash("Faltan datos para agendar la cita.")
            return redirect(url_for("index"))

        if barbero_id not in BARBEROS:
            flash("El barbero seleccionado no es válido.")
            return redirect(url_for("index"))

        if servicio not in SERVICIOS:
            flash("El servicio seleccionado no es válido.")
            return redirect(url_for("index"))

        hoy_cr = datetime.now(TZ).strftime("%Y-%m-%d")
        if fecha < hoy_cr:
            flash("No puedes agendar en una fecha pasada.")
            return redirect(url_for("index"))

        citas_existentes = obtener_citas_barbero_fecha(barbero_id, fecha)
        duracion_nueva = calcular_duracion(servicio)

        for cita in citas_existentes:
            estado = str(cita.get("estado", "")).lower()
            if estado == "cancelada":
                continue

            hora_existente = str(cita.get("hora"))
            servicio_existente = cita.get("servicio", "")
            duracion_existente = calcular_duracion(servicio_existente)

            if hora_choque(hora, duracion_nueva, hora_existente, duracion_existente):
                flash("Ese barbero ya tiene una cita en ese horario.")
                return redirect(url_for("index"))

        hora_db = datetime.strptime(hora.upper(), "%I:%M%p").strftime("%H:%M:%S")

        data = {
            "cliente_nombre": cliente,
            "cliente_telefono": normalizar_numero_cr(cliente_telefono),
            "servicio": servicio,
            "fecha": fecha,
            "hora": hora_db,
            "barbero_id": int(barbero_id),
            "estado": "pendiente",
            "origen": "online",
            "recordatorio_30_enviado": False
        }

        r = requests.post(f"{SUPABASE_URL}/rest/v1/citas", headers=_headers(), json=data)

        if r.status_code not in [200, 201]:
            print("STATUS SUPABASE:", r.status_code)
            print("RESPUESTA SUPABASE:", r.text)
            flash("No se pudo guardar la cita.")
            return redirect(url_for("index"))

        nombre_barbero = BARBEROS[barbero_id]["nombre"]
        telefono_barbero = BARBEROS[barbero_id]["telefono"]

        mensaje_barbero = (
            f"💈 Nueva cita agendada\n"
            f"Cliente: {cliente}\n"
            f"Teléfono: {normalizar_numero_cr(cliente_telefono)}\n"
            f"Servicio: {servicio}\n"
            f"Fecha: {fecha}\n"
            f"Hora: {hora}"
        )

        mensaje_cliente = (
            f"✅ Tu cita fue confirmada\n"
            f"Barbero: {nombre_barbero}\n"
            f"Servicio: {servicio}\n"
            f"Fecha: {fecha}\n"
            f"Hora: {hora}\n"
            f"Te esperamos en la barbería."
        )

        enviar_whatsapp_texto(telefono_barbero, mensaje_barbero)
        enviar_whatsapp_texto(cliente_telefono, mensaje_cliente)

        flash("¡Cita agendada correctamente!")
    except Exception as e:
        print(f"Error agendando: {e}")
        flash("Ocurrió un error al agendar.")

    return redirect(url_for("index"))


@app.route("/horas")
def horas():
    fecha = request.args.get("fecha")
    barbero_id = request.args.get("barbero_id")
    servicio = request.args.get("servicio")

    if not all([fecha, barbero_id, servicio]):
        return jsonify([])

    if barbero_id not in BARBEROS:
        return jsonify([])

    if servicio not in SERVICIOS:
        return jsonify([])

    # Verificar si el barbero está disponible hoy
    if fecha == datetime.now(TZ).strftime("%Y-%m-%d"):
        if not barbero_disponible_hoy(barbero_id):
            return jsonify([])

    duracion_nueva = calcular_duracion(servicio)
    citas = obtener_citas_barbero_fecha(barbero_id, fecha)

    ocupados = []
    for cita in citas:
        estado = str(cita.get("estado", "")).lower()
        if estado == "cancelada":
            continue

        hora_existente = str(cita.get("hora"))
        servicio_existente = cita.get("servicio", "")
        duracion_existente = calcular_duracion(servicio_existente)

        inicio = datetime.strptime(hora_existente, "%H:%M:%S")
        fin = inicio + timedelta(minutes=duracion_existente)
        ocupados.append((inicio, fin))

    disponibles = []
    apertura = datetime.strptime("08:00AM", "%I:%M%p")
    cierre = datetime.strptime("07:00PM", "%I:%M%p")

    fecha_hoy_cr = datetime.now(TZ).strftime("%Y-%m-%d")
    ahora_cr = datetime.now(TZ)

    actual = apertura

    while actual + timedelta(minutes=duracion_nueva) <= cierre:
        fin_actual = actual + timedelta(minutes=duracion_nueva)
        libre = True

        for inicio_ocupado, fin_ocupado in ocupados:
            if actual < fin_ocupado and fin_actual > inicio_ocupado:
                libre = False
                break

        if libre:
            if fecha == fecha_hoy_cr:
                hora_slot_hoy = ahora_cr.replace(
                    hour=actual.hour,
                    minute=actual.minute,
                    second=0,
                    microsecond=0
                )
                if hora_slot_hoy > ahora_cr:
                    disponibles.append(actual.strftime("%I:%M%p").lower())
            else:
                disponibles.append(actual.strftime("%I:%M%p").lower())

        actual += timedelta(minutes=15)

    return jsonify(disponibles)


@app.route("/cancelar_cliente", methods=["POST"])
def cancelar_cliente():
    try:
        cliente = request.form.get("cliente", "").strip()
        barbero_id = request.form.get("barbero_id", "").strip()
        fecha = request.form.get("fecha", "").strip()
        hora = request.form.get("hora", "").strip()

        if not cliente or not barbero_id or not fecha or not hora:
            flash("Completa todos los datos para cancelar.")
            return redirect(url_for("index"))

        hora_db = datetime.strptime(hora.upper(), "%I:%M%p").strftime("%H:%M:%S")

        buscar_url = (
            f"{SUPABASE_URL}/rest/v1/citas"
            f"?cliente_nombre=eq.{cliente}"
            f"&barbero_id=eq.{barbero_id}"
            f"&fecha=eq.{fecha}"
            f"&hora=eq.{hora_db}"
        )

        res = requests.get(buscar_url, headers=_headers())
        data = res.json() if res.ok else []

        if not data:
            flash("No se encontró una cita con esos datos.")
            return redirect(url_for("index"))

        cita = data[0]
        cita_id = cita["id"]

        patch = requests.patch(
            f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita_id}",
            headers=_headers(),
            json={"estado": "cancelada"}
        )

        if patch.status_code not in [200, 204]:
            flash("No se pudo cancelar la cita.")
            return redirect(url_for("index"))

        nombre_barbero = BARBEROS[barbero_id]["nombre"]
        telefono_barbero = BARBEROS[barbero_id]["telefono"]
        cliente_telefono = cita.get("cliente_telefono", "")

        mensaje_barbero = (
            f"❌ Cita cancelada\n"
            f"Cliente: {cliente}\n"
            f"Fecha: {fecha}\n"
            f"Hora: {hora}\n"
            f"Barbero: {nombre_barbero}"
        )

        mensaje_cliente = (
            f"❌ Tu cita fue cancelada correctamente\n"
            f"Barbero: {nombre_barbero}\n"
            f"Fecha: {fecha}\n"
            f"Hora: {hora}"
        )

        enviar_whatsapp_texto(telefono_barbero, mensaje_barbero)
        if cliente_telefono:
            enviar_whatsapp_texto(cliente_telefono, mensaje_cliente)

        flash("Cita cancelada correctamente.")
    except Exception as e:
        print("Error cancelando cliente:", e)
        flash("Ocurrió un error al cancelar la cita.")

    return redirect(url_for("index"))


@app.route("/panel/<id_barbero>")
def panel_barbero(id_barbero):
    if id_barbero not in BARBEROS:
        flash("Barbero no encontrado.")
        return redirect(url_for("index"))

    citas = obtener_todas_citas_barbero(id_barbero)

    for cita in citas:
        cita["hora_formateada"] = formatear_hora(cita.get("hora"))
        cita["precio"] = calcular_precio(cita.get("servicio", ""))

    hoy = datetime.now(TZ).strftime("%Y-%m-%d")
    manana = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    modo = request.args.get("solo", "hoy")
    mes = request.args.get("mes", datetime.now(TZ).strftime("%m"))

    if modo == "hoy":
        filtradas = [c for c in citas if str(c.get("fecha")) == hoy and str(c.get("estado", "")).lower() != "cancelada"]
    elif modo == "manana":
        filtradas = [c for c in citas if str(c.get("fecha")) == manana and str(c.get("estado", "")).lower() != "cancelada"]
    elif modo == "historial_2026":
        filtradas = [
            c for c in citas
            if str(c.get("fecha", "")).startswith(f"2026-{mes}-")
        ]
    else:
        filtradas = [c for c in citas if str(c.get("estado", "")).lower() != "cancelada"]

    hoy_citas = [c for c in citas if str(c.get("fecha")) == hoy and str(c.get("estado", "")).lower() != "cancelada"]
    hoy_atendidas = [c for c in hoy_citas if str(c.get("estado", "")).lower() == "atendida"]
    hoy_canceladas = [c for c in citas if str(c.get("fecha")) == hoy and str(c.get("estado", "")).lower() == "cancelada"]

    ganancia = sum(calcular_precio(c.get("servicio", "")) for c in hoy_atendidas)

    stats = {
        "id": id_barbero,
        "nombre": BARBEROS[id_barbero]["nombre"],
        "total": len(hoy_citas),
        "ganancia": ganancia,
        "canceladas_hoy": len(hoy_canceladas),
        "modo": modo,
        "mes": mes
    }

    return render_template(
        "barbero.html",
        citas=filtradas,
        stats=stats,
        meses_2026=MESES_2026
    )


@app.route("/atendida", methods=["POST"])
def atendida():
    cita_id = request.form.get("id")
    barbero_id = request.form.get("barbero_id")

    if not cita_id:
        flash("No se encontró la cita.")
        return redirect(url_for("index"))

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita_id}",
        headers=_headers(),
        json={"estado": "atendida"}
    )

    flash("Cita marcada como atendida.")
    return redirect(url_for("panel_barbero", id_barbero=barbero_id))


@app.route("/cancelar_barbero", methods=["POST"])
def cancelar_barbero():
    cita_id = request.form.get("id")
    barbero_id = request.form.get("barbero_id")

    if not cita_id:
        flash("No se encontró la cita.")
        return redirect(url_for("index"))

    cita = obtener_cita_por_id(cita_id)

    requests.patch(
        f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita_id}",
        headers=_headers(),
        json={"estado": "cancelada"}
    )

    if cita:
        cliente_telefono = cita.get("cliente_telefono", "")
        cliente_nombre = cita.get("cliente_nombre", "")
        fecha = cita.get("fecha", "")
        hora = formatear_hora(cita.get("hora", ""))
        nombre_barbero = BARBEROS.get(barbero_id, {}).get("nombre", "Barbero")

        mensaje_cliente = (
            f"❌ Tu cita fue cancelada por la barbería\n"
            f"Barbero: {nombre_barbero}\n"
            f"Fecha: {fecha}\n"
            f"Hora: {hora}\n"
            f"Cliente: {cliente_nombre}"
        )

        if cliente_telefono:
            enviar_whatsapp_texto(cliente_telefono, mensaje_cliente)

    flash("Cita cancelada correctamente.")
    return redirect(url_for("panel_barbero", id_barbero=barbero_id))


@app.route("/dueno")
def panel_dueno():
    """Panel administrativo único para ver y gestionar los 3 barberos"""
    hoy = datetime.now(TZ).strftime("%Y-%m-%d")
    
    # Obtener todas las citas del día
    url = f"{SUPABASE_URL}/rest/v1/citas?fecha=eq.{hoy}&order=hora.asc"
    res = requests.get(url, headers=_headers())
    
    try:
        citas_hoy = res.json() if res.status_code == 200 else []
        citas_hoy = citas_hoy if isinstance(citas_hoy, list) else []
    except:
        citas_hoy = []
    
    # Obtener información de barberos
    barberos_info = obtener_todos_barberos()
    barberos_dict = {str(b.get("id")): b for b in barberos_info}
    
    # Enriquecer citas con información del barbero
    for cita in citas_hoy:
        if str(cita.get("estado", "")).lower() == "cancelada":
            continue
        
        barbero_id = str(cita.get("barbero_id", ""))
        cita["barbero_nombre"] = barberos_dict.get(barbero_id, {}).get("nombre", "Sin asignar")
        cita["barbero_activo"] = barberos_dict.get(barbero_id, {}).get("activo", False)
        cita["precio"] = calcular_precio(cita.get("servicio", ""))
        cita["hora_formateada"] = formatear_hora(cita.get("hora"))
        cita["origen"] = cita.get("origen", "online")
        cita["tipo_visual"] = "online" if cita.get("origen") == "online" else "manual"
    
    # Filtrar solo citas activas para la vista
    citas_activas = [c for c in citas_hoy if str(c.get("estado", "")).lower() != "cancelada"]
    
    # Agrupar por barbero
    citas_por_barbero = {}
    for cita in citas_activas:
        bid = str(cita.get("barbero_id", ""))
        if bid not in citas_por_barbero:
            citas_por_barbero[bid] = []
        citas_por_barbero[bid].append(cita)
    
    # Calcular estadísticas por barbero
    stats = {}
    for barbero in barberos_info:
        bid = str(barbero.get("id"))
        citas = citas_por_barbero.get(bid, [])
        atendidas = [c for c in citas if str(c.get("estado", "")).lower() == "atendida"]
        ganancia = sum(calcular_precio(c.get("servicio", "")) for c in atendidas)
        
        stats[bid] = {
            "nombre": barbero.get("nombre"),
            "total": len(citas),
            "ganancia": ganancia,
            "activo": barbero.get("activo", False),
            "disponible_hoy": barbero.get("disponible_hoy", False),
            "citas": citas
        }
    
    return render_template(
        "panel_admin.html",
        stats=stats,
        barberos_info=barberos_info,
        citas_activas=citas_activas,
        servicios=SERVICIOS,
        hoy=hoy
    )


# ============ RUTAS DEL PANEL ADMINISTRATIVO ============

@app.route("/api/barbero/<barbero_id>/toggle_disponibilidad", methods=["POST"])
def toggle_disponibilidad(barbero_id):
    """Activar/desactivar disponibilidad del barbero para hoy"""
    try:
        barbero = obtener_barbero_info(barbero_id)
        if not barbero:
            return jsonify({"error": "Barbero no encontrado"}), 404
        
        nuevo_estado = not barbero.get("disponible_hoy", False)
        
        res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/barberos?id=eq.{barbero_id}",
            headers=_headers(),
            json={"disponible_hoy": nuevo_estado}
        )
        
        if res.status_code in [200, 204]:
            return jsonify({
                "success": True,
                "disponible_hoy": nuevo_estado,
                "mensaje": "Disponibilidad actualizada"
            })
        else:
            return jsonify({"error": "No se pudo actualizar"}), 500
    except Exception as e:
        print(f"Error toggle_disponibilidad: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/barbero/<barbero_id>/toggle_activo", methods=["POST"])
def toggle_activo(barbero_id):
    """Activar/desactivar barbero (actividad general)"""
    try:
        barbero = obtener_barbero_info(barbero_id)
        if not barbero:
            return jsonify({"error": "Barbero no encontrado"}), 404
        
        nuevo_estado = not barbero.get("activo", False)
        
        res = requests.patch(
            f"{SUPABASE_URL}/rest/v1/barberos?id=eq.{barbero_id}",
            headers=_headers(),
            json={"activo": nuevo_estado}
        )
        
        if res.status_code in [200, 204]:
            return jsonify({
                "success": True,
                "activo": nuevo_estado,
                "mensaje": "Estado actualizado"
            })
        else:
            return jsonify({"error": "No se pudo actualizar"}), 500
    except Exception as e:
        print(f"Error toggle_activo: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cita_manual", methods=["POST"])
def crear_cita_manual():
    """Crear una cita manual o bloqueo de horario desde el panel"""
    try:
        barbero_id = request.json.get("barbero_id", "").strip()
        fecha = request.json.get("fecha", "").strip()
        hora = request.json.get("hora", "").strip()
        servicio = request.json.get("servicio", "").strip()
        cliente_nombre = request.json.get("cliente_nombre", "Cliente presencial").strip()
        observacion = request.json.get("observacion", "").strip()

        if not all([barbero_id, fecha, hora]):
            return jsonify({"error": "Faltan datos requeridos"}), 400

        if barbero_id not in BARBEROS:
            return jsonify({"error": "Barbero no válido"}), 400

        # Validar que no sea fecha pasada
        hoy_cr = datetime.now(TZ).strftime("%Y-%m-%d")
        if fecha < hoy_cr:
            return jsonify({"error": "No se puede agendar en fecha pasada"}), 400

        # Verificar conflictos de horario
        citas_existentes = obtener_citas_barbero_fecha(barbero_id, fecha)
        duracion_nueva = calcular_duracion(servicio) if servicio else 30

        for cita in citas_existentes:
            if str(cita.get("estado", "")).lower() == "cancelada":
                continue

            if hora_choque(hora, duracion_nueva, str(cita.get("hora")), calcular_duracion(cita.get("servicio", ""))):
                return jsonify({"error": "Hay conflicto con otra cita en ese horario"}), 409

        # Convertir hora
        hora_db = datetime.strptime(hora.upper(), "%I:%M%p").strftime("%H:%M:%S")

        # Crear cita manual
        data = {
            "cliente_nombre": cliente_nombre,
            "cliente_telefono": "",
            "servicio": servicio or "Bloqueo manual",
            "fecha": fecha,
            "hora": hora_db,
            "barbero_id": int(barbero_id),
            "estado": "pendiente",
            "origen": "manual",
            "observacion": observacion,
            "recordatorio_30_enviado": True  # No enviar recordatorio para citas manuales
        }

        res = requests.post(f"{SUPABASE_URL}/rest/v1/citas", headers=_headers(), json=data)

        if res.status_code in [200, 201]:
            return jsonify({
                "success": True,
                "mensaje": "Cita manual creada correctamente"
            })
        else:
            print(f"Error Supabase: {res.status_code} - {res.text}")
            return jsonify({"error": "No se pudo crear la cita"}), 500

    except Exception as e:
        print(f"Error crear_cita_manual: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/recordatorios", methods=["POST"])
def procesar_recordatorios():
    """Procesar y enviar recordatorios automáticos 30 minutos antes"""
    try:
        ahora = datetime.now(TZ)
        ventana_inicio = ahora + timedelta(minutes=25)
        ventana_fin = ahora + timedelta(minutes=35)

        # Obtener todas las citas pendientes para hoy
        hoy = ahora.strftime("%Y-%m-%d")
        url = f"{SUPABASE_URL}/rest/v1/citas?fecha=eq.{hoy}&estado=eq.pendiente&recordatorio_30_enviado=eq.false"
        res = requests.get(url, headers=_headers())

        if res.status_code != 200:
            return jsonify({"error": "No se pudo obtener citas"}), 500

        citas = res.json() if isinstance(res.json(), list) else []
        recordatorios_enviados = 0

        for cita in citas:
            # Solo enviar recordatorio a citas online
            if cita.get("origen") != "online":
                continue

            hora_str = cita.get("hora", "")
            try:
                hora_cita = datetime.strptime(hora_str, "%H:%M:%S").time()
                hora_cita_dt = datetime.combine(datetime.strptime(hoy, "%Y-%m-%d").date(), hora_cita)
                hora_cita_dt = TZ.localize(hora_cita_dt)
            except:
                continue

            # Verificar si está dentro de la ventana de 30 minutos
            if ventana_inicio <= hora_cita_dt <= ventana_fin:
                cliente_telefono = cita.get("cliente_telefono", "")
                cliente_nombre = cita.get("cliente_nombre", "")
                hora_formateada = formatear_hora(hora_cita)

                if cliente_telefono:
                    mensaje = (
                        f"Hola, te recordamos que tienes una cita agendada en la barbería "
                        f"hoy a las {hora_formateada}. Te esperamos."
                    )

                    enviar_whatsapp_texto(cliente_telefono, mensaje)
                    recordatorios_enviados += 1

                    # Marcar como enviado
                    try:
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita.get('id')}",
                            headers=_headers(),
                            json={
                                "recordatorio_30_enviado": True,
                                "fecha_recordatorio_30": datetime.now(TZ).isoformat()
                            }
                        )
                    except:
                        pass

        return jsonify({
            "success": True,
            "recordatorios_enviados": recordatorios_enviados
        })

    except Exception as e:
        print(f"Error procesar_recordatorios: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200

    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def recibir_webhook():
    data = request.get_json(silent=True)
    print("WEBHOOK RECIBIDO:", data)
    return "EVENT_RECEIVED", 200


# ============ TAREA AUTOMÁTICA DE RECORDATORIOS ============

def tarea_recordatorios_automaticos():
    """Ejecutar recordatorios automáticos cada cierto tiempo"""
    while True:
        try:
            ahora = datetime.now(TZ)
            
            # Solo procesar entre 8am y 7pm
            if 8 <= ahora.hour < 19:
                with app.app_context():
                    # Llamar a la función de recordatorios
                    ahora = datetime.now(TZ)
                    ventana_inicio = ahora + timedelta(minutes=25)
                    ventana_fin = ahora + timedelta(minutes=35)

                    hoy = ahora.strftime("%Y-%m-%d")
                    url = f"{SUPABASE_URL}/rest/v1/citas?fecha=eq.{hoy}&estado=eq.pendiente&recordatorio_30_enviado=eq.false"
                    res = requests.get(url, headers=_headers())

                    if res.status_code == 200:
                        citas = res.json() if isinstance(res.json(), list) else []

                        for cita in citas:
                            if cita.get("origen") != "online":
                                continue

                            hora_str = cita.get("hora", "")
                            try:
                                hora_cita = datetime.strptime(hora_str, "%H:%M:%S").time()
                                hora_cita_dt = datetime.combine(datetime.strptime(hoy, "%Y-%m-%d").date(), hora_cita)
                                hora_cita_dt = TZ.localize(hora_cita_dt)
                            except:
                                continue

                            if ventana_inicio <= hora_cita_dt <= ventana_fin:
                                cliente_telefono = cita.get("cliente_telefono", "")
                                if cliente_telefono:
                                    hora_formateada = formatear_hora(hora_cita)
                                    mensaje = (
                                        f"Hola, te recordamos que tienes una cita agendada en la barbería "
                                        f"hoy a las {hora_formateada}. Te esperamos."
                                    )
                                    enviar_whatsapp_texto(cliente_telefono, mensaje)

                                    try:
                                        requests.patch(
                                            f"{SUPABASE_URL}/rest/v1/citas?id=eq.{cita.get('id')}",
                                            headers=_headers(),
                                            json={
                                                "recordatorio_30_enviado": True,
                                                "fecha_recordatorio_30": datetime.now(TZ).isoformat()
                                            }
                                        )
                                    except:
                                        pass
        except Exception as e:
            print(f"Error en tarea_recordatorios_automaticos: {e}")

        # Esperar 2 minutos antes de la siguiente ejecución
        time.sleep(120)


if __name__ == "__main__":
    # Inicializar barberos al iniciar
    inicializar_barberos()
    
    # Iniciar tarea de recordatorios en un hilo separado
    hilo_recordatorios = threading.Thread(target=tarea_recordatorios_automaticos, daemon=True)
    hilo_recordatorios.start()
    
    app.run(debug=True)


