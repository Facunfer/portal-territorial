# usuarios_admin.py
import streamlit as st
import pandas as pd
import datetime
import bcrypt

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

from db import get_supabase
import permisos
import personas_scope_rules


def _hash_password(plain: str) -> str:
    """Genera un hash bcrypt para una contraseña en texto plano."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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


def _fetch_users_for_admin(user: dict) -> pd.DataFrame:
    supabase = get_supabase()

    cols = "id, username, tipo_usuario, ambito, vertical, rol, comuna_id, activo"
    q = supabase.table("usuarios").select(cols).order("id", desc=False)

    scope = permisos.users_scope(user)

    if scope.kind == "COMUNA":
        if user.get("comuna_id") is not None:
            q = q.eq("comuna_id", int(user["comuna_id"]))

    elif scope.kind == "USERS_VERTICAL":
        parts = (scope.value or "").split("|", 1)
        amb = parts[0].strip() if len(parts) > 0 else ""
        vert = parts[1].strip() if len(parts) > 1 else ""
        if amb:
            q = q.eq("ambito", amb)
        if vert:
            q = q.eq("vertical", vert)

    res = q.execute()
    return pd.DataFrame(res.data or [])


def _fetch_personas_for_comuna(user: dict, comuna_id: int) -> pd.DataFrame:
    supabase = get_supabase()
    cols = "id, nombre_apellido, telefono, barrio, comuna_id, tags, de_donde_salio"
    q = supabase.table("personas").select(cols)
    
    # Aplicar visibilidad
    q = personas_scope_rules.apply_personas_visibility_filter(q, user, force_filter=True)
    
    # Filtro específico de comuna
    q = q.eq("comuna_id", int(comuna_id))
    
    res = q.order("nombre_apellido", desc=False).execute()
    return pd.DataFrame(res.data or [])


def _fetch_asociaciones_for_comuna(comuna_id: int) -> pd.DataFrame:
    supabase = get_supabase()
    cols = "id, nombre, direccion, tipo, comuna_id, referente_nombre, referente_telefono"
    res = (
        supabase.table("asociaciones")
        .select(cols)
        .eq("comuna_id", int(comuna_id))
        .order("nombre", desc=False)
        .execute()
    )
    return pd.DataFrame(res.data or [])



def _fetch_personas_for_vertical(user: dict) -> pd.DataFrame:
    """
    Devuelve personas accesibles para una VERTICAL_PERSONAS.
    Usa la misma lógica que personas_app: filtra por TAG (case-insensitive) en Python,
    para que funcione si personas.tags es array o string.
    """
    scope = permisos.personas_scope(user)
    if (scope.kind or "").upper() != "TAG" or not scope.value:
        # si por alguna razón no hay tag, devolvemos vacío para ser seguros
        return pd.DataFrame([])

    tag_obj = str(scope.value).strip().upper()
    if not tag_obj:
        return pd.DataFrame([])

    allowed_tags = {t.strip() for t in tag_obj.split("|") if t.strip()}

    supabase = get_supabase()
    cols = "id, nombre_apellido, telefono, barrio, comuna_id, tags"
    q = supabase.table("personas").select(cols)

    # Aplicar visibilidad SENSIBLE
    q = personas_scope_rules.apply_personas_visibility_filter(q, user, force_filter=True)

    # paginado (por si hay muchas)
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

    # Filtrado por tag ya realizado server-side vía personas_scope_rules.apply_personas_visibility_filter
    pass

    # normalizar tags a string para UI
    if "tags" in df.columns:
        def _norm_tags(v):
            if isinstance(v, list):
                return ", ".join([str(t).strip() for t in v if str(t).strip()])
            return "" if v is None else str(v)
        df["tags"] = df["tags"].apply(_norm_tags)

    return df


def _fetch_asociaciones_for_vertical(user: dict) -> pd.DataFrame:
    """
    Devuelve asociaciones accesibles para una VERTICAL_ASOCIACIONES.
    Usa permisos.asociaciones_scope(user) -> kind=ASOC_TIPO y filtra por in_('tipo', ...).
    """
    scope = permisos.asociaciones_scope(user)
    if (scope.kind or "").upper() != "ASOC_TIPO" or not scope.value:
        return pd.DataFrame([])

    tipos_permitidos = [x.strip() for x in str(scope.value).split("|") if x.strip()]
    if not tipos_permitidos:
        return pd.DataFrame([])

    supabase = get_supabase()
    cols = "id, nombre, direccion, tipo, comuna_id, referente_nombre, referente_telefono"
    res = (
        supabase.table("asociaciones")
        .select(cols)
        .in_("tipo", tipos_permitidos)
        .order("nombre", desc=False)
        .execute()
    )
    return pd.DataFrame(res.data or [])


def _aggrid_multiselect(df: pd.DataFrame, key: str, height: int = 320):
    """Devuelve lista de dicts seleccionados (AgGrid).
    ✅ Compatible con selected_rows como list o DataFrame.
    ✅ Evita `DataFrame or []` (truth value ambiguous).
    """
    if df is None or df.empty:
        return []

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True, minWidth=140)
    
    # Habilitamos selección múltiple con checkbox
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    grid_options = gb.build()

    # PATCH: Habilitar "Seleccionar solo filtrados" en el header checkbox
    # Buscamos la columna que tiene el checkbox (usualmente la primera o configurada así)
    cols = grid_options.get("columnDefs", [])
    for col in cols:
        if col.get("checkboxSelection") or col.get("headerCheckboxSelection"):
            col["headerCheckboxSelectionFilteredOnly"] = True

    grid = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED | GridUpdateMode.MODEL_CHANGED,
        theme="alpine",
        enable_enterprise_modules=False,
        height=height,
        fit_columns_on_grid_load=True,
        localeText=LOCALE_ES,
        key=key,
    )

    sel = None

    # Caso 1: objeto AgGridReturn con atributo
    if hasattr(grid, "selected_rows"):
        sel = grid.selected_rows  # puede ser list o DataFrame o None

    # Caso 2: dict legacy
    elif isinstance(grid, dict):
        sel = grid.get("selected_rows", None)

    # Normalización segura
    if sel is None:
        return []

    if isinstance(sel, pd.DataFrame):
        return sel.to_dict("records")

    if isinstance(sel, list):
        return sel

    # fallback defensivo
    try:
        return list(sel)
    except Exception:
        return []


def _insert_asignaciones(usuario_id: int, personas_ids: list[int], asociaciones_ids: list[int]):
    """Inserta filas en usuarios_asignaciones.

    Requiere columnas:
      - usuario_id (int)
      - objeto_tipo (text) => 'PERSONA' / 'ASOCIACION'
      - objeto_id (int)
    """
    supabase = get_supabase()

    rows = []
    for pid in (personas_ids or []):
        rows.append({"usuario_id": int(usuario_id), "objeto_tipo": "PERSONA", "objeto_id": int(pid)})

    for aid in (asociaciones_ids or []):
        rows.append({"usuario_id": int(usuario_id), "objeto_tipo": "ASOCIACION", "objeto_id": int(aid)})

    if not rows:
        return

    supabase.table("usuarios_asignaciones").insert(rows).execute()


def _is_missing_es_original_error(exc: Exception) -> bool:
    msg = str(exc)
    return "es_original" in msg and ("schema cache" in msg or "does not exist" in msg or "column" in msg)


def _insert_usuario(payload: dict):
    supabase = get_supabase()
    try:
        return supabase.table("usuarios").insert(payload).execute()
    except Exception as exc:
        if not _is_missing_es_original_error(exc):
            raise
        payload_sin_original = dict(payload)
        payload_sin_original.pop("es_original", None)
        return supabase.table("usuarios").insert(payload_sin_original).execute()


def _delete_asignaciones(usuario_id: int, objeto_tipo: str, object_ids: list[int]):
    """Elimina asignaciones de un usuario y tipo específico."""
    if not object_ids:
        return
    supabase = get_supabase()
    (
        supabase.table("usuarios_asignaciones")
        .delete()
        .eq("usuario_id", int(usuario_id))
        .eq("objeto_tipo", objeto_tipo)
        .in_("objeto_id", object_ids)
        .execute()
    )



# ==============================================================================
# HELPERS: Semáforos y Feedback
# ==============================================================================

def _chunk_list(xs, size: int):
    xs = list(xs or [])
    for i in range(0, len(xs), size):
        yield xs[i:i + size]

def _semaforo_tiempo_label(ultima_fecha):
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

def _semaforo_respuesta_label(status):
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

def _norm_feedback(v):
    up = (v or "").strip().upper()
    allowed = ["POSITIVO", "NEUTRO", "NEGATIVO", "NO VISITADO"]
    return up if up in set(allowed) else "NO VISITADO"

def _fetch_interacciones_personas_resumen(p_ids: list[int]):
    """Devuelve dict: pid -> (fecha_dt, status_norm)"""
    if not p_ids:
        return {}
    supabase = get_supabase()
    rows = []
    # Chunking para no explotar URL
    for chunk in _chunk_list(p_ids, 200):
        page, page_size = 0, 1000
        while True:
            res = (
                supabase.table("interacciones_personas")
                .select("persona_id, fecha, respuesta")
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

    # Procesar
    resumen = {}
    from datetime import date
    # sort por fecha desc global
    rows_sorted = sorted(rows, key=lambda r: pd.to_datetime(r.get("fecha")) if r.get("fecha") else pd.NaT, reverse=True)
    
    seen = set()
    for r in rows_sorted:
        pid = r.get("persona_id")
        if pid in seen:
            continue
        seen.add(pid)
        
        rid = int(pid)
        fecha_raw = r.get("fecha")
        try:
            val_dt = pd.to_datetime(fecha_raw).date() if str(fecha_raw).strip() else None
        except:
            val_dt = None
            
        status = _semaforo_respuesta_label(r.get("respuesta"))
        resumen[rid] = (val_dt, status)
    return resumen

def _fetch_interacciones_asoc_resumen(a_ids: list[int]):
    """Devuelve dict: aid -> (fecha_dt, feedback_norm)"""
    if not a_ids:
        return {}
    supabase = get_supabase()

    # Chunking: .in_() con listas largas genera URLs > 2KB que PostgREST rechaza.
    # Paginación: garantiza traer todas las filas aunque superen el límite por defecto.
    chunk_size = 200
    rows = []
    for i in range(0, len(a_ids), chunk_size):
        chunk = a_ids[i:i + chunk_size]
        page = 0
        while True:
            res = (
                supabase.table("interacciones_asociaciones")
                .select("asociacion_id, fecha, respuesta, tipo")
                .in_("asociacion_id", chunk)
                .order("fecha", desc=True)
                .order("id", desc=True)
                .range(page * 1000, (page + 1) * 1000 - 1)
                .execute()
            )
            data = res.data or []
            rows.extend(data)
            if len(data) < 1000:
                break
            page += 1
    
    resumen = {}
    for r in rows:
        aid = int(r.get("asociacion_id"))
        if aid in resumen:
            continue
        
        resp_raw = (r.get("respuesta") or "").strip().upper()
        tipo = (r.get("tipo") or "").strip().lower()

        if tipo == "seguimiento asignado" and resp_raw == "":
            continue
        if resp_raw == "":
            continue
            
        fecha_raw = r.get("fecha")
        try:
            val_dt = pd.to_datetime(fecha_raw).date() if str(fecha_raw).strip() else None
        except:
            val_dt = None
        
        fb = _norm_feedback(resp_raw)
        resumen[aid] = (val_dt, fb)
        
    return resumen



def _fetch_asignaciones_detalle(usuario_id: int):
    """Obtiene DataFrames de Personas y Asociaciones asignadas a un usuario."""
    supabase = get_supabase()
    
    # 1. Obtener IDs de asignaciones
    res = (
        supabase.table("usuarios_asignaciones")
        .select("objeto_tipo, objeto_id")
        .eq("usuario_id", int(usuario_id))
        .execute()
    )
    asigs = res.data or []
    
    if not asigs:
        return pd.DataFrame(), pd.DataFrame()

    p_ids = [a["objeto_id"] for a in asigs if a["objeto_tipo"] == "PERSONA"]
    a_ids = [a["objeto_id"] for a in asigs if a["objeto_tipo"] == "ASOCIACION"]
    
    df_p = pd.DataFrame()
    df_a = pd.DataFrame()
    
    # 2. Fetch Personas
    if p_ids:
        rp = (
            supabase.table("personas")
            .select("id, nombre_apellido, barrio, tags, telefono")
            .in_("id", p_ids)
            .execute()
        )
        df_p = pd.DataFrame(rp.data or [])
        # Norm tags
        if not df_p.empty and "tags" in df_p.columns:
            df_p["tags"] = df_p["tags"].apply(
                lambda x: ", ".join([str(t) for t in x]) if isinstance(x, list) else str(x)
            )

    # 3. Fetch Asociaciones
    if a_ids:
        ra = (
            supabase.table("asociaciones")
            .select("id, nombre, tipo, direccion, referente_nombre")
            .in_("id", a_ids)
            .execute()
        )
        df_a = pd.DataFrame(ra.data or [])
        
    return df_p, df_a


    return final_map


def _fetch_all_assigned_users_details(object_type: str, object_ids: list[int]) -> dict:
    """
    Retorna {object_id: [ {username, rol, comuna_id, vertical}, ... ] }
    Para filtrar visualmente según quién esté mirando.
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


