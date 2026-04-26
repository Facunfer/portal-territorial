# kpis_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import personas_scope_rules

# =========================
# CONFIG / MAPEOS
# =========================
COLOR_MAP = {
    "POSITIVO": "#10b981",
    "NEUTRO": "#f59e0b",
    "NEGATIVO": "#ef4444",
    "NO CONTACTADO": "#6b7280",
    "NO VISITADO": "#6b7280",
    "NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 POSITIVO": "#10b981",
    "🟡 NEUTRO": "#f59e0b",
    "🔴 NEGATIVO": "#ef4444",
    "⚫ NO CONTACTADO": "#6b7280",
    "⚫ NO VISITADO": "#6b7280",
    "🟠 NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 <30 días": "#10b981",
    "🟡 30-60 días": "#f59e0b",
    "🔴 >60 días": "#ef4444",
    "⚫ SIN CONTACTO": "#6b7280",
    "⚫ SIN VISITA": "#6b7280",
}

# CONSTANTES DE ORDENAMIENTO
ORDEN_TIEMPO_PERSONAS = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN CONTACTO"]
ORDEN_RESPUESTA_PERSONAS = ["🟢 POSITIVO", "🟡 NEUTRO", "🔴 NEGATIVO", "🟠 NÚMERO INEXISTENTE/EQUIVOCADO", "⚫ NO CONTACTADO"]

ORDEN_TIEMPO_ASOC = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN VISITA"]
ORDEN_RESPUESTA_ASOC = ["🟢 POSITIVO", "🟡 NEUTRO", "🔴 NEGATIVO", "⚫ NO VISITADO"]

# =========================
# HELPERS DE PROCESAMIENTO
# =========================

def _semaforo_tiempo_label(days, is_asoc=False):
    if days is None or pd.isna(days): 
        return "⚫ SIN VISITA" if is_asoc else "⚫ SIN CONTACTO"
    if days < 30: return "🟢 <30 días"
    if days <= 60: return "🟡 30-60 días"
    return "🔴 >60 días"

def _semaforo_respuesta_label(status, is_asoc=False):
    s = str(status or "").strip().upper()
    if s == "POSITIVO": return "🟢 POSITIVO"
    if s == "NEUTRO": return "🟡 NEUTRO"
    if s == "NEGATIVO": return "🔴 NEGATIVO"
    if s == "NUMERO INEXISTENTE/EQUIVOCADO": return "🟠 NÚMERO INEXISTENTE/EQUIVOCADO"
    return "⚫ NO VISITADO" if is_asoc else "⚫ NO CONTACTADO"

# =========================
# HELPERS DE DATA
# =========================
# ... (rest of fetch_kpis_data remains unchanged, skipping to UI RENDER part where charts are) ...

