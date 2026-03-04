# reuniones_app.py
import streamlit as st
import pandas as pd
import datetime
import personas_scope_rules


# =========================
# CONFIG / CONSTANTES
# =========================
TIPOS_REUNION = [
    "comuna", 
    "vecinos", 
    "comerciantes", 
    "juventud", 
    "generación plateada", 
    "profesionales", 
    "migrantes", 
    "culto"
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

    res = q.order("fecha", desc=True).order("created_at", desc=True).limit(500).execute()
    return pd.DataFrame(res.data or [])

def search_personas(supabase, user, term):
    if not term or len(term) < 3:
        return []
    
    q = supabase.table("personas").select("id, nombre_apellido, dni, telefono")
    q = personas_scope_rules.apply_personas_visibility_filter(q, user)
    q = q.or_(f"nombre_apellido.ilike.%{term}%,dni.ilike.%{term}%,telefono.ilike.%{term}%")
    res = q.limit(20).execute()
    return res.data or []


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
        "participantes_estimados": data.get("participantes_estimados"),
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
    st.header("🤝 Reuniones")
    
    # =========================
    # 1. Formulario de Carga
    # =========================
    with st.expander("➕ Cargar nueva reunión", expanded=False):
        # --- Selector de Asistentes (FUERA del form para interactividad) ---
        st.markdown("#### 👥 Asistentes")
        
        if "reunion_form_key" not in st.session_state:
            st.session_state["reunion_form_key"] = 0
            
        if "reunion_asistentes_opts" not in st.session_state:
            st.session_state["reunion_asistentes_opts"] = {}

        col_search, col_reset = st.columns([3, 1])
        with col_search:
            search_query = st.text_input("Buscar asistentes (Nombre, DNI...)", placeholder="Escribí al menos 3 letras...", key="search_asist_reunion")
        with col_reset:
            if st.button("Limpiar búsqueda"):
                st.session_state["reunion_asistentes_opts"] = {}
        
        if len(search_query.strip()) >= 3:
            found = search_personas(supabase, user, search_query.strip())
            new_opts = {p['id']: f"{p['nombre_apellido']} ({p['dni'] or 'S/DNI'})" for p in found}
            st.session_state["reunion_asistentes_opts"].update(new_opts)
            
        # Opciones acumuladas
        current_opts = st.session_state["reunion_asistentes_opts"]
        
        # Dynamic key to allow reset
        ms_key = f"ms_reunion_asistentes_{st.session_state['reunion_form_key']}"
        
        selected_asistentes_ids = st.multiselect(
            "Seleccionar asistentes confirmados",
            options=current_opts.keys(),
            format_func=lambda x: current_opts[x],
            key=ms_key
        )
        st.caption(f"Seleccionados: {len(selected_asistentes_ids)}")
        st.markdown("---")

        with st.form("form_nueva_reunion", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                fecha = st.date_input("Fecha *", value=datetime.date.today())
                tipo = st.selectbox("Tipo de reunión *", TIPOS_REUNION)
                titulo = st.text_input("Título / Tema (Opcional)", placeholder="Ej: Mesa de trabajo Jóvenes")
                lugar = st.text_input("Lugar (Opcional)", placeholder="Ej: Club Social Comuna 1")
                
            with c2:
                participantes = st.number_input("Participantes estimados (Opcional)", min_value=0, value=0)
                descripcion = st.text_area("Descripción / Notas", placeholder="Resumen de lo hablado...", height=150)
            
            submit = st.form_submit_button("✅ Guardar reunión", use_container_width=True)
            
            if submit:
                try:
                    insert_reunion(supabase, user, {
                        "fecha": fecha,
                        "tipo": tipo,
                        "titulo": titulo.strip() if titulo.strip() else f"Reunión de {tipo}",
                        "descripcion": descripcion,
                        "lugar": lugar,
                        "participantes_estimados": participantes if participantes > 0 else None
                    }, asistentes_ids=selected_asistentes_ids)  # Pasamos los asistentes
                    
                    st.success("¡Reunión guardada correctamente con asistentes!")
                    
                    # Reset multiselect and search by changing key
                    st.session_state["reunion_form_key"] += 1
                    st.session_state["reunion_asistentes_opts"] = {}
                    
                    st.balloons()
                    st.rerun() # Force rerun to update UI with new empty widget
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

    st.markdown("---")

    # =========================
    # 2. Listado e Historial
    # =========================
    st.subheader("📋 Historial de reuniones")
    
    # Filtros
    with st.container(border=True):
        f1, f2, f3 = st.columns([1, 1, 2])
        with f1:
            fecha_desde = st.date_input("Desde", value=datetime.date.today() - datetime.timedelta(days=30))
        with f2:
            fecha_hasta = st.date_input("Hasta", value=datetime.date.today())
        with f3:
            search_text = st.text_input("Buscar (Tema o Descripción)", placeholder="Buscar...")
            
        f4, f5 = st.columns([1, 1])
        with f4:
            tipo_flt = st.selectbox("Filtrar por tipo", ["Todos"] + TIPOS_REUNION, key="flt_reunion_tipo")
            
    # Fetch Data
    df = fetch_reuniones(supabase, user, filters={
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "tipo": tipo_flt,
        "search": search_text
    })
    
    if df.empty:
        st.info("No se encontraron reuniones con los filtros aplicados.")
    else:
        st.caption(f"Mostrando {len(df)} reuniones.")
        
        # Reformatear para visualización
        df_display = df.copy()
        
        # Columnas amigables
        cols_map = {
            "fecha": "Fecha",
            "tipo": "Tipo",
            "titulo": "Tema",
            "lugar": "Lugar",
            "participantes_estimados": "Part.",
            "description": "Notas",
            "created_by_nombre": "Creado por"
        }
        
        cols_to_show = ["fecha", "tipo", "titulo", "lugar", "participantes_estimados", "created_by_nombre"]
        df_display = df_display[cols_to_show].rename(columns=cols_map)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        # Visualización de detalles (opcional)
        if st.checkbox("Ver descripciones desarrolladas"):
            for idx, row in df.iterrows():
                with st.expander(f"{row['fecha']} - {row['titulo']} ({row['tipo']})"):
                    st.write(f"**Lugar:** {row['lugar'] or '-'}")
                    st.write(f"**Participantes:** {row['participantes_estimados'] or '-'}")
                    st.write(f"**Descripción:**")
                    st.write(row["descripcion"] or "_Sin notas_")
                    st.caption(f"ID: {row['id']} | Cargado por: {row['created_by_nombre']} el {row['created_at']}")