def _filter_assignments_by_context(assigned_users_list, viewer_user: dict):
    """
    Filtra la lista de usuarios asignados según el contexto del viewer.
    - Si viewer es ADMIN/GLOBAL: ve todo.
    - Si viewer es COMUNA X (rol Comuna o Extracto Comuna): solo ve asignados de Comuna X.
    - Si viewer es VERTICAL Y: solo ve asignados de Vertical Y.
    """
    if not assigned_users_list:
        return []
        
    v_rol = (viewer_user.get("rol") or "").strip().upper()
    v_comuna = viewer_user.get("comuna_id")
    v_vertical = (viewer_user.get("vertical") or "").strip().upper()
    
    # GLOBAL / ADMIN ve todo
    if v_rol in ["ADMIN", "GLOBAL", "SOPORTE"]:
        return [u.get("username") for u in assigned_users_list if u.get("username")]

    filtered = []
    for u in assigned_users_list:
        u_rol = (u.get("rol") or "").strip().upper()
        # Si el asignado es 'EXTRACTO' (caso mas comun), chequear su scope.
        # Si el asignado es otro rol, tambien chequeamos su scope.
        
        # Match Comuna
        # Si soy de Comuna, solo me importa gente de mi comuna (Extractos de mi comuna)
        if v_role_is_comuna(v_rol): # Helper implicito o check directo
             # Asumimos rol COMUNA o asignado a comuna?
             # Simplificacion: Si v_comuna coincide con u_comuna
             u_comuna = u.get("comuna_id")
             if v_comuna is not None and u_comuna == v_comuna:
                 filtered.append(u.get("username"))
                 
        # Match Vertical
        elif v_vertical:
             # Si soy de Vertical, solo gente de mi vertical
             u_vert = (u.get("vertical") or "").strip().upper()
             if u_vert == v_vertical:
                 filtered.append(u.get("username"))
        
        # Fallback: Si no soy Comuna ni Vertical definida (raro), muestro todo?
        # O si soy un Extracto viendo?
        else:
             # Default show all if no restriction found? Or Restricted?
             # User "head_juventud" has vertical='JUVENTUD'.
             # User "comuna 1" has comuna_id=1.
             # Si no machea nada, mostramos todo por seguridad o nada?
             # Mejor mostrar todo si no encajamos en logica estricta para no ocultar info critica,
             # PERO el user pidio filtrar.
             # Asumamos que si llegamos aca es porque no aplicó filtro estricto.
             filtered.append(u.get("username"))

    return sorted(filtered)

