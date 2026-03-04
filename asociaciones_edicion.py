import streamlit as st
import pandas as pd
import datetime
import requests

from supabase import create_client, Client

# =========================
# Cliente Supabase
# =========================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)


# =========================
# Constantes
# =========================
RESPUESTAS_ASOC = ["POSITIVO", "NEUTRO", "NEGATIVO", "NO VISITADO"]
MEDIOS = ["WhatsApp", "Llamada", "Instagram", "Facebook", "Email", "Presencial", "Otro"]

TIPOS_ASOC = [
    "Local comercial",
    "Centros de Jubilados",
    "Clubes",
    "Espacios Culturales",
    "Espacios de Culto",
]

SEGUIMIENTO_ESTADOS = ["pendiente", "hecho", "cancelado"]


# =========================
# Helpers "tolerantes" a columnas faltantes
# (evita que reviente si en Supabase falta alguna columna)
# =========================
def _is_missing_column_error(e: Exception) -> bool:
    msg = str(e) or ""
    return ("does not exist" in msg) and ("column" in msg)


def _extract_missing_column_name(e: Exception):
    # Ej: "column interacciones_asociaciones.para_que_contacte does not exist"
    msg = str(e) or ""
    marker = "column "
    if marker not in msg or " does not exist" not in msg:
        return None
    frag = msg.split(marker, 1)[1].split(" does not exist", 1)[0].strip()
    # frag puede venir como "tabla.columna"
    if "." in frag:
        return frag.split(".")[-1].strip()
    return frag.strip() if frag else None


def _safe_select(table: str, cols_csv: str, where_eq: dict = None, order_by: str = None, desc: bool = False):
    supabase = get_supabase()
    cols = [c.strip() for c in cols_csv.split(",") if c.strip()]

    while True:
        try:
            q = supabase.table(table).select(", ".join(cols))
            if where_eq:
                for k, v in where_eq.items():
                    q = q.eq(k, v)
            if order_by:
                q = q.order(order_by, desc=bool(desc))
            res = q.execute()
            return res.data or []
        except Exception as e:
            if not _is_missing_column_error(e):
                raise
            missing = _extract_missing_column_name(e)
            if not missing or missing not in cols:
                raise
            # sacamos la columna faltante y reintentamos
            cols = [c for c in cols if c != missing]
            if not cols:
                return []


def _safe_insert(table: str, payload: dict):
    """
    Inserta y si falla por columna inexistente, la elimina del payload y reintenta.
    """
    supabase = get_supabase()
    data = dict(payload or {})

    for _ in range(5):
        try:
            return supabase.table(table).insert(data).execute()
        except Exception as e:
            if not _is_missing_column_error(e):
                raise
            missing = _extract_missing_column_name(e)
            if not missing or missing not in data:
                raise
            data.pop(missing, None)

    # si agotó reintentos
    return supabase.table(table).insert(data).execute()


def _safe_update(table: str, payload: dict, where_eq: dict):
    supabase = get_supabase()
    data = dict(payload or {})

    for _ in range(5):
        try:
            q = supabase.table(table).update(data)
            for k, v in (where_eq or {}).items():
                q = q.eq(k, v)
            return q.execute()
        except Exception as e:
            if not _is_missing_column_error(e):
                raise
            missing = _extract_missing_column_name(e)
            if not missing or missing not in data:
                raise
            data.pop(missing, None)

    q = supabase.table(table).update(data)
    for k, v in (where_eq or {}).items():
        q = q.eq(k, v)
    return q.execute()


# =========================
# Geocoding USIG (lat/lon)
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
# DB: Asociaciones
# =========================
def get_asociacion(asoc_id: int):
    cols = (
        "id, nombre, direccion, comuna_id, tipo, observaciones, "
        "latitud, longitud, referente_nombre, referente_telefono"
    )
    rows = _safe_select("asociaciones", cols, where_eq={"id": int(asoc_id)})
    return rows[0] if rows else None


