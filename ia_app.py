
import streamlit as st
import pandas as pd
import datetime
import re
from supabase import create_client, Client
import plotly.express as px

# Reuse existing scope rules
import personas_scope_rules
import permisos

# =========================
# CONFIG / CONSTANTS
# =========================
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)

POS_SET = {"positiva", "positivo", "interesado", "ok", "si", "muy interesado", "verde"}

# =========================
# CATALOG: CONSULTATION TOOLS
# =========================
CONSULTATION_TOOLS = {
    "LIST_PERSONAS_CONTACTADAS": {
        "label": "Personas Contactadas hace poco",
        "params": [{"name": "days", "type": "int", "default": 7, "label": "Días atrás"}],
        "desc": "Personas con interacción en los últimos X días."
    },
    "LIST_PERSONAS_SIN_CONTACTO": {
        "label": "Personas NO Contactadas hace tiempo",
        "params": [{"name": "days", "type": "int", "default": 30, "label": "Días sin contacto"}],
        "desc": "Personas visibles sin interacción en los últimos X días."
    },
    "LIST_ASOC_RESPUESTA_POSITIVA": {
        "label": "Asociaciones con Respuesta Positiva",
        "params": [],
        "desc": "Asociaciones cuya última interacción fue evaluada como positiva."
    },
    "LIST_ASOC_POS_SIN_CONTACTO": {
        "label": "Asoc. Positivas SIN visita reciente",
        "params": [{"name": "days", "type": "int", "default": 30, "label": "Días sin visita"}],
        "desc": "Asociaciones positivas que no visitamos hace X días."
    },
    "LIST_PERSONAS_SIN_ASIGNAR": {
        "label": "Personas SIN usuario asignado",
        "params": [],
        "desc": "Personas en tu scope que no tienen nadie asignado en 'usuarios_asignaciones'."
    },
    "LIST_ASOC_SIN_ASIGNAR": {
        "label": "Asociaciones SIN usuario asignado",
        "params": [],
        "desc": "Asociaciones en tu scope que no tienen nadie asignado."
    },
     "LIST_ASOC_SIN_VISITA": {
        "label": "Asociaciones (general) sin visita",
        "params": [{"name": "days", "type": "int", "default": 60, "label": "Días sin visita"}],
        "desc": "Cualquier asociación visible sin visita en X días."
    },
    "LIST_REUNION_ASISTENTES": {
        "label": "Personas que asistieron a reunión",
        "params": [{"name": "days", "type": "int", "default": 30, "label": "Días atrás"}],
        "desc": "Personas que participaron de reuniones recientes."
    },
    "LIST_PERSONAS_POS_SIN_CONTACTO": {
        "label": "Personas Positivas SIN contacto",
        "params": [{"name": "days", "type": "int", "default": 30, "label": "Días sin contacto"}],
        "desc": "Personas (Semaforo Verde/Positivo) sin interacción reciente."
    }
}

# =========================
# HELPERS: SCOPE
# =========================
def _get_scope_asoc():
    kind = st.session_state.get("PERM_ASOC_SCOPE_KIND") or "ALL"
    value = st.session_state.get("PERM_ASOC_SCOPE_VALUE")
    return (str(kind).upper(), value)

def apply_asociaciones_visibility_filter(query, user_ctx: dict):
    scope_kind, scope_value = _get_scope_asoc()
    
    if user_ctx.get("rol") == "EXTRACTO":
        supabase = get_supabase()
        res = supabase.table("usuarios_asignaciones").select("objeto_id").eq("usuario_id", user_ctx["id"]).eq("objeto_tipo", "ASOCIACION").execute()
        assigned_ids = [r["objeto_id"] for r in res.data or []]
        if not assigned_ids: return query.eq("id", -1) 
        return query.in_("id", assigned_ids)

    tipo_user = (user_ctx.get("tipo_usuario") or "").strip().upper()
    if scope_kind == "COMUNA" or tipo_user in ["REFERENTE", "REFERENTE_MASTER", "REFERENTE_EXTRACTO"]:
        if user_ctx.get("comuna_id") is not None:
             query = query.eq("comuna_id", int(user_ctx["comuna_id"]))

    if scope_kind == "ASOC_TIPO" and scope_value:
        raw = str(scope_value)
        tipos = [x.strip() for x in raw.split("|") if x.strip()]
        if tipos: query = query.in_("tipo", tipos)
        else: return query.eq("id", -1)

    return query

