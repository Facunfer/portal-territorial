# reuniones_app.py
import streamlit as st
import pandas as pd
import datetime
import personas_scope_rules
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode


# =========================
# CONFIG / CONSTANTES
# =========================
TIPOS_ACTIVIDAD = [
    "Reunión",
    "Reunión de Comuna",
    "Reunión de Vecinos",
    "Reunión de Comerciantes",
    "Reunión de Juventud",
    "Reunión de Libertad Plateada",
    "Reunión de Profesionales",
    "Reunión de Educación",
    "Reunión de Salud",
    "Reunión de Culto",
    "Caminata",
]

def get_reuniones_scope(user: dict):
    """
    Determina el scope de las reuniones según el usuario.
    Retorna (scope_tipo, scope_valor)
    """
    ambito = (user.get("ambito") or "").strip().upper()
    rol = (user.get("rol") or "").strip().upper()
    
    # GLOBAL MASTER ve todo
    if ambito == "GLOBAL" and rol == "MASTER":
        return "GLOBAL", None
        
    # SEGMENTOS ve todo
    if ambito == "SEGMENTOS":
        return "GLOBAL", None
        
    # COMUNA
    if ambito == "COMUNA":
        return "COMUNA", str(user.get("comuna_id") or "")
        
    # VERTICAL (independiente de si es VERTICAL_PERSONAS o VERTICAL_ASOCIACIONES)
    vertical = (user.get("vertical") or "").strip().upper()
    if vertical and vertical != "NONE":
        return "VERTICAL", vertical
        
    return "GLOBAL", None

def fetch_reuniones(supabase, user_ctx: dict, filters: dict = None):
    """Consulta reuniones aplicando el scope del usuario y filtros. DESC."""
    scope_tipo, scope_valor = get_reuniones_scope(user_ctx)
    
    q = supabase.table("reuniones").select("*")
    
    # Aplicar Scope
    if scope_tipo == "COMUNA":
        q = q.eq("scope_tipo", "COMUNA").eq("scope_valor", scope_valor)
    elif scope_tipo == "VERTICAL":
        q = q.eq("scope_tipo", "VERTICAL").eq("scope_valor", scope_valor)
    
    # Aplicar Filtros UI
    if filters:
        if filters.get("fecha_desde"):
            q = q.gte("fecha", str(filters["fecha_desde"]))
        if filters.get("fecha_hasta"):
            q = q.lte("fecha", str(filters["fecha_hasta"]))
        if filters.get("tipo") and filters["tipo"] != "Todos":
            q = q.eq("tipo", filters["tipo"])
        if filters.get("search"):
            search = filters["search"].strip()
            # Or query for titulo/descripcion
            q = q.or_(f"titulo.ilike.%{search}%,descripcion.ilike.%{search}%")

        if filters.get("solo_programadas"):
            q = q.is_("realizada", "null")

    res = q.order("fecha", desc=True).order("created_at", desc=True).limit(500).execute()
    df = pd.DataFrame(res.data or [])

    if filters and filters.get("solo_historial") and not df.empty:
        hoy_str = str(datetime.date.today())
        mask = (
            (df["realizada"] == True) |
            (df["realizada"].isna() & (df["fecha"] < hoy_str))
        )
        df = df[mask]

    if filters and filters.get("solo_programadas") and not df.empty:
        df = df[df["realizada"].isna()]

    return df