def update_asociacion(asoc_id: int, payload: dict):
    _safe_update("asociaciones", payload, where_eq={"id": int(asoc_id)})


# =========================
# DB: Interacciones (asociaciones)
# =========================
def insert_interaccion_asoc(payload: dict):
    _safe_insert("interacciones_asociaciones", payload)


def get_historial_asoc(asoc_id: int):
    """
    Historial ordenado por fecha desc (más reciente arriba).
    Importante: la fila "seguimiento asignado" debe mostrar respuesta vacía
    (la insertamos como None / "") y NO debe pisar el feedback de la tabla.
    """
    cols = (
        "fecha, respuesta, observaciones, creado_en, tipo, medio, "
        "para_que_contacte, seguimiento_id, seguimiento_cerrado, created_by, proxima_fecha"
    )
    rows = _safe_select(
        "interacciones_asociaciones",
        cols,
        where_eq={"asociacion_id": int(asoc_id)},
        order_by="fecha",
        desc=True,
    )

    df = pd.DataFrame(rows or [])
    if df.empty:
        return df

    # refuerzo: parse fecha y ordenar igual
    df["fecha"] = pd.to_datetime(df.get("fecha"), errors="coerce")
    df = df.sort_values("fecha", ascending=False, na_position="last")

    return df


def _norm_resp_asoc(v):
    if v is None:
        return None
    s = str(v).strip().upper()
    return s if s in set(RESPUESTAS_ASOC) else None


def get_ultima_fecha_evento_asoc(asoc_id: int):
    """
    Devuelve la fecha del último evento (incluye "seguimiento asignado").
    """
    df = get_historial_asoc(asoc_id)
    if df.empty:
        return None
    # ya viene ordenado desc
    f0 = df.iloc[0].get("fecha")
    if pd.isna(f0):
        return None
    try:
        return pd.to_datetime(f0).date()
    except Exception:
        return None


def get_ultimo_feedback_real_asoc(asoc_id: int):
    """
    Devuelve el feedback de la última interacción REAL, ignorando:
      - tipo == "seguimiento asignado"
      - respuesta vacía / None
    Si no hay, devuelve "NO VISITADO".
    """
    df = get_historial_asoc(asoc_id)
    if df.empty:
        return "NO VISITADO"

    # ignorar "seguimiento asignado"
    tipo = df.get("tipo")
    if tipo is not None:
        mask_tipo = tipo.fillna("").astype(str).str.strip().str.lower() != "seguimiento asignado"
        df2 = df[mask_tipo].copy()
    else:
        df2 = df.copy()

    if df2.empty:
        return "NO VISITADO"

    # buscar primera respuesta válida
    for _, r in df2.iterrows():
        resp = _norm_resp_asoc(r.get("respuesta"))
        if resp:
            return resp

    return "NO VISITADO"


# =========================
# DB: Usuarios
# =========================
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


# =========================
# DB: Seguimientos (asociaciones)
# =========================
def insert_seguimiento_asoc(payload: dict):
    _safe_insert("seguimientos_asociaciones", payload)


def get_casos_asignados_asoc(user):
    supabase = get_supabase()
    res = (
        supabase.table("seguimientos_asociaciones")
        .select("id, asociacion_id, assigned_to, created_by, fecha, estado, observaciones, creado_en")
        .eq("assigned_to", int(user["id"]))
        .neq("estado", "hecho")
        .neq("estado", "cancelado")
        .order("fecha", desc=False)
        .execute()
    )
    return res.data or []


def cerrar_seguimiento_asoc(seguimiento_id: int):
    supabase = get_supabase()
    supabase.table("seguimientos_asociaciones").update({"estado": "hecho"}).eq("id", int(seguimiento_id)).execute()

def get_usuarios_mapping_asoc():
    """Retorna un dict {id: username} de todos los usuarios para mostrar en el historial."""
    supabase = get_supabase()
    res = supabase.table("usuarios").select("id, username").execute()
    return {r["id"]: r["username"] for r in (res.data or [])}