def v_role_is_comuna(rol):
    return rol in ["COMUNA", "REFERENTE_COMUNA", "RESPONSABLE_COMUNA", "EXTRACTO_COMUNA", "COMUNAL"]  # Ajustar segun roles reales
    # En usuarios_admin.py, usamos "COMUNA" como rol principal.
    # Pero cuidado, el usuario dijo "head_juventud".
    
# Mejor approach inline en la función para simplificar sin helpers externos
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
        
        # Logica:
        # Si viewer tiene Comuna definido (y no vertical, o prioridad comuna?):
        # Asumimos que si v_rol es "COMUNA" O tiene comuna_id y NO vertical: Scope Comuna.
        # Usuario "head_juventud": rol="VERTICAL"?, vertical="JUVENTUD".
        
        keep = False
        
        # Caso VERTICAL
        if v_vertical and v_vertical != "NONE":
            if u_vertical == v_vertical:
                keep = True
        
        # Caso COMUNA
        elif v_comuna is not None:
             if u_comuna == v_comuna:
                 keep = True
                 
        # Si no tengo scope definido (ej. usuario raro), muestro?
        # Mejor mostrar para no romper.
        else:
            keep = True
            
        if keep:
            res.append(uname)
            
    return sorted(res)



def _calc_estado_asignacion(asignado_str):
    if not asignado_str:
        return "No asignado"
    parts = [x for x in asignado_str.split(",") if x.strip()]
    c = len(parts)
    if c == 0:
        return "No asignado"
    if c == 1:
        return "1 asignado"
    if c == 2:
        return "2 asignados"
    return "+ de 2 asignados"