def get_visible_personas_query(user_ctx):
    supabase = get_supabase()
    q = supabase.table("personas").select("id, nombre_apellido, telefono, email, comuna_id, barrio, tags")
    return personas_scope_rules.apply_personas_visibility_filter(q, user_ctx)


def get_visible_asociaciones_query(user_ctx):
    supabase = get_supabase()
    q = supabase.table("asociaciones").select("id, nombre, direccion, referente_nombre, referente_telefono, tipo, comuna_id")
    return apply_asociaciones_visibility_filter(q, user_ctx)

# =========================
# LOGIC: DATA FETCHERS
# =========================
def fetch_asociaciones_con_respuesta_positiva(user_ctx):
    """Retorna DF de asoc visibles con ultima respuesta positiva."""
    sb = get_supabase()
    q_a = get_visible_asociaciones_query(user_ctx)
    
    # FETCH ALL IDS (Pagination loop to avoid limits if needed, but for Asoc usually < 5000 is ok. 
    # Current limit is default 1000. Let's bump to 5000 safety.)
    df_a = pd.DataFrame(q_a.limit(5000).execute().data or [])
    if df_a.empty: return pd.DataFrame()
    
    aids = df_a["id"].tolist()
    
    # 2. Interacciones
    res_i = sb.table("interacciones_asociaciones").select("asociacion_id, fecha, respuesta").in_("asociacion_id", aids).order("fecha", desc=True).execute()
    data_i = res_i.data or []
    last_int_map = {} 
    
    for row in data_i:
        aid = row["asociacion_id"]
        if aid not in last_int_map:
            last_int_map[aid] = row
            
    final_rows = []
    for index, row in df_a.iterrows():
        aid = row["id"]
        if aid in last_int_map:
            last = last_int_map[aid]
            resp = (last.get("respuesta") or "").strip().lower()
            if resp in POS_SET:
                r_copy = row.to_dict()
                r_copy["ultima_interaccion"] = last["fecha"]
                r_copy["estado_respuesta"] = last.get("respuesta")
                r_copy["motivo"] = "Respuesta Positiva"
                final_rows.append(r_copy)
                
    return pd.DataFrame(final_rows)

def fetch_unassigned_objects(user_ctx, obj_type="PERSONA"):
    """
    Trae TODOS los IDs visibles y resta los asignados.
    Evita limit(2000) haciendo fetch paginado de IDs.
    """
    sb = get_supabase()
    
    # 1. Fetch ALL Visible IDs
    ids_visibles = []
    
    if obj_type == "PERSONA":
        # Only select ID to be fast
        q = get_supabase().table("personas").select("id")
        q = personas_scope_rules.apply_personas_visibility_filter(q, user_ctx)
    else:
        q = get_supabase().table("asociaciones").select("id")
        q = apply_asociaciones_visibility_filter(q, user_ctx)
        
    # Paginación manual para traer todo
    page_size = 1000
    current_page = 0
    while True:
        r = q.range(current_page * page_size, (current_page + 1) * page_size - 1).execute()
        d = r.data or []
        if not d: break
        ids_visibles.extend([x["id"] for x in d])
        if len(d) < page_size: break
        current_page += 1
        
    if not ids_visibles: return pd.DataFrame()
    
    # 2. Fetch Assigned IDs relating to these objects
    # Warning: .in_() might fail if thousands of IDs. 
    # Better strategy: Fetch ALL assignments of this Type, then set difference in Python.
    # Assignments table is usually smaller than Personas, or manageable.
    
    db_type = "ASOCIACION" if obj_type == "ASOCIACION" else "PERSONA"
    
    # Fetch all assignments of this type (global or scoped by user? 
    # If I am Master of Comuna 1, I only care about if SOMEONE is assigned, not if I am.
    # So we check global assignments table for these object IDs.
    
    ids_asignados = set()
    
    # Chunking input IN clause
    chunk_sz = 200 # Safe for URL length
    
    # Convert list to unique set for query efficiency (though input logic handles it)
    ids_visibles = list(set(ids_visibles))
    
    for i in range(0, len(ids_visibles), chunk_sz):
        chunk = ids_visibles[i:i+chunk_sz]
        res_asig = sb.table("usuarios_asignaciones").select("objeto_id").eq("objeto_tipo", db_type).in_("objeto_id", chunk).execute()
        if res_asig.data:
            for x in res_asig.data:
                ids_asignados.add(x["objeto_id"])
                
    # 3. Diff
    unassigned_ids = [x for x in ids_visibles if x not in ids_asignados]
    
    if not unassigned_ids: return pd.DataFrame()
    
    # 4. Fetch Details for unassigned (Paginated or limit for display?)
    # User complains about limits. Let's return full DF.
    # Re-fetch details for these specific IDs
    
    final_data = []
    
    # Chunk fetch details
    cols = "id, nombre_apellido, telefono, email, comuna_id, barrio" if obj_type == "PERSONA" else "id, nombre, direccion, tipo, comuna_id"
    table = "personas" if obj_type == "PERSONA" else "asociaciones"
    
    for i in range(0, len(unassigned_ids), chunk_sz):
        chunk = unassigned_ids[i:i+chunk_sz]
        res = sb.table(table).select(cols).in_("id", chunk).execute()
        if res.data:
            final_data.extend(res.data)
            
    df_res = pd.DataFrame(final_data)
    if not df_res.empty:
        df_res["motivo"] = f"Sin usuario asignado ({obj_type})"
        
    return df_res