# =========================
# UI: Casos asignados (ASOCIACIONES)
# =========================
def render_casos_asignados(user):
    st.markdown("### 📌 Mis casos asignados (Asociaciones)")

    casos = get_casos_asignados_asoc(user)
    if not casos:
        st.info("No tenés casos asignados.")
        return

    for c in casos:
        asoc = get_asociacion(c["asociacion_id"])
        if not asoc:
            titulo = f"Asociación ID {c.get('asociacion_id')} — objetivo {c.get('fecha','')}"
        else:
            titulo = f"{asoc.get('nombre','')} — objetivo {c.get('fecha','')}"

        with st.expander(titulo, expanded=False):
            st.write(f"**Observación:** {c.get('observaciones','')}")
            st.write(f"**Estado:** {c.get('estado','')}")
            st.write("---")

            st.markdown("### Cargar interacción por seguimiento")

            fecha = st.date_input("Fecha", value=datetime.date.today(), key=f"asoc_seg_fecha_{c['id']}")
            respuesta = st.selectbox("Feedback / Resultado", RESPUESTAS_ASOC, index=3, key=f"asoc_seg_resp_{c['id']}")
            medio = st.selectbox("Medio", MEDIOS, index=0, key=f"asoc_seg_medio_{c['id']}")

            para_que = st.text_input("Motivo / Para qué fui o contacté", value="", key=f"asoc_seg_para_{c['id']}")
            obs = st.text_area("Observaciones", value="", key=f"asoc_seg_obs_{c['id']}")

            if st.button("✅ Guardar interacción y cerrar seguimiento", key=f"asoc_seg_guardar_{c['id']}"):
                try:
                    insert_interaccion_asoc({
                        "asociacion_id": int(c["asociacion_id"]),
                        "fecha": str(fecha),
                        "respuesta": respuesta,  # ✅ esto SI tiene feedback y debe reflejar
                        "medio": medio,
                        "para_que_contacte": para_que,
                        "observaciones": obs,
                        "tipo": "seguimiento realizado",
                        "created_by": int(user["id"]),
                        "seguimiento_id": int(c["id"]),
                        "seguimiento_cerrado": True,
                    })
                    cerrar_seguimiento_asoc(int(c["id"]))
                    st.success("Interacción cargada y seguimiento cerrado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")