# ... (inside render_kpis_tab) ...

    if vista_activa == "Personas":
        st.subheader("👥 Indicadores de Personas")
        if df_p.empty:
            st.info("No hay datos de personas para este ámbito.")
        else:
            k1, k2, k3 = st.columns(3)
            # Contactada = respuesta no nula y no contiene "NO CONTACTADO"
            contactadas = df_p[~df_p["semaforo_respuesta"].fillna("").str.contains("NO CONTACTADO", case=False)]
            k1.metric("Total Base", f"{len(df_p):,}")
            k2.metric("Contactadas", f"{len(contactadas):,}")
            k3.metric("% Penetración", f"{(len(contactadas)/len(df_p)*100):.1f}%" if not df_p.empty else "0%")

            g1, g2 = st.columns(2)
            with g1:
                df_pie = pd.DataFrame({"Estado": ["Contactadas", "Pendientes"], "Cant": [len(contactadas), len(df_p)-len(contactadas)]})
                st.plotly_chart(px.pie(df_pie, values="Cant", names="Estado", title="Cobertura de Base", hole=0.4, color_discrete_sequence=["#10b981", "#6b7280"]), use_container_width=True)
            with g2:
                if not df_ip.empty:
                    df_time = df_ip.copy()
                    df_time["dia"] = pd.to_datetime(df_time["fecha"]).dt.date
                    df_counts = df_time.groupby("dia").size().reset_index(name="Interacciones")
                    st.plotly_chart(px.line(df_counts, x="dia", y="Interacciones", title="Actividad Diaria (Cant. Interacciones)", markers=True), use_container_width=True)
                else:
                    st.info("Sin actividad registrada por los usuarios en este rango.")

            g3, g4 = st.columns(2)
            with g3:
                # Reindexar para mostrar todos los estados
                s_counts = df_p["semaforo_respuesta"].value_counts()
                s_counts = s_counts.reindex(ORDEN_RESPUESTA_PERSONAS, fill_value=0)
                cnt_res = s_counts.reset_index()
                cnt_res.columns = ["Estado", "Cantidad"]
                st.plotly_chart(px.bar(cnt_res, x="Estado", y="Cantidad", title="Clasificación por Respuesta", 
                                       color="Estado", color_discrete_map=COLOR_MAP,
                                       category_orders={"Estado": ORDEN_RESPUESTA_PERSONAS}), use_container_width=True)
            with g4:
                # Reindexar Recencia
                t_counts = df_p["semaforo_tiempo"].value_counts()
                t_counts = t_counts.reindex(ORDEN_TIEMPO_PERSONAS, fill_value=0)
                cnt_time = t_counts.reset_index()
                cnt_time.columns = ["Antigüedad", "Cantidad"]
                st.plotly_chart(px.bar(cnt_time, x="Antigüedad", y="Cantidad", title="Recencia de Contacto", 
                                       color="Antigüedad", color_discrete_map=COLOR_MAP,
                                       category_orders={"Antigüedad": ORDEN_TIEMPO_PERSONAS}), use_container_width=True)

    else: # Vista Asociaciones
        st.subheader("🏢 Indicadores de Asociaciones")
        if df_a.empty:
            st.info("No hay asociaciones asignadas a este ámbito.")
        else:
            k1, k2, k3 = st.columns(3)
            visitadas = df_a[~df_a["semaforo_respuesta"].fillna("").str.contains("NO VISITADO", case=False)]
            # Fix metricas
            k1.metric("Total Asociaciones", f"{len(df_a):,}")
            k2.metric("Visitadas", f"{len(visitadas):,}")
            k3.metric("% Cobertura", f"{(len(visitadas)/len(df_a)*100):.1f}%" if not df_a.empty else "0%")

            g1, g2 = st.columns(2)
            with g1:
                df_pie_a = pd.DataFrame({"Estado": ["Visitadas", "Pendientes"], "Cant": [len(visitadas), len(df_a)-len(visitadas)]})
                st.plotly_chart(px.pie(df_pie_a, values="Cant", names="Estado", title="Cobertura de Visitas", hole=0.4, color_discrete_sequence=["#10b981", "#6b7280"]), use_container_width=True)
            with g2:
                if not df_ia.empty:
                    df_time_a = df_ia.copy()
                    df_time_a["dia"] = pd.to_datetime(df_time_a["fecha"]).dt.date
                    df_counts_a = df_time_a.groupby("dia").size().reset_index(name="Interacciones")
                    st.plotly_chart(px.line(df_counts_a, x="dia", y="Interacciones", title="Actividad Diaria (Cant. Visitas)", markers=True), use_container_width=True)
                else:
                    st.info("Sin actividad registrada por los usuarios en este rango.")

            g3, g4 = st.columns(2)
            with g3:
                # Reindexar Respuestas Asoc
                s_counts_a = df_a["semaforo_respuesta"].value_counts()
                s_counts_a = s_counts_a.reindex(ORDEN_RESPUESTA_ASOC, fill_value=0)
                cnt_res_a = s_counts_a.reset_index()
                cnt_res_a.columns = ["Resultado", "Cantidad"]
                st.plotly_chart(px.bar(cnt_res_a, x="Resultado", y="Cantidad", title="Resultados de Visitas", 
                                       color="Resultado", color_discrete_map=COLOR_MAP,
                                       category_orders={"Resultado": ORDEN_RESPUESTA_ASOC}), use_container_width=True)
            with g4:
                # Reindexar Recencia Asoc
                t_counts_a = df_a["semaforo_tiempo"].value_counts()
                t_counts_a = t_counts_a.reindex(ORDEN_TIEMPO_ASOC, fill_value=0)
                cnt_time_a = t_counts_a.reset_index()
                cnt_time_a.columns = ["Recencia", "Cantidad"]
                st.plotly_chart(px.bar(cnt_time_a, x="Recencia", y="Cantidad", title="Recencia de Visita", 
                                       color="Recencia", color_discrete_map=COLOR_MAP,
                                       category_orders={"Recencia": ORDEN_TIEMPO_ASOC}), use_container_width=True)