def _render_assignment_selector(viewer_user: dict, target_conf: dict, key_prefix: str):
    """
    Renderiza el UI para seleccionar asignaciones (Personas / Asociaciones)
    dependiendo del 'ambito' del usuario destino y los permisos del viewer (admin logueado).
    
    Returns:
       (personas_ids: list[int], asociaciones_ids: list[int])
    """
    p_ids_res = []
    a_ids_res = []
    
    ambito = target_conf.get("ambito")
    comuna_id = target_conf.get("comuna_id")
    # vertical no se usa mucho aun porque la logica de vertical va por el ambito "VERTICAL_X" pero por las dudas
    
    amb_up = (ambito or "").strip().upper()

    # ----------------------------------------------------
    # CASO 1: COMUNA
    # ----------------------------------------------------
    if amb_up == "COMUNA" and comuna_id is not None:
        tab_p, tab_a = st.tabs(["👤 Personas", "📍 Lugares (Asociaciones)"])

        # ----------- PERSONAS -----------
        with tab_p:
            dfp = _fetch_personas_for_comuna(viewer_user, int(comuna_id))
            if dfp.empty:
                st.info("No hay personas cargadas en esa comuna (o no tenés permiso para verlas).")
            else:
                df_show = dfp.copy()
                # Norm Tags
                if "tags" in df_show.columns:
                    def _norm_tags_list(x):
                        if isinstance(x, list):
                            return ",".join([str(t).strip() for t in x if str(t).strip()])
                        return str(x) if x else ""
                    df_show["tags"] = df_show["tags"].apply(_norm_tags_list)

                # Enriquecer (Semaforos + Asignados)
                pids = df_show["id"].tolist()
                res_sem = _fetch_interacciones_personas_resumen(pids)
                assigned_details_map = _fetch_all_assigned_users_details("PERSONA", pids)

                def _get_assigned_info_str(pid):
                    details = assigned_details_map.get(int(pid), [])
                    filtered_names = _get_filtered_usernames(details, viewer_user)
                    return ", ".join(filtered_names)

                def _get_sem_data(pid):
                    return res_sem.get(int(pid), (None, "⚫ NO CONTACTADO"))
                
                sem_cols = df_show["id"].apply(lambda x: pd.Series(_get_sem_data(x), index=["ultima_fecha_dt", "semaforo_respuesta"]))
                df_show["ultima_fecha_dt"] = sem_cols["ultima_fecha_dt"]
                df_show["semaforo_respuesta"] = sem_cols["semaforo_respuesta"]
                df_show["semaforo_tiempo"] = df_show["ultima_fecha_dt"].apply(_semaforo_tiempo_label)
                df_show["asignado_a"] = df_show["id"].apply(_get_assigned_info_str)
                df_show["estado_asignacion"] = df_show["asignado_a"].apply(_calc_estado_asignacion)
                
                # --- Filtros ---
                c_f1, c_f2 = st.columns(2)
                with c_f1:
                    all_tags = set()
                    for t_str in df_show["tags"].unique():
                        if t_str:
                            for t in t_str.split(","):
                                all_tags.add(t.strip())
                    sel_tags = st.multiselect("Tags", options=sorted(list(all_tags)), key=f"{key_prefix}_p_tags")
                    
                    sem_t_opts = sorted(df_show["semaforo_tiempo"].unique().tolist())
                    sel_sem_t = st.multiselect("Semáforo Tiempo", options=sem_t_opts, key=f"{key_prefix}_p_semt")

                with c_f2:
                    sem_r_opts = sorted(df_show["semaforo_respuesta"].unique().tolist())
                    sel_sem_r = st.multiselect("Semáforo Respuesta", options=sem_r_opts, key=f"{key_prefix}_p_semr")
                    
                    est_asign_opts = sorted(df_show["estado_asignacion"].unique().tolist())
                    sel_est_asign = st.multiselect("Estado Asignación", options=est_asign_opts, key=f"{key_prefix}_p_est_asign")

                if sel_tags:
                    def _match_tags(row_tags):
                        r_set = {x.strip() for x in row_tags.split(",")}
                        return all(s in r_set for s in sel_tags)
                    df_show = df_show[df_show["tags"].apply(_match_tags)]
                if sel_sem_t:
                    df_show = df_show[df_show["semaforo_tiempo"].isin(sel_sem_t)]
                if sel_sem_r:
                    df_show = df_show[df_show["semaforo_respuesta"].isin(sel_sem_r)]
                if sel_est_asign:
                     df_show = df_show[df_show["estado_asignacion"].isin(sel_est_asign)]

                cols_show = [c for c in ["id", "nombre_apellido", "telefono", "barrio", "tags", "semaforo_tiempo", "semaforo_respuesta", "asignado_a", "estado_asignacion"] if c in df_show.columns]
                df_show_view = df_show[cols_show].copy()
                
                st.info(f"Mostrando {len(df_show_view)} personas.")
                assign_all = st.checkbox(f"✅ Seleccionar TODAS ({len(df_show_view)})", value=False, key=f"{key_prefix}_p_all")
                
                if assign_all:
                     p_ids_res = [int(x) for x in df_show_view["id"].tolist()]
                     st.write(f"**{len(p_ids_res)} personas seleccionadas automáticamente.**")
                     # visual only
                     gb = GridOptionsBuilder.from_dataframe(df_show_view)
                     gb.configure_default_column(sortable=True, filter=True, resizable=True)
                     AgGrid(df_show_view, gridOptions=gb.build(), theme="alpine", height=250)
                else:
                     selected = _aggrid_multiselect(df_show_view, key=f"{key_prefix}_sel_p", height=250)
                     p_ids_res = [int(r.get("id")) for r in selected if r.get("id")]

        # ----------- ASOCIACIONES -----------
        with tab_a:
            dfa = _fetch_asociaciones_for_comuna(int(comuna_id))
            if dfa.empty:
                st.info("No hay asociaciones cargadas en esa comuna.")
            else:
                df_show_a = dfa.copy()
                aids = df_show_a["id"].tolist()
                res_fb = _fetch_interacciones_asoc_resumen(aids)
                assigned_details_map_a = _fetch_all_assigned_users_details("ASOCIACION", aids)

                def _get_fb_data(aid):
                    return res_fb.get(int(aid), (None, "NO VISITADO"))

                def _get_assigned_info_str_a(aid):
                    details = assigned_details_map_a.get(int(aid), [])
                    filtered_names = _get_filtered_usernames(details, viewer_user)
                    return ", ".join(filtered_names)

                fb_cols = df_show_a["id"].apply(lambda x: pd.Series(_get_fb_data(x), index=["ultima_fecha_dt", "feedback"]))
                df_show_a["feedback"] = fb_cols["feedback"]
                df_show_a["asignado_a"] = df_show_a["id"].apply(_get_assigned_info_str_a)
                df_show_a["estado_asignacion"] = df_show_a["asignado_a"].apply(_calc_estado_asignacion)
                
                c_fa1, c_fa2, c_fa3 = st.columns(3)
                with c_fa1:
                    tipos_asoc = sorted([x for x in df_show_a["tipo"].dropna().unique() if str(x).strip()])
                    sel_tipo = st.selectbox("Tipo", ["Todos"] + tipos_asoc, key=f"{key_prefix}_a_tipo")
                with c_fa2:
                    fb_opts = sorted(df_show_a["feedback"].unique().tolist())
                    sel_fb = st.multiselect("Feedback", options=fb_opts, key=f"{key_prefix}_a_fb")
                with c_fa3:
                    est_asign_opts = sorted(df_show_a["estado_asignacion"].unique().tolist())
                    sel_est_asign = st.multiselect("Estado Asignación", options=est_asign_opts, key=f"{key_prefix}_a_est_asign")
                
                if sel_tipo != "Todos":
                    df_show_a = df_show_a[df_show_a["tipo"] == sel_tipo]
                if sel_fb:
                    df_show_a = df_show_a[df_show_a["feedback"].isin(sel_fb)]
                if sel_est_asign:
                    df_show_a = df_show_a[df_show_a["estado_asignacion"].isin(sel_est_asign)]

                cols_show = [c for c in ["id", "nombre", "tipo", "direccion", "referente_nombre", "feedback", "asignado_a", "estado_asignacion"] if c in df_show_a.columns]
                df_show_view_a = df_show_a[cols_show].copy()
                
                st.info(f"Mostrando {len(df_show_view_a)} asociaciones.")
                assign_all_a = st.checkbox(f"✅ Seleccionar TODAS ({len(df_show_view_a)})", value=False, key=f"{key_prefix}_a_all")
                
                if assign_all_a:
                    a_ids_res = [int(x) for x in df_show_view_a["id"].tolist()]
                    st.write(f"**{len(a_ids_res)} lugares seleccionados automáticamente.**")
                    gb = GridOptionsBuilder.from_dataframe(df_show_view_a)
                    gb.configure_default_column(sortable=True, filter=True, resizable=True)
                    AgGrid(df_show_view_a, gridOptions=gb.build(), theme="alpine", height=250)
                else:
                    selected = _aggrid_multiselect(df_show_view_a, key=f"{key_prefix}_sel_asoc", height=250)
                    a_ids_res = [int(r.get("id")) for r in selected if r.get("id")]

    # ----------------------------------------------------
    # CASO 2: VERTICAL_PERSONAS
    # ----------------------------------------------------
    elif amb_up == "VERTICAL_PERSONAS":
        st.caption("Solo podés asignar **personas** dentro de tu vertical.")
        dfp = _fetch_personas_for_vertical(viewer_user) # OJO: ¿fetch basando en el viewer o en el target? 
        # Si el admin es Global, _fetch_personas_for_vertical(viewer_user) podria no traer nada si el viewer no tiene tag_config.
        # Pero si el viewer es Admin Global, deberia ver TODOs los tags? 
        # _fetch_personas_for_vertical usa 'permisos.personas_scope(user)' del viewer.
        # Si Admin Global asigna a user de "Mesa Joven", deberia ver personas de Mesa Joven.
        # Actualmente _fetch_personas_for_vertical solo funciona si el VIEWER tiene el scope configurado.
        # FIX: Si soy ADMIN, deberia poder ver lo que corresponde al TARGET. 
        # PERO, _fetch_personas_for_vertical está codeado contra 'user'.
        # Por ahora asumimos que quien crea el usuario (Viewer) tiene permisos o comparte scope. 
        # Si el Admin no tiene scope vertical, devolverá vacio. Esto es una limitación del helper actual.
        # Dejaremos así porque suele crear el Reference Master del area.
        
        if dfp.empty:
            st.info("No hay personas accesibles para tu vertical (o no tenés TAG configurado).")
        else:
            df_show = dfp.copy()
            if "tags" in df_show.columns:
                df_show["tags"] = df_show["tags"].astype(str)
                
            pids = df_show["id"].tolist()
            res_sem = _fetch_interacciones_personas_resumen(pids)
            assigned_details_map = _fetch_all_assigned_users_details("PERSONA", pids)

            def _get_sem_data_v(pid):
                return res_sem.get(int(pid), (None, "⚫ NO CONTACTADO"))
            
            sem_cols = df_show["id"].apply(lambda x: pd.Series(_get_sem_data_v(x), index=["ultima_fecha_dt", "semaforo_respuesta"]))
            df_show["semaforo_respuesta"] = sem_cols["semaforo_respuesta"]
            df_show["semaforo_tiempo"] = sem_cols["ultima_fecha_dt"].apply(_semaforo_tiempo_label)
            
            df_show["asignado_a"] = df_show["id"].apply(
                lambda x: ", ".join(_get_filtered_usernames(assigned_details_map.get(int(x), []), viewer_user))
            )
            df_show["estado_asignacion"] = df_show["asignado_a"].apply(_calc_estado_asignacion)

            # Filtros Vertical
            c_vert_1, c_vert_2 = st.columns(2)
            with c_vert_1:
                all_tags = set()
                for t_str in df_show["tags"].unique():
                    if t_str and t_str.lower() != "nan":
                        for t in t_str.split(","):
                            all_tags.add(t.strip())
                sel_tags = st.multiselect("Tags (extra)", options=sorted(list(all_tags)), key=f"{key_prefix}_vp_tags")
                sem_t_opts = sorted(df_show["semaforo_tiempo"].unique().tolist())
                sel_sem_t = st.multiselect("Semáforo Tiempo", options=sem_t_opts, key=f"{key_prefix}_vp_semt")

            with c_vert_2:
                sem_r_opts = sorted(df_show["semaforo_respuesta"].unique().tolist())
                sel_sem_r = st.multiselect("Semáforo Respuesta", options=sem_r_opts, key=f"{key_prefix}_vp_semr")
                est_asign_opts = sorted(df_show["estado_asignacion"].unique().tolist())
                sel_est_asign = st.multiselect("Estado Asignación", options=est_asign_opts, key=f"{key_prefix}_vp_est")

            if sel_tags:
                    def _match_tags_v(row_tags):
                        r_set = {x.strip() for x in row_tags.split(",")}
                        return all(s in r_set for s in sel_tags)
                    df_show = df_show[df_show["tags"].apply(_match_tags_v)]
            if sel_sem_t:
                df_show = df_show[df_show["semaforo_tiempo"].isin(sel_sem_t)]
            if sel_sem_r:
                df_show = df_show[df_show["semaforo_respuesta"].isin(sel_sem_r)]
            if sel_est_asign:
                df_show = df_show[df_show["estado_asignacion"].isin(sel_est_asign)]

            cols_show = [c for c in ["id", "nombre_apellido", "telefono", "barrio", "tags", "semaforo_tiempo", "semaforo_respuesta", "asignado_a", "estado_asignacion"] if c in df_show.columns]
            df_show_view = df_show[cols_show].copy()
            
            st.info(f"Mostrando {len(df_show_view)} personas.")
            assign_all_v = st.checkbox(f"✅ Seleccionar TODAS ({len(df_show_view)})", value=False, key=f"{key_prefix}_vp_all")
            
            if assign_all_v:
                    p_ids_res = [int(x) for x in df_show_view["id"].tolist()]
                    st.write(f"**{len(p_ids_res)} personas seleccionadas**")
                    gb = GridOptionsBuilder.from_dataframe(df_show_view)
                    gb.configure_default_column(sortable=True, filter=True, resizable=True)
                    AgGrid(df_show_view, gridOptions=gb.build(), theme="alpine", height=250)
            else:
                    selected = _aggrid_multiselect(df_show_view, key=f"{key_prefix}_sel_vp", height=340)
                    p_ids_res = [int(r.get("id")) for r in selected if r.get("id")]

    # ----------------------------------------------------
    # CASO 3: VERTICAL_ASOCIACIONES
    # ----------------------------------------------------
    elif amb_up == "VERTICAL_ASOCIACIONES":
        st.caption("Solo podés asignar **lugares/asociaciones** dentro de tu vertical.")
        dfa = _fetch_asociaciones_for_vertical(viewer_user)
        if dfa.empty:
            st.info("No hay asociaciones accesibles para tu vertical.")
        else:
            df_show_a = dfa.copy()
            aids = df_show_a["id"].tolist()
            res_fb = _fetch_interacciones_asoc_resumen(aids)
            assigned_details_map_a = _fetch_all_assigned_users_details("ASOCIACION", aids)

            def _get_fb_data_v(aid):
                return res_fb.get(int(aid), (None, "NO VISITADO"))
            fb_cols = df_show_a["id"].apply(lambda x: pd.Series(_get_fb_data_v(x), index=["ultima_fecha_dt", "feedback"]))
            df_show_a["feedback"] = fb_cols["feedback"]
            
            df_show_a["asignado_a"] = df_show_a["id"].apply(
                    lambda x: ", ".join(_get_filtered_usernames(assigned_details_map_a.get(int(x), []), viewer_user))
            )
            df_show_a["estado_asignacion"] = df_show_a["asignado_a"].apply(_calc_estado_asignacion)

            # Filtros
            c_fa1, c_fa2, c_fa3 = st.columns(3)
            with c_fa1:
                tipos_asoc = sorted([x for x in df_show_a["tipo"].dropna().unique() if str(x).strip()])
                sel_tipo = st.selectbox("Filtrar Tipo", ["Todos"] + tipos_asoc, key=f"{key_prefix}_va_tipo")
            with c_fa2:
                fb_opts = sorted(df_show_a["feedback"].unique().tolist())
                sel_fb = st.multiselect("Feedback", options=fb_opts, key=f"{key_prefix}_va_fb")
            with c_fa3:
                est_asign_opts = sorted(df_show_a["estado_asignacion"].unique().tolist())
                sel_est_asign = st.multiselect("Estado Asignación", options=est_asign_opts, key=f"{key_prefix}_va_est")

            if sel_tipo != "Todos":
                df_show_a = df_show_a[df_show_a["tipo"] == sel_tipo]
            if sel_fb:
                df_show_a = df_show_a[df_show_a["feedback"].isin(sel_fb)]
            if sel_est_asign:
                df_show_a = df_show_a[df_show_a["estado_asignacion"].isin(sel_est_asign)]

            cols_show = [c for c in ["id", "nombre", "tipo", "direccion", "referente_nombre", "feedback", "asignado_a", "estado_asignacion"] if c in df_show_a.columns]
            df_show_view_a = df_show_a[cols_show].copy()
            
            st.info(f"Mostrando {len(df_show_view_a)} asociaciones.")
            assign_all_va = st.checkbox(f"✅ Seleccionar TODAS ({len(df_show_view_a)})", value=False, key=f"{key_prefix}_va_all")
            
            if assign_all_va:
                a_ids_res = [int(x) for x in df_show_view_a["id"].tolist()]
                st.write(f"**{len(a_ids_res)} asociaciones seleccionadas**")
                gb = GridOptionsBuilder.from_dataframe(df_show_view_a)
                gb.configure_default_column(sortable=True, filter=True, resizable=True)
                AgGrid(df_show_view_a, gridOptions=gb.build(), theme="alpine", height=250)
            else:
                selected = _aggrid_multiselect(df_show_view_a, key=f"{key_prefix}_sel_va", height=250)
                a_ids_res = [int(r.get("id")) for r in selected if r.get("id")]
    
    else:
        st.info("Para asignar, el usuario destino debe ser COMUNA o VERTICAL, o no hay ámbito definido.")

    return p_ids_res, a_ids_res