# =========================
# UI: Ficha asociación
# =========================
def render_ficha_asociacion(user, asoc_id: int):
    asoc = get_asociacion(asoc_id)
    if not asoc:
        st.warning("No se encontró la asociación.")
        return

    # ✅ fecha: último evento (incluye asignación de seguimiento)
    ultima_fecha_evento = get_ultima_fecha_evento_asoc(asoc_id)

    # ✅ feedback: última interacción REAL (ignora seguimiento asignado)
    ultimo_feedback = get_ultimo_feedback_real_asoc(asoc_id)

    # flags independientes por asociación
    edit_key = f"asoc_show_edit_{asoc_id}"
    int_key = f"asoc_show_int_{asoc_id}"
    seg_key = f"asoc_show_seg_{asoc_id}"

    if edit_key not in st.session_state:
        st.session_state[edit_key] = False
    if int_key not in st.session_state:
        st.session_state[int_key] = False
    if seg_key not in st.session_state:
        st.session_state[seg_key] = False

    st.markdown("## 📌 Ficha de asociación")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.write(f"**Nombre:** {asoc.get('nombre','')}")
        st.write(f"**Dirección:** {asoc.get('direccion','')}")
        st.write(f"**Comuna:** {asoc.get('comuna_id','')}")
        st.write(f"**Tipo:** {asoc.get('tipo','')}")
        st.write(f"**Referente:** {asoc.get('referente_nombre','')}")
        st.write(f"**Tel. referente:** {asoc.get('referente_telefono','')}")
    with c2:
        st.write("**Último evento (fecha):**")
        st.write(str(ultima_fecha_evento) if ultima_fecha_evento else "-")
        st.write("**Feedback (última interacción real):**")
        st.write(ultimo_feedback)

    st.markdown("---")

    # fila horizontal de botones
    b1, b2, b3 = st.columns(3)

    with b1:
        if st.button("✏️ Editar datos", use_container_width=True, key=f"btn_asoc_edit_{asoc_id}"):
            st.session_state[edit_key] = not st.session_state[edit_key]

    with b2:
        if st.button("📌 Cargar interacción", use_container_width=True, key=f"btn_asoc_int_{asoc_id}"):
            st.session_state[int_key] = not st.session_state[int_key]

    with b3:
        if st.button("🧭 Asignar seguimiento", use_container_width=True, key=f"btn_asoc_seg_{asoc_id}"):
            st.session_state[seg_key] = not st.session_state[seg_key]

    st.markdown("---")

    # =========================
    # 1) EDITAR DATOS
    # =========================
    if st.session_state[edit_key]:
        st.markdown("### ✏️ Editar datos de la asociación")

        nombre = st.text_input("Nombre", value=asoc.get("nombre") or "", key=f"ea_nombre_{asoc_id}")
        direccion = st.text_input("Dirección", value=asoc.get("direccion") or "", key=f"ea_dir_{asoc_id}")

        tipo_actual = (asoc.get("tipo") or "").strip()
        tipo_opts = [""] + TIPOS_ASOC
        tipo_index = tipo_opts.index(tipo_actual) if tipo_actual in tipo_opts else 0
        tipo = st.selectbox("Tipo", tipo_opts, index=tipo_index, key=f"ea_tipo_{asoc_id}")

        ref_nombre = st.text_input(
            "Referente (Nombre y apellido)",
            value=asoc.get("referente_nombre") or "",
            key=f"ea_refnom_{asoc_id}",
        )
        ref_tel = st.text_input(
            "Teléfono del referente",
            value=asoc.get("referente_telefono") or "",
            key=f"ea_reftel_{asoc_id}",
        )

        obs = st.text_area("Observaciones", value=asoc.get("observaciones") or "", key=f"ea_obs_{asoc_id}")

        regeo = st.checkbox("Recalcular lat/lon por dirección", value=False, key=f"ea_regeo_{asoc_id}")

        if st.button("💾 Guardar cambios", key=f"btn_save_asoc_{asoc_id}"):
            try:
                # Normalización automática si se cambió el texto
                dir_final = direccion.strip()
                lat_final = asoc.get("latitud")
                lon_final = asoc.get("longitud")

                # Si la dirección es distinta a la original, normalizamos y geocodificamos por defecto
                if dir_final != (asoc.get("direccion") or "").strip():
                    dir_norm, err = normalizar_domicilio_caba(dir_final)
                    if not err:
                        dir_final = dir_norm
                        # Forzamos geocodificación si la dirección cambió
                        lat_new, lon_new = geocodificar_con_reintentos(dir_final)
                        if lat_new:
                            lat_final, lon_final = lat_new, lon_new
                
                # O si el usuario marcó explícitamente recalcular
                elif regeo and dir_final:
                    lat_new, lon_new = geocodificar_con_reintentos(dir_final)
                    if lat_new:
                        lat_final, lon_final = lat_new, lon_new

                payload = {
                    "nombre": nombre.strip() if nombre else None,
                    "direccion": dir_final if dir_final else None,
                    "tipo": tipo.strip() if tipo else None,
                    "referente_nombre": ref_nombre.strip() if ref_nombre else None,
                    "referente_telefono": ref_tel.strip() if ref_tel else None,
                    "observaciones": obs.strip() if obs else None,
                    "latitud": lat_final,
                    "longitud": lon_final,
                }

                update_asociacion(asoc_id, payload)
                st.success("Asociación actualizada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

        st.markdown("---")

    # =========================
    # 2) CARGAR INTERACCIÓN
    # =========================
    if st.session_state[int_key]:
        st.markdown("### 📌 Cargar interacción")

        c3, c4, c5 = st.columns(3)
        with c3:
            fecha = st.date_input("Fecha", value=datetime.date.today(), key=f"asoc_int_fecha_{asoc_id}")
        with c4:
            respuesta = st.selectbox("Feedback / Resultado", RESPUESTAS_ASOC, index=3, key=f"asoc_int_resp_{asoc_id}")
        with c5:
            medio = st.selectbox("Medio", MEDIOS, index=0, key=f"asoc_int_medio_{asoc_id}")

        para_que = st.text_input("Motivo / Para qué fui o contacté", value="", key=f"asoc_int_para_{asoc_id}")
        observ = st.text_area("Observaciones", value="", key=f"asoc_int_obs_{asoc_id}")

        if st.button("✅ Guardar interacción", key=f"asoc_int_guardar_{asoc_id}"):
            try:
                insert_interaccion_asoc({
                    "asociacion_id": int(asoc_id),
                    "fecha": str(fecha),
                    "respuesta": respuesta,  # ✅ esto SI debe reflejar en historial y tabla
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

    # =========================
    # 3) ASIGNAR SEGUIMIENTO
    # =========================
    if st.session_state[seg_key]:
        st.markdown("### 🧭 Asignar seguimiento")

        usuarios = get_users_same_comuna(user)
        opciones = [(u["id"], u["username"]) for u in usuarios]
        if not opciones:
            st.info("No hay usuarios activos en tu comuna para asignar.")
        else:
            elegido = st.selectbox("Asignar a", opciones, format_func=lambda x: x[1], key=f"asoc_seg_asignar_a_{asoc_id}")
            fecha_obj = st.date_input("Fecha objetivo", value=datetime.date.today(), key=f"asoc_seg_fecha_obj_{asoc_id}")
            motivo = st.text_area("Observación / motivo", value="", key=f"asoc_seg_motivo_{asoc_id}")

            if st.button("📌 Confirmar asignación", key=f"asoc_seg_confirmar_{asoc_id}"):
                try:
                    insert_seguimiento_asoc({
                        "asociacion_id": int(asoc_id),
                        "assigned_to": int(elegido[0]),
                        "created_by": int(user["id"]),
                        "fecha": str(fecha_obj),
                        "estado": "pendiente",
                        "observaciones": motivo,
                        "creado_en": str(datetime.date.today()),
                    })

                    # ✅ log en historial: FECHA sí, FEEDBACK vacío (NO debe pisar la tabla)
                    insert_interaccion_asoc({
                        "asociacion_id": int(asoc_id),
                        "fecha": str(datetime.date.today()),
                        "respuesta": None,  # 👈 CLAVE: vacío
                        "medio": "Otro",
                        "para_que_contacte": "seguimiento asignado",
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

    # =========================
    # HISTORIAL (ordenado desc)
    # =========================
    st.markdown("## 🧾 Historial")
    hist = get_historial_asoc(asoc_id)
    if hist.empty:
        st.info("Sin historial todavía.")
        return

    hist = hist.copy()
    
    # Mapear usuario que cargó la interacción (created_by)
    user_map = get_usuarios_mapping_asoc()
    if "created_by" in hist.columns:
        hist["Usuario"] = hist["created_by"].map(user_map).fillna("Desconocido")

    if "tipo" in hist.columns:
        hist["tipo"] = hist["tipo"].fillna("").astype(str)

    # para que en la fila "seguimiento asignado" se vea vacío aunque venga como NaN
    if "respuesta" in hist.columns:
        def _resp_display(row):
            t = (row.get("tipo") or "").strip().lower()
            if t == "seguimiento asignado":
                return ""
            v = row.get("respuesta")
            return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
        hist["respuesta"] = hist.apply(_resp_display, axis=1)

    cols_show = [
        "fecha", "tipo", "Usuario", "respuesta", "medio", "para_que_contacte",
        "observaciones", "creado_en"
    ]
    cols_show = [c for c in cols_show if c in hist.columns or c == "Usuario"]
    st.dataframe(hist[cols_show], use_container_width=True)
