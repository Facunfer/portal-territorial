# personas_app.py
import streamlit as st
import pandas as pd
import datetime
import requests

from supabase import create_client, Client
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

import personas_edicion
import personas_scope_rules


# =========================
# Cliente Supabase
# =========================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)


# =========================
# Locale ES AgGrid
# =========================
LOCALE_ES = {
    "page": "Página",
    "more": "más",
    "to": "a",
    "of": "de",
    "next": "Siguiente",
    "last": "Última",
    "first": "Primera",
    "previous": "Anterior",
    "loadingOoo": "Cargando...",
    "selectAll": "Seleccionar todo",
    "searchOoo": "Buscar...",
    "blanks": "(En blanco)",
    "filterOoo": "Filtrar...",
    "applyFilter": "Aplicar filtro...",
    "clearFilter": "Borrar filtro...",
    "equals": "Igual a",
    "notEqual": "Distinto de",
    "contains": "Contiene",
    "notContains": "No contiene",
    "startsWith": "Empieza con",
    "endsWith": "Termina con",
    "lessThan": "Menor que",
    "greaterThan": "Mayor que",
    "lessThanOrEqual": "Menor o igual que",
    "greaterThanOrEqual": "Mayor o igual que",
    "inRange": "Entre",
    "andCondition": "Y",
    "orCondition": "O",
    "noRowsToShow": "No hay filas para mostrar",
}


# =========================
# Barrios por comuna (CABA)
# =========================
BARRIOS_POR_COMUNA = {
    1: ["Retiro", "San Nicolás", "Puerto Madero", "San Telmo", "Montserrat", "Constitución"],
    2: ["Recoleta"],
    3: ["Balvanera", "San Cristóbal"],
    4: ["La Boca", "Barracas", "Parque Patricios", "Nueva Pompeya"],
    5: ["Almagro", "Boedo"],
    6: ["Caballito"],
    7: ["Flores", "Parque Chacabuco"],
    8: ["Villa Soldati", "Villa Riachuelo", "Villa Lugano"],
    9: ["Liniers", "Mataderos", "Parque Avellaneda"],
    10: ["Villa Real", "Monte Castro", "Versalles", "Floresta", "Vélez Sarsfield", "Villa Luro"],
    11: ["Villa General Mitre", "Villa Devoto", "Villa del Parque", "Villa Santa Rita"],
    12: ["Coghlan", "Saavedra", "Villa Pueyrredón", "Villa Urquiza"],
    13: ["Belgrano", "Colegiales", "Núñez"],
    14: ["Palermo"],
    15: ["Agronomía", "Chacarita", "La Paternal", "Villa Crespo", "Villa Ortúzar", "Parque Chas"],
}


# =========================
# Normalizador USIG
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
    except Exception as e:
        st.warning(f"No se pudieron obtener sugerencias de direcciones: {e}")
        return []