def render(user: dict):
    if not permisos.can_manage_users(user):
        st.warning("No tenés permisos para administrar usuarios.")
        return

    st.header("Administración de usuarios")

    rules = permisos.creatable_roles(user)
    roles_permitidos = rules.get("roles_permitidos", []) or []

    # =========================
    # Ver usuarios existentes
    # =========================
    with st.expander("👀 Ver usuarios existentes", expanded=True):
        df = _fetch_users_for_admin(user)

        if df.empty:
            st.info("No hay usuarios para mostrar en tu ámbito.")
        else:
            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(sortable=True, filter=True, resizable=True, minWidth=140)
            gb.configure_selection(selection_mode="single", use_checkbox=True)
            grid_options = gb.build()

            sel_user_grid = AgGrid(
                df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                theme="alpine",
                enable_enterprise_modules=False,
                height=380,
                fit_columns_on_grid_load=True,
                localeText=LOCALE_ES,
                key="grid_existing_users"
            )

            # --- Detalle de asignaciones (si hay selección) ---
            selected_rows = sel_user_grid.get("selected_rows", [])
            # Compatibilidad versiones aggrid
            if isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict("records")
            elif not isinstance(selected_rows, list) and hasattr(sel_user_grid, "selected_rows"):
                 selected_rows = sel_user_grid.selected_rows
            
            # Defensive check
            if selected_rows and len(selected_rows) > 0:
                # Sometimes selected_rows is a list of dicts, sometimes just objects depending on version
                # Let's assume list of dicts or list of objects that behave like dicts
                try: 
                    sel_user = selected_rows[0]
                    # Check if it's a dict or object
                    if not isinstance(sel_user, dict):
                         # Try to convert if it's a legacy object (unlikely with this setup but safe)
                         sel_user = dict(sel_user)
                except:
                    sel_user = None

                if sel_user:
                    uid = sel_user.get("id")
                    u_rol = sel_user.get("rol")
                    u_user = sel_user.get("username")
                    
                    if uid:
                        st.info(f"Mostrando asignaciones para: **{u_user}** (Rol: {u_rol})")
                        
                        if (u_rol or "").upper() == "EXTRACTO":
                            df_p_asig, df_a_asig = _fetch_asignaciones_detalle(uid)
                            
                            t1, t2 = st.tabs([f"👤 Personas Asignadas ({len(df_p_asig)})", f"📍 Asociaciones Asignadas ({len(df_a_asig)})"])
                            
                            with t1:
                                if df_p_asig.empty:
                                    st.caption("No tiene personas asignadas.")
                                else:
                                    # Mostrar Grid Seleccionable
                                    cols_p = [c for c in ["id", "nombre_apellido", "barrio", "tags", "telefono"] if c in df_p_asig.columns]
                                    df_p_view = df_p_asig[cols_p]
                                    sel_p_del = _aggrid_multiselect(df_p_view, key=f"del_p_{uid}", height=300)
                                    
                                    if sel_p_del:
                                        if st.button(f"🗑️ Eliminar {len(sel_p_del)} Personas Asignadas", key=f"btn_del_p_{uid}"):
                                            ids_to_del = [int(r["id"]) for r in sel_p_del if r.get("id")]
                                            _delete_asignaciones(uid, "PERSONA", ids_to_del)
                                            st.success("Asignaciones eliminadas.")
                                            st.rerun()
                            
                            with t2:
                                if df_a_asig.empty:
                                    st.caption("No tiene asociaciones asignadas.")
                                else:
                                    # Mostrar Grid Seleccionable
                                    cols_a = [c for c in ["id", "nombre", "tipo", "direccion"] if c in df_a_asig.columns]
                                    df_a_view = df_a_asig[cols_a]
                                    sel_a_del = _aggrid_multiselect(df_a_view, key=f"del_a_{uid}", height=300)

                                    if sel_a_del:
                                        if st.button(f"🗑️ Eliminar {len(sel_a_del)} Asociaciones Asignadas", key=f"btn_del_a_{uid}"):
                                            ids_to_del = [int(r["id"]) for r in sel_a_del if r.get("id")]
                                            _delete_asignaciones(uid, "ASOCIACION", ids_to_del)
                                            st.success("Asignaciones eliminadas.")
                                            st.rerun()
                            st.markdown("---")
                            show_create_assign = st.checkbox("➕ Agregar asignaciones", value=False, key=f"chk_add_assign_{uid}")
                            if show_create_assign:
                                # Determinar scope destino basado en datos del usuario seleccionado
                                target_conf = {
                                    "ambito": sel_user.get("ambito"),
                                    "comuna_id": sel_user.get("comuna_id"),
                                    "vertical": sel_user.get("vertical")
                                }
                                
                                # Renderizar selector
                                p_add_ids, a_add_ids = _render_assignment_selector(user, target_conf, key_prefix=f"add_exist_{uid}")
                                
                                if p_add_ids or a_add_ids:
                                    st.info(f"Seleccionaste: {len(p_add_ids)} Personas y {len(a_add_ids)} Asociaciones nuevas.")
                                    if st.button("💾 Guardar asignaciones", key=f"btn_save_add_{uid}"):
                                        _insert_asignaciones(uid, p_add_ids, a_add_ids)
                                        st.success("Asignaciones agregadas con éxito.")
                                        st.rerun()

                        else:
                            st.caption("Este usuario no es EXTRACTO, por lo que ve todo según su Permiso (Comuna/Vertical). "
                                       "Las asignaciones puntuales solo aplican a rol EXTRACTO.")





    st.markdown("---")

    # =========================
    # Crear usuario
    # =========================
    with st.expander("➕ Crear nuevo usuario", expanded=True):
        if not roles_permitidos:
            st.error("Tu usuario no tiene permitido crear nuevos usuarios.")
            return

        c1, c2 = st.columns(2)

        with c1:
            username = st.text_input("Username *", value="", key="u_new_username")
            password = st.text_input("Password *", value="", type="password", key="u_new_password")
            # activo = st.checkbox("Activo", value=True, key="u_new_activo")
            activo = True

        with c2:
            ambito_fijo = rules.get("ambito_fijo")
            vertical_fijo = rules.get("vertical_fijo")
            comuna_fija = rules.get("comuna_fija")
            tipo_usuario_fijo = rules.get("tipo_usuario_fijo")

            if ambito_fijo:
                ambito = ambito_fijo
                st.text_input("Ámbito", value=ambito, disabled=True, key="u_new_ambito_disabled")
            else:
                ambito = st.selectbox(
                    "Ámbito",
                    ["GLOBAL", "COMUNA", "VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"],
                    key="u_new_ambito",
                )

            if vertical_fijo:
                vertical = vertical_fijo
                st.text_input("Vertical", value=vertical, disabled=True, key="u_new_vertical_disabled")
            else:
                ambito_actual = (ambito or "").strip().upper()
                if ambito_actual == "VERTICAL_PERSONAS":
                    opciones_vertical = [""] + sorted(permisos.VERT_PERSONAS)
                    vertical = st.selectbox("Vertical *", opciones_vertical, index=0, key="u_new_vertical")
                elif ambito_actual == "VERTICAL_ASOCIACIONES":
                    opciones_vertical = [""] + sorted(permisos.VERT_ASOC)
                    vertical = st.selectbox("Vertical *", opciones_vertical, index=0, key="u_new_vertical")
                else:
                    vertical = None

            if comuna_fija is not None:
                comuna_id = comuna_fija
                st.text_input("Comuna ID", value=str(comuna_id), disabled=True, key="u_new_comuna_disabled")
            else:
                comuna_txt = st.text_input("Comuna ID (si aplica)", value="", key="u_new_comuna")
                comuna_id = int(comuna_txt) if str(comuna_txt).strip().isdigit() else None

            rol = st.selectbox("Rol", roles_permitidos, index=0, key="u_new_rol")

            if tipo_usuario_fijo:
                tipo_usuario = tipo_usuario_fijo
                st.text_input("Tipo usuario", value=tipo_usuario, disabled=True, key="u_new_tipous_disabled")
            else:
                tipo_usuario = st.selectbox("Tipo usuario", ["MASTER", "REFERENTE"], index=0, key="u_new_tipous")

        # =========================
        # Asignaciones EXTRACTO (COMUNA / VERTICALES)
        # =========================
        personas_ids: list[int] = []
        asociaciones_ids: list[int] = []

        if (rol or "").strip().upper() == "EXTRACTO":
            st.markdown("### 🎯 Asignaciones para este usuario EXTRACTO")
            st.caption("Este usuario solo verá lo que le asignes acá.")

            target_conf_new = {
                "ambito": ambito,
                "comuna_id": comuna_id,
                "vertical": vertical
            }
            
            personas_ids, asociaciones_ids = _render_assignment_selector(user, target_conf_new, key_prefix="u_new_create")


        if st.button("✅ Crear usuario", key="u_new_create_btn"):
            if not username.strip() or not password.strip():
                st.error("Completá username y password.")
                return

            if len(password.strip()) < 6:
                st.error("La contraseña debe tener al menos 6 caracteres.")
                return

            payload = {
                "username": username.strip(),
                "password_hash": _hash_password(password.strip()),
                "activo": bool(activo),
                "ambito": (ambito or "").strip().upper() if ambito else None,
                "vertical": (vertical or "").strip().upper() if vertical else None,
                "rol": (rol or "").strip().upper() if rol else None,
                "tipo_usuario": (tipo_usuario or "").strip().upper() if tipo_usuario else None,
                "comuna_id": int(comuna_id) if comuna_id is not None else None,
                # Los usuarios creados desde UI nunca son originales; solo Supabase puede promoverlos.
                "es_original": False,
            }

            # reglas duras (igual a lo que venías usando)
            if payload["ambito"] == "COMUNA":
                payload["vertical"] = None
                payload["tipo_usuario"] = "REFERENTE"

            if payload["ambito"] in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
                payload["comuna_id"] = None
                payload["tipo_usuario"] = "MASTER"

            try:
                supabase = get_supabase()

                # evitar duplicados
                exists = (
                    supabase.table("usuarios")
                    .select("id")
                    .eq("username", payload["username"])
                    .limit(1)
                    .execute()
                )
                if exists.data:
                    st.error("Ya existe un usuario con ese username.")
                    return

                # 1) crear usuario
                ins = _insert_usuario(payload)

                # 2) recuperar id (si no vino en response, buscar por username)
                new_id = None
                if ins.data and isinstance(ins.data, list) and len(ins.data) > 0:
                    new_id = ins.data[0].get("id")

                if new_id is None:
                    lookup = (
                        supabase.table("usuarios")
                        .select("id")
                        .eq("username", payload["username"])
                        .limit(1)
                        .execute()
                    )
                    if lookup.data:
                        new_id = lookup.data[0].get("id")

                if new_id is None:
                    st.error("Se creó el usuario pero no pude recuperar su ID. Revisá la tabla usuarios.")
                    return

                # 3) guardar asignaciones si es EXTRACTO
                if (payload.get("rol") or "").upper() == "EXTRACTO":
                    try:
                        _insert_asignaciones(int(new_id), personas_ids, asociaciones_ids)
                        chk = (
                            supabase.table("usuarios_asignaciones")
                            .select("id", count="exact")
                            .eq("usuario_id", int(new_id))
                            .execute()
                        )
                        st.success(f"Usuario creado (id={new_id}) + asignaciones guardadas: {chk.count or 0}")
                    except Exception as e_asig:
                        st.warning(
                            "El usuario se creó, pero no pude guardar asignaciones en usuarios_asignaciones. "
                            f"Detalle: {e_asig}"
                        )
                else:
                    st.success(f"Usuario creado (id={new_id}).")

                st.rerun()

            except Exception as e:
                st.error(f"Error creando usuario: {e}")

    # =========================
    # Cambiar contraseña de un usuario existente
    # =========================
    st.markdown("---")
    with st.expander("🔑 Cambiar contraseña de usuario existente"):
        st.caption("Usá esto para resetear la contraseña de cualquier usuario de tu ámbito.")

        # Obtener lista de usuarios visibles
        try:
            supabase = get_supabase()
            u_list_res = supabase.table("usuarios").select("id, username, activo").order("username").execute()
            u_list = u_list_res.data or []
        except Exception as e:
            st.error(f"No se pudo cargar la lista de usuarios: {e}")
            u_list = []

        if u_list:
            opciones_u = {f"{u['username']} (id={u['id']}){'  🔴' if not u.get('activo') else ''}": u["id"] for u in u_list}
            u_selected_label = st.selectbox("Usuario", list(opciones_u.keys()), key="pw_change_user")
            u_selected_id = opciones_u[u_selected_label]

            col_pw1, col_pw2 = st.columns(2)
            with col_pw1:
                new_pw = st.text_input("Nueva contraseña", type="password", key="pw_change_new")
            with col_pw2:
                new_pw_confirm = st.text_input("Confirmar contraseña", type="password", key="pw_change_confirm")

            if st.button("💾 Guardar nueva contraseña", key="pw_change_btn"):
                if not new_pw.strip():
                    st.error("Ingresá la nueva contraseña.")
                elif len(new_pw.strip()) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                elif new_pw != new_pw_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        hashed = _hash_password(new_pw.strip())
                        supabase.table("usuarios").update(
                            {"password_hash": hashed}
                        ).eq("id", u_selected_id).execute()
                        st.success(f"Contraseña actualizada correctamente para '{u_selected_label.split(' (')[0]}'.")
                    except Exception as e:
                        st.error(f"Error al actualizar contraseña: {e}")
