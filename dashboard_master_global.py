import streamlit as st
import pandas as pd
import plotly.express as px
import datetime

from db import get_supabase
from constants import VERTICALES_SEGMENTOS
import personas_edicion

# Mapeo vertical → tag en personas
VERTICAL_TAG_MAP = {
    "GENERACION_PLATEADA": "GENERACIÓN PLATEADA",
    "MIGRANTES":           "MIGRANTE",
    "CULTO":               "CULTO",
    "CCAA":                "COMERCIANTE",
    "PYMES":               "PYME",
    "JOVENES_EMPRESARIOS": "JUVENTUD",
    "INNOVACION_TECNOLOGIA": None,
    "EDUCACION":           "EDUCACIÓN",
    "SALUD":               "SALUD",
    "CULTURA":             "CULTURA",
}

# Mapeo vertical → tipo en asociaciones
VERTICAL_TIPO_MAP = {
    "CULTO":    "Espacios de Culto",
    "CCAA":     "Local comercial",
    "CULTURA":  "Espacios Culturales",
    "CLUBES":   "Clubes",
}

# Labels legibles para mostrar en el selector
VERTICAL_LABELS = {
    "GENERACION_PLATEADA":   "Generación Plateada",
    "MIGRANTES":             "Migrantes",
    "CULTO":                 "Culto",
    "CCAA":                  "CCAA",
    "PYMES":                 "Pymes",
    "JOVENES_EMPRESARIOS":   "Jóvenes Empresarios",
    "INNOVACION_TECNOLOGIA": "Innovación / Tecnología",
    "EDUCACION":             "Educación",
    "SALUD":                 "Salud",
    "CULTURA":               "Cultura",
}

@st.cache_data(ttl=300)
def fetch_global_data():
    """
    Trae los datos base necesarios para el dashboard usando paginación total.
    Incluye REUNIONES.
    """
    supabase = get_supabase()
    
    def _cols(select_cols: str):
        """Extrae lista de nombres de columnas desde el string 'a, b, c'."""
        return [c.strip() for c in select_cols.split(",")]

    def fetch_all(table_name, select_cols):
        rows = []
        page = 0
        page_size = 1000
        while True:
            # ORDER BY id garantiza paginación determinista con offset-based range
            res = supabase.table(table_name).select(select_cols).order("id", desc=False).range(page * page_size, (page + 1) * page_size - 1).execute()
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1
        # Si no hay filas, devolver DataFrame con columnas explícitas para evitar KeyError
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_cols(select_cols))

    # 1. Personas
    df_p = fetch_all("personas", "id, comuna_id, tags, creado_en, telefono, barrio")

    # 2. Asociaciones
    df_a = fetch_all("asociaciones", "id, comuna_id, tipo, referente_nombre, referente_telefono")

    # 3. Interacciones (ampliamos a 180 días para tener más margen histórico)
    since_180 = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    def fetch_all_interacciones(table_name, select_cols, date_col, since_val):
        rows = []
        page = 0
        page_size = 1000
        while True:
            # ORDER BY id garantiza paginación determinista — sin esto .range() devuelve
            # filas repetidas o incompletas en páginas > 1
            res = (
                supabase.table(table_name)
                .select(select_cols)
                .gte(date_col, since_val)
                .order("id", desc=False)
                .range(page * page_size, (page + 1) * page_size - 1)
                .execute()
            )
            data = res.data or []
            rows.extend(data)
            if len(data) < page_size:
                break
            page += 1
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=_cols(select_cols))

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
    "NO CONTACTADO": "#6b7280", "NO RESPONDIÓ": "#6b7280", "NO VISITADO": "#6b7280", "NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 POSITIVO": "#10b981", "🟡 NEUTRO": "#f59e0b", "🔴 NEGATIVO": "#ef4444",
    "⚫ NO RESPONDIÓ": "#6b7280", "⚫ NO CONTACTADO": "#6b7280", "⚫ NO VISITADO": "#6b7280", "🟠 NÚMERO INEXISTENTE/EQUIVOCADO": "#f97316",
    "🟢 <30 días": "#10b981", "🟡 30-60 días": "#f59e0b", "🔴 >60 días": "#ef4444", 
    "⚫ SIN CONTACTO": "#6b7280", "⚫ SIN VISITA": "#6b7280"
}