# =========================
# TOOL HANDLER
# =========================
def execute_tool(user_ctx, tool_id, params):
    sb = get_supabase()
    days = params.get("days", 30)
    limit_date = datetime.date.today() - datetime.timedelta(days=days)
    
    if tool_id == "LIST_PERSONAS_CONTACTADAS":
        q_p = get_visible_personas_query(user_ctx)
        res_i = sb.table("interacciones_personas").select("persona_id, fecha").gte("fecha", str(limit_date)).execute()
        pids_int = list(set([r["persona_id"] for r in res_i.data or []]))
        if not pids_int: return pd.DataFrame(), "No hubo interacciones."
        
        all_rows = []
        for i in range(0, len(pids_int), 200):
            ch = pids_int[i:i+200]
            res = q_p.in_("id", ch).execute()
            if res.data: all_rows.extend(res.data)
        return pd.DataFrame(all_rows), f"Personas contactadas en últimos {days} días."

    elif tool_id == "LIST_PERSONAS_SIN_CONTACTO":
        # Fetch Visible Personas Basic
        # Warning: If user has 50k visible personas, this is slow.
        # MVP: Increase safety limit to 10k or improve logic.
        q_p = get_visible_personas_query(user_ctx).limit(5000) 
        df_p = pd.DataFrame(q_p.execute().data or [])
        if df_p.empty: return pd.DataFrame(), "No hay personas visibles."
        
        res_i = sb.table("interacciones_personas").select("persona_id").gte("fecha", str(limit_date)).in_("persona_id", df_p["id"].tolist()).execute()
        contactados = set([r["persona_id"] for r in res_i.data or []])
        return df_p[~df_p["id"].isin(contactados)], f"Personas sin contacto en últimos {days} días."


    elif tool_id == "LIST_PERSONAS_POS_SIN_CONTACTO":
        # 1. Fetch visibles
        # Use pagination loop to get ALL IDs if needed, but for MVP keep LIMIT safe or bump it.
        # Ideally we want ALL positive people.
        q_p = get_visible_personas_query(user_ctx)
        # Limit 5000 is safe for now.
        df_p = pd.DataFrame(q_p.limit(5000).execute().data or [])
        if df_p.empty: return pd.DataFrame(), "No hay personas visibles."
        
        pids = df_p["id"].tolist()
        
        # 2. Fetch Last Interaction for these people
        # We need: persona_id, fecha, respuesta.
        # Optimization: Fetch interactions only for these IDs.
        # We need ALL interactions to determine the LAST one correctly? 
        # Or can we order by date desc and rely on python to dedupe? Yes.
        
        # Split in chunks if > 200 IDs
        last_interactions = {}
        chunk_sz = 200
        
        for i in range(0, len(pids), chunk_sz):
            chunk = pids[i:i+chunk_sz]
            res = sb.table("interacciones_personas").select("persona_id, fecha, respuesta").in_("persona_id", chunk).order("fecha", desc=True).execute()
            
            # Process chunk: Keep only the first (latest) occurrence per ID
            for r in res.data or []:
                pid = r["persona_id"]
                if pid not in last_interactions:
                     last_interactions[pid] = r
                     
        # 3. Filter:
        #  - Status is POSITIVE
        #  - Date < Limit Date (No recent contact)
        
        final_rows = []
        for index, row in df_p.iterrows():
            pid = row["id"]
            if pid in last_interactions:
                last = last_interactions[pid]
                
                # Check Positive
                resp = (last.get("respuesta") or "").strip().lower()
                if resp in POS_SET:
                    # Check Date (No recent contact)
                    # "No contactado en ultimos 30 dias" means Last Date < Today - 30.
                    # Verify conversion
                    try:
                        last_date = pd.to_datetime(last["fecha"]).date()
                    except:
                        continue
                        
                    if last_date < limit_date:
                        r_copy = row.to_dict()
                        r_copy["ultima_interaccion"] = str(last_date)
                        r_copy["estado_respuesta"] = last.get("respuesta")
                        r_copy["motivo"] = f"Positivo sin contacto (> {days}d)"
                        final_rows.append(r_copy)
                        
        return pd.DataFrame(final_rows), f"Personas Positivas sin contacto en últimos {days} días."

    elif tool_id == "LIST_PERSONAS_SIN_ASIGNAR":
        df = fetch_unassigned_objects(user_ctx, "PERSONA")
        return df, "Personas visibles sin usuario asignado (Total)."

    elif tool_id == "LIST_REUNION_ASISTENTES":
        res_a = sb.table("reuniones_asistentes").select("persona_id").gte("created_at", str(limit_date)).execute()
        pids = list(set([r["persona_id"] for r in res_a.data or []]))
        if not pids: return pd.DataFrame(), "No hubo asistentes."
        q_p = get_visible_personas_query(user_ctx).in_("id", pids)
        return pd.DataFrame(q_p.execute().data or []), f"Asistentes a reuniones ({days}d)."

    elif tool_id == "LIST_ASOC_RESPUESTA_POSITIVA":
        df = fetch_asociaciones_con_respuesta_positiva(user_ctx)
        return df, "Asociaciones con respuesta positiva."

    elif tool_id == "LIST_ASOC_POS_SIN_CONTACTO":
        df_pos = fetch_asociaciones_con_respuesta_positiva(user_ctx)
        if df_pos.empty: return pd.DataFrame(), "No hay asoc positivas."
        aids = df_pos["id"].tolist()
        res_i = sb.table("interacciones_asociaciones").select("asociacion_id").in_("asociacion_id", aids).gte("fecha", str(limit_date)).execute()
        recent = set([r["asociacion_id"] for r in res_i.data or []])
        return df_pos[~df_pos["id"].isin(recent)], f"Asociaciones positivas sin visita ({days}d)."

    elif tool_id == "LIST_ASOC_SIN_ASIGNAR":
        df = fetch_unassigned_objects(user_ctx, "ASOCIACION")
        return df, "Asociaciones sin asignar."

    elif tool_id == "LIST_ASOC_SIN_VISITA":
        q_a = get_visible_asociaciones_query(user_ctx).limit(2000)
        df_a = pd.DataFrame(q_a.execute().data or [])
        res_i = sb.table("interacciones_asociaciones").select("asociacion_id").in_("asociacion_id", df_a["id"].tolist()).gte("fecha", str(limit_date)).execute()
        visitadas = set([r["asociacion_id"] for r in res_i.data or []])
        return df_a[~df_a["id"].isin(visitadas)], f"Asoc sin visita ({days}d)."

    return pd.DataFrame(), "N/A"

