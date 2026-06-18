import streamlit as st
import pandas as pd
import datetime
import requests
import re
import urllib.parse

from db import get_supabase


# =========================
# Constantes
# =========================
TAGS_SUGERIDOS = [
    "JUVENTUD",
    "LIBERTAD PLATEADA",
    "MIGRANTE",
    "PROFESIONAL",
    "FISCAL OCTUBRE",
    "FISCAL MAYO",
    "AFILIADO",
    "PARTE DEL EQUIPO",
    "FISCAL GENERAL",
    "CULTO",
    "PYME",
    "COMERCIANTE",
    "BASES",
    "UNIVERSIDAD",
    "VECINO EMBLEMATICO",
    "PORTERO/ENCARGADO",
    "EMPRENDEDOR", 
    "EDUCACIÓN", 
    "SALUD", 
    "CULTURA",
]

RESPUESTAS = ["POSITIVO", "NEUTRO", "NEGATIVO", "NO RESPONDIÓ", "NUMERO INEXISTENTE/EQUIVOCADO"]
MEDIOS = ["WhatsApp", "Llamada", "Instagram", "Facebook", "Email", "Presencial", "Otro"]

SEGUIMIENTO_ESTADOS = ["pendiente", "hecho", "cancelado"]

from constants import BARRIOS_POR_COMUNA


# =========================
# Helpers WhatsApp / Email
# =========================
def _limpiar_tel_para_wa(tel: str):
    if not tel:
        return None
    s = str(tel).strip()
    digits = re.sub(r"\D+", "", s)
    if not digits:
        return None
    if digits.startswith("54"):
        return digits
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    return "54" + digits


def _build_whatsapp_link(tel: str, message: str):
    phone = _limpiar_tel_para_wa(tel)
    if not phone:
        return None
    text = urllib.parse.quote(message or "")
    return f"https://wa.me/{phone}?text={text}"


def _build_gmail_link(email: str, subject: str, body: str):
    if not email or not str(email).strip():
        return None
    to = str(email).strip()
    # https://mail.google.com/mail/?view=cm&fs=1&to=<EMAIL>&su=<SUBJECT>&body=<BODY>
    qs = {
        "view": "cm", 
        "fs": "1", 
        "to": to,
        "su": subject or "",
        "body": body or ""
    }
    return f"https://mail.google.com/mail/?{urllib.parse.urlencode(qs)}"


def _safe_link_button(label: str, url: str, key: str):
    if not url:
        st.button(label, disabled=True, key=key)
        return

    if getattr(st, "link_button", None):
        st.link_button(label, url, use_container_width=True)
    else:
        st.markdown(f"[{label}]({url})")


# =========================
# Helpers tags
# =========================
def normalize_tag(t):
    if not t: return None
    return str(t).strip().upper()