# =========================
# HELPERS DE DATA
# =========================

def fetch_kpis_data(supabase, user_ctx, date_from, date_to, scope_override=None):
    """
    Trae los datos necesarios para KPIs respetando el scope, filtrando por usuarios y calculando semáforos.
    """
    effective_ctx = user_ctx.copy()
    if scope_override:
        if scope_override.get("comuna"):
            effective_ctx["comuna_id"] = scope_override["comuna"]
            effective_ctx["ambito"] = "COMUNA"
            effective_ctx["rol"] = "CABEZA"
        elif scope_override.get("vertical"):
            effective_ctx["vertical"] = scope_override["vertical"]
            effective_ctx["ambito"] = "VERTICAL_PERSONAS"
            effective_ctx["rol"] = "CABEZA"

    # Helper para paginación genérica
    def _fetch_all(query):
        rows = []
        page = 0
        page_size = 1000
        while True:
            # .range() es inclusivo en start y end
            res = query.range(page * page_size, (page + 1) * page_size - 1).execute()
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1
        return pd.DataFrame(rows)

    # 1. Obtener IDs de usuarios del ámbito para filtrar interacciones (Pedido del usuario)
    u_query = supabase.table("usuarios").select("id")
    if effective_ctx.get("ambito") == "COMUNA" and effective_ctx.get("comuna_id"):
        u_query = u_query.eq("comuna_id", int(effective_ctx["comuna_id"]))
    elif effective_ctx.get("vertical") and "VERTICAL" in effective_ctx.get("ambito", ""):
        u_query = u_query.eq("vertical", effective_ctx["vertical"])
    
    # Usuarios suelen ser pocos, pero por seguridad usamos fetch_all si creciera
    # Aunque execute() directo suele bastar usuarios < 1000. Dejamos execute() por ahora para usuarios.
    res_u = u_query.execute()
    user_ids = [r["id"] for r in (res_u.data or [])]

    # 2. Fetch Personas (Filtrado por visibilidad)
    p_query = supabase.table("personas").select("id, comuna_id, tags, creado_en")
    p_query = personas_scope_rules.apply_personas_visibility_filter(p_query, effective_ctx)
    # USAR PAGINACION
    df_p = _fetch_all(p_query)
    
    # 3. Fetch Asociaciones
    a_query = supabase.table("asociaciones").select("id, comuna_id, tipo, nombre")
    if effective_ctx.get("ambito") == "COMUNA" and effective_ctx.get("comuna_id"):
        a_query = a_query.eq("comuna_id", int(effective_ctx["comuna_id"]))
    # USAR PAGINACION
    df_a = _fetch_all(a_query)

    # 4. Fetch Interacciones (Históricas para semáforos y rango UI para analítico)
    since_180 = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
    
    def fetch_paged(table, id_col):
        rows = []
        page = 0
        while True:
            q = supabase.table(table).select(f"{id_col}, fecha, respuesta, created_by")
            q = q.gte("fecha", since_180)
            res = q.range(page*1000, (page+1)*1000 - 1).execute()
            data = res.data or []
            rows.extend(data)
            if len(data) < 1000: break
            page += 1
        return pd.DataFrame(rows)

    df_ip_raw = fetch_paged("interacciones_personas", "persona_id")
    df_ia_raw = fetch_paged("interacciones_asociaciones", "asociacion_id")
    
    # Filtrar interacciones por los Usuarios del ámbito (Pedido crítico)
    if user_ids:
        if not df_ip_raw.empty:
            df_ip_raw = df_ip_raw[df_ip_raw["created_by"].isin(user_ids)]
        if not df_ia_raw.empty:
            df_ia_raw = df_ia_raw[df_ia_raw["created_by"].isin(user_ids)]

    # 5. Calcular Semáforos
    today_ts = pd.Timestamp.now().normalize()
    if not df_p.empty:
        # Nota: Aquí usamos todas las interacciones filtradas por usuario para ver el estado "nuestro"
        last_ip = df_ip_raw.sort_values('fecha', ascending=False).drop_duplicates('persona_id') if not df_ip_raw.empty else pd.DataFrame(columns=['persona_id', 'fecha', 'respuesta'])
        df_p = df_p.merge(last_ip, left_on='id', right_on='persona_id', how='left')
        df_p['dias_contacto'] = (today_ts - pd.to_datetime(df_p['fecha'])).dt.days
        df_p['semaforo_tiempo'] = df_p['dias_contacto'].apply(lambda x: _semaforo_tiempo_label(x, is_asoc=False))
        df_p['semaforo_respuesta'] = df_p['respuesta'].apply(lambda x: _semaforo_respuesta_label(x, is_asoc=False))
    
    if not df_a.empty:
        last_ia = df_ia_raw.sort_values('fecha', ascending=False).drop_duplicates('asociacion_id') if not df_ia_raw.empty else pd.DataFrame(columns=['asociacion_id', 'fecha', 'respuesta'])
        df_a = df_a.merge(last_ia, left_on='id', right_on='asociacion_id', how='left')
        df_a['dias_contacto'] = (today_ts - pd.to_datetime(df_a['fecha'])).dt.days
        df_a['semaforo_tiempo'] = df_a['dias_contacto'].apply(lambda x: _semaforo_tiempo_label(x, is_asoc=True))
        df_a['semaforo_respuesta'] = df_a['respuesta'].apply(lambda x: _semaforo_respuesta_label(x, is_asoc=True))

    # Filtrar por fecha para el rango de visualización
    df_ip_ui = df_ip_raw[(pd.to_datetime(df_ip_raw['fecha']).dt.date >= date_from) & (pd.to_datetime(df_ip_raw['fecha']).dt.date <= date_to)] if not df_ip_raw.empty else pd.DataFrame()
    df_ia_ui = df_ia_raw[(pd.to_datetime(df_ia_raw['fecha']).dt.date >= date_from) & (pd.to_datetime(df_ia_raw['fecha']).dt.date <= date_to)] if not df_ia_raw.empty else pd.DataFrame()

    return df_p, df_a, df_ip_ui, df_ia_ui