def normalizar_domicilio_caba(domicilio_input: str):
    texto = (domicilio_input or "").strip()
    if texto == "":
        return None, None
    try:
        direcciones = _llamar_usig(texto)
        if not direcciones:
            return None, "No se encontró una dirección válida en CABA."
        d0 = direcciones[0]
        dir_norm = _texto_desde_obj_direccion(d0)
        return dir_norm, None
    except Exception as e:
        return None, f"Error: {e}"


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
# Helpers semáforos
# =========================
def _parse_tags(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join([str(x) for x in v if str(x).strip()])
    return str(v).strip()


def semaforo_tiempo_label(ultima_fecha):
    if ultima_fecha is None:
        return "⚫ SIN CONTACTO"
    hoy = datetime.date.today()
    try:
        dias = (hoy - ultima_fecha).days
    except Exception:
        return "⚫ SIN CONTACTO"

    if dias < 30:
        return "🟢 <30 días"
    if 30 <= dias <= 60:
        return "🟡 30–60 días"
    return "🔴 >60 días"


def semaforo_respuesta_label(status):
    s = (status or "NO CONTACTADO").strip().upper()
    if s == "POSITIVO":
        return "🟢 POSITIVO"
    if s == "NEUTRO":
        return "🟡 NEUTRO"
    if s == "NEGATIVO":
        return "🔴 NEGATIVO"
    if s == "NUMERO INEXISTENTE/EQUIVOCADO":
        return "🟠 NÚMERO INEXISTENTE/EQUIVOCADO"
    return "⚫ NO CONTACTADO"


# =========================
# Permisos / Scope desde routers
# =========================
def _get_scope():
    """
    router_personas guarda:
      - PERM_PERSONAS_SCOPE_KIND
      - PERM_PERSONAS_SCOPE_VALUE
    """
    kind = (st.session_state.get("PERM_PERSONAS_SCOPE_KIND") or "ALL").strip().upper()
    value = st.session_state.get("PERM_PERSONAS_SCOPE_VALUE")
    if isinstance(value, str):
        value = value.strip()
    return kind, value



# =========================
# Asignaciones (EXTRACTO) - SOLO lo asignado
# =========================
def _is_extracto(user: dict) -> bool:
    return (str(user.get("rol") or "").strip().upper() == "EXTRACTO")


def _get_assigned_persona_ids_via_usuarios_asignaciones(user: dict) -> list[int]:
    """Trae IDs de personas asignadas al usuario desde `usuarios_asignaciones`."""
    try:
        uid = user.get("id")
        if uid is None:
            return []
        supabase = get_supabase()
        res = (
            supabase.table("usuarios_asignaciones")
            .select("objeto_id")
            .eq("usuario_id", int(uid))
            .eq("objeto_tipo", "PERSONA")
            .execute()
        )
        rows = res.data or []
        ids = []
        for r in rows:
            oid = r.get("objeto_id")
            if oid is None:
                continue
            try:
                ids.append(int(oid))
            except Exception:
                pass
        # únicos
        seen=set()
        out=[]
        for x in ids:
            if x not in seen:
                seen.add(x); out.append(x)
        return out
    except Exception:
        return []

# =========================
# Data Personas (respetando scope)
# =========================
def get_personas_for_user(user, force_vertical_filter: bool = True):
    """
    Respeta el scope definido en router_personas:
    - ALL: sin filtro
    - COMUNA: filtra por comuna_id del user
    - TAG: filtra por tag exacto (case-insensitive) sobre personas.tags

    Importante:
    - personas.tags puede ser array (list) o string.
    - Para TAG, filtramos en Python para evitar depender de operadores de PostgREST
      y para que funcione igual si tags es array o string.
    """
    supabase = get_supabase()
    cols = (
        "id, nombre_apellido, dni, telefono, barrio, comuna_id, domicilio, email, "
        "sexo, edad, fiscalizo, de_donde_salio, creado_en, tags, latitud, longitud"
    )

    kind, scope_value = _get_scope()

    # 0) EXTRACTO: ver SOLO lo asignado (ignora scope general)
    if _is_extracto(user):
        ids = _get_assigned_persona_ids_via_usuarios_asignaciones(user)
        if not ids:
            return pd.DataFrame([])

        # Traer solo las personas asignadas (en chunks para no romper URL)
        rows = []
        def _chunk(xs, n=200):
            xs=list(xs)
            for i in range(0, len(xs), n):
                yield xs[i:i+n]

        for ch in _chunk(ids, 200):
            page, page_size = 0, 1000
            while True:
                res = (
                    supabase.table("personas")
                    .select(cols)
                    .in_("id", [int(x) for x in ch])
                    .range(page * page_size, (page + 1) * page_size - 1)
                    .execute()
                )
                data = res.data or []
                rows.extend(data)
                if len(data) < page_size:
                    break
                page += 1

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # normalizar tags a string para filtros y UI
        if "tags" in df.columns:
            df["tags"] = df["tags"].apply(_parse_tags)

        if "creado_en" in df.columns:
            df["creado_en"] = df["creado_en"].astype("string").replace("NaT", "").fillna("")

        return df


    q = supabase.table("personas").select(cols)

    # Aplicar reglas de visibilidad SENSIBLES (server-side)
    q = personas_scope_rules.apply_personas_visibility_filter(q, user, force_filter=force_vertical_filter)

    # 2) Traer en páginas
    rows, page = [], 0
    page_size = 1000
    while True:
        res = q.range(page * page_size, (page + 1) * page_size - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        page += 1

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 3) Filtro por TAG (Legacy/Fallback)
    # Si por alguna razón el scope_rules no atrapó la vertical pero el scope es TAG,
    # filtramos en Python como fallback de seguridad.
    kind, scope_value = _get_scope() # Re-check scope
    if kind == "TAG" and not personas_scope_rules.is_restricted_vertical(user):
        tag_obj = (scope_value or "").strip().upper()
        if tag_obj:
            allowed_tags = {t.strip() for t in tag_obj.split("|") if t.strip()}
            def _tiene_tag(tags_str: str):
                tagset = {t.strip().upper() for t in str(tags_str).split(",") if t.strip()}
                return any(t in tagset for t in allowed_tags)
            
            # Nota: Necesitamos parsear tags antes de aplicar el filtro si vienen como array
            def _local_parse(x):
                if isinstance(x, list): return ",".join([str(i) for i in x])
                return str(x) if x else ""

            df["_tmp_tags"] = df["tags"].apply(_local_parse)
            df = df[df["_tmp_tags"].fillna("").astype(str).apply(_tiene_tag)].copy()
            df.drop(columns=["_tmp_tags"], inplace=True)
        else:
            df = df.iloc[0:0].copy()

    # normalizar tags a string para filtros y UI
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(_parse_tags)

    if "creado_en" in df.columns:
        df["creado_en"] = df["creado_en"].astype("string").replace("NaT", "").fillna("")

    # 3) filtro por TAG (vertical personas)
    if kind == "TAG":
        tag_obj = (scope_value or "").strip().upper()
        if tag_obj:
            allowed_tags = {t.strip() for t in tag_obj.split("|") if t.strip()}
            def _tiene_tag(tags_str: str):
                tagset = {t.strip().upper() for t in str(tags_str).split(",") if t.strip()}
                return any(t in tagset for t in allowed_tags)

            df = df[df["tags"].fillna("").astype(str).apply(_tiene_tag)].copy()
        else:
            # scope TAG sin value => nada
            df = df.iloc[0:0].copy()

    return df


# =========================
# Interacciones resumen (FIX: chunking para no romper URL)
# =========================
def _chunk_list(xs, size: int):
    xs = list(xs or [])
    for i in range(0, len(xs), size):
        yield xs[i:i + size]


def get_interacciones_resumen(persona_ids, chunk_size: int = 250):
    """
    Devuelve dict:
      persona_id -> (fecha_dt, status_norm, created_by_id)
    """
    if not persona_ids:
        return {}

    supabase = get_supabase()
    rows = []

    for chunk in _chunk_list([int(x) for x in persona_ids], chunk_size):
        page, page_size = 0, 1000
        while True:
            res = (
                supabase.table("interacciones_personas")
                .select("persona_id, fecha, respuesta, created_by")
                .in_("persona_id", chunk)
                .order("fecha", desc=True)
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1

    def norm_status(s):
        if s is None:
            return "NO CONTACTADO"
        up = str(s).strip().upper()
        allowed = ["POSITIVO", "NEUTRO", "NEGATIVO", "NO CONTACTADO", "NUMERO INEXISTENTE/EQUIVOCADO"]
        return up if up in allowed else "NO CONTACTADO"

    resumen = {}
    def _parse_fecha(x):
        try:
            return pd.to_datetime(x)
        except Exception:
            return pd.NaT

    rows_sorted = sorted(rows, key=lambda r: _parse_fecha(r.get("fecha")), reverse=True)

    for r in rows_sorted:
        pid = r.get("persona_id")
        if pid is None or pid in resumen:
            continue
        fecha_raw = r.get("fecha")
        try:
            fecha_dt = pd.to_datetime(fecha_raw).date() if str(fecha_raw).strip() else None
        except Exception:
            fecha_dt = None
        resumen[int(pid)] = (fecha_dt, norm_status(r.get("respuesta")), r.get("created_by"))
    return resumen


    return resumen


def _fetch_all_assigned_users_details(object_type: str, object_ids: list[int]) -> dict:
    """
    Retorna {object_id: [ {username, rol, comuna_id, vertical}, ... ] }
    """
    if not object_ids:
        return {}
    supabase = get_supabase()
    rows = []
    chunk_size = 200
    oids_list = list(object_ids)
    
    for i in range(0, len(oids_list), chunk_size):
        chunk = oids_list[i:i+chunk_size]
        res = (
            supabase.table("usuarios_asignaciones")
            .select("objeto_id, usuario:usuarios(username, rol, comuna_id, vertical)")
            .eq("objeto_tipo", object_type)
            .in_("objeto_id", chunk)
            .execute()
        )
        if res.data:
            rows.extend(res.data)

    from collections import defaultdict
    mapping = defaultdict(list)
    for r in rows:
        oid = r.get("objeto_id")
        u_obj = r.get("usuario")
        if oid and u_obj:
            mapping[oid].append(u_obj)
            
    return mapping


def _get_filtered_usernames(assigned_users_list, viewer_user):
    if not assigned_users_list:
        return []

    # Datos Viewer
    v_rol = (viewer_user.get("rol") or "").strip().upper()
    v_comuna = viewer_user.get("comuna_id")
    v_vertical = (viewer_user.get("vertical") or "").strip().upper()

    # Si es Admin/Global -> Todo
    if v_rol in ["ADMIN", "GLOBAL", "SOPORTE", "SUPER"]:
        return sorted([u["username"] for u in assigned_users_list if u.get("username")])

    # Filtrado
    res = []
    for u in assigned_users_list:
        uname = u.get("username")
        if not uname: continue
        
        u_comuna = u.get("comuna_id")
        u_vertical = (u.get("vertical") or "").strip().upper()
        
        keep = False
        
        # Caso VERTICAL
        if v_vertical and v_vertical != "NONE":
            if u_vertical == v_vertical:
                keep = True
        
        # Caso COMUNA
        elif v_comuna is not None:
             if u_comuna == v_comuna:
                 keep = True
        
        # Fallback
        else:
            keep = True
            
        if keep:
            res.append(uname)
            
    return sorted(res)


def _calc_estado_asignacion(asignado_str):
    if not asignado_str:
        return "No asignado"
    # asignado_str viene como "juan, pedro"
    parts = [x for x in asignado_str.split(",") if x.strip()]
    c = len(parts)
    if c == 0:
        return "No asignado"
    if c == 1:
        return "1 asignado"
    if c == 2:
        return "2 asignados"
    return "+ de 2 asignados"


# =========================
# UI principal Personas
# =========================
def personas_screen():
    user = st.session_state["user"]

    st.header("Personas")

    if "show_new_persona" not in st.session_state:
        st.session_state["show_new_persona"] = False
    if "selected_persona_id" not in st.session_state:
        st.session_state["selected_persona_id"] = None
    if "ficha_abierta" not in st.session_state:
        st.session_state["ficha_abierta"] = True

    # --- Lógica de Visibilidad por Vertical (Toggle) ---
    force_vertical = True
    if personas_scope_rules.is_restricted_vertical(user):
        tags = personas_scope_rules.get_vertical_tags(user)
        tags_str = " o ".join(tags)
        st.info(f"💡 Vista filtrada por vertical: **{tags_str}**")
        # El requerimiento dice default ON y que NO pueden ver fuera de esos tags
        st.toggle(f"Filtrar por mi vertical ({tags_str})", value=True, disabled=True, key="v_toggle")
        force_vertical = True
    # ----------------------------------------------------

    # botón alta
    cbtn, _ = st.columns([1, 6])
    with cbtn:
        if st.button("➕ Agregar persona"):
            st.session_state["show_new_persona"] = not st.session_state["show_new_persona"]

    # alta persona
    if st.session_state["show_new_persona"]:
        st.markdown("### ➕ Nueva persona")
        supabase = get_supabase()

        # TAGS_SUGERIDOS_LOCAL eliminado para usar la fuente única en personas_edicion
        
        c1, c2 = st.columns(2)
        with c1:
            nombre_apellido = st.text_input("Nombre y apellido *", value="", key="np_nombre")
            dni = st.text_input("DNI *", value="", key="np_dni")
            telefono = st.text_input("Teléfono *", value="", key="np_tel")

            opciones_comunas = list(range(1, 16))

            # Si el scope es COMUNA, fijamos comuna. Si es TAG/ALL, dejamos elegir.
            kind, _scope_value = _get_scope()
            if kind == "COMUNA":
                comuna_id_new = int(user.get("comuna_id") or 1)
                st.selectbox("Comuna", opciones_comunas, index=opciones_comunas.index(comuna_id_new), disabled=True)
            else:
                comuna_id_new = st.selectbox("Comuna", opciones_comunas, index=0, key="np_comuna")

            barrios_opciones = BARRIOS_POR_COMUNA.get(int(comuna_id_new), [])
            barrio = st.selectbox("Barrio", barrios_opciones, key="np_barrio") if barrios_opciones else st.text_input(
                "Barrio", key="np_barrio_text"
            )

        with c2:
            domicilio = st.text_input("Domicilio (CABA, normalizado)", value="", key="np_dom")
            dom_sel = None
            if len(domicilio.strip()) >= 3:
                sug = sugerir_direcciones_caba(domicilio)
                if sug:
                    dom_sel = st.selectbox("Sugerencias", ["(Usar texto)"] + sug, index=0, key="np_dom_sug")

            email = st.text_input("Email", value="", key="np_email")
            sexo = st.selectbox("Sexo", ["", "MASCULINO", "FEMENINO"], index=0, key="np_sexo")
            edad = st.number_input("Edad", min_value=0, max_value=120, value=0, key="np_edad")
            fiscalizo = st.selectbox("Fiscalizó", ["", "SI", "NO"], index=0, key="np_fiscalizo")

        tags_sel = st.multiselect("Tags", options=sorted(personas_edicion.TAGS_SUGERIDOS), default=[], key="np_tags")

        cg1, cg2 = st.columns(2)
        with cg1:
            guardar = st.button("Guardar nueva persona", key="np_guardar")
        with cg2:
            cancelar = st.button("Cancelar", key="np_cancelar")

        if cancelar:
            st.session_state["show_new_persona"] = False
            st.rerun()

        if guardar:
            if not nombre_apellido.strip() or not dni.strip() or not telefono.strip():
                st.error("Completá Nombre y apellido, DNI y Teléfono.")
            else:
                try:
                    ex = supabase.table("personas").select("id, dni").eq("dni", dni.strip()).limit(1).execute()
                    if (ex.data or []):
                        st.error("Ese DNI ya existe en la base.")
                        st.stop()

                    if dom_sel and dom_sel != "(Usar texto)":
                        dom_normalizado = dom_sel
                        err_norm = None
                    else:
                        dom_normalizado, err_norm = normalizar_domicilio_caba(domicilio)

                    if err_norm:
                        st.error(err_norm)
                    else:
                        # Geocodificación automática en el alta
                        lat, lon = geocodificar_con_reintentos(dom_normalizado)

                        data = {
                            "nombre_apellido": nombre_apellido.strip(),
                            "dni": dni.strip(),
                            "telefono": telefono.strip(),
                            "barrio": barrio.strip() if barrio else None,
                            "comuna_id": int(comuna_id_new),
                            "domicilio": dom_normalizado,
                            "email": email.strip() if email else None,
                            "sexo": sexo.strip().upper() if sexo else None,
                            "edad": int(edad) if edad is not None else 0,
                            "fiscalizo": (fiscalizo or "").strip().upper() if fiscalizo else None,
                            "de_donde_salio": "Agregado a la BBDD",
                            "creado_en": str(datetime.date.today()),
                            "tags": tags_sel if tags_sel else None,
                            "latitud": lat,
                            "longitud": lon,
                        }
                        supabase.table("personas").insert(data).execute()
                        st.success("Persona creada correctamente (con geolocalización).")
                        st.session_state["show_new_persona"] = False
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al crear persona: {e}")

        st.markdown("---")

    # =========================
    # Cargar personas (respetando scope)
    # =========================
    df = get_personas_for_user(user, force_vertical_filter=force_vertical)
    if df.empty:
        st.info("No hay personas para mostrar.")
        return

    persona_ids = df["id"].astype(int).tolist()

    # Resumen últimas interacciones (chunked)
    pids = df["id"].tolist()
    resumen_int = get_interacciones_resumen(pids)
    
    # Mapeo de usuarios para "Cargado por"
    user_map = personas_edicion.get_usuarios_mapping()

    def _get_resumen(pid):
        data = resumen_int.get(int(pid))
        if not data:
            return None, "NO CONTACTADO", "Desconocido"
        fdt, st_norm, c_by = data
        user_name = user_map.get(c_by, "Desconocido") if c_by else "Desconocido"
        return fdt, st_norm, user_name

    res_list = [ _get_resumen(pid) for pid in pids ]
    df["ultima_fecha_dt"] = [ r[0] for r in res_list ]
    df["ultima_fecha"] = [ "" if r[0] is None else str(r[0]) for r in res_list ]
    df["ultima_resp"] = [ r[1] for r in res_list ]
    df["cargado_por"] = [ r[2] for r in res_list ]
    df["semaforo_tiempo"] = df["ultima_fecha_dt"].apply(semaforo_tiempo_label)
    df["semaforo_respuesta"] = df["ultima_resp"].apply(semaforo_respuesta_label)

    # Asignados
    assigned_details_map = _fetch_all_assigned_users_details("PERSONA", persona_ids)
    # user = st.session_state["user"] (ya definido al inicio de personas_screen)
    user = st.session_state["user"]
    
    df["asignado_a"] = df["id"].apply(
        lambda x: ", ".join(_get_filtered_usernames(assigned_details_map.get(int(x), []), user))
    )
    df["estado_asignacion"] = df["asignado_a"].apply(_calc_estado_asignacion)

    # =========================
    # filtros (con keys para reset)
    # =========================
    # filtros (con keys para reset)
    # =========================
    
    # --- REFACTOR UI: Filtros Compactos ---
    with st.expander("🔎 Filtros y Búsqueda", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        
        # COL 1
        with c1:
            sexo_vals = sorted([x for x in df.get("sexo", pd.Series()).dropna().unique().tolist() if str(x).strip()])
            filtro_sexo = st.selectbox("Sexo", ["Todos"] + sexo_vals, index=0, key="flt_sexo")
            
            est_asign_opts = sorted(df["estado_asignacion"].unique().tolist())
            filtro_est_asign = st.selectbox("Asignación", ["Todos"] + est_asign_opts, key="flt_p_est_asign")
            
            # NUEVO: Filtro Comuna (Solo si es Vertical/Global, o sea tiene scope TAG/ALL)
            kind, val = _get_scope()
            filtro_comuna_vertical = None
            if kind in ["TAG", "ALL"]:
                 # Para usuarios verticales/globales, mostramos SIEMPRE el selector de comunas (1-15)
                 # aunque no tengan datos aun, para que puedan filtrar explicitamente o ver "Todas".
                 # Ojo: si hay datos de una sola comuna, el selector igual es util para confirmar "estoy viendo todo" o "solo esto".
                 comunas_disp = list(range(1, 16))
                 # Podriamos filtrar solo las presentes: 
                 # comunas_disp = sorted(df["comuna_id"].dropna().unique().astype(int).tolist())
                 # Pero el usuario pide VER el filtro. Si no hay datos, pues no habra resultados.
                 # Mejor strategy: Mostrar todas las comunas posibles (1..15) para que el filtro exista.
                 filtro_comuna_vertical = st.selectbox("Comuna (Vertical)", ["Todas"] + comunas_disp, index=0, key="flt_p_comuna_v")

        # COL 2
        with c2:
            filtro_fiscal = st.selectbox("Fiscalizó", ["Todos", "SI", "NO"], index=0, key="flt_fiscal")
            
            # Tags
            # Lógica corregida: Si es Vertical (TAG), solo mostrar tags de su vertical.
            if kind == "TAG" and val:
                # val viene como "JUVENTUD|BASES|UNIVERSIDAD"
                tags_permitidos = {t.strip().upper() for t in val.split("|") if t.strip()}
                tags_vals = sorted(list(tags_permitidos))
            else:
                # Global / Comuna / Otro -> Mostrar TODOS los sugeridos + los presentes
                data_tags = {
                    t.strip().upper()
                    for v in df.get("tags", pd.Series()).fillna("").tolist()
                    for t in str(v).split(",")
                    if t.strip()
                }
                sugeridos_tags = set([t.upper() for t in personas_edicion.TAGS_SUGERIDOS])
                tags_vals = sorted(list(data_tags | sugeridos_tags))
                
            filtro_tags_multi = st.multiselect("Tags", options=tags_vals, default=[], key="flt_tags")

        # COL 3
        with c3:
            # Semáforos
            tiempo_vals = sorted(df["semaforo_tiempo"].unique().tolist())
            filtro_tiempo = st.selectbox("Semáforo Tiempo", ["Todos"] + tiempo_vals, index=0, key="flt_tiempo")
            
            resp_vals = sorted(df["semaforo_respuesta"].unique().tolist())
            filtro_resp = st.selectbox("Semáforo Respuesta", ["Todos"] + resp_vals, index=0, key="flt_resp")

        # COL 4
        with c4:
            # Barrio (Recuperamos logica anterior y adaptamos si se filtro comuna arriba)
            barrios_disponibles_df = set(df['barrio'].dropna().unique())
            
            # Si el user seleccionó una comuna específica en el filtro vertical, mostramos solo esos barrios
            # Si eligió "Todas", mostramos todos los del DF.
            comunas_para_barrios = df['comuna_id'].dropna().unique()
            if filtro_comuna_vertical and filtro_comuna_vertical != "Todas":
                comunas_para_barrios = [int(filtro_comuna_vertical)]
                # Re-filtramos barrios disponibles para que solo muestre los de esa comuna (cleaner)
                # Ojo: barrios_disponibles_df tiene lo del DF completo por ahora.
                # Mejor reconstruimos:
                barrios_disponibles_df = set() # Start fresh if filtering
            
            for c in comunas_para_barrios:
                try:
                    # Agregamos DE LA ESTRUCTURA si existe
                    for b in personas_edicion.BARRIOS_POR_COMUNA.get(int(c), []):
                         barrios_disponibles_df.add(b)
                except: pass
            
            # Tambien agregamos los que ya esten en la data (si coinciden con la comuna seleccionada)
            if filtro_comuna_vertical and filtro_comuna_vertical != "Todas":
                 # Filtramos data temp
                 bs_data = df[df["comuna_id"] == int(filtro_comuna_vertical)]["barrio"].dropna().unique()
                 for b in bs_data: barrios_disponibles_df.add(b)
            else:
                 # Todas
                 bs_data = df["barrio"].dropna().unique()
                 for b in bs_data: barrios_disponibles_df.add(b)

            barrios_opciones = sorted(list(barrios_disponibles_df))
            filtro_barrios = st.multiselect("Barrio", options=barrios_opciones, default=[], key="flt_barrio")
            
            origen_vals = sorted([x for x in df.get("de_donde_salio", pd.Series()).fillna("").unique().tolist() if str(x).strip()])
            filtro_origen = st.selectbox("Origen", ["Todos"] + origen_vals, index=0, key="flt_origen")

        # Fechas (Full width o abajo)
        fechas_validas = [d for d in df["ultima_fecha_dt"].tolist() if isinstance(d, datetime.date)]
        filtro_fecha_desde, filtro_fecha_hasta = None, None
        
        if fechas_validas:
             st.markdown("---")
             cf1, cf2 = st.columns([3, 1])
             with cf1:
                 min_d, max_d = min(fechas_validas), max(fechas_validas)
                 rango = st.date_input("📅 Rango de Último Contacto", value=(min_d, max_d), key="flt_rango_fecha")
                 if isinstance(rango, tuple) and len(rango) == 2:
                     filtro_fecha_desde, filtro_fecha_hasta = rango
             with cf2:
                 st.write("") # Spacer
                 if st.button("🧹 Limpiar", use_container_width=True, key="btn_limpiar_p"):
                      # Hacky clear
                      for k in ["flt_sexo", "flt_p_est_asign", "flt_fiscal", "flt_tags", "flt_tiempo", "flt_resp", "flt_barrio", "flt_origen"]:
                          if k in st.session_state: del st.session_state[k]
                      st.rerun()

    # aplicar filtros
    dff = df.copy()

    if filtro_sexo != "Todos" and "sexo" in dff.columns:
        dff = dff[dff["sexo"].fillna("").astype(str) == filtro_sexo]

    if filtro_fiscal != "Todos" and "fiscalizo" in dff.columns:
        dff = dff[dff["fiscalizo"].fillna("").astype(str).str.upper() == filtro_fiscal]

    if filtro_resp != "Todos":
        dff = dff[dff["semaforo_respuesta"] == filtro_resp]

    if filtro_tiempo != "Todos":
        dff = dff[dff["semaforo_tiempo"] == filtro_tiempo]

    if filtro_origen != "Todos":
        dff = dff[dff["de_donde_salio"].fillna("").astype(str) == filtro_origen]

    if filtro_tags_multi:
        def contiene_todos(tags_str: str):
            tagset = {t.strip().lower() for t in str(tags_str).split(",") if t.strip()}
            return all(t.lower() in tagset for t in filtro_tags_multi)

        dff = dff[dff["tags"].fillna("").astype(str).apply(contiene_todos)]
    
    if filtro_barrios:
        dff = dff[dff["barrio"].isin(filtro_barrios)]

    if filtro_est_asign != "Todos":
        dff = dff[dff["estado_asignacion"] == filtro_est_asign]

    if filtro_fecha_desde and filtro_fecha_hasta and fechas_validas:
        if not (filtro_fecha_desde == min(fechas_validas) and filtro_fecha_hasta == max(fechas_validas)):
            dff = dff[dff["ultima_fecha_dt"].notna()]
            dff = dff[(dff["ultima_fecha_dt"] >= filtro_fecha_desde) & (dff["ultima_fecha_dt"] <= filtro_fecha_hasta)]

    if filtro_comuna_vertical and filtro_comuna_vertical != "Todas":
        dff = dff[dff["comuna_id"] == int(filtro_comuna_vertical)]

    st.markdown("---")

    columnas = [
        "id",
        "nombre_apellido",
        "dni",
        "telefono",
        "barrio",
        "comuna_id",
        "fiscalizo",
        "de_donde_salio",
        "creado_en",
        "tags",
        "semaforo_respuesta",
        "ultima_fecha",
        "cargado_por",
        "semaforo_tiempo",
        "asignado_a",
        "estado_asignacion",
    ]
    columnas = [c for c in columnas if c in dff.columns]
    dff_show = dff[columnas].copy()

    # KPIs segun filtros (NO TOCAR)
    def _count_label(df_, label):
        if df_.empty or "semaforo_tiempo" not in df_.columns:
            return 0
        return int((df_["semaforo_tiempo"] == label).sum())

    k_total = int(len(dff_show))
    k_30 = _count_label(dff_show, "🟢 <30 días")
    k_3060 = _count_label(dff_show, "🟡 30–60 días")
    k_60 = _count_label(dff_show, "🔴 >60 días")
    k_sin = _count_label(dff_show, "⚫ SIN CONTACTO")

    def _limpiar_filtros():
        for k in ["flt_sexo", "flt_tags", "flt_fiscal", "flt_tiempo", "flt_origen", "flt_resp", "flt_rango_fecha", "flt_p_est_asign"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    # --- INIT STATES (at the top or before usage) ---
    if "show_mass_interaction" not in st.session_state:
        st.session_state["show_mass_interaction"] = False
    if "show_casos_personas" not in st.session_state:
        st.session_state["show_casos_personas"] = False
    
    is_mass_mode = st.session_state["show_mass_interaction"]
    selection_mode = "multiple" if is_mass_mode else "single"
    use_checkbox = True if is_mass_mode else False

    # 1. KPIs
    with st.container(border=True):
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1.3, 1.0, 1.15, 1.0, 1.4, 1.2, 1.5])
        with c1:
            st.metric("Personas", k_total)
        with c2:
            st.metric("🟢 <30", k_30)
        with c3:
            st.metric("🟡 30–60", k_3060)
        with c4:
            st.metric("🔴 >60", k_60)
        with c5:
            st.metric("⚫ Sin contacto", k_sin)
        with c6:
            st.button("🧹 Limpiar filtros", use_container_width=True, on_click=_limpiar_filtros)
        with c7:
            csv_bytes = dff_show.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Exportar CSV",
                data=csv_bytes,
                file_name=f"personas_filtradas_{datetime.date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.markdown("---")

    # 2. Main AgGrid (Moved Up)
    gb = GridOptionsBuilder.from_dataframe(dff_show)
    gb.configure_default_column(sortable=True, filter=True, resizable=True, minWidth=140, wrapText=True, autoHeight=True)
    
    # Configuración de columnas específicas
    gb.configure_column("id", headerName="ID", width=100)
    gb.configure_column("ultima_fecha", headerName="Última fecha")
    gb.configure_column("ultima_resp", headerName="Resultado")
    gb.configure_column("cargado_por", headerName="Interacción por")
    gb.configure_column("asignado_a", headerName="Asignado a")
    gb.configure_column("ultima_fecha_dt", hide=True)
    
    # Checkbox selection for mass mode
    if is_mass_mode:
        # Habilitamos checkbox específicamente en la primera columna (id o nombre_apellido)
        first_col = dff_show.columns[0]
        gb.configure_column(first_col, checkboxSelection=True, headerCheckboxSelection=True)
        gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    else:
        gb.configure_selection(selection_mode="single", use_checkbox=False)
    grid_options = gb.build()

    grid_response = AgGrid(
        dff_show,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        theme="streamlit",
        enable_enterprise_modules=False,
        height=520,
        fit_columns_on_grid_load=False,
        localeText=LOCALE_ES,
        key=f"grid_personas_{selection_mode}"
    )
    selected_rows = grid_response.get("selected_rows", None)

    st.markdown("---")

    # 3. Botonera (Moved Down)
    ccas, cmass, _ = st.columns([1, 1, 5])
    with ccas:
        if st.button("📌 Ver mis casos asignados", use_container_width=True, key="btn_toggle_casos_personas"):
            st.session_state["show_casos_personas"] = not st.session_state["show_casos_personas"]
            if st.session_state["show_casos_personas"]:
                st.session_state["show_mass_interaction"] = False
    
    with cmass:
        label_mass = "⚡ Cargar interacción masiva"
        if st.session_state["show_mass_interaction"]:
            label_mass = "❌ Cancelar masiva"
        if st.button(label_mass, use_container_width=True, key="btn_toggle_mass_int"):
            st.session_state["show_mass_interaction"] = not st.session_state["show_mass_interaction"]
            if st.session_state["show_mass_interaction"]:
                st.session_state["ficha_abierta"] = False
                st.session_state["selected_persona_id"] = None
            st.rerun()

    if st.session_state["show_casos_personas"]:
        personas_edicion.render_casos_asignados(user)
    
    # ---------------------------------------------------------
    # MODO MASIVO: Formulario (visible only when is_mass_mode is True)
    # ---------------------------------------------------------
    if is_mass_mode:
        selected_list = []
        if isinstance(selected_rows, list):
            selected_list = selected_rows
        elif isinstance(selected_rows, pd.DataFrame):
            selected_list = selected_rows.to_dict("records")
            
        ids_selected = [int(r["id"]) for r in selected_list if r.get("id")]
        
        if not ids_selected:
            st.warning("Seleccioná al menos una persona en la tabla para cargar interacción.")
        else:
            st.markdown(f"### ⚡ Cargando interacción para **{len(ids_selected)}** personas")
            with st.container(border=True):
                c3, c4, c5 = st.columns(3)
                with c3:
                    fecha = st.date_input("Fecha", value=datetime.date.today(), key="mass_int_fecha")
                with c4:
                    respuesta = st.selectbox("Respuesta", personas_edicion.RESPUESTAS, index=0, key="mass_int_resp")
                with c5:
                    medio = st.selectbox("Medio", personas_edicion.MEDIOS, index=0, key="mass_int_medio")

                para_que = st.text_input("Motivo / Para qué lo contacté", value="", key="mass_int_para")
                observ = st.text_area("Observaciones", value="", key="mass_int_obs")

                if st.button(f"✅ Guardar interacción para {len(ids_selected)} personas", key="btn_save_mass"):
                    success_count = 0
                    error_count = 0
                    bar = st.progress(0)
                    
                    for i, pid in enumerate(ids_selected):
                        try:
                            personas_edicion.insert_interaccion({
                                "persona_id": int(pid),
                                "fecha": str(fecha),
                                "respuesta": respuesta,
                                "medio": medio,
                                "para_que_contacte": para_que,
                                "observaciones": observ,
                                "tipo": "interacción masiva",
                                "created_by": int(user["id"]),
                                "seguimiento_cerrado": False,
                            })
                            success_count += 1
                        except Exception:
                            error_count += 1
                        bar.progress((i + 1) / len(ids_selected))
                    
                    st.success(f"Finalizado. Exitosos: {success_count}. Errores: {error_count}.")
                    st.session_state["show_mass_interaction"] = False
                    st.rerun()

    # ---------------------------------------------------------
    # MODO SINGLE: Ficha normal (visible only when not in mass mode)
    # ---------------------------------------------------------
    else: # not is_mass_mode
        # Process single selection for ficha
        selected = None
        if isinstance(selected_rows, list) and len(selected_rows) > 0:
            selected = selected_rows[0]
        elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
            selected = selected_rows.iloc[0].to_dict()

        if selected is not None and selected.get("id") is not None:
            st.session_state["selected_persona_id"] = int(selected["id"])
            st.session_state["ficha_abierta"] = True
        else:
            # If no single row is selected, ensure ficha is closed
            st.session_state["ficha_abierta"] = False
            st.session_state["selected_persona_id"] = None

        st.markdown("---")

        if st.session_state.get("selected_persona_id") and st.session_state.get("ficha_abierta", True):
            pid = int(st.session_state["selected_persona_id"])
            personas_edicion.render_ficha_persona(user, pid)