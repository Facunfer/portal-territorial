# asociaciones_app.py
import streamlit as st
import pandas as pd
import requests
import datetime
import io

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from db import get_supabase
from permisos import allowed_modules
import asociaciones_edicion

# Mapa interactivo (click + tooltip)
try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except Exception:
    HAS_FOLIUM = False


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
    "noRowsToShow": "No hay filas para mostrar",
}


# =========================
# Opciones predefinidas
# =========================
TIPOS_ASOC = [
    "Local comercial",
    "Centros de Jubilados",
    "Clubes",
    "Espacios Culturales",
    "Espacios de Culto",
]

RESPUESTAS_ASOC = ["POSITIVO", "NEUTRO", "NEGATIVO", "NO VISITADO"]


# =========================
# Scope desde router
# =========================
def _get_scope_asoc():
    kind = st.session_state.get("PERM_ASOC_SCOPE_KIND") or "ALL"
    value = st.session_state.get("PERM_ASOC_SCOPE_VALUE")
    return (str(kind).upper(), value)



# =========================
# Asignaciones (EXTRACTO) - SOLO lo asignado
# =========================
def _is_extracto(user: dict) -> bool:
    return (str(user.get("rol") or "").strip().upper() == "EXTRACTO")


def _get_assigned_asoc_ids_via_usuarios_asignaciones(user: dict) -> list[int]:
    """Trae IDs de asociaciones asignadas al usuario desde `usuarios_asignaciones`."""
    try:
        uid = user.get("id")
        if uid is None:
            return []
        supabase = get_supabase()
        res = (
            supabase.table("usuarios_asignaciones")
            .select("objeto_id")
            .eq("usuario_id", int(uid))
            .eq("objeto_tipo", "ASOCIACION")
            .execute()
        )
        rows = res.data or []
        ids=[]
        for r in rows:
            oid = r.get("objeto_id")
            if oid is None:
                continue
            try:
                ids.append(int(oid))
            except Exception:
                pass
        # únicos
        seen=set(); out=[]
        for x in ids:
            if x not in seen:
                seen.add(x); out.append(x)
        return out
    except Exception:
        return []

# =========================
# Normalizador USIG (normalizar dirección)
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
            return None, "No se encontró una dirección válida en CABA."
        d0 = direcciones[0]
        dir_norm = _texto_desde_obj_direccion(d0)
        if not dir_norm:
            return None, "No se pudo interpretar la dirección."
        return dir_norm, None
    except Exception as e:
        return None, f"Error al normalizar: {e}"


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
    # El orden prioriza 'normalizar' porque ya sabemos que ese dominio responde JSON
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
        },
        {
            "url": "http://usig.buenosaires.gob.ar/servicios/geocodar",
            "params": {"direccion": direccion_normalizada},
            "headers": {"User-Agent": "Mozilla/5.0"}
        }
    ]

    for it in intentos:
        try:
            resp = requests.get(it["url"], params=it["params"], headers=it["headers"], timeout=5)
            
            # Si responde HTML, es una redirección al mapa, no nos sirve
            if "text/html" in resp.headers.get("Content-Type", "").lower():
                continue
            if "<!doctype html" in resp.text.lower()[:200]:
                continue
                
            data = resp.json()

            # Caso 1: Estructura de 'normalizar' (lista de direcciones)
            # data suele ser {"direccionesNormalizadas": [...]} o {"direcciones_normalizadas": [...]} o una lista [...]
            direcciones = []
            if isinstance(data, list):
                direcciones = data
            elif isinstance(data, dict):
                direcciones = data.get("direccionesNormalizadas") or data.get("direcciones_normalizadas") or data.get("direcciones") or []

            for d in direcciones:
                if isinstance(d, dict):
                    # El normalizar devuelve x e y (long/lat)
                    # A menudo están dentro de un objeto "coordenadas"
                    coords = d.get("coordenadas")
                    if isinstance(coords, dict):
                        x = coords.get("x")
                        y = coords.get("y")
                    else:
                        x = d.get("x")
                        y = d.get("y")

                    if x and y:
                        try:
                            fx, fy = float(x), float(y)
                            # Si son coordenadas WGS84 (lat/lon estándar)
                            if -60 < fy < -10 and -70 < fx < -30: 
                                return fy, fx
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
# Helpers feedback/colores
# =========================
def _norm_feedback(v):
    up = (v or "").strip().upper()
    return up if up in set(RESPUESTAS_ASOC) else "NO VISITADO"


def _color_por_feedback(fb: str):
    fb = _norm_feedback(fb)
    if fb == "POSITIVO":
        return "green"
    if fb == "NEUTRO":
        return "orange"
    if fb == "NEGATIVO":
        return "red"
    return "black"


# =========================
# Seguridad dura: quién puede entrar
# =========================
def _tiene_permiso_modulo_asoc(user: dict) -> bool:
    return "Asociaciones" in allowed_modules(user)


# =========================
# Data: asociaciones
# =========================
def get_asociaciones_for_user(user):
    supabase = get_supabase()
    cols = (
        "id, nombre, direccion, comuna_id, tipo, observaciones, "
        "latitud, longitud, referente_nombre, referente_telefono"
    )
    q = supabase.table("asociaciones").select(cols)

    # scope desde router (PERM_ASOC_SCOPE_KIND / VALUE)
    scope_kind, scope_value = _get_scope_asoc()

    # 0) EXTRACTO: ver SOLO lo asignado (ignora scope general)
    if _is_extracto(user):
        ids = _get_assigned_asoc_ids_via_usuarios_asignaciones(user)
        if not ids:
            return pd.DataFrame([])

        rows = []
        def _chunk(xs, n=200):
            xs=list(xs)
            for i in range(0, len(xs), n):
                yield xs[i:i+n]

        for ch in _chunk(ids, 200):
            page, page_size = 0, 1000
            while True:
                res = (
                    supabase.table("asociaciones")
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

        return pd.DataFrame(rows)


    # 1) COMUNA: filtrar por comuna_id
    tipo_user = (user.get("tipo_usuario") or "").strip().upper()
    if scope_kind == "COMUNA" or tipo_user in ["REFERENTE", "REFERENTE_MASTER", "REFERENTE_EXTRACTO"]:
        if user.get("comuna_id") is not None:
            q = q.eq("comuna_id", int(user["comuna_id"]))

    # 2) VERTICAL ASOCIACIONES: filtrar por "tipo" permitido según vertical
    if scope_kind == "ASOC_TIPO" and scope_value:
        raw = str(scope_value)

        # CLUBES llega desde permisos.py como ASOC_TIPO -> "Clubes"; esta query alimenta tabla, filtros, CSV y mapa.
        # puede venir tipo "Centros de Jubilados|Clubes|Espacios Culturales"
        # o puede venir uno solo tipo "Local comercial"
        tipos_permitidos = [x.strip() for x in raw.split("|") if x.strip()]

        # Normalización defensiva: "Local comercial " (con espacio) => "Local comercial"
        tipos_permitidos = [t.strip() for t in tipos_permitidos if t.strip()]

        if tipos_permitidos:
            q = q.in_("tipo", tipos_permitidos)
        else:
            return pd.DataFrame([])

    # res = q.execute()  <-- LIMITADO A 1000 por defecto
    # fetch all manual
    rows_all = []
    page = 0
    page_size = 1000
    while True:
        # .range() es inclusivo en start y end
        r = q.range(page*page_size, (page+1)*page_size - 1).execute()
        d = r.data or []
        rows_all.extend(d)
        if len(d) < page_size:
            break
        page += 1

    return pd.DataFrame(rows_all)


def get_ultimas_interacciones_asoc(asoc_ids):
    """
    Devuelve dict:
      asoc_id -> (fecha_dt_or_None, respuesta_norm, created_by_id)
    Importante: solo toma como "feedback" la última interacción que tenga respuesta válida.
       Si la fila es de "seguimiento asignado" y viene sin respuesta, no pisa el feedback.
    """
    if not asoc_ids:
        return {}

    supabase = get_supabase()
    q = (
        supabase.table("interacciones_asociaciones")
        .select("asociacion_id, fecha, respuesta, tipo, created_by")
        .in_("asociacion_id", [int(x) for x in asoc_ids])
        .order("fecha", desc=True)
    )

    # Ultima fecha: una sola carga paginada para las asociaciones visibles, sin query por asociacion.
    rows, page = [], 0
    page_size = 1000
    while True:
        res = q.range(page * page_size, (page + 1) * page_size - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        page += 1

    resumen = {}
    if rows:
        df_int = pd.DataFrame(rows)
        df_int["respuesta_limpia"] = df_int["respuesta"].fillna("").astype(str).str.strip()
        df_int["fecha_dt"] = pd.to_datetime(df_int["fecha"], errors="coerce")
        df_int["asociacion_id_int"] = pd.to_numeric(df_int["asociacion_id"], errors="coerce")

        # Se excluyen respuestas NULL/vacias para que seguimientos asignados no contaminen la ultima fecha.
        df_validas = df_int[
            (df_int["respuesta_limpia"] != "")
            & df_int["fecha_dt"].notna()
            & df_int["asociacion_id_int"].notna()
        ].copy()

        if not df_validas.empty:
            df_validas["asociacion_id_int"] = df_validas["asociacion_id_int"].astype(int)
            idx_ultimas = df_validas.groupby("asociacion_id_int")["fecha_dt"].idxmax()
            ultimas = df_validas.loc[idx_ultimas]
            for _, r in ultimas.iterrows():
                aid = int(r["asociacion_id_int"])
                resumen[aid] = (
                    r["fecha_dt"].date(),
                    _norm_feedback(r["respuesta_limpia"]),
                    r.get("created_by"),
                )

    for aid in asoc_ids:
        if int(aid) not in resumen:
            resumen[int(aid)] = (None, "NO VISITADO", None)

    return resumen


def _format_fecha_ddmmyyyy(value):
    if value is None or pd.isna(value):
        return "-"
    try:
        return pd.to_datetime(value).strftime("%d/%m/%Y")
    except Exception:
        return "-"


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
# UI principal
# =========================
def asociaciones_screen():
    user = st.session_state["user"]

    # ✅ bloqueo duro
    if not _tiene_permiso_modulo_asoc(user):
        st.error("No tenés permisos para acceder al módulo Asociaciones.")
        st.stop()

    st.header("Asociaciones")

    if "show_new_asoc" not in st.session_state:
        st.session_state["show_new_asoc"] = False
    if "selected_asoc_id" not in st.session_state:
        st.session_state["selected_asoc_id"] = None
    if "asoc_ficha_abierta" not in st.session_state:
        st.session_state["asoc_ficha_abierta"] = True
    if "show_csv_asoc" not in st.session_state:
        st.session_state["show_csv_asoc"] = False
    if "csv_asoc_paso" not in st.session_state:
        st.session_state["csv_asoc_paso"] = 1

    # Determinar si puede cargar CSV
    _rol_usr_asoc = (user.get("rol") or "").strip().upper()
    _puede_csv_asoc = _rol_usr_asoc in ["MASTER", "CABEZA"] and "Asociaciones" in allowed_modules(user)

    # =========================
    # Botones de acción
    # =========================
    if _puede_csv_asoc:
        cbtn, cbtn_csv, _ = st.columns([1, 1, 5])
    else:
        cbtn, _ = st.columns([1, 6])
    with cbtn:
        if st.button("➕ Agregar asociación"):
            st.session_state["show_new_asoc"] = not st.session_state["show_new_asoc"]
            st.session_state["show_csv_asoc"] = False
    if _puede_csv_asoc:
        with cbtn_csv:
            if st.button("📄 Cargar CSV masivo"):
                st.session_state["show_csv_asoc"] = not st.session_state["show_csv_asoc"]
                st.session_state["show_new_asoc"] = False
                st.session_state["csv_asoc_paso"] = 1

    # =========================
    # Carga masiva CSV asociaciones
    # =========================
    if _puede_csv_asoc and st.session_state["show_csv_asoc"]:
        st.markdown("### 📄 Carga masiva de Asociaciones por CSV")
        _TIPOS_VALIDOS = ["Centro de Jubilados", "Clubes", "Espacios Culturales", "Espacios de Culto", "Local comercial"]

        # -----------------------------------------------
        st.markdown("### Paso 1 — Descargar plantilla para normalizar direcciones")
        # -----------------------------------------------
        st.info(
            "Completá la plantilla con los datos crudos. "
            "En el **Paso 2** el sistema normalizará las direcciones automáticamente."
        )
        _tmpl_norm_df = pd.DataFrame(columns=["Nombre", "Tipo", "Comuna", "Direccion_Original", "Direccion_Normalizada"])
        st.download_button(
            "📥 Descargar plantilla para normalización",
            data=_tmpl_norm_df.to_csv(index=False).encode("utf-8"),
            file_name="plantilla_normalizacion_asociaciones.csv",
            mime="text/csv",
            key="dl_tmpl_norm",
        )
        st.caption(f"Tipos válidos: {', '.join(_TIPOS_VALIDOS)}")

        st.markdown("---")
        # -----------------------------------------------
        st.markdown("### Paso 2 — Subir plantilla y normalizar direcciones")
        # -----------------------------------------------
        st.info(
            "Subí la plantilla completada (con **Direccion_Normalizada** vacía). "
            "El sistema rellenará esa columna y te dará el archivo listo para el Paso 3."
        )
        _norm_file = st.file_uploader(
            "Subir plantilla del Paso 1",
            type=["csv"],
            key="csv_norm_uploader_asoc",
        )
        if _norm_file is not None:
            try:
                _df_norm = pd.read_csv(_norm_file)
                _df_norm.columns = [str(c).strip() for c in _df_norm.columns]

                # Asegurarse de que existe la columna de salida
                if "Direccion_Original" not in _df_norm.columns:
                    st.error("La plantilla no tiene la columna 'Direccion_Original'.")
                else:
                    st.write(f"Filas a procesar: {len(_df_norm)}")
                    if st.button("⚙️ Normalizar direcciones", key="btn_normalizar_asoc"):
                        _progreso_norm = st.progress(0)
                        _resultados_norm = []
                        for _i, _row in _df_norm.iterrows():
                            _dir_orig = str(_row.get("Direccion_Original", "")).strip()
                            if _dir_orig:
                                _dir_n, _ = normalizar_domicilio_caba(_dir_orig)
                                _resultados_norm.append(_dir_n or _dir_orig)
                            else:
                                _resultados_norm.append("")
                            _progreso_norm.progress((_i + 1) / len(_df_norm))

                        _df_norm["Direccion_Normalizada"] = _resultados_norm
                        _csv_norm_out = _df_norm.to_csv(index=False).encode("utf-8")
                        st.success("¡Normalización completada! Descargá el archivo, revisalo y usalo en el Paso 3.")
                        st.download_button(
                            "📥 Descargar archivo normalizado",
                            data=_csv_norm_out,
                            file_name="asociaciones_normalizadas.csv",
                            mime="text/csv",
                            key="dl_norm_result",
                        )
            except Exception as _e:
                st.error(f"Error al procesar el archivo: {_e}")

        st.markdown("---")
        # -----------------------------------------------
        st.markdown("### Paso 3 — Subir CSV final e importar")
        # -----------------------------------------------
        st.info(
            "Subí el CSV final con las columnas obligatorias: "
            "**Nombre**, **Tipo**, **Direccion**, **Comuna**."
        )
        _final_file = st.file_uploader(
            "Subir CSV final",
            type=["csv"],
            key="csv_final_uploader_asoc",
        )
        if _final_file is not None:
            try:
                _df_final = pd.read_csv(_final_file)
                _df_final.columns = [str(c).strip() for c in _df_final.columns]

                # Mapeo tolerante de columnas
                _asoc_col_alias = {
                    "NOMBRE": "Nombre",
                    "TIPO": "Tipo",
                    "DIRECCION": "Direccion",
                    "DIRECCIÓN": "Direccion",
                    "DIRECCION_NORMALIZADA": "Direccion",
                    "DIRECCIÓN_NORMALIZADA": "Direccion",
                    "COMUNA": "Comuna",
                }
                _df_final = _df_final.rename(
                    columns={c: _asoc_col_alias.get(c.upper(), c) for c in _df_final.columns}
                )

                _req_final = ["Nombre", "Tipo", "Direccion", "Comuna"]
                _miss_final = [c for c in _req_final if c not in _df_final.columns]
                if _miss_final:
                    st.error(f"Faltan columnas obligatorias: {', '.join(_miss_final)}")
                else:
                    st.write(f"**Vista previa ({min(5, len(_df_final))} filas):**")
                    st.dataframe(_df_final.head(5), use_container_width=True)

                    if st.button("✅ Procesar e importar", key="btn_import_asoc"):
                        _supabase = get_supabase()
                        _exitosos_asoc, _errores_asoc = 0, []
                        _prog_asoc = st.progress(0)
                        _total_asoc = len(_df_final)

                        for _idx, _row in _df_final.iterrows():
                            try:
                                _nombre = str(_row.get("Nombre", "")).strip()
                                _tipo = str(_row.get("Tipo", "")).strip()
                                _dir = str(_row.get("Direccion", "")).strip()
                                _com_raw = _row.get("Comuna")

                                if not _nombre or not _tipo or not _dir:
                                    _errores_asoc.append(f"Fila {_idx + 2}: Nombre, Tipo y Dirección son obligatorios.")
                                    continue

                                if _tipo not in _TIPOS_VALIDOS:
                                    _errores_asoc.append(
                                        f"Fila {_idx + 2}: Tipo '{_tipo}' no válido. "
                                        f"Usar uno de: {', '.join(_TIPOS_VALIDOS)}"
                                    )
                                    continue

                                # Determinar comuna_id
                                if (user.get("ambito") or "").strip().upper() == "COMUNA":
                                    _com_id = int(user.get("comuna_id") or 1)
                                else:
                                    try:
                                        _com_id = int(float(str(_com_raw).strip()))
                                    except Exception:
                                        _errores_asoc.append(f"Fila {_idx + 2}: Comuna inválida ('{_com_raw}').")
                                        continue

                                # Geocodificar
                                _lat, _lon = geocodificar_con_reintentos(_dir)

                                _supabase.table("asociaciones").insert({
                                    "nombre": _nombre,
                                    "tipo": _tipo,
                                    "direccion": _dir,
                                    "comuna_id": _com_id,
                                    "latitud": _lat,
                                    "longitud": _lon,
                                }).execute()
                                _exitosos_asoc += 1
                            except Exception as _e:
                                _errores_asoc.append(f"Fila {_idx + 2}: {_e}")

                            _prog_asoc.progress((_idx + 1) / _total_asoc)

                        st.success(f"Finalizado. ✅ Insertadas: {_exitosos_asoc} | ❌ Errores: {len(_errores_asoc)}")
                        if _errores_asoc:
                            with st.expander("Ver detalle de errores"):
                                for _err in _errores_asoc:
                                    st.caption(_err)
                        if _exitosos_asoc > 0:
                            st.session_state["show_csv_asoc"] = False
                            st.rerun()
            except Exception as _e:
                st.error(f"Error al procesar el archivo: {_e}")

        st.markdown("---")

    # =========================
    # Alta asociación
    # =========================
    if st.session_state["show_new_asoc"]:
        st.markdown("### ➕ Nueva asociación")
        supabase = get_supabase()
        # Alta manual: asociaciones.comuna_id es NOT NULL; verticales/global deben elegir comuna.
        tipo_user = (user.get("tipo_usuario") or "").strip().upper()
        scope_kind_form, _ = _get_scope_asoc()
        tiene_comuna_fija = (
            scope_kind_form == "COMUNA"
            or tipo_user in ["REFERENTE", "REFERENTE_MASTER", "REFERENTE_EXTRACTO"]
        )
        comuna_fija = int(user.get("comuna_id") or 1) if tiene_comuna_fija else None

        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Nombre *", value="", key="na_nombre")
            direccion = st.text_input("Dirección (CABA, normalizada) *", value="", key="na_dir")

            dir_sel = None
            if len(direccion.strip()) >= 3:
                sug = sugerir_direcciones_caba(direccion)
                if sug:
                    dir_sel = st.selectbox("Sugerencias", ["(Usar texto)"] + sug, index=0, key="na_dir_sug")

            tipo = st.selectbox("Tipo", [""] + TIPOS_ASOC, index=0, key="na_tipo")

        with c2:
            ref_nombre = st.text_input("Referente (Nombre y apellido)", value="", key="na_ref_nom")
            ref_tel = st.text_input("Teléfono del referente", value="", key="na_ref_tel")
            observaciones = st.text_area("Observaciones", value="", key="na_obs")
            if comuna_fija is not None:
                st.selectbox("Comuna *", list(range(1, 16)), index=max(0, comuna_fija - 1), disabled=True, key="na_comuna_fija")
                comuna_seleccionada = comuna_fija
            else:
                # Verticales como CCAA/CLUBES necesitan comuna explicita para cumplir el NOT NULL de Supabase.
                comuna_seleccionada = st.selectbox("Comuna *", ["Seleccionar"] + list(range(1, 16)), index=0, key="na_comuna")

        cg1, cg2 = st.columns(2)
        with cg1:
            guardar = st.button("Guardar nueva asociación", key="na_guardar")
        with cg2:
            cancelar = st.button("Cancelar", key="na_cancelar")

        if cancelar:
            st.session_state["show_new_asoc"] = False
            st.rerun()


        if guardar:
            if not nombre.strip() or not direccion.strip():
                st.error("Completá nombre y dirección.")
            elif comuna_fija is None and comuna_seleccionada == "Seleccionar":
                st.error("Seleccioná una comuna.")
            else:
                try:
                    if dir_sel and dir_sel != "(Usar texto)":
                        dir_normalizada = dir_sel
                        err = None
                    else:
                        dir_normalizada, err = normalizar_domicilio_caba(direccion)

                    if err:
                        st.error(err)
                        st.stop()

                    lat, lon = geocodificar_con_reintentos(dir_normalizada)

                    data = {
                        "nombre": nombre.strip(),
                        "direccion": dir_normalizada,
                        "tipo": tipo.strip() if tipo else None,
                        "observaciones": observaciones.strip() if observaciones else None,
                        "referente_nombre": ref_nombre.strip() if ref_nombre else None,
                        "referente_telefono": ref_tel.strip() if ref_tel else None,
                        "latitud": float(lat) if lat is not None else None,
                        "longitud": float(lon) if lon is not None else None,
                        "comuna_id": int(comuna_seleccionada),
                    }

                    supabase.table("asociaciones").insert(data).execute()

                    st.success("Asociación creada.")
                    st.session_state["show_new_asoc"] = False
                    st.session_state["selected_asoc_id"] = None
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        st.markdown("---")

    # =========================
    # Cargar tabla + feedback/fecha_visita
    # =========================
    df = get_asociaciones_for_user(user)
    if df.empty:
        st.info("No hay asociaciones para mostrar.")
        return

    asoc_ids = df["id"].astype(int).tolist()
    resumen_int = get_ultimas_interacciones_asoc(asoc_ids)
    
    # Mapeo de usuarios para "Cargado por"
    user_map = asociaciones_edicion.get_usuarios_mapping_asoc()

    # Ultima interaccion: se une por id en pandas luego de calcular MAX(fecha) valida por asociacion.
    df_resumen_int = pd.DataFrame(
        [
            {
                "id": int(aid),
                "ultima_fecha": data[0],
                "ultimo_feedback": data[1],
                "ultima_created_by": data[2],
            }
            for aid, data in resumen_int.items()
        ]
    )
    df = df.merge(df_resumen_int, on="id", how="left")
    df["ultimo_feedback"] = df["ultimo_feedback"].fillna("NO VISITADO")
    df["cargado_por"] = df["ultima_created_by"].apply(
        lambda uid: user_map.get(uid, "Desconocido") if pd.notna(uid) and uid else "Desconocido"
    )
    df.drop(columns=["ultima_created_by"], inplace=True, errors="ignore")

    # Asignados
    assigned_details_map = _fetch_all_assigned_users_details("ASOCIACION", asoc_ids)
    user_session = st.session_state["user"]
    
    df["asignado_a"] = df["id"].apply(
        lambda x: ", ".join(_get_filtered_usernames(assigned_details_map.get(int(x), []), user_session))
    )
    df["estado_asignacion"] = df["asignado_a"].apply(_calc_estado_asignacion)

    # =========================
    # Filtros (arriba del mapa)
    # =========================
    st.markdown("### 🔎 Filtros del mapa")

    with st.container(border=True):
        # Row 1: Tipo, Feedback, Estado Asignacion, COMUNA (Vertical)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            tipos_asoc = sorted([x for x in df["tipo"].dropna().unique() if str(x).strip()])
            sel_tipo = st.selectbox("Tipo", ["Todos"] + tipos_asoc, key="flt_a_tipo")
        
        with c2:
            fb_vals = sorted(df["ultimo_feedback"].unique().tolist())
            sel_fb = st.selectbox("Feedback", ["Todos"] + fb_vals, index=0, key="asoc_flt_fb")
            
        with c3:
            est_asign_opts = sorted(df["estado_asignacion"].unique().tolist())
            sel_est_asign = st.selectbox("Estado Asignación", ["Todos"] + est_asign_opts, key="flt_a_est_asign")

        with c4:
             # NUEVO: Filtro Comuna (Solo si es Vertical/Global)
             # Chequeamos si el user NO está restringido a comuna ya.
             scope_kind, _ = _get_scope_asoc()
             filter_comuna_asoc = None
             
             # Si es Global (ALL) o Vertical (ASOC_TIPO), mostramos filtro de comunas completo (1..15)
             if scope_kind in ["ALL", "ASOC_TIPO"]:
                  comunas_disp = list(range(1, 16))
                  filter_comuna_asoc = st.selectbox("Comuna", ["Todas"] + comunas_disp, index=0, key="flt_asoc_comuna_v")
             else:
                  # Si es COMUNA, ver si hay algo más complejo (ej. referente extracto), pero por lo general está fijo.
                  # Si el DF trae > 1 comuna (raro si es scope Comuna, pero posible si es Referente con varias comunas manualmente asignadas?)
                  # Por seguridad, si el df tiene > 1 comuna, mostramos
                  c_in_df = sorted(df["comuna_id"].dropna().unique().astype(int).tolist())
                  if len(c_in_df) > 1:
                       filter_comuna_asoc = st.selectbox("Comuna", ["Todas"] + c_in_df, index=0, key="flt_asoc_comuna_v_dynamic")
                  else:
                       st.write("") # placeholder

        from constants import BARRIOS_POR_COMUNA

        # Construir opciones de barrio basado en lo disponible en el DF + Info de Comuna
        barrios_disponibles_df = set(df['barrio'].unique()) if 'barrio' in df.columns else set()
        # Eliminar nulos
        barrios_disponibles_df = {b for b in barrios_disponibles_df if b}

        # Lógica de filtrado de BARRIOS x COMUNA seleccionada
        comunas_para_barrios = comunas_presentes = df['comuna_id'].dropna().unique()
        
        if filter_comuna_asoc and filter_comuna_asoc != "Todas":
             comunas_para_barrios = [int(filter_comuna_asoc)]
             barrios_disponibles_df = set() # reset para filtrar

        # Si el usuario tiene scope comuna o el DF es monocomuna, sumamos los de la estructura oficial
        for c in comunas_para_barrios:
            try:
                for b in BARRIOS_POR_COMUNA.get(int(c), []):
                    barrios_disponibles_df.add(b)
            except: pass
        
        # Agregar los existentes en la data
        if filter_comuna_asoc and filter_comuna_asoc != "Todas":
             if "barrio" in df.columns:
                 bs_data = df[df["comuna_id"] == int(filter_comuna_asoc)]["barrio"].unique()
                 for b in bs_data: 
                     if b: barrios_disponibles_df.add(b)
        else:
             if "barrio" in df.columns:
                 for b in df["barrio"].unique():
                     if b: barrios_disponibles_df.add(b)

        barrios_opciones = sorted(list(barrios_disponibles_df))
        if barrios_opciones:
             sel_barrios = st.multiselect("Filtrar por Barrio", options=barrios_opciones, default=[], key="flt_asoc_barrio")
        else:
             sel_barrios = []

        # Row 2: Fecha Rango + filtros de referente + Limpiar
        c_fecha, c_ref_nom, c_ref_tel, c_limpiar = st.columns([2, 1, 1, 1])
        with c_fecha:
            fechas_validas = [d for d in df["ultima_fecha"].tolist() if isinstance(d, datetime.date)]
            if fechas_validas:
                min_d, max_d = min(fechas_validas), max(fechas_validas)
                if "asoc_flt_rango" not in st.session_state:
                    st.session_state["asoc_flt_rango"] = (min_d, max_d)
                
                rango = st.date_input("Fecha de visita (rango)", key="asoc_flt_rango")
                if isinstance(rango, tuple) and len(rango) == 2:
                    flt_desde, flt_hasta = rango
                else:
                    flt_desde, flt_hasta = min_d, max_d
                
                # Checkbox para incluir vacíos
                incluir_sin_fecha = st.checkbox("Incluir sin fecha", value=True, key="asoc_inc_sin_fecha")
            else:
                st.caption("Fecha de visita: sin datos")
                flt_desde, flt_hasta = None, None
                incluir_sin_fecha = True

        with c_ref_nom:
            st.write("") # spacer
            solo_ref_nombre = st.checkbox("Solo con referente nombre", key="asoc_solo_ref_nombre")

        with c_ref_tel:
            st.write("") # spacer
            solo_ref_tel = st.checkbox("Solo con referente teléfono", key="asoc_solo_ref_tel")

        with c_limpiar:
            st.write("") # spacer
            st.write("") # spacer
            def _limpiar_filtros_asoc():
                for k in [
                    "flt_a_tipo", "asoc_flt_fb", "flt_a_est_asign", "asoc_flt_rango",
                    "asoc_inc_sin_fecha", "asoc_solo_ref_nombre", "asoc_solo_ref_tel"
                ]:
                    if k in st.session_state:
                         del st.session_state[k]
                st.rerun()
            st.button("🧹 Limpiar Filtros", use_container_width=True, on_click=_limpiar_filtros_asoc, key="btn_clr_a")


    # Aplicar filtros del mapa a un DF "base"
    df_base = df.copy()

    # 1) Tipo
    if sel_tipo != "Todos":
        df_base = df_base[df_base["tipo"].fillna("").astype(str) == sel_tipo]
    
    # 2) Feedback
    if sel_fb != "Todos":
        df_base = df_base[df_base["ultimo_feedback"] == sel_fb]
        
    # 3) Estado Asignación
    if sel_est_asign != "Todos":
        df_base = df_base[df_base["estado_asignacion"] == sel_est_asign]

    # 4) Barrio (Nuevo)
    if sel_barrios:
        if "barrio" in df_base.columns:
            df_base = df_base[df_base["barrio"].isin(sel_barrios)]

    # 5) Comuna Vertical
    if filter_comuna_asoc and filter_comuna_asoc != "Todas":
        df_base = df_base[df_base["comuna_id"] == int(filter_comuna_asoc)]

    # 6) Referentes: capa adicional sobre el dataframe ya filtrado por scope.
    if solo_ref_nombre and "referente_nombre" in df_base.columns:
        df_base = df_base[df_base["referente_nombre"].fillna("").astype(str).str.strip() != ""]
    if solo_ref_tel and "referente_telefono" in df_base.columns:
        df_base = df_base[df_base["referente_telefono"].fillna("").astype(str).str.strip() != ""]

    # 7) Fecha Rango
    if flt_desde and flt_hasta and fechas_validas:
        # Lógica: (fecha in range) OR (fecha is null AND incluir_sin_fecha)
        fecha_series = pd.to_datetime(df_base["ultima_fecha"], errors="coerce").dt.date
        mask_rango = (fecha_series >= flt_desde) & (fecha_series <= flt_hasta)
        if incluir_sin_fecha:
            mask_final = mask_rango | fecha_series.isna()
        else:
            mask_final = mask_rango
        
        df_base = df_base[mask_final]

    # =========================
    # KPIs + acciones de mapa
    # =========================
    def _kpi_count(label):
        if df_base.empty:
            return 0
        return int((df_base["ultimo_feedback"] == label).sum())

    k_total = int(len(df_base))
    k_pos = _kpi_count("POSITIVO")
    k_neu = _kpi_count("NEUTRO")
    k_neg = _kpi_count("NEGATIVO")
    k_nov = _kpi_count("NO VISITADO")

    st.markdown("### 🗺️ Mapa y Gestión")

    with st.container(border=True):
        a1, a2, a3, a4, a5, a6, a7 = st.columns([1.2, 1, 1, 1, 1.4, 1.2, 1.6])
        with a1:
            st.metric("Total", k_total)
        with a2:
            st.metric("🟢 Pos", k_pos)
        with a3:
            st.metric("🟡 Neu", k_neu)
        with a4:
            st.metric("🔴 Neg", k_neg)
        with a5:
            st.metric("⚫ No visitado", k_nov)
        
        with a6:
            st.write("") # spacer
            # Exportar CSV aquí
            csv = df_base.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 CSV",
                data=csv,
                file_name=f"asociaciones_{datetime.date.today()}.csv",
                mime="text/csv",
                key="btn_desc_asoc_csv_top",
                help="Descargar tabla filtrada"
            )
            
        with a7:
            st.write("") # spacer
            if st.button("🗺️ Reset Mapa", use_container_width=True, key="btn_asoc_reset_sel"):
                st.session_state["selected_asoc_id"] = None
                st.session_state["asoc_ficha_abierta"] = True
                st.rerun()

    # =========================
    # Selección desde el MAPA
    # =========================
    selected_id = st.session_state.get("selected_asoc_id")
    df_map = df_base.copy()

    if selected_id:
        df_map = df_map[df_map["id"].astype(int) == int(selected_id)]

    df_map = df_map.dropna(subset=["latitud", "longitud"])
    df_map = df_map[df_map["latitud"].astype(str).str.strip() != ""]
    df_map = df_map[df_map["longitud"].astype(str).str.strip() != ""]

    # =========================
    # Render mapa
    # =========================
    if not HAS_FOLIUM:
        st.warning("Para mapa con click/tooltip instalá: pip install streamlit-folium folium")
        if df_map.empty:
            st.info("No hay coordenadas (latitud/longitud) para mapear.")
        else:
            df_map_plot = df_map.rename(columns={"latitud": "lat", "longitud": "lon"})
            st.map(df_map_plot[["lat", "lon"]])
    else:
        if df_map.empty:
            st.info("No hay coordenadas (latitud/longitud) para mapear con esos filtros.")
        else:
            try:
                center_lat = float(df_map["latitud"].astype(float).mean())
                center_lon = float(df_map["longitud"].astype(float).mean())
            except Exception:
                center_lat, center_lon = -34.6037, -58.3816

            m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)

            for _, row in df_map.iterrows():
                aid = int(row.get("id"))
                nombre = (row.get("nombre") or "").strip()
                direccion = (row.get("direccion") or "").strip()
                tipo = (row.get("tipo") or "").strip()
                ref_nom = (row.get("referente_nombre") or "").strip()
                ref_tel = (row.get("referente_telefono") or "").strip()
                fb = _norm_feedback(row.get("ultimo_feedback"))
                fecha_val = row.get("ultima_fecha")
                fecha_fmt = _format_fecha_ddmmyyyy(fecha_val)
                fecha = fecha_fmt if fecha_fmt != "-" else ""

                tooltip_html = f"""
                <div style="font-size:12px;">
                  <b>{nombre}</b><br/>
                  📍 {direccion}<br/>
                  🧾 Tipo: {tipo or "-"}<br/>
                  👤 Ref: {ref_nom or "-"}<br/>
                  📞 {ref_tel or "-"}<br/>
                  ✅ {fb} {("— " + fecha) if fecha else ""}
                </div>
                """

                color = _color_por_feedback(fb)

                folium.CircleMarker(
                    location=[float(row["latitud"]), float(row["longitud"])],
                    radius=4,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.9,
                    tooltip=folium.Tooltip(tooltip_html, sticky=True),
                    popup=str(aid),
                ).add_to(m)

            map_out = st_folium(m, height=520, width=None)

            try:
                popup = map_out.get("last_object_clicked_popup", None)
                if popup:
                    aid_clicked = int(str(popup).strip())
                    if st.session_state.get("selected_asoc_id") != aid_clicked:
                        st.session_state["selected_asoc_id"] = aid_clicked
                        st.session_state["asoc_ficha_abierta"] = True
                        st.rerun()
            except Exception:
                pass

    st.markdown("---")

    # =========================
    # TABLA (si hay selección, filtra tabla)
    # =========================
    df_table = df_base.copy()
    if st.session_state.get("selected_asoc_id"):
        df_table = df_table[df_table["id"].astype(int) == int(st.session_state["selected_asoc_id"])]

    columnas = [
        "id",
        "nombre",
        "direccion",
        "comuna_id",
        "tipo",
        "referente_nombre",
        "referente_telefono",
        "ultimo_feedback",
        "ultima_fecha",
        "cargado_por",
        "observaciones",
        "latitud",
        "longitud",
        "asignado_a",
        "estado_asignacion",
    ]
    columnas = [c for c in columnas if c in df_table.columns]
    df_show = df_table[columnas].copy()
    if "ultima_fecha" in df_show.columns:
        # Tabla principal: muestra DD/MM/YYYY sin cambiar el valor fecha usado por los filtros.
        df_show["ultima_fecha"] = df_show["ultima_fecha"].apply(_format_fecha_ddmmyyyy)

    gb = GridOptionsBuilder.from_dataframe(df_show)
    gb.configure_default_column(sortable=True, filter=True, resizable=True, minWidth=140, wrapText=True, autoHeight=True)
    
    gb.configure_column("id", headerName="ID", width=100)
    gb.configure_column("ultima_fecha", headerName="Última fecha")
    gb.configure_column("ultimo_feedback", headerName="Resultado")
    gb.configure_column("cargado_por", headerName="Interacción por")
    gb.configure_column("asignado_a", headerName="Asignado a")

    gb.configure_selection(selection_mode="single", use_checkbox=False)
    grid_options = gb.build()

    # Botón exportar CSV
    csv = df_show.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        "📥 Descargar CSV",
        data=csv,
        file_name=f"asociaciones_filtradas_{datetime.date.today()}.csv",
        mime="text/csv",
        key="btn_desc_asoc_csv"
    )

    grid_response = AgGrid(
        df_show,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        theme="alpine",
        enable_enterprise_modules=False,
        height=520,
        fit_columns_on_grid_load=False,
        localeText=LOCALE_ES,
    )

    selected_rows = grid_response.get("selected_rows", None)
    selected = None
    if isinstance(selected_rows, list) and len(selected_rows) > 0:
        selected = selected_rows[0]
    elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
        selected = selected_rows.iloc[0].to_dict()

    if selected is not None and selected.get("id") is not None:
        st.session_state["selected_asoc_id"] = int(selected["id"])
        st.session_state["asoc_ficha_abierta"] = True

    st.markdown("---")

    # =========================
    # Casos asignados debajo de tabla (toggle)
    # =========================
    if "show_casos_asoc" not in st.session_state:
        st.session_state["show_casos_asoc"] = False

    ccas, _ = st.columns([1, 6])
    with ccas:
        if st.button("📌 Ver mis casos asignados", use_container_width=True, key="btn_toggle_casos_asoc"):
            st.session_state["show_casos_asoc"] = not st.session_state["show_casos_asoc"]

    if st.session_state["show_casos_asoc"]:
        asociaciones_edicion.render_casos_asignados(user)

    st.markdown("---")

    # =========================
    # Ficha (si hay seleccionado)
    # =========================
    if st.session_state.get("selected_asoc_id") and st.session_state.get("asoc_ficha_abierta", True):
        asociaciones_edicion.render_ficha_asociacion(
            user,
            int(st.session_state["selected_asoc_id"]),
        )
