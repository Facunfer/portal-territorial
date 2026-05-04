import streamlit as st
import pandas as pd
import plotly.express as px
import datetime

from db import get_supabase
import personas_edicion

@st.cache_data(ttl=300)
def fetch_global_data():
    """
    Trae los datos base necesarios para el dashboard usando paginación total.
    Incluye REUNIONES.
    """
    supabase = get_supabase()
    
    def fetch_all(table_name, select_cols):
        rows = []
        page = 0
        page_size = 1000
        while True:
            res = supabase.table(table_name).select(select_cols).range(page * page_size, (page + 1) * page_size - 1).execute()
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1
        return pd.DataFrame(rows)

    # 1. Personas
    df_p = fetch_all("personas", "id, comuna_id, tags, creado_en, telefono, barrio")
    
    # 2. Asociaciones
    df_a = fetch_all("asociaciones", "id, comuna_id, tipo, referente_nombre, referente_telefono")
    
    # 3. Interacciones (ampliamos a 180 días para tener más margen histórico)
    since_180 = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
    def fetch_all_interacciones(table_name, select_cols, date_col, since_val):
        rows = []
        page = 0
        page_size = 1000
        while True:
            res = supabase.table(table_name).select(select_cols).gte(date_col, since_val).range(page * page_size, (page + 1) * page_size - 1).execute()
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1
        return pd.DataFrame(rows)

    df_ip = fetch_all_interacciones("interacciones_personas", "id, persona_id, fecha, respuesta", "fecha", since_180)
    df_ia = fetch_all_interacciones("interacciones_asociaciones", "id, asociacion_id, fecha, respuesta", "fecha", since_180)
    
    # 4. Reuniones (NUEVO)
    # Traemos reuniones recientes (ultimos 180 dias) para graficar
    df_r = fetch_all_interacciones("reuniones", "id, fecha, scope_tipo, scope_valor", "fecha", since_180)

    return df_p, df_a, df_ip, df_ia, df_r

# ==============================================================================
# HELPERS DE PROCESAMIENTO
# ==============================================================================

def _parse_tags(v):
    if v is None: return []
    if isinstance(v, list): return [str(x).strip().upper() for x in v if str(x).strip()]
    return [x.strip().upper() for x in str(v).split(",") if x.strip()]

# COLORES Y LABELS (IDENTICOS A VISUALIZACION/KPIs)
COLOR_MAP = {
    "POSITIVO": "#10b981", "NEUTRO": "#f59e0b", "NEGATIVO": "#ef4444", 
    "NO CONTACTADO": "#6b7280", "NO VISITADO": "#6b7280", "NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 POSITIVO": "#10b981", "🟡 NEUTRO": "#f59e0b", "🔴 NEGATIVO": "#ef4444", 
    "⚫ NO CONTACTADO": "#6b7280", "⚫ NO VISITADO": "#6b7280", "🟠 NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 <30 días": "#10b981", "🟡 30-60 días": "#f59e0b", "🔴 >60 días": "#ef4444", 
    "⚫ SIN CONTACTO": "#6b7280", "⚫ SIN VISITA": "#6b7280"
}

LABELS_TIEMPO_P = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN CONTACTO"]
LABELS_TIEMPO_A = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN VISITA"]
LABELS_RESP_P = ["🟢 POSITIVO", "🟡 NEUTRO", "🔴 NEGATIVO", "🟠 NÚMERO INEXISTENTE/EQUIVOCADO", "⚫ NO CONTACTADO"]
LABELS_RESP_A = ["🟢 POSITIVO", "🟡 NEUTRO", "🔴 NEGATIVO", "⚫ NO VISITADO"]

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