LABELS_TIEMPO_P = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN CONTACTO"]
LABELS_TIEMPO_A = ["🟢 <30 días", "🟡 30-60 días", "🔴 >60 días", "⚫ SIN VISITA"]
LABELS_RESP_P = ["🟢 POSITIVO", "🟡 NEUTRO", "🔴 NEGATIVO", "🟠 NÚMERO INEXISTENTE/EQUIVOCADO", "⚫ NO RESPONDIÓ", "⚫ NO CONTACTADO"]
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
    if is_asoc: return "⚫ NO VISITADO"
    if s == "NO RESPONDIÓ": return "⚫ NO RESPONDIÓ"
    return "⚫ NO CONTACTADO"

def _norm_comuna(val) -> str:
    """Normaliza un valor de comuna_id a string entero, tolerante a float ('1.0' → '1')."""
    try:
        return str(int(float(val)))
    except (ValueError, TypeError):
        return ""


def _comuna_sort_key(c):
    """Clave de orden para comunas: 1→15 numérico, 'Desconocido'/vacío al final."""
    s = str(c).strip()
    try:
        return (0, int(float(s)))
    except (ValueError, TypeError):
        return (1, 0)


def filter_data(df_p, df_a, df_ip, df_ia, df_r, filters):
    f_comunas    = filters.get("comunas", [])
    f_barrios    = filters.get("barrios", [])
    f_tags       = filters.get("tags", [])
    f_fechas     = filters.get("fechas", [])
    f_verticales = filters.get("verticales", [])
    f_tipo_asoc  = filters.get("tipo_asoc", [])

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
        # Normalizamos a entero-string para tolerar float64 de pandas ('1.0' → '1')
        str_comunas = [str(int(c)) for c in f_comunas]
        p = p[p['comuna_id'].apply(_norm_comuna).isin(str_comunas)]
        a = a[a['comuna_id'].apply(_norm_comuna).isin(str_comunas)]

        # Reuniones de esas comunas + todas las de scope VERTICAL/GLOBAL (no tienen comarca)
        if not r.empty:
            r_comunas = r[(r['scope_tipo'] == "COMUNA") & (r['scope_valor'].astype(str).isin(str_comunas))]
            r_no_comunas = r[r['scope_tipo'] != "COMUNA"]
            r = pd.concat([r_comunas, r_no_comunas], ignore_index=True)

        # Propagar a interacciones
        p_ids, a_ids = set(p['id'].tolist()), set(a['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]
        ia = ia[ia['asociacion_id'].isin(a_ids)]
    # else: sin filtro de comunas → todas las reuniones visibles (incluye VERTICAL y GLOBAL)

    # 2b. Filtro Barrio (Multiselect)
    if f_barrios:
        p = p[p['barrio'].isin(f_barrios)]
        if 'barrio' in a.columns:
            a = a[a['barrio'].isin(f_barrios)]

        # Propagar a interacciones
        p_ids, a_ids = set(p['id'].tolist()), set(a['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]
        ia = ia[ia['asociacion_id'].isin(a_ids)]

    # 3. Filtro Vertical Personas (Tags - Multiselect)
    if f_tags:
        # OR Logic: Si tiene al menos uno de los tags seleccionados
        f_tags_upper = [t.upper() for t in f_tags]
        p['tag_list'] = p['tags'].apply(_parse_tags)
        p = p[p['tag_list'].apply(lambda x: any(t in x for t in f_tags_upper))]
        p_ids = set(p['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]

    # 4. Filtro Vertical de Segmento (afecta personas por tag, asociaciones por tipo Y reuniones por scope_valor)
    if f_verticales:
        # Tags de personas que corresponden a las verticales seleccionadas
        tags_verticales = {
            VERTICAL_TAG_MAP[v]
            for v in f_verticales
            if VERTICAL_TAG_MAP.get(v)
        }
        # Tipos de asociaciones que corresponden a las verticales seleccionadas
        tipos_verticales = {
            VERTICAL_TIPO_MAP[v]
            for v in f_verticales
            if VERTICAL_TIPO_MAP.get(v)
        }

        # Personas: filtrar por tag si la vertical tiene mapeo
        if tags_verticales and not p.empty:
            tags_upper = {t.upper() for t in tags_verticales}
            p['_tag_list'] = p['tags'].apply(_parse_tags)
            p = p[p['_tag_list'].apply(lambda x: any(t in x for t in tags_upper))].copy()
            p.drop(columns=['_tag_list'], inplace=True)
        elif not tags_verticales:
            # Vertical sin mapeo de personas → personas = 0
            p = p.head(0).copy()
        p_ids = set(p['id'].tolist())
        ip = ip[ip['persona_id'].isin(p_ids)]

        # Asociaciones: filtrar por tipo si la vertical tiene mapeo, si no → asociaciones = 0
        if not a.empty:
            if tipos_verticales:
                a = a[a['tipo'].isin(tipos_verticales)].copy()
            else:
                # Vertical sin mapeo de asociaciones (ej. Generación Plateada) → asociaciones = 0
                a = a.head(0).copy()
        a_ids = set(a['id'].tolist())
        ia = ia[ia['asociacion_id'].isin(a_ids)]

        # Reuniones: scope_tipo=VERTICAL con scope_valor en las verticales seleccionadas
        if not r.empty:
            r = r[(r['scope_tipo'] == "VERTICAL") & (r['scope_valor'].isin(f_verticales))].copy()

    # 5. Filtro directo por Tipo de Asociación (multiselect independiente)
    #    Al filtrar solo por tipo de asociación (sin vertical), personas = 0
    #    porque no hay relación directa persona ↔ tipo de asociación
    if f_tipo_asoc:
        if not a.empty:
            a = a[a['tipo'].isin(f_tipo_asoc)].copy()
        a_ids = set(a['id'].tolist())
        ia = ia[ia['asociacion_id'].isin(a_ids)]
        if not f_verticales:
            # Sin vertical activa, las personas no tienen contexto en este filtro
            p = p.head(0).copy()
            ip = ip.head(0).copy()

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
        
        # Comunas disponibles: tolerante a float64 de pandas (1.0 → 1)
        comunas_available = sorted(set(
            int(float(x)) for x in df_p_raw['comuna_id'].dropna().unique()
            if str(x) not in ('', 'nan', 'None')
        ))

        with fcol1:
            f_comunas = st.multiselect("Comunas (Vacío = Todas)", options=comunas_available)

            # Filtro de Barrios
            barrios_p = set(df_p_raw['barrio'].dropna().unique())
            barrios_a = set(df_a_raw['barrio'].dropna().unique()) if 'barrio' in df_a_raw.columns else set()
            all_barrios = sorted(list(barrios_p.union(barrios_a)))

            # Si hay comunas seleccionadas, reducir opciones de barrios usando la misma normalización
            if f_comunas:
                str_comunas_norm = [str(int(c)) for c in f_comunas]
                df_p_filt = df_p_raw[df_p_raw['comuna_id'].apply(_norm_comuna).isin(str_comunas_norm)]
                barrios_p_filt = set(df_p_filt['barrio'].dropna().unique())
                barrios_a_filt = set()
                if 'barrio' in df_a_raw.columns:
                    df_a_filt = df_a_raw[df_a_raw['comuna_id'].apply(_norm_comuna).isin(str_comunas_norm)]
                    barrios_a_filt = set(df_a_filt['barrio'].dropna().unique())
                all_barrios = sorted(list(barrios_p_filt.union(barrios_a_filt)))

            f_barrios = st.multiselect("Barrios", options=all_barrios)
        
        with fcol2:
            # Filtro por Vertical de Segmento (filtra personas por tag Y asociaciones por tipo)
            vertical_options = {VERTICAL_LABELS[v]: v for v in VERTICALES_SEGMENTOS if v in VERTICAL_LABELS}
            f_verticales_labels = st.multiselect(
                "Verticales de Segmento",
                options=list(vertical_options.keys()),
                help="Filtra personas por su tag correspondiente y asociaciones por su tipo."
            )
            f_verticales = [vertical_options[lbl] for lbl in f_verticales_labels]

            all_tags = set(personas_edicion.TAGS_SUGERIDOS)
            for row in df_p_raw['tags'].dropna():
                for t in _parse_tags(row): all_tags.add(t)
            f_tags = st.multiselect("Tags Personas (OR)", options=sorted(list(all_tags)))

        with fcol3:
            tipos_available = sorted([str(x) for x in df_a_raw['tipo'].dropna().unique()])
            f_tipo_asoc = st.multiselect("Tipo de Asociación", options=tipos_available)

            today = datetime.date.today()
            def_start = today - datetime.timedelta(days=30)
            f_fechas = st.date_input("Rango de Interacciones", value=(def_start, today))

    filters = {"comunas": f_comunas, "barrios": f_barrios, "tags": f_tags, "fechas": f_fechas, "verticales": f_verticales, "tipo_asoc": f_tipo_asoc}
    p, a, ip, ia, r = filter_data(df_p_raw, df_a_raw, df_ip_raw, df_ia_raw, df_r_raw, filters)

    # --- ENRIQUECIMIENTO GLOBAL (Comuna IDs) ---
    # Mapeamos comuna_id a las interacciones para usarlas en todos los tabs (Tendencias, Territorio, etc)
    p_map_global = df_p_raw[['id', 'comuna_id']].set_index('id')['comuna_id'].to_dict()
    a_map_global = df_a_raw[['id', 'comuna_id']].set_index('id')['comuna_id'].to_dict()
    
    ip['comuna_id'] = ip['persona_id'].map(p_map_global).fillna("Desconocido")
    ia['comuna_id'] = ia['asociacion_id'].map(a_map_global).fillna("Desconocido")

    # --- CALCULO DE SEMAFOROS ---
    def _calc_sem(df_obj, df_int_raw, id_col, is_asoc=False):
        # Siempre devolvemos con las columnas esperadas para evitar KeyError en la UI
        if df_obj.empty:
            df_obj = df_obj.copy()
            df_obj['Última Fecha'] = pd.Series(dtype=str)
            df_obj['Resultado'] = pd.Series(dtype=str)
            return df_obj
        last_int = df_int_raw.sort_values('fecha', ascending=False).drop_duplicates(id_col)
        df_merged = df_obj.merge(last_int[[id_col, 'fecha', 'respuesta']], left_on='id', right_on=id_col, how='left')
        today_ts = pd.Timestamp.now().normalize()
        df_merged['dias_contacto'] = (today_ts - pd.to_datetime(df_merged['fecha'])).dt.days
        df_merged['Última Fecha'] = df_merged['dias_contacto'].apply(lambda x: _semaforo_tiempo_label(x, is_asoc))
        df_merged['Resultado'] = df_merged['respuesta'].apply(lambda x: _semaforo_respuesta_label(x, is_asoc))
        return df_merged

    p_sem = _calc_sem(p, ip, 'persona_id', is_asoc=False)
    a_sem = _calc_sem(a, ia, 'asociacion_id', is_asoc=True)

    # --- KPIs ---
    st.markdown("### 📊 Resumen Ejecutivo")
    k1, k2, k3, k4 = st.columns(4)
    total_p, total_a = len(p), len(a)
    # Usamos ip / ia (ya filtrados por fecha y demás filtros)
    contacted_p = ip['persona_id'].nunique() if not ip.empty else 0
    contacted_a = ia['asociacion_id'].nunique() if not ia.empty else 0
    k1.metric("Total Personas", f"{total_p:,}")
    k2.metric("Total Asociaciones", f"{total_a:,}")
    k3.metric(
        "% Personas Contactadas",
        f"{(contacted_p/total_p*100):.1f}%" if total_p>0 else "0%",
        delta=f"{contacted_p:,} contactadas",
        delta_color="off",
    )
    k4.metric(
        "% Asoc. Visitadas",
        f"{(contacted_a/total_a*100):.1f}%" if total_a>0 else "0%",
        delta=f"{contacted_a:,} visitadas",
        delta_color="off",
    )

    tab_territorio, tab_tematico, tab_tendencias, tab_reuniones, tab_calidad = st.tabs([
        "📍 Territorial (Comunas)", "🏷️ Temático (Verticales)", "📈 Tendencias", "🤝 Reuniones", "🔍 Auditoría y Calidad"
    ])

    with tab_territorio:
        # --- SEMÁFOROS (Calidad de Contacto) ---
        st.subheader("Semáforos de Gestión (Calidad de Contacto)")
        
        def _semaforos_ui(df, title_suffix, is_asoc=False):
            with st.expander(f"Ver Semáforos de {title_suffix}", expanded=True):
                if df.empty or 'Resultado' not in df.columns or 'Última Fecha' not in df.columns:
                    st.info(f"No hay datos de {title_suffix} para los filtros seleccionados.")
                    return

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

        st.divider()
        st.subheader("📊 Totales por Comuna")

        # 3. Interacciones de Personas por Comuna (barras)
        if not ip.empty:
            ip_bar = ip.copy()
            ip_bar["Comuna"] = ip_bar["comuna_id"].apply(lambda v: _norm_comuna(v) or "Desconocido")
            bar_p = ip_bar.groupby("Comuna").size().reset_index(name="Interacciones")
            bar_p = bar_p.sort_values("Comuna", key=lambda s: s.map(_comuna_sort_key))
            fig_bp = px.bar(bar_p, x="Comuna", y="Interacciones", title="Interacciones de Personas por Comuna")
            st.plotly_chart(fig_bp, use_container_width=True)
        else:
            st.info("Sin interacciones con Personas para mostrar por comuna.")

        # 4. Visitas a Asociaciones por Comuna (barras)
        if not ia.empty:
            ia_bar = ia.copy()
            ia_bar["Comuna"] = ia_bar["comuna_id"].apply(lambda v: _norm_comuna(v) or "Desconocido")
            bar_a = ia_bar.groupby("Comuna").size().reset_index(name="Interacciones")
            bar_a = bar_a.sort_values("Comuna", key=lambda s: s.map(_comuna_sort_key))
            fig_ba = px.bar(bar_a, x="Comuna", y="Interacciones", title="Visitas a Asociaciones por Comuna")
            st.plotly_chart(fig_ba, use_container_width=True)
        else:
            st.info("Sin visitas a Asociaciones para mostrar por comuna.")

    with tab_reuniones:
        st.subheader("🤝 Reuniones realizadas")
        if r.empty:
            st.info("No hay reuniones registradas en este periodo / filtros.")
        else:
            # Grafico Lineas por Comuna
            r_graph = r.copy()
            r_graph['fecha_dt'] = pd.to_datetime(r_graph['fecha']).dt.date
            
            # Agrupar por fecha y ámbito (puede ser comuna o vertical)
            r_counts = r_graph.groupby(['fecha_dt', 'scope_tipo', 'scope_valor']).size().reset_index(name='Cant')
            r_counts['Ámbito'] = r_counts['scope_tipo'] + ": " + r_counts['scope_valor'].astype(str)

            fig_r = px.line(r_counts, x='fecha_dt', y='Cant', color='Ámbito', title="Reuniones por Ámbito (Evolución)", markers=True)
            st.plotly_chart(fig_r, use_container_width=True)
            
            with st.expander("Ver detalle de reuniones"):
                st.dataframe(r[['fecha', 'scope_valor', 'scope_tipo', 'id']], use_container_width=True)

            st.divider()
            # Reuniones por Comuna (solo scope COMUNA; VERTICAL/GLOBAL no tienen comuna)
            r_com = r[r["scope_tipo"] == "COMUNA"].copy()
            if r_com.empty:
                st.caption("No hay reuniones de ámbito Comuna en este período.")
            else:
                r_com["Comuna"] = r_com["scope_valor"].apply(lambda v: _norm_comuna(v) or "Desconocido")
                bar_r = r_com.groupby("Comuna").size().reset_index(name="Reuniones")
                bar_r = bar_r.sort_values("Comuna", key=lambda s: s.map(_comuna_sort_key))
                fig_rc = px.bar(bar_r, x="Comuna", y="Reuniones", title="Reuniones por Comuna")
                st.plotly_chart(fig_rc, use_container_width=True)

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


    st.sidebar.markdown("---")
    st.sidebar.caption(f"Actualizado: {datetime.datetime.now().strftime('%H:%M')}")

def render(user):
    render_dashboard_master_global(user)