def fetch_personas_para_reunion(supabase, user):
    q = supabase.table("personas").select("id, nombre_apellido, dni, telefono, comuna_id, tags")
    q = personas_scope_rules.apply_personas_visibility_filter(q, user)
    # Paginar
    rows, page, page_size = [], 0, 1000
    while True:
        res = q.range(page * page_size, (page + 1) * page_size - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        page += 1
    return pd.DataFrame(rows)


def insert_reunion(supabase, user: dict, data: dict, asistentes_ids: list = None):
    """Inserta una nueva reunión calculando el scope automáticamente."""
    scope_tipo, scope_valor = get_reuniones_scope(user)
    
    payload = {
        "created_by_user_id": user.get("id"),
        "created_by_nombre": user.get("username"),
        "scope_tipo": scope_tipo,
        "scope_valor": scope_valor,
        "fecha": str(data["fecha"]),
        "tipo": data["tipo"],
        "titulo": data["titulo"],
        "descripcion": data.get("descripcion"),
        "lugar": data.get("lugar"),
        "necesita_cobertura": data.get("necesita_cobertura", False),
        "realizada": data.get("realizada"),
    }
    
    res = supabase.table("reuniones").insert(payload).execute()
    if not res.data:
        return res
        
    new_reunion_id = res.data[0]["id"]
    
    if asistentes_ids:
        # 1. Insertar asistentes en tabla puente
        asistentes_data = []
        interacciones_data = []
        hoy = str(datetime.date.today())
        
        for pid in asistentes_ids:
            asistentes_data.append({
                "reunion_id": new_reunion_id,
                "persona_id": pid,
                "created_by": user.get("id")
            })
            
            # Chequeo muy básico de duplicados en memoria no es ideal, pero confiamos 
            # en que insertamos todo junto. Si la reunión es nueva, no debería haber duplicados.
            
            # 2. Interacciones automáticas
            interacciones_data.append({
                 "persona_id": pid,
                 "tipo": "Participó de reunión",
                 "respuesta": "POSITIVO",
                 "fecha": str(data["fecha"]), # Usamos fecha de reunión
                 "reunion_id": new_reunion_id,
                 "created_by": user.get("id"),
                 "observaciones": f"Asistió a reunión: {data['titulo']}"
            })
            
        if asistentes_data:
            supabase.table("reuniones_asistentes").insert(asistentes_data).execute()
        if interacciones_data:
            supabase.table("interacciones_personas").insert(interacciones_data).execute()
            
    return res

def render_reuniones_screen(user: dict, supabase):
    st.header("🤝 Reuniones / Actividades")
    
    # =========================
    # 1. Formulario de Carga
    # =========================
    with st.expander("➕ Cargar nueva actividad", expanded=False):
        # --- Selector de Asistentes (FUERA del form para interactividad) ---
        st.markdown("#### 👥 Asistentes")
        
        if "reunion_form_key" not in st.session_state:
            st.session_state["reunion_form_key"] = 0

        df_personas_visible = fetch_personas_para_reunion(supabase, user)
        # Filtro rápido
        search_rapido = st.text_input("Filtrar rápido asistentes (Nombre, DNI, Teléfono...)", key=f"tbl_search_{st.session_state['reunion_form_key']}")
        if search_rapido and not df_personas_visible.empty:
            df_personas_visible = df_personas_visible[
                df_personas_visible["nombre_apellido"].fillna("").str.contains(search_rapido, case=False) |
                df_personas_visible["dni"].fillna("").astype(str).str.contains(search_rapido) |
                df_personas_visible["telefono"].fillna("").astype(str).str.contains(search_rapido)
            ]

        selected_asistentes_ids = []
        if not df_personas_visible.empty:
            gb = GridOptionsBuilder.from_dataframe(df_personas_visible)
            gb.configure_default_column(sortable=True, filter=True, resizable=True)
            first_col = df_personas_visible.columns[0]
            gb.configure_column(first_col, checkboxSelection=True, headerCheckboxSelection=True)
            gb.configure_selection(selection_mode="multiple", use_checkbox=True)
            gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
            grid_options = gb.build()

            grid_response = AgGrid(
                df_personas_visible,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                theme="streamlit",
                height=400,
                fit_columns_on_grid_load=True,
                key=f"grid_reunion_asist_{st.session_state['reunion_form_key']}"
            )

            selected_rows = grid_response.get("selected_rows", [])
            # AgGrid returns a dataframe under "selected_rows" in some versions, or list in others
            if isinstance(selected_rows, list):
                selected_asistentes_ids = [int(r["id"]) for r in selected_rows if r.get("id")]
            elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
                selected_asistentes_ids = [int(r["id"]) for _, r in selected_rows.iterrows() if r.get("id") is not None]

        st.caption(f"Asistentes seleccionados: {len(selected_asistentes_ids)}")
        st.markdown("---")

        with st.form("form_nueva_reunion", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                fecha = st.date_input("Fecha *", value=datetime.date.today())
                tipo = st.selectbox("Tipo de actividad *", TIPOS_ACTIVIDAD)
                titulo = st.text_input("Título / Tema (Opcional)", placeholder="Ej: Mesa de trabajo Jóvenes")
                lugar = st.text_input("Lugar (Opcional)", placeholder="Ej: Club Social Comuna 1")
                
            with c2:
                necesita_cobertura = st.checkbox("Necesita cobertura", value=False)
                descripcion = st.text_area("Descripción / Notas", placeholder="Resumen de lo hablado...", height=150)
            
            submit = st.form_submit_button("✅ Guardar actividad", use_container_width=True)
            
            if submit:
                try:
                    hoy = datetime.date.today()
                    es_pasada = fecha < hoy
                    
                    insert_reunion(supabase, user, {
                        "fecha": fecha,
                        "tipo": tipo,
                        "titulo": titulo.strip() if titulo.strip() else f"{tipo}",
                        "descripcion": descripcion,
                        "lugar": lugar,
                        "necesita_cobertura": necesita_cobertura,
                        "realizada": True if es_pasada else None,
                    }, asistentes_ids=selected_asistentes_ids)  # Pasamos los asistentes
                    
                    if es_pasada:
                        st.success("¡Actividad guardada en el historial!")
                    else:
                        st.success("¡Actividad programada correctamente!")
                    
                    # Reset multiselect and search by changing key
                    st.session_state["reunion_form_key"] += 1
                    st.session_state["reunion_asistentes_opts"] = {}
                    
                    st.balloons()
                    st.rerun() # Force rerun to update UI with new empty widget
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

    st.markdown("---")

    # =========================
    # 2. TABS: Programadas + Historial
    # =========================
    tab_prog, tab_hist = st.tabs(["📅 Actividades Programadas", "📋 Historial de Actividades"])

    # -------------------------
    # TAB 1: PROGRAMADAS (fecha >= hoy Y realizada IS NULL)
    # -------------------------
    with tab_prog:
        st.subheader("📅 Actividades Programadas")
        st.caption("Actividades con fecha de hoy o futura que aún no fueron confirmadas.")
        
        # Fetch programadas
        hoy = datetime.date.today()
        df_prog = fetch_reuniones(supabase, user, filters={
            "fecha_desde": hoy,
            "solo_programadas": True,
        })
        
        if df_prog.empty:
            st.info("No hay actividades programadas.")
        else:
            st.caption(f"Mostrando {len(df_prog)} actividades programadas.")
            
            for idx, row in df_prog.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        st.markdown(f"**{row['fecha']}** — {row['tipo']}")
                        st.markdown(f"_{row['titulo'] or 'Sin título'}_")
                        if row.get('lugar'):
                            st.caption(f"📍 {row['lugar']}")
                        if row.get('necesita_cobertura'):
                            st.caption("📸 Necesita cobertura")
                    with c2:
                        if st.button("✅ Se realizó", key=f"btn_realizada_{row['id']}"):
                            supabase.table("reuniones").update({"realizada": True}).eq("id", row["id"]).execute()
                            st.success("Marcada como realizada.")
                            st.rerun()
                    with c3:
                        if st.button("❌ No se hizo", key=f"btn_no_realizada_{row['id']}"):
                            supabase.table("reuniones").update({"realizada": False}).eq("id", row["id"]).execute()
                            st.warning("Marcada como no realizada.")
                            st.rerun()

    # -------------------------
    # TAB 2: HISTORIAL (fecha < hoy O realizada = TRUE)
    # -------------------------
    with tab_hist:
        st.subheader("📋 Historial de Actividades")
        
        # Filtros
        with st.container(border=True):
            f1, f2, f3 = st.columns([1, 1, 2])
            with f1:
                fecha_desde = st.date_input("Desde", value=datetime.date.today() - datetime.timedelta(days=30), key="hist_desde")
            with f2:
                fecha_hasta = st.date_input("Hasta", value=datetime.date.today(), key="hist_hasta")
            with f3:
                search_text = st.text_input("Buscar (Tema o Descripción)", placeholder="Buscar...", key="hist_search")
                
            f4, _ = st.columns([1, 1])
            with f4:
                tipo_flt = st.selectbox("Filtrar por tipo", ["Todos"] + TIPOS_ACTIVIDAD, key="flt_actividad_tipo")
        
        # Fetch historial
        df_hist = fetch_reuniones(supabase, user, filters={
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "tipo": tipo_flt,
            "search": search_text,
            "solo_historial": True,
        })
        
        if df_hist.empty:
            st.info("No se encontraron actividades con los filtros aplicados.")
        else:
            st.caption(f"Mostrando {len(df_hist)} actividades.")
            
            # Tabla
            cols_to_show = ["fecha", "tipo", "titulo", "lugar", "necesita_cobertura", "created_by_nombre"]
            cols_to_show = [c for c in cols_to_show if c in df_hist.columns]
            
            cols_map = {
                "fecha": "Fecha",
                "tipo": "Tipo",
                "titulo": "Tema",
                "lugar": "Lugar",
                "necesita_cobertura": "Cobertura",
                "created_by_nombre": "Creado por"
            }
            
            df_display = df_hist[cols_to_show].rename(columns=cols_map)
            
            # Formatear booleano de cobertura
            if "Cobertura" in df_display.columns:
                df_display["Cobertura"] = df_display["Cobertura"].apply(lambda x: "Sí" if x else "No")
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Detalles expandibles
            if st.checkbox("Ver descripciones desarrolladas", key="hist_descripciones"):
                for idx, row in df_hist.iterrows():
                    with st.expander(f"{row['fecha']} - {row['titulo']} ({row['tipo']})"):
                        st.write(f"**Lugar:** {row.get('lugar') or '-'}")
                        st.write(f"**Cobertura:** {'Sí' if row.get('necesita_cobertura') else 'No'}")
                        st.write(f"**Descripción:**")
                        st.write(row.get("descripcion") or "_Sin notas_")
                        st.caption(f"ID: {row['id']} | Cargado por: {row.get('created_by_nombre','-')} el {row.get('created_at','-')}")