def filter_data(df_p, df_a, df_ip, df_ia, df_r, filters):
    f_comunas = filters.get("comunas", [])
    f_barrios = filters.get("barrios", [])
    f_tags = filters.get("tags", [])
    f_tipo = filters.get("tipo")
    f_fechas = filters.get("fechas", [])
    
    p, a, ip, ia, r = df_p.copy(), df_a.copy(), df_ip.copy(), df_ia.copy(), df_r.copy()
    
    # 1. Filtro de Fechas
    if len(f_fechas) == 2:
        start_date, end_date = f_fechas
        if not ip.empty:
            ip['fecha_dt'] = pd.to_datetime(ip['fecha']).dt.date
            ip = ip[(ip['fecha_dt'] >= start_date) & (ip['fecha_dt'] <= end_date)]
        if not ia.empty:
            ia['fecha_dt'] = pd.to_datetime(ia['fecha']).dt.date
            ia = ia[(ia['fecha_dt'] >= start_date) & (ia['fecha_dt'] <= end_date)]
        if not r.empty:
            r['fecha_dt'] = pd.to_datetime(r['fecha']).dt.date
            r = r[(r['fecha_dt'] >= start_date) & (r['fecha_dt'] <= end_date)]

    # 2. Filtro Comuna (Multiselect)
    if f_comunas:
        str_comunas = [str(c) for c in f_comunas]
        p = p[p['comuna_id'].astype(str).isin(str_comunas)]
        a = a[a['comuna_id'].astype(str).isin(str_comunas)]
        
        # Filtro Reuniones Por Comuna
        if not r.empty:
             r = r[ (r['scope_tipo'] == "COMUNA") & (r['scope_valor'].astype(str).isin(str_comunas)) ]
        
        # Propagar a interacciones
        p_ids, a_ids = set(p['id'].tolist()), set(a['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]
        ia = ia[ia['asociacion_id'].isin(a_ids)]
    else:
        # Si NO filtra comunas, para reuniones igual solo mostramos las de tipo COMUNA para el grafico "por comuna"
        if not r.empty:
             r = r[r['scope_tipo'] == "COMUNA"]
    
    # 2b. Filtro Barrio (Multiselect)
    if f_barrios:
        p = p[p['barrio'].isin(f_barrios)]
        # Para asociaciones, asumimos que tambien tienen barrio, si no existe la columna en df_a, fallara o se ignorara si no la trajimos
        if 'barrio' in a.columns:
            a = a[a['barrio'].isin(f_barrios)]
            
        # Propagar a interacciones
        p_ids, a_ids = set(p['id'].tolist()), set(a['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]
        ia = ia[ia['asociacion_id'].isin(a_ids)]

    # 3. Filtro Vertical Personas (Tags - Multiselect)
    if f_tags:
        # OR Logic: Si tiene al menos uno de los tags seleccionados
        # Normalizamos a upper en el filtro tambien por seguridad
        f_tags_upper = [t.upper() for t in f_tags]
        p['tag_list'] = p['tags'].apply(_parse_tags)
        p = p[p['tag_list'].apply(lambda x: any(t in x for t in f_tags_upper))]
        p_ids = set(p['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]
        
    # 4. Filtro Vertical Asociaciones (Tipo)
    if f_tipo != "Todos":
        a = a[a['tipo'] == f_tipo]
        a_ids = set(a['id'].tolist())
        ia = ia[ia['asociacion_id'].isin(a_ids)]
        
    return p, a, ip, ia, r
    
# ==============================================================================
# RENDER PRINCIPAL
# ==============================================================================

def render_dashboard_master_global(user):
    st.title("🛡️ MASTER GLOBAL - Command Center")
    st.caption("Visión analítica integral del territorio y rendimiento de equipos.")

    # --- BOTON REFRESCAR ---
    if st.button("🔄 Refrescar datos"):
        fetch_global_data.clear()
        st.rerun()

    with st.spinner("Cargando métricas globales..."):
        df_p_raw, df_a_raw, df_ip_raw, df_ia_raw, df_r_raw = fetch_global_data()

    if df_p_raw.empty and df_a_raw.empty:
        st.warning("No se encontraron datos.")
        return

    # --- FILTROS GLOBALES ---
    with st.expander("🎯 Filtros Globales y Drill-down", expanded=True):
        fcol1, fcol2, fcol3 = st.columns([1, 1, 1])
        
        comunas_available = sorted([int(x) for x in df_p_raw['comuna_id'].dropna().unique() if str(x).isdigit()])
        
        with fcol1:
            f_comunas = st.multiselect("Comunas (Vacío = Todas)", options=comunas_available)
            
            # Filtro de Barrios
            # Obtenemos todos los barrios unicos de ambas tablas
            barrios_p = set(df_p_raw['barrio'].dropna().unique())
            barrios_a = set(df_a_raw['barrio'].dropna().unique()) if 'barrio' in df_a_raw.columns else set()
            all_barrios = sorted(list(barrios_p.union(barrios_a)))
            
            # Si hay comunas seleccionadas, podriamos filtrar los barrios disponibles si tuvieramos el mapeo exacto o usando la data
            # Por simplicidad y consistencia con datos reales, filtramos las opciones usando los datos filtrados por comuna (si quisieramos ser estrictos)
            # Pero para UX rapida, mostramos todos O filtramos si hay comuna.
            # Vamos a filtrar opciones si hay comunas seleccionadas usando el DF raw
            if f_comunas:
                str_comunas = [str(c) for c in f_comunas]
                df_p_filt = df_p_raw[df_p_raw['comuna_id'].astype(str).isin(str_comunas)]
                # Para df_a tambien si tiene barrio
                barrios_p_filt = set(df_p_filt['barrio'].dropna().unique())
                barrios_a_filt = set()
                if 'barrio' in df_a_raw.columns:
                     df_a_filt = df_a_raw[df_a_raw['comuna_id'].astype(str).isin(str_comunas)]
                     barrios_a_filt = set(df_a_filt['barrio'].dropna().unique())
                all_barrios = sorted(list(barrios_p_filt.union(barrios_a_filt)))
            
            f_barrios = st.multiselect("Barrios", options=all_barrios)
        
        with fcol2:
            all_tags = set(personas_edicion.TAGS_SUGERIDOS) # Inicializar con los sugeridos
            for row in df_p_raw['tags'].dropna():
                for t in _parse_tags(row): all_tags.add(t)
            # CAMBIO: Multiselect para Tags
            f_tags = st.multiselect("Tags Personas (OR)", options=sorted(list(all_tags)))
            
            tipos_available = sorted([str(x) for x in df_a_raw['tipo'].dropna().unique()])
            f_tipo = st.selectbox("Vertical (Asociaciones)", ["Todos"] + tipos_available)
            
        with fcol3:
            # Filtro de fecha rango
            today = datetime.date.today()
            def_start = today - datetime.timedelta(days=30)
            f_fechas = st.date_input("Rango de Interacciones", value=(def_start, today))
    
    filters = {"comunas": f_comunas, "barrios": f_barrios, "tags": f_tags, "tipo": f_tipo, "fechas": f_fechas}
    p, a, ip, ia, r = filter_data(df_p_raw, df_a_raw, df_ip_raw, df_ia_raw, df_r_raw, filters)

    # --- ENRIQUECIMIENTO GLOBAL (Comuna IDs) ---
    # Mapeamos comuna_id a las interacciones para usarlas en todos los tabs (Tendencias, Territorio, etc)
    p_map_global = df_p_raw[['id', 'comuna_id']].set_index('id')['comuna_id'].to_dict()
    a_map_global = df_a_raw[['id', 'comuna_id']].set_index('id')['comuna_id'].to_dict()
    
    ip['comuna_id'] = ip['persona_id'].map(p_map_global).fillna("Desconocido")
    ia['comuna_id'] = ia['asociacion_id'].map(a_map_global).fillna("Desconocido")

    # --- CALCULO DE SEMAFOROS ---
    def _calc_sem(df_obj, df_int_raw, id_col, is_asoc=False):
        if df_obj.empty: return df_obj
        # Usamos df_int_raw para ver el HISTORICO completo de semaforos (independiente del filtro de fecha actual UI)
        last_int = df_int_raw.sort_values('fecha', ascending=False).drop_duplicates(id_col)
        df_merged = df_obj.merge(last_int[[id_col, 'fecha', 'respuesta']], left_on='id', right_on=id_col, how='left')
        
        today_ts = pd.Timestamp.now().normalize()
        df_merged['dias_contacto'] = (today_ts - pd.to_datetime(df_merged['fecha'])).dt.days
        df_merged['Última Fecha'] = df_merged['dias_contacto'].apply(lambda x: _semaforo_tiempo_label(x, is_asoc))
        df_merged['Resultado'] = df_merged['respuesta'].apply(lambda x: _semaforo_respuesta_label(x, is_asoc))
        return df_merged

    p_sem = _calc_sem(p, df_ip_raw, 'persona_id', is_asoc=False)
    a_sem = _calc_sem(a, df_ia_raw, 'asociacion_id', is_asoc=True)

    # --- KPIs ---
    st.markdown("### 📊 Resumen Ejecutivo")
    k1, k2, k3, k4 = st.columns(4)
    total_p, total_a = len(p), len(a)
    contacted_p = len(ip['persona_id'].unique())
    contacted_a = len(ia['asociacion_id'].unique())
    k1.metric("Total Personas", f"{total_p:,}")
    k2.metric("Total Asociaciones", f"{total_a:,}")
    k3.metric("% Personas Contactadas", f"{(contacted_p/total_p*100):.1f}%" if total_p>0 else "0%")
    k4.metric("% Asoc. Visitadas", f"{(contacted_a/total_a*100):.1f}%" if total_a>0 else "0%")

    tab_territorio, tab_tematico, tab_tendencias, tab_reuniones, tab_calidad = st.tabs([
        "📍 Territorial (Comunas)", "🏷️ Temático (Verticales)", "📈 Tendencias", "🤝 Reuniones", "🔍 Auditoría y Calidad"
    ])

    with tab_territorio:
        # --- PARTE 1: DENSIDAD Y CARGA ---
        st.subheader("Carga y Actividad por Comuna")
        
        # Agregación base para ranking
        p_by_c = p.groupby('comuna_id').size().reset_index(name='Personas')
        a_by_c = a.groupby('comuna_id').size().reset_index(name='Asociaciones')
        
        ranking_comuna = pd.DataFrame({'comuna_id': range(1, 16)})
        ranking_comuna = ranking_comuna.merge(p_by_c, on='comuna_id', how='left').merge(a_by_c, on='comuna_id', how='left').fillna(0)
        
        # Usamos ip/ia ya enriquecidos
        int_by_c = pd.concat([
            ip.groupby('comuna_id').size().reset_index(name='Int'),
            ia.groupby('comuna_id').size().reset_index(name='Int')
        ]).groupby('comuna_id').sum().reset_index() if not (ip.empty and ia.empty) else pd.DataFrame(columns=['comuna_id', 'Int'])
        
        ranking_comuna = ranking_comuna.merge(int_by_c, on='comuna_id', how='left').fillna(0)
        ranking_comuna = ranking_comuna.rename(columns={'Int': 'Interacciones'})

        # Si hay filtro de comunas, filtramos el ranking también
        if f_comunas:
            ranking_comuna = ranking_comuna[ranking_comuna['comuna_id'].isin(f_comunas)]

        col_rank1, col_rank2 = st.columns([2, 1])
        with col_rank1:
            fig_den = px.bar(ranking_comuna, x='comuna_id', y=['Personas', 'Asociaciones'], title="Densidad de Carga", barmode='group')
            fig_den.update_layout(xaxis={'type':'category'})
            st.plotly_chart(fig_den, use_container_width=True)
        with col_rank2:
            st.write("**Detalle Territorial (Ranking)**")
            st.dataframe(
                ranking_comuna.sort_values('Personas', ascending=False).style.background_gradient(
                    cmap='Blues', subset=['Personas', 'Asociaciones', 'Interacciones']
                ), 
                use_container_width=True, 
                hide_index=True
            )

        st.markdown("---")
        
        # --- PARTE 2: SEMÁFOROS (Asegurando match con Visualización) ---
        st.subheader("Semáforos de Gestión (Calidad de Contacto)")
        
        def _semaforos_ui(df, title_suffix, is_asoc=False):
            with st.expander(f"Ver Semáforos de {title_suffix}", expanded=True):
                c1, c2 = st.columns(2)
                
                expected_resp = LABELS_RESP_A if is_asoc else LABELS_RESP_P
                expected_time = LABELS_TIEMPO_A if is_asoc else LABELS_TIEMPO_P
                
                with c1:
                    resp_counts = df.groupby(['Resultado']).size().reset_index(name='count')
                    fig_r = px.bar(resp_counts, x='Resultado', y='count', title=f"Resultado ({title_suffix})", 
                                   color='Resultado',
                                   color_discrete_map=COLOR_MAP,
                                   category_orders={"Resultado": expected_resp})
                    st.plotly_chart(fig_r, use_container_width=True)
                with c2:
                    time_counts = df.groupby(['Última Fecha']).size().reset_index(name='count')
                    fig_t = px.bar(time_counts, x='Última Fecha', y='count', title=f"Última Fecha ({title_suffix})",
                                   color='Última Fecha',
                                   color_discrete_map=COLOR_MAP,
                                   category_orders={"Última Fecha": expected_time})
                    st.plotly_chart(fig_t, use_container_width=True)

        _semaforos_ui(p_sem, "Personas", is_asoc=False)
        _semaforos_ui(a_sem, "Asociaciones", is_asoc=True)

    with tab_tematico:
        c_v1, c_v2 = st.columns(2)
        with c_v1:
            st.subheader("Verticales: Personas")
            p_exploded = p.copy()
            p_exploded['tag_list'] = p_exploded['tags'].apply(_parse_tags)
            p_exploded = p_exploded.explode('tag_list')
            tag_counts = p_exploded.groupby('tag_list').size().reset_index(name='Cant').sort_values('Cant', ascending=False)
            if not tag_counts.empty:
                st.plotly_chart(px.bar(tag_counts.head(10), y='tag_list', x='Cant', orientation='h', title="Top 10 Tags", color='Cant'), use_container_width=True)
        with c_v2:
            st.subheader("Verticales: Asociaciones")
            asoc_counts = a.groupby('tipo').size().reset_index(name='Cant').sort_values('Cant', ascending=False)
            if not asoc_counts.empty:
                st.plotly_chart(px.bar(asoc_counts, y='tipo', x='Cant', orientation='h', title="Por Tipo", color='Cant'), use_container_width=True)

    with tab_tendencias:
        st.subheader("📈 Análisis de Actividad (Líneas por Comuna)")
        
        # 1. Personas Line Chart
        if not ip.empty:
            df_time = ip.copy()
            df_time["fecha_dt"] = pd.to_datetime(df_time["fecha"]).dt.date
            # Agrupar por fecha Y Comuna
            df_counts = df_time.groupby(["fecha_dt", "comuna_id"]).size().reset_index(name="Interacciones")
            fig_p = px.line(df_counts, x="fecha_dt", y="Interacciones", color="comuna_id", 
                            title="Interacciones Personas por Día y Comuna", markers=True)
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info("Sin interacciones con Personas en este rango.")

        st.divider()

        # 2. Asociaciones Line Chart
        if not ia.empty:
            df_time_a = ia.copy()
            df_time_a["fecha_dt"] = pd.to_datetime(df_time_a["fecha"]).dt.date
            # Agrupar por fecha Y Comuna
            df_counts_a = df_time_a.groupby(["fecha_dt", "comuna_id"]).size().reset_index(name="Visitas")
            fig_a = px.line(df_counts_a, x="fecha_dt", y="Visitas", color="comuna_id",
                            title="Visitas Asociaciones por Día y Comuna", markers=True)
            st.plotly_chart(fig_a, use_container_width=True)
        else:
            st.info("Sin visitas a Asociaciones en este rango.")

    with tab_reuniones:
        st.subheader("🤝 Reuniones realizadas")
        if r.empty:
            st.info("No hay reuniones registradas en este periodo / filtros.")
        else:
            # Grafico Lineas por Comuna
            r_graph = r.copy()
            r_graph['fecha_dt'] = pd.to_datetime(r_graph['fecha']).dt.date
            
            # Agrupar por fecha y comuna
            r_counts = r_graph.groupby(['fecha_dt', 'scope_valor']).size().reset_index(name='Cant')
            r_counts = r_counts.rename(columns={'scope_valor': 'Comuna'})
            
            fig_r = px.line(r_counts, x='fecha_dt', y='Cant', color='Comuna', title="Reuniones por Comuna (Evolución)", markers=True)
            st.plotly_chart(fig_r, use_container_width=True)
            
            with st.expander("Ver detalle de reuniones"):
                st.dataframe(r[['fecha', 'scope_valor', 'scope_tipo', 'id']], use_container_width=True)

    with tab_calidad:
        st.subheader("Auditoría de Datos y Ritmo de Carga")
        total = len(p)
        if total > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("Sin Teléfono", p['telefono'].isna().sum(), delta_color="inverse")
            c2.metric("Sin Barrio", p['barrio'].isna().sum(), delta_color="inverse")
            c3.metric("Sin Vertical", p['tags'].isna().sum(), delta_color="inverse")
            
            st.markdown("#### 📈 Crecimiento de la Base (Cargas)")
            if 'creado_en' in p.columns:
                p['creado_dt'] = pd.to_datetime(p['creado_en']).dt.date
                p_growth = p.groupby('creado_dt').size().reset_index(name='Altas')
                st.plotly_chart(px.area(p_growth, x='creado_dt', y='Altas', title="Nuevas Personas", color_discrete_sequence=['#10b981']), use_container_width=True)

            st.markdown("#### 🚩 Alertas de Gestión")
            alertas = []
            avg_p = total / (len(f_comunas) if f_comunas else 15)
            low_c = ranking_comuna[ranking_comuna['Personas'] < (avg_p*0.5)]['comuna_id'].tolist()
            if low_c: alertas.append({"Prioridad":"Alta", "Modulo":"Territorio", "Desc": f"Carga bajísima en: {low_c}"})
            if alertas: st.table(pd.DataFrame(alertas))
            else: st.success("Todo en orden.")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Actualizado: {datetime.datetime.now().strftime('%H:%M')}")

def render(user):
    render_dashboard_master_global(user)