# =========================
# UI RENDER
# =========================
def render_paginated_table(df: pd.DataFrame, key_prefix="ia"):
    if df.empty:
        st.info("No hay resultados para mostrar.")
        return

    col_exp, col_count, col_page = st.columns([1, 1, 2])
    with col_exp:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 CSV Completo",
            data=csv,
            file_name=f"export_{key_prefix}_{datetime.date.today()}.csv",
            mime="text/csv",
            key=f"btn_exp_{key_prefix}"
        )
    with col_count:
        st.metric("Total", len(df))

    page_size_opts = [50, 100, 200, 500]
    page_size = st.selectbox("Filas/pág", page_size_opts, index=1, key=f"ps_{key_prefix}")
    
    total_pages = (len(df) // page_size) + (1 if len(df) % page_size > 0 else 0)
    
    if f"page_{key_prefix}" not in st.session_state: st.session_state[f"page_{key_prefix}"] = 1
    if st.session_state[f"page_{key_prefix}"] > total_pages: st.session_state[f"page_{key_prefix}"] = 1
    current_page = st.session_state[f"page_{key_prefix}"]
    
    with col_page:
        prev, curr, next_b = st.columns([1, 2, 1])
        if prev.button("◀", key=f"p_{key_prefix}") and current_page > 1:
            st.session_state[f"page_{key_prefix}"] -= 1
            st.rerun()
        curr.write(f"Pág {current_page}/{total_pages}")
        if next_b.button("▶", key=f"n_{key_prefix}") and current_page < total_pages:
            st.session_state[f"page_{key_prefix}"] += 1
            st.rerun()

    start_idx = (current_page - 1) * page_size
    st.dataframe(df.iloc[start_idx:start_idx + page_size], use_container_width=True)

# =========================
# UI MAIN
# =========================
def render(user):
    st.title("CONSULTAS")
    
    tab_cons, tab_intel = st.tabs(["🔎 Consultas", "🧠 Inteligencia"])
    
    # STATE INIT
    if "ia_curr_tool" not in st.session_state: st.session_state["ia_curr_tool"] = None
    if "ia_curr_params" not in st.session_state: st.session_state["ia_curr_params"] = {}
    if "ia_run_trigger" not in st.session_state: st.session_state["ia_run_trigger"] = False

    # --- TAB 1: CONSULTAS ---
    with tab_cons:
        st.markdown("#### Selección de Consulta")
        
        # Tools options list
        tool_opts = ["(Seleccionar...)"] + [f"{k}: {v['label']}" for k,v in CONSULTATION_TOOLS.items()]
        con_sel = st.selectbox("¿Qué necesitás buscar?", tool_opts)
        
        selected_tool_id = None
        if con_sel != "(Seleccionar...)":
            selected_tool_id = con_sel.split(":")[0]
            
        if selected_tool_id:
            tool_def = CONSULTATION_TOOLS.get(selected_tool_id)
            st.info(f"📋 **{tool_def['label']}**")
            st.caption(tool_def['desc'])
            
            # Param inputs
            final_params = {}
            if tool_def["params"]:
                st.markdown("##### Parámetros:")
                cols_p = st.columns(len(tool_def["params"]))
                for i, p_schema in enumerate(tool_def["params"]):
                    p_name = p_schema["name"]
                    p_label = p_schema["label"]
                    p_default = p_schema["default"]
                    
                    if p_schema["type"] == "int":
                        val = cols_p[i].number_input(p_label, value=int(p_default), min_value=0, key=f"param_{p_name}")
                        final_params[p_name] = val
            
            if st.button("🚀 Ejecutar Consulta", key="btn_run_tool"):
                st.session_state["ia_curr_tool"] = selected_tool_id
                st.session_state["ia_curr_params"] = final_params
                st.session_state["ia_run_trigger"] = True
        
        st.divider()
        
        # Result
        if st.session_state.get("ia_run_trigger"):
            tid = st.session_state["ia_curr_tool"]
            tparams = st.session_state["ia_curr_params"]
            
            if tid in CONSULTATION_TOOLS:
                with st.spinner("Procesando..."):
                    df_res, msg = execute_tool(user, tid, tparams)
                    st.success(f"Resultados: {msg}")
                    render_paginated_table(df_res, key_prefix="res")

    # --- TAB 2: INTELIGENCIA ---
    with tab_intel:
        st.subheader("⚠️ Alertas de Gestión")
        
        if st.button("🔄 Actualizar Alertas"):
            st.rerun()
            
        c1, c2 = st.columns(2)
        
        # KPI 1: Personas Positivas Sin Contacto
        with c1.container(border=True):
            st.subheader("👥 Personas Positivas Olvidadas")
            st.caption("Semáforo Verde/Positivo SIN contacto en 30 días.")
            with st.spinner("Analizando..."):
                df_pp, _ = execute_tool(user, "LIST_PERSONAS_POS_SIN_CONTACTO", {"days": 30})
            st.metric("Casos", len(df_pp))
            if not df_pp.empty:
                with st.expander("Ver lista"):
                    render_paginated_table(df_pp, key_prefix="kpi_p_pos")

        # KPI 2: Asoc Positiva Sin Contacto
        with c2.container(border=True):
             st.subheader("🏢 Asociaciones Positivas Olvidadas")
             st.caption("Respuesta Positiva SIN visita en 30 días.")
             with st.spinner("Analizando..."):
                df_ap, _ = execute_tool(user, "LIST_ASOC_POS_SIN_CONTACTO", {"days": 30})
             st.metric("Casos", len(df_ap))
             if not df_ap.empty:
                 with st.expander("Ver lista"):
                     render_paginated_table(df_ap, key_prefix="kpi_a_pos")