def _parse_tags(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [normalize_tag(x) for x in v if normalize_tag(x)]
    s = str(v).strip()
    if not s:
        return []
    return [normalize_tag(x) for x in s.split(",") if normalize_tag(x)]


def _tags_to_db_value(tags_sel):
    if tags_sel is None:
        return None
    if isinstance(tags_sel, str):
        val = normalize_tag(tags_sel)
        return [val] if val else []
    if isinstance(tags_sel, list):
        cleaned = [normalize_tag(t) for t in tags_sel if normalize_tag(t)]
        return cleaned if cleaned else None
    return None


# =========================
# Helpers semáforos
# =========================
def _norm_status(s):
    if s is None:
        return "NO CONTACTADO"
    up = str(s).strip().upper()
    # Ambos son estados válidos con significado distinto:
    # NO CONTACTADO = nunca se intentó contactar (estado inicial)
    # NO RESPONDIÓ  = se intentó contactar pero no respondió (respuesta de interacción)
    if up in ("NO CONTACTADO", "NO RESPONDIÓ"):
        return up
    return up if up in RESPUESTAS else "NO CONTACTADO"


def _semaforo_respuesta_badge(status):
    s = _norm_status(status)
    if s == "POSITIVO":
        return "🟢 POSITIVO"
    if s == "NEUTRO":
        return "🟡 NEUTRO"
    if s == "NEGATIVO":
        return "🔴 NEGATIVO"
    if s == "NUMERO INEXISTENTE/EQUIVOCADO":
        return "🟠 NÚMERO INEXISTENTE/EQUIVOCADO"
    if s == "NO RESPONDIÓ":
        return "⚫ NO RESPONDIÓ"
    return "⚫ NO CONTACTADO"


def _semaforo_tiempo_badge(ultima_fecha):
    if not ultima_fecha:
        return "⚫ SIN CONTACTO"
    try:
        uf = pd.to_datetime(ultima_fecha).date()
    except Exception:
        return "⚫ SIN CONTACTO"
    dias = (datetime.date.today() - uf).days
    if dias < 30:
        return "🟢 <30 días"
    if 30 <= dias <= 60:
        return "🟡 30–60 días"
    return "🔴 >60 días"


# =========================
# Geocoder USIG (lat/lon)
# =========================
def geocodificar_usig(direccion_normalizada: str):
    """
    Devuelve (lat, lon) usando USIG.
    Usa preferentemente el endpoint de normalizar con flag de geocodificación,
    ya que es el más estable y evita redirecciones HTML.
    """
    if not direccion_normalizada or not str(direccion_normalizada).strip():
        return None, None

    # Lista de intentos con diferentes APIs y protocolos
    intentos = [
        {
            "url": "https://servicios.usig.buenosaires.gob.ar/normalizar",
            "params": {"direccion": direccion_normalizada, "geocodificar": "true"},
            "headers": {"User-Agent": "Mozilla/5.0"}
        },
        {
            "url": "http://servicios.usig.buenosaires.gob.ar/geocoder/2.2/geocoding",
            "params": {"q": direccion_normalizada},
            "headers": {"User-Agent": "Mozilla/5.0"}
        }
    ]

    for it in intentos:
        try:
            resp = requests.get(it["url"], params=it["params"], headers=it["headers"], timeout=5)
            # Si responde HTML, es una redirección al mapa, no nos sirve
            if "text/html" in resp.headers.get("Content-Type", "").lower() or "<!doctype html" in resp.text.lower()[:200]:
                continue
                
            data = resp.json()

            # Caso 1: Estructura de 'normalizar'
            direcciones = []
            if isinstance(data, list):
                direcciones = data
            elif isinstance(data, dict):
                direcciones = data.get("direccionesNormalizadas") or data.get("direcciones_normalizadas") or data.get("direcciones") or []

            for d in direcciones:
                if isinstance(d, dict):
                    coords = d.get("coordenadas")
                    fx, fy = None, None
                    if isinstance(coords, dict):
                        fx, fy = coords.get("x"), coords.get("y")
                    else:
                        fx, fy = d.get("x"), d.get("y")

                    if fx and fy:
                        try:
                            # Validamos que sean coordenadas lat/lon estándar (WGS84)
                            f_lon, f_lat = float(fx), float(fy)
                            if -60 < f_lat < -10 and -70 < f_lon < -30: 
                                return f_lat, f_lon
                        except: pass
            
            # Caso 2: Estructura GeoJSON (Geocoder 2.2)
            if isinstance(data, dict) and "features" in data:
                for f in data["features"]:
                    geom = f.get("geometry", {})
                    if geom and geom.get("type") == "Point":
                        coords = geom.get("coordinates")
                        if coords and len(coords) >= 2:
                            return float(coords[1]), float(coords[0])

        except Exception:
            continue
            
    return None, None


def geocodificar_con_reintentos(direccion_normalizada: str):
    """
    Intenta geocodificar la dirección normalizada y, si falla,
    prueba variantes de formato para maximizar chances de éxito con USIG.
    """
    # 1. Intento directo
    lat, lon = geocodificar_usig(direccion_normalizada)
    if lat is not None and lon is not None:
        return lat, lon

    base = (direccion_normalizada or "").strip()
    if not base:
        return None, None

    # 2. Intentos con variantes
    import re
    candidatos = []
    # Variante sin ", CABA"
    candidatos.append(re.sub(r",\s*CABA.*", "", base, flags=re.I).strip())
    # Variante con CABA explícito
    if "CABA" not in base.upper():
        candidatos.append(f"{base}, CABA")
    
    for cand in candidatos:
        if not cand or cand == base:
            continue
        lat2, lon2 = geocodificar_usig(cand)
        if lat2 is not None and lon2 is not None:
            return lat2, lon2

    return None, None


# =========================
# Normalizador USIG (para Editar)
# =========================
def _llamar_usig(direccion: str):
    base_url = "https://servicios.usig.buenosaires.gob.ar/normalizar"
    dir_txt = (direccion or "").strip()
    if not dir_txt:
        return []

    up = dir_txt.upper()
    if (
        "CABA" not in up
        and "CAPITAL FEDERAL" not in up
        and "CIUDAD AUTONOMA" not in up
        and "CIUDAD AUTÓNOMA" not in up
    ):
        dir_txt = f"{dir_txt}, CABA"

    resp = requests.get(base_url, params={"direccion": dir_txt}, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "direcciones" in data:
            return data["direcciones"]
        if "direccionesNormalizadas" in data:
            return data["direccionesNormalizadas"]
    return []


def _texto_desde_obj_direccion(d):
    if not isinstance(d, dict):
        return None
    if d.get("direccion_normalizada"):
        return str(d["direccion_normalizada"])
    if d.get("direccion"):
        return str(d["direccion"])

    calle = d.get("nombre_calle") or d.get("calle") or d.get("calle_nombre") or d.get("nombre")
    altura = d.get("altura") or d.get("altura_calle") or d.get("numero")
    if calle and altura:
        return f"{calle} {altura}"
    return None


def sugerir_direcciones_caba(domicilio_input: str, max_sugerencias: int = 10):
    texto = (domicilio_input or "").strip()
    if len(texto) < 3:
        return []
    try:
        direcciones = _llamar_usig(texto)
        sugerencias = []
        for d in direcciones:
            dir_norm = _texto_desde_obj_direccion(d)
            if dir_norm and dir_norm not in sugerencias:
                sugerencias.append(dir_norm)
            if len(sugerencias) >= max_sugerencias:
                break
        return sugerencias
    except Exception:
        return []


def normalizar_domicilio_caba(domicilio_input: str):
    texto = (domicilio_input or "").strip()
    if texto == "":
        return None, None
    try:
        direcciones = _llamar_usig(texto)
        if not direcciones:
            return None, "No se encontró una dirección válida en CABA para ese domicilio."
        d0 = direcciones[0]
        dir_norm = _texto_desde_obj_direccion(d0)
        if not dir_norm:
            return None, "No se pudo interpretar la dirección devuelta por el servicio."
        return dir_norm, None
    except Exception as e:
        return None, f"Error al normalizar el domicilio: {e}"


# =========================
# DB funciones
# =========================
def get_persona(persona_id: int):
    supabase = get_supabase()
    res = (
        supabase.table("personas")
        .select(
            "id, nombre_apellido, dni, telefono, domicilio, email, comuna_id, barrio, "
            "sexo, edad, fiscalizo, tags, latitud, longitud"
        )
        .eq("id", int(persona_id))
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_historial_persona(persona_id: int):
    supabase = get_supabase()
    cols = (
        "fecha, usuario_id, respuesta, observaciones, creado_en, tipo, medio, motivo, "
        "para_que_contacte, seguimiento_id, seguimiento_cerrado, created_by, proxima_fecha"
    )
    res = (
        supabase.table("interacciones_personas")
        .select(cols)
        .eq("persona_id", int(persona_id))
        .order("fecha", desc=True)
        .execute()
    )
    return pd.DataFrame(res.data or [])


def get_ultima_interaccion_real(persona_id: int):
    """
    Última interacción REAL: ignora filas con respuesta vacía/None (ej: 'seguimiento asignado').
    """
    df = get_historial_persona(persona_id)
    if df.empty:
        return None, "NO CONTACTADO"

    # filtrar solo las que tengan respuesta válida
    def _is_valid_resp(x):
        if x is None:
            return False
        s = str(x).strip().upper()
        return s in set(RESPUESTAS)

    df2 = df[df["respuesta"].apply(_is_valid_resp)] if "respuesta" in df.columns else df.iloc[0:0]
    if df2.empty:
        # No hubo contactos reales todavía, pero puede haber logs de seguimiento asignado
        return None, "NO CONTACTADO"

    r0 = df2.iloc[0]
    return r0.get("fecha"), _norm_status(r0.get("respuesta"))


def update_persona(persona_id: int, payload: dict):
    supabase = get_supabase()
    supabase.table("personas").update(payload).eq("id", int(persona_id)).execute()


def _clear_interacciones_cache():
    """Invalida solo las cachés afectadas por una nueva interacción."""
    import logging
    _log = logging.getLogger(__name__)

    try:
        from personas_app import get_interacciones_resumen
        get_interacciones_resumen.clear()
    except Exception as e:
        _log.warning(f"_clear_interacciones_cache: no se pudo limpiar get_interacciones_resumen: {e}")
    try:
        from kpis_app import fetch_kpis_data
        fetch_kpis_data.clear()
    except Exception as e:
        _log.warning(f"_clear_interacciones_cache: no se pudo limpiar fetch_kpis_data: {e}")
    try:
        from dashboard_master_global import fetch_global_data
        fetch_global_data.clear()
    except Exception as e:
        _log.warning(f"_clear_interacciones_cache: no se pudo limpiar fetch_global_data: {e}")

    # Reset del filtro de fecha: evita que una persona recién contactada quede fuera
    # del rango del slider (que guarda el max anterior en session_state)
    try:
        import streamlit as st
        if "flt_rango_fecha" in st.session_state:
            del st.session_state["flt_rango_fecha"]
    except Exception:
        pass


def insert_interaccion(payload: dict):
    supabase = get_supabase()
    supabase.table("interacciones_personas").insert(payload).execute()
    _clear_interacciones_cache()


def insert_interacciones_bulk(payloads: list):
    """Inserta múltiples interacciones en una sola llamada a la base de datos."""
    if not payloads:
        return
    supabase = get_supabase()
    supabase.table("interacciones_personas").insert(payloads).execute()
    _clear_interacciones_cache()


def get_users_same_comuna(user):
    supabase = get_supabase()
    res = (
        supabase.table("usuarios")
        .select("id, username, comuna_id, activo")
        .eq("activo", True)
        .eq("comuna_id", int(user["comuna_id"]))
        .order("username")
        .execute()
    )
    return res.data or []


def insert_seguimiento(payload: dict):
    supabase = get_supabase()
    supabase.table("seguimientos_personas").insert(payload).execute()


def get_casos_asignados(user):
    supabase = get_supabase()
    res = (
        supabase.table("seguimientos_personas")
        .select("id, persona_id, assigned_to, created_by, fecha, estado, observaciones, creado_en")
        .eq("assigned_to", int(user["id"]))
        .neq("estado", "hecho")
        .neq("estado", "cancelado")
        .order("fecha", desc=False)
        .execute()
    )
    return res.data or []


def cerrar_seguimiento(seguimiento_id: int):
    supabase = get_supabase()
    supabase.table("seguimientos_personas").update({"estado": "hecho"}).eq("id", int(seguimiento_id)).execute()


@st.cache_data(ttl=300)
def get_usuarios_mapping():
    """Retorna un dict {id: username} de todos los usuarios para mostrar en el historial."""
    supabase = get_supabase()
    res = supabase.table("usuarios").select("id, username").execute()
    return {r["id"]: r["username"] for r in (res.data or [])}


# =========================
# UI: Casos asignados (SIN EXPANDER ADENTRO)
# =========================
def render_casos_asignados(user):
    st.markdown("## 📌 Casos asignados al usuario")

    casos = get_casos_asignados(user)
    if not casos:
        st.info("No tenés casos asignados.")
        return

    # Render plano: sin expander acá (para evitar nested expanders)
    for c in casos:
        persona = get_persona(c["persona_id"])
        if not persona:
            titulo = f"Persona ID {c.get('persona_id')} — objetivo {c.get('fecha','')}"
        else:
            titulo = f"{persona.get('nombre_apellido','')} — DNI {persona.get('dni','')} — objetivo {c.get('fecha','')}"

        with st.container(border=True):
            st.markdown(f"### {titulo}")
            st.write(f"**Observación:** {c.get('observaciones','')}")
            st.write(f"**Estado:** {c.get('estado','')}")
            st.write("---")

            st.markdown("### Cargar interacción por seguimiento")

            fecha = st.date_input("Fecha", value=datetime.date.today(), key=f"seg_fecha_{c['id']}")
            respuesta = st.selectbox("Respuesta de la persona", RESPUESTAS, index=0, key=f"seg_resp_{c['id']}")
            medio = st.selectbox("Medio", MEDIOS, index=0, key=f"seg_medio_{c['id']}")

            para_que = st.text_input("Motivo / Para qué lo contacté", value="", key=f"seg_para_{c['id']}")
            obs = st.text_area("Observaciones", value="", key=f"seg_obs_{c['id']}")

            if st.button("✅ Guardar interacción y cerrar seguimiento", key=f"seg_guardar_{c['id']}"):
                try:
                    insert_interaccion({
                        "persona_id": int(c["persona_id"]),
                        "fecha": str(fecha),
                        "respuesta": respuesta,  # ✅ acá sí se guarda
                        "medio": medio,
                        "para_que_contacte": para_que,
                        "observaciones": obs,
                        "tipo": "seguimiento realizado",
                        "created_by": int(user["id"]),
                        "seguimiento_id": int(c["id"]),
                        "seguimiento_cerrado": True,
                    })
                    cerrar_seguimiento(int(c["id"]))
                    st.success("Interacción cargada y seguimiento cerrado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


# =========================
# UI: Ficha persona
# =========================
def render_ficha_persona(user, persona_id: int):
    persona = get_persona(persona_id)
    if not persona:
        st.warning("No se encontró la persona.")
        return

    ultima_fecha, ultimo_status = get_ultima_interaccion_real(persona_id)

    # Flags independientes por persona
    contact_key = f"show_contact_{persona_id}"
    edit_key = f"show_edit_{persona_id}"
    int_key = f"show_int_{persona_id}"
    seg_key = f"show_seg_{persona_id}"

    if contact_key not in st.session_state:
        st.session_state[contact_key] = False
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False
    if int_key not in st.session_state:
        st.session_state[int_key] = False
    if seg_key not in st.session_state:
        st.session_state[seg_key] = False

    # Encabezado: título + botón Contactar
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown("## 📌 Ficha de persona")
    with h2:
        if st.button("🗣️ Contactar", use_container_width=True, key=f"btn_contact_top_{persona_id}"):
            st.session_state[contact_key] = not st.session_state[contact_key]

    # Datos de ficha
    c1, c2 = st.columns([2, 1])

    with c1:
        st.write(f"**Nombre y apellido:** {persona.get('nombre_apellido','')}")
        st.write(f"**DNI:** {persona.get('dni','')}")
        st.write(f"**Teléfono:** {persona.get('telefono','')}")
        st.write(f"**Email:** {persona.get('email','')}")
        st.write(f"**Comuna:** {persona.get('comuna_id','')}")
        st.write(f"**Barrio:** {persona.get('barrio','')}")

    with c2:
        st.write("**Último contacto real:**")
        st.write(str(ultima_fecha) if ultima_fecha else "-")
        st.write("**Semáforo respuesta:**")
        st.write(_semaforo_respuesta_badge(ultimo_status))
        st.write("**Semáforo tiempo:**")
        st.write(_semaforo_tiempo_badge(ultima_fecha))

    st.markdown("---")

    # Contactar (solo links)
    if st.session_state[contact_key]:
        tel = (persona.get("telefono") or "").strip()
        mail = (persona.get("email") or "").strip()

        msg_key = f"msg_contacto_{persona_id}"
        subj_key = f"subj_contacto_{persona_id}"

        if msg_key not in st.session_state:
            st.session_state[msg_key] = f"Hola {persona.get('nombre_apellido','')}, ¿cómo estás? Te escribo por..."
        if subj_key not in st.session_state:
            st.session_state[subj_key] = "Contacto"

        st.markdown("### 💬 Contactar")

        m1, m2 = st.columns([2, 1])
        with m1:
            mensaje = st.text_area("Mensaje", value=st.session_state[msg_key], height=120, key=msg_key)
            asunto = st.text_input("Asunto (Email)", value=st.session_state[subj_key], key=subj_key)

        with m2:
            wa_url = _build_whatsapp_link(tel, mensaje) if tel else None
            gmail_url = _build_gmail_link(mail, asunto, mensaje) if mail else None

            if not tel:
                st.caption("⚠️ Sin teléfono para WhatsApp")
            _safe_link_button("🟩 Abrir WhatsApp", wa_url, key=f"lnk_wa_{persona_id}")

            if not mail:
                st.warning("⚠️ Esta persona no tiene email cargado")
            elif gmail_url:
                _safe_link_button("📧 Enviar mail (Gmail)", gmail_url, key=f"lnk_mail_{persona_id}")

            if st.button("❌ Cerrar", use_container_width=True, key=f"btn_close_contact_{persona_id}"):
                st.session_state[contact_key] = False
                st.rerun()

        st.markdown("---")

    # Fila horizontal de botones
    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("✏️ Editar datos", use_container_width=True, key=f"btn_edit_{persona_id}"):
            st.session_state[edit_key] = not st.session_state[edit_key]

    with b2:
        if st.button("📌 Cargar interacción", use_container_width=True, key=f"btn_int_{persona_id}"):
            st.session_state[int_key] = not st.session_state[int_key]

    with b3:
        if st.button("🧭 Asignar seguimiento", use_container_width=True, key=f"btn_seg_{persona_id}"):
            st.session_state[seg_key] = not st.session_state[seg_key]

    st.markdown("---")

    # 1) EDITAR DATOS
    if st.session_state[edit_key]:
        st.markdown("### ✏️ Editar datos de la persona")

        comuna_actual = int(float(persona.get("comuna_id") or 0)) if str(persona.get("comuna_id") or "").strip() else 0
        comunas = list(range(1, 16))
        comuna_index = comunas.index(comuna_actual) if comuna_actual in comunas else 0
        comuna_nueva = st.selectbox("Comuna", comunas, index=comuna_index, key=f"edit_comuna_{persona_id}")

        barrios_opciones = BARRIOS_POR_COMUNA.get(int(comuna_nueva), [])
        barrio_actual = (persona.get("barrio") or "").strip()
        if barrios_opciones:
            barrio_index = barrios_opciones.index(barrio_actual) if barrio_actual in barrios_opciones else 0
            barrio = st.selectbox("Barrio", barrios_opciones, index=barrio_index, key=f"edit_barrio_{persona_id}")
        else:
            barrio = st.text_input("Barrio", value=barrio_actual, key=f"edit_barrio_text_{persona_id}")

        cc1, cc2 = st.columns(2)
        with cc1:
            telefono_edit = st.text_input("Teléfono", value=persona.get("telefono") or "", key=f"edit_tel_{persona_id}")
            email_edit = st.text_input("Email", value=persona.get("email") or "", key=f"edit_email_{persona_id}")

            domicilio_input = st.text_input(
                "Domicilio (CABA, normalizado)",
                value=persona.get("domicilio") or "",
                key=f"edit_dom_{persona_id}",
            )

            dom_sel = None
            if len(domicilio_input.strip()) >= 3:
                sug = sugerir_direcciones_caba(domicilio_input)
                if sug:
                    dom_sel = st.selectbox(
                        "Sugerencias de domicilio",
                        ["(Usar texto)"] + sug,
                        index=0,
                        key=f"edit_dom_sug_{persona_id}",
                    )

        with cc2:
            sexo_actual = (persona.get("sexo") or "").strip().upper()
            sexo_opts = ["", "MASCULINO", "FEMENINO"]
            sexo_index = sexo_opts.index(sexo_actual) if sexo_actual in sexo_opts else 0
            sexo = st.selectbox("Sexo", sexo_opts, index=sexo_index, key=f"edit_sexo_{persona_id}")

            edad = st.number_input(
                "Edad", min_value=0, max_value=120,
                value=int(float(persona.get("edad") or 0)),
                key=f"edit_edad_{persona_id}"
            )

            fiscal_opts = ["", "SI", "NO"]
            fiscal_actual = (persona.get("fiscalizo") or "").strip().upper()
            fiscal_index = fiscal_opts.index(fiscal_actual) if fiscal_actual in fiscal_opts else 0
            fiscalizo = st.selectbox("Fiscalizó", fiscal_opts, index=fiscal_index, key=f"edit_fiscal_{persona_id}")

        tags_actual = _parse_tags(persona.get("tags"))
        tags_sel = st.multiselect(
            "Tags",
            options=sorted(list(set(TAGS_SUGERIDOS + tags_actual))),
            default=tags_actual,
            key=f"edit_tags_{persona_id}",
        )

        if st.button("💾 Guardar cambios", key=f"btn_save_persona_{persona_id}"):
            try:
                # Normalización y geocodificación automática
                domicilio_final = (persona.get("domicilio") or "").strip()
                lat_final = persona.get("latitud")
                lon_final = persona.get("longitud")

                input_dom = domicilio_input.strip()
                
                # Si el input es distinto al original
                if input_dom != (persona.get("domicilio") or "").strip():
                    if dom_sel and dom_sel != "(Usar texto)":
                        domicilio_final = dom_sel
                        err_norm = None
                    else:
                        domicilio_final, err_norm = normalizar_domicilio_caba(input_dom)

                    if err_norm:
                        st.error(err_norm)
                        st.stop()
                    
                    # Geocodificar la nueva dirección
                    lat_new, lon_new = geocodificar_con_reintentos(domicilio_final)
                    if lat_new:
                        lat_final, lon_final = lat_new, lon_new

                payload = {
                    "telefono": telefono_edit.strip() if telefono_edit else None,
                    "email": email_edit.strip() if email_edit else None,
                    "domicilio": domicilio_final,
                    "sexo": sexo.strip() if sexo else None,
                    "edad": int(edad),
                    "fiscalizo": (fiscalizo or "").strip().upper() if fiscalizo else None,
                    "comuna_id": int(comuna_nueva),
                    "barrio": barrio.strip() if barrio else None,
                    "tags": _tags_to_db_value(tags_sel),
                    "latitud": lat_final,
                    "longitud": lon_final,
                }
                update_persona(persona_id, payload)

                if user.get("tipo_usuario") == "REFERENTE" and int(comuna_nueva) != int(user.get("comuna_id")):
                    st.success("Datos actualizados. Se movió de tu comuna, ya no lo vas a ver en tu tabla.")
                    st.session_state["selected_persona_id"] = None
                    st.session_state["ficha_abierta"] = False
                    st.rerun()

                st.success("Datos actualizados correctamente (con geolocalización).")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar: {e}")

        st.markdown("---")

    # 2) CARGAR INTERACCIÓN (real)
    if st.session_state[int_key]:
        st.markdown("### 📌 Cargar interacción")

        c3, c4, c5 = st.columns(3)
        with c3:
            fecha = st.date_input("Fecha", value=datetime.date.today(), key=f"int_fecha_{persona_id}")
        with c4:
            respuesta = st.selectbox("Respuesta de la persona", RESPUESTAS, index=0, key=f"int_resp_{persona_id}")
        with c5:
            medio = st.selectbox("Medio", MEDIOS, index=0, key=f"int_medio_{persona_id}")

        para_que = st.text_input("Motivo / Para qué lo contacté", value="", key=f"int_para_{persona_id}")
        observ = st.text_area("Observaciones", value="", key=f"int_obs_{persona_id}")

        if st.button("✅ Guardar interacción", key=f"int_guardar_{persona_id}"):
            try:
                insert_interaccion({
                    "persona_id": int(persona_id),
                    "fecha": str(fecha),
                    "respuesta": respuesta,  # ✅ real
                    "medio": medio,
                    "para_que_contacte": para_que,
                    "observaciones": observ,
                    "tipo": "interacción",
                    "created_by": int(user["id"]),
                    "seguimiento_cerrado": False,
                })
                st.success("Interacción guardada.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al guardar interacción: {e}")

        st.markdown("---")

    # 3) ASIGNAR SEGUIMIENTO (log con respuesta VACÍA)
    if st.session_state[seg_key]:
        st.markdown("### 🧭 Asignar seguimiento")

        usuarios = get_users_same_comuna(user)
        opciones = [(u["id"], u["username"]) for u in usuarios]
        if not opciones:
            st.info("No hay usuarios activos en tu comuna para asignar.")
        else:
            elegido = st.selectbox("Asignar a", opciones, format_func=lambda x: x[1], key=f"seg_asignar_a_{persona_id}")
            fecha_obj = st.date_input("Fecha objetivo", value=datetime.date.today(), key=f"seg_fecha_obj_{persona_id}")
            motivo = st.text_area("Observación / motivo", value="", key=f"seg_motivo_{persona_id}")

            if st.button("📌 Confirmar asignación", key=f"seg_confirmar_{persona_id}"):
                try:
                    insert_seguimiento({
                        "persona_id": int(persona_id),
                        "assigned_to": int(elegido[0]),
                        "created_by": int(user["id"]),
                        "fecha": str(fecha_obj),
                        "estado": "pendiente",
                        "observaciones": motivo,
                        "creado_en": str(datetime.date.today()),
                    })

                    # ✅ log: mantiene fecha, pero NO pisa feedback
                    insert_interaccion({
                        "persona_id": int(persona_id),
                        "fecha": str(datetime.date.today()),
                        "respuesta": None,          # 👈 CLAVE: vacío
                        "medio": "Otro",
                        "observaciones": motivo,
                        "tipo": "seguimiento asignado",
                        "created_by": int(user["id"]),
                        "seguimiento_cerrado": False,
                    })

                    st.success("Seguimiento asignado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al asignar seguimiento: {e}")

        st.markdown("---")

    # HISTORIAL (siempre visible)
    st.markdown("## 🧾 Historial")
    hist = get_historial_persona(persona_id)
    if hist.empty:
        st.info("Sin historial todavía.")
        return

    hist = hist.copy()
    
    # Mapear usuario que cargó la interacción (created_by)
    user_map = get_usuarios_mapping()
    if "created_by" in hist.columns:
        hist["Usuario"] = hist["created_by"].map(user_map).fillna("Desconocido")
    elif "usuario_id" in hist.columns:
        # Fallback por si usan usuario_id en lugar de created_by
        hist["Usuario"] = hist["usuario_id"].map(user_map).fillna("Desconocido")

    if "tipo" in hist.columns:
        hist["tipo"] = hist["tipo"].fillna("").astype(str)

    cols_show = [
        "fecha",
        "tipo",
        "Usuario",            # ✅ Nueva columna
        "respuesta",          # ✅ acá se verá vacío en seguimiento asignado
        "medio",
        "para_que_contacte",
        "motivo",
        "observaciones",
        "creado_en",
    ]
    cols_show = [c for c in cols_show if c in hist.columns or c == "Usuario"]
    st.dataframe(hist[cols_show], use_container_width=True)