# =========================
# UI RENDER
# =========================

def render_kpis_tab(user_ctx, supabase):
    st.header("📈 Visualización / KPIs")
    
    # --- FILTROS GLOBALES ---
    with st.container(border=True):
        c1, c2 = st.columns([1, 1])
        with c1:
            # Selector de Vista Principal
            vista_activa = st.radio("Seleccionar Información:", ["Personas", "Asociaciones"], horizontal=True)
        with c2:
            rango = st.date_input("Rango de análisis (Actividad)", 
                                  value=(datetime.date.today() - datetime.timedelta(days=30), datetime.date.today()))
            date_from, date_to = (rango[0], rango[1]) if len(rango) == 2 else (datetime.date.today(), datetime.date.today())
        
        scope_override = {}

    # Fetch Data
    with st.spinner("Cargando analíticas..."):
        try:
            df_p, df_a, df_ip, df_ia = fetch_kpis_data(supabase, user_ctx, date_from, date_to, scope_override)
        except Exception as e:
            st.error(f"Error al obtener datos: {e}")
            return

    if vista_activa == "Personas":
        st.subheader("👥 Indicadores de Personas")
        if df_p.empty:
            st.info("No hay datos de personas para este ámbito.")
        else:
            k1, k2, k3 = st.columns(3)
            # Contactada = respuesta no nula y no contiene "NO CONTACTADO"
            contactadas = df_p[~df_p["semaforo_respuesta"].fillna("").str.contains("NO CONTACTADO", case=False)]
            k1.metric("Total Base", f"{len(df_p):,}")
            k2.metric("Contactadas", f"{len(contactadas):,}")
            k3.metric("% Penetración", f"{(len(contactadas)/len(df_p)*100):.1f}%" if not df_p.empty else "0%")

            g1, g2 = st.columns(2)
            with g1:
                df_pie = pd.DataFrame({"Estado": ["Contactadas", "Pendientes"], "Cant": [len(contactadas), len(df_p)-len(contactadas)]})
                st.plotly_chart(px.pie(df_pie, values="Cant", names="Estado", title="Cobertura de Base", hole=0.4, color_discrete_sequence=["#10b981", "#6b7280"]), use_container_width=True)
            with g2:
                if not df_ip.empty:
                    df_time = df_ip.copy()
                    df_time["dia"] = pd.to_datetime(df_time["fecha"]).dt.date
                    df_counts = df_time.groupby("dia").size().reset_index(name="Interacciones")
                    st.plotly_chart(px.line(df_counts, x="dia", y="Interacciones", title="Actividad Diaria (Cant. Interacciones)", markers=True), use_container_width=True)
                else:
                    st.info("Sin actividad registrada por los usuarios en este rango.")

            g3, g4 = st.columns(2)
            with g3:
                cnt_res = df_p["semaforo_respuesta"].value_counts().reset_index()
                cnt_res.columns = ["Estado", "Cantidad"]
                st.plotly_chart(px.bar(cnt_res, x="Estado", y="Cantidad", title="Clasificación por Respuesta", color="Estado", color_discrete_map=COLOR_MAP), use_container_width=True)
            with g4:
                cnt_time = df_p["semaforo_tiempo"].value_counts().reset_index()
                cnt_time.columns = ["Antigüedad", "Cantidad"]
                st.plotly_chart(px.bar(cnt_time, x="Antigüedad", y="Cantidad", title="Recencia de Contacto", color="Antigüedad", color_discrete_map=COLOR_MAP), use_container_width=True)

    else: # Vista Asociaciones
        st.subheader("🏢 Indicadores de Asociaciones")
        if df_a.empty:
            st.info("No hay asociaciones asignadas a este ámbito.")
        else:
            k1, k2, k3 = st.columns(3)
            visitadas = df_a[~df_a["semaforo_respuesta"].fillna("").str.contains("NO VISITADO", case=False)]
            k1.metric("Total Asociaciones", f"{len(df_a):,}")
            k2.metric("Visitadas", f"{len(visitadas):,}")
            k3.metric("% Cobertura", f"{(len(visitadas)/len(df_a)*100):.1f}%" if not df_a.empty else "0%")

            g1, g2 = st.columns(2)
            with g1:
                df_pie_a = pd.DataFrame({"Estado": ["Visitadas", "Pendientes"], "Cant": [len(visitadas), len(df_a)-len(visitadas)]})
                st.plotly_chart(px.pie(df_pie_a, values="Cant", names="Estado", title="Cobertura de Visitas", hole=0.4, color_discrete_sequence=["#10b981", "#6b7280"]), use_container_width=True)
            with g2:
                if not df_ia.empty:
                    df_time_a = df_ia.copy()
                    df_time_a["dia"] = pd.to_datetime(df_time_a["fecha"]).dt.date
                    df_counts_a = df_time_a.groupby("dia").size().reset_index(name="Interacciones")
                    st.plotly_chart(px.line(df_counts_a, x="dia", y="Interacciones", title="Actividad Diaria (Cant. Visitas)", markers=True), use_container_width=True)
                else:
                    st.info("Sin actividad registrada por los usuarios en este rango.")

            g3, g4 = st.columns(2)
            with g3:
                cnt_res_a = df_a["semaforo_respuesta"].value_counts().reset_index()
                cnt_res_a.columns = ["Resultado", "Cantidad"]
                st.plotly_chart(px.bar(cnt_res_a, x="Resultado", y="Cantidad", title="Resultados de Visitas", color="Resultado", color_discrete_map=COLOR_MAP), use_container_width=True)
            with g4:
                cnt_time_a = df_a["semaforo_tiempo"].value_counts().reset_index()
                cnt_time_a.columns = ["Recencia", "Cantidad"]
                st.plotly_chart(px.bar(cnt_time_a, x="Recencia", y="Cantidad", title="Recencia de Visita", color="Recencia", color_discrete_map=COLOR_MAP), use_container_width=True)

def render(user_ctx, supabase):
    render_kpis_tab(user_ctx, supabase)
