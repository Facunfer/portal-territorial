# reuniones_app.py
import streamlit as st
import pandas as pd
import datetime
import personas_scope_rules
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from constants import VERTICALES_SEGMENTOS


# =========================
# CONFIG / CONSTANTES
# =========================
TIPOS_ACTIVIDAD = [
    "Reunión",
    "Caminata",
    "Charla",
    "Otro",
]

SUBTIPOS_REUNION = [
    "Reunión de Comuna",
    "Reunión de Vecinos",
    "Reunión de Comerciantes",
    "Reunión de Juventud",
    "Reunión de Libertad Plateada",
    "Reunión de Profesionales",
    "Reunión de Educación",
    "Reunión de Salud",
    "Reunión de Culto",
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
        
    # SEGMENTOS ve todo excepto reuniones de ámbito COMUNA
    if ambito == "SEGMENTOS":
        return "SEGMENTOS_GLOBAL", None
        
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
    elif scope_tipo == "SEGMENTOS_GLOBAL":
        # SEGMENTOS ve GLOBAL y VERTICAL, pero NO las reuniones de COMUNA
        q = q.neq("scope_tipo", "COMUNA")
    
    # Aplicar Filtros UI
    if filters:
        if filters.get("fecha_desde"):
            q = q.gte("fecha", str(filters["fecha_desde"]))
        if filters.get("fecha_hasta"):
            q = q.lte("fecha", str(filters["fecha_hasta"]))
        if filters.get("tipo") and filters["tipo"] != "Todos":
            q = q.eq("tipo", filters["tipo"])
        if filters.get("search"):
            # Escapar caracteres especiales de PostgREST antes de interpolar
            search = filters["search"].strip()
            search_safe = search.replace("\\", "").replace(",", "").replace("%", r"\%")
            if search_safe:
                q = q.or_(f"titulo.ilike.%{search_safe}%,descripcion.ilike.%{search_safe}%")

        if filters.get("solo_programadas"):
            q = q.is_("realizada", "null")

    # Paginación completa — sin límite fijo de 500
    rows, page, page_size = [], 0, 1000
    q_ordered = q.order("fecha", desc=True).order("created_at", desc=True)
    while True:
        res = q_ordered.range(page * page_size, (page + 1) * page_size - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        page += 1
    df = pd.DataFrame(rows)

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

def fetch_personas_para_reunion(supabase, user, search: str = ""):
    """Carga personas filtrando por búsqueda en el servidor para no traer los 31k registros."""
    q = supabase.table("personas").select("id, nombre_apellido, dni, telefono, comuna_id, tags")
    q = personas_scope_rules.apply_personas_visibility_filter(q, user)
    if search:
        search_safe = search.replace("\\", "").replace("%", r"\%").replace(",", "")
        q = q.or_(f"nombre_apellido.ilike.%{search_safe}%,dni.ilike.%{search_safe}%,telefono.ilike.%{search_safe}%")
    q = q.limit(200)
    res = q.execute()
    return pd.DataFrame(res.data or [])


def insert_reunion(supabase, user: dict, data: dict, asistentes_ids: list = None):
    """Inserta una nueva reunión calculando el scope automáticamente."""
    scope_tipo, scope_valor = get_reuniones_scope(user)

    hora_val = data.get("hora")
    hora_str = hora_val.strftime("%H:%M:%S") if hora_val else None

    payload = {
        "created_by_user_id": user.get("id"),
        "created_by_nombre": user.get("username"),
        "scope_tipo": scope_tipo,
        "scope_valor": scope_valor,
        "fecha": str(data["fecha"]),
        "hora": hora_str,
        "tipo": data["tipo"],
        "subtipo_reunion": data.get("subtipo_reunion"),
        "titulo": data["titulo"],
        "descripcion": data.get("descripcion"),
        "lugar": data.get("lugar"),
        "realizada": data.get("realizada"),
    }
    
    try:
        res = supabase.table("reuniones").insert(payload).execute()
    except Exception as e:
        raise RuntimeError(f"No se pudo guardar la reunión: {e}") from e

    if not res.data:
        return res

    new_reunion_id = res.data[0]["id"]

    if asistentes_ids:
        asistentes_data = []
        interacciones_data = []

        for pid in asistentes_ids:
            asistentes_data.append({
                "reunion_id": new_reunion_id,
                "persona_id": pid,
                "created_by": user.get("id")
            })
            interacciones_data.append({
                "persona_id": pid,
                "tipo": "Participó de reunión",
                "respuesta": "POSITIVO",
                "fecha": str(data["fecha"]),
                "reunion_id": new_reunion_id,
                "created_by": user.get("id"),
                "observaciones": f"Asistió a reunión: {data['titulo']}"
            })

        try:
            if asistentes_data:
                supabase.table("reuniones_asistentes").insert(asistentes_data).execute()
            if interacciones_data:
                supabase.table("interacciones_personas").insert(interacciones_data).execute()
        except Exception as e:
            raise RuntimeError(f"Reunión guardada, pero falló el registro de asistentes: {e}") from e

    return res

def _scope_label(scope_tipo: str, scope_valor) -> str:
    """Etiqueta legible para el scope de una reunión."""
    st_val = (scope_tipo or "").strip().upper()
    sv = str(scope_valor or "").strip()
    if st_val == "VERTICAL":
        return f"Vertical: {sv}"
    if st_val == "COMUNA":
        return f"Comuna {sv}"
    return "Global"


def _build_scope_options(df: pd.DataFrame) -> list:
    """Opciones únicas de scope para el filtro SEGMENTOS."""
    if df.empty or "scope_tipo" not in df.columns:
        return []
    labels = df.apply(
        lambda r: _scope_label(r.get("scope_tipo"), r.get("scope_valor")), axis=1
    )
    return sorted(labels.unique().tolist())


def _apply_scope_filter(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Filtra el df por etiqueta de scope seleccionada."""
    return df[df.apply(
        lambda r: _scope_label(r.get("scope_tipo"), r.get("scope_valor")) == label, axis=1
    )]


def render_reuniones_screen(user: dict, supabase):
    st.header("🤝 Reuniones / Actividades")

    ambito = (user.get("ambito") or "").strip().upper()
    es_segmentos = ambito == "SEGMENTOS"

    # =========================
    # 1. Formulario de Carga (oculto para SEGMENTOS)
    # =========================
    if not es_segmentos:
      with st.expander("➕ Cargar nueva actividad", expanded=False):

        if "reunion_form_key" not in st.session_state:
            st.session_state["reunion_form_key"] = 0

        fkey = st.session_state["reunion_form_key"]

        # --- Tipo de actividad (FUERA del form para condicional subtipo) ---
        tipo = st.selectbox(
            "Tipo de actividad *",
            TIPOS_ACTIVIDAD,
            key=f"tipo_act_{fkey}"
        )
        subtipo_reunion = None
        if tipo == "Reunión":
            subtipo_reunion = st.selectbox(
                "Tipo de Reunión *",
                SUBTIPOS_REUNION,
                key=f"subtipo_act_{fkey}"
            )

        st.markdown("---")

        # --- Selector de Asistentes (desplegable opcional) ---
        mostrar_asistentes = st.checkbox(
            "👥 Seleccionar Asistentes",
            value=False,
            key=f"toggle_asist_{fkey}"
        )

        selected_asistentes_ids = []
        if mostrar_asistentes:
            search_rapido = st.text_input(
                "🔍 Buscar por Nombre, DNI o Teléfono (mínimo 3 caracteres)",
                key=f"tbl_search_{fkey}"
            )
            df_personas_visible = pd.DataFrame()
            if len(search_rapido) >= 3:
                df_personas_visible = fetch_personas_para_reunion(supabase, user, search=search_rapido)
            elif search_rapido:
                st.caption("Escribí al menos 3 caracteres para buscar.")

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
                    theme="alpine",
                    height=350,
                    fit_columns_on_grid_load=True,
                    key=f"grid_reunion_asist_{fkey}"
                )

                selected_rows = grid_response.get("selected_rows", [])
                if isinstance(selected_rows, list):
                    selected_asistentes_ids = [int(r["id"]) for r in selected_rows if r.get("id")]
                elif isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
                    selected_asistentes_ids = [int(r["id"]) for _, r in selected_rows.iterrows() if r.get("id") is not None]

            st.caption(f"Asistentes seleccionados: {len(selected_asistentes_ids)}")
            st.markdown("---")

        # --- Formulario principal ---
        with st.form("form_nueva_reunion", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                fecha = st.date_input("Fecha *", value=datetime.date.today())
                hora  = st.time_input("Hora *", value=datetime.time(10, 0))
                lugar = st.text_input("Lugar *", placeholder="Ej: Club Social Comuna 1")
                titulo = st.text_input("Título / Tema (Opcional)", placeholder="Ej: Mesa de trabajo Jóvenes")
            with c2:
                descripcion = st.text_area("Descripción / Notas", placeholder="Resumen de lo hablado...", height=180)

            submit = st.form_submit_button("✅ Guardar actividad", use_container_width=True)

            if submit:
                # Validación de obligatorios
                errores = []
                if not lugar.strip():
                    errores.append("El campo **Lugar** es obligatorio.")
                if tipo == "Reunión" and not subtipo_reunion:
                    errores.append("Seleccioná el **Tipo de Reunión**.")

                if errores:
                    for e in errores:
                        st.error(e)
                else:
                    try:
                        hoy = datetime.date.today()
                        es_pasada = fecha < hoy

                        insert_reunion(supabase, user, {
                            "fecha":           fecha,
                            "hora":            hora,
                            "tipo":            tipo,
                            "subtipo_reunion": subtipo_reunion,
                            "titulo":          titulo.strip() if titulo.strip() else (subtipo_reunion or tipo),
                            "descripcion":     descripcion,
                            "lugar":           lugar.strip(),
                            "realizada":       True if es_pasada else None,
                        }, asistentes_ids=selected_asistentes_ids)

                        if es_pasada:
                            st.success("¡Actividad guardada en el historial!")
                        else:
                            st.success("¡Actividad programada correctamente!")

                        st.session_state["reunion_form_key"] += 1
                        st.balloons()
                        st.rerun()
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

        # Filtro por vertical (solo para SEGMENTOS)
        if es_segmentos:
            sel_seg_prog = st.selectbox(
                "Filtrar por Vertical",
                ["Todos"] + VERTICALES_SEGMENTOS,
                key="prog_seg_flt",
            )
            if sel_seg_prog != "Todos" and not df_prog.empty:
                df_prog = df_prog[
                    df_prog["scope_tipo"].str.upper().eq("VERTICAL") &
                    df_prog["scope_valor"].eq(sel_seg_prog)
                ]

        if df_prog.empty:
            st.info("No hay actividades programadas.")
        else:
            st.caption(f"Mostrando {len(df_prog)} actividades programadas.")
            
            for idx, row in df_prog.iterrows():
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    with c1:
                        hora_str = str(row['hora'])[:5] if row.get('hora') else ""
                        tipo_label = row.get('subtipo_reunion') or row['tipo']
                        fecha_hora = f"**{row['fecha']}**" + (f" — {hora_str}" if hora_str else "")
                        st.markdown(f"{fecha_hora} — {tipo_label}")
                        st.markdown(f"_{row['titulo'] or 'Sin título'}_")
                        if row.get('lugar'):
                            st.caption(f"📍 {row['lugar']}")
                        if es_segmentos:
                            st.caption(f"🏷️ {_scope_label(row.get('scope_tipo'), row.get('scope_valor'))}")
                    with c2:
                        if st.button("✅ Se realizó", key=f"btn_realizada_{row['id']}"):
                            try:
                                supabase.table("reuniones").update({"realizada": True}).eq("id", row["id"]).execute()
                                st.success("Marcada como realizada.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo actualizar la reunión. Intentá de nuevo.")
                    with c3:
                        if st.button("❌ No se hizo", key=f"btn_no_realizada_{row['id']}"):
                            try:
                                supabase.table("reuniones").update({"realizada": False}).eq("id", row["id"]).execute()
                                st.warning("Marcada como no realizada.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo actualizar la reunión. Intentá de nuevo.")

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

        # Filtro por vertical (solo para SEGMENTOS)
        if es_segmentos:
            sel_seg_hist = st.selectbox(
                "Filtrar por Vertical",
                ["Todos"] + VERTICALES_SEGMENTOS,
                key="hist_seg_flt",
            )
            if sel_seg_hist != "Todos" and not df_hist.empty:
                df_hist = df_hist[
                    df_hist["scope_tipo"].str.upper().eq("VERTICAL") &
                    df_hist["scope_valor"].eq(sel_seg_hist)
                ]

        if df_hist.empty:
            st.info("No se encontraron actividades con los filtros aplicados.")
        else:
            st.caption(f"Mostrando {len(df_hist)} actividades.")

            # Para SEGMENTOS: agregar columna de segmento a la tabla
            if es_segmentos and "scope_tipo" in df_hist.columns:
                df_hist = df_hist.copy()
                df_hist["segmento"] = df_hist.apply(
                    lambda r: _scope_label(r.get("scope_tipo"), r.get("scope_valor")), axis=1
                )

            # Tabla
            cols_to_show = ["fecha", "hora", "tipo", "subtipo_reunion", "titulo", "lugar", "created_by_nombre"]
            if es_segmentos:
                cols_to_show.insert(2, "segmento")
            cols_to_show = [c for c in cols_to_show if c in df_hist.columns]

            cols_map = {
                "fecha": "Fecha",
                "hora": "Hora",
                "segmento": "Segmento",
                "tipo": "Tipo",
                "subtipo_reunion": "Subtipo",
                "titulo": "Tema",
                "lugar": "Lugar",
                "created_by_nombre": "Creado por",
            }

            df_display = df_hist[cols_to_show].rename(columns=cols_map)

            # Formatear hora: mostrar solo HH:MM
            if "Hora" in df_display.columns:
                df_display["Hora"] = df_display["Hora"].apply(
                    lambda x: str(x)[:5] if pd.notna(x) and x else ""
                )

            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Detalles expandibles
            if st.checkbox("Ver descripciones desarrolladas", key="hist_descripciones"):
                for idx, row in df_hist.iterrows():
                    hora_str = str(row['hora'])[:5] if row.get('hora') else "-"
                    subtipo_str = row.get('subtipo_reunion') or "-"
                    with st.expander(f"{row['fecha']} - {row['titulo']} ({row['tipo']})"):
                        if es_segmentos:
                            st.caption(f"🏷️ {_scope_label(row.get('scope_tipo'), row.get('scope_valor'))}")
                        st.write(f"**Hora:** {hora_str}")
                        st.write(f"**Subtipo:** {subtipo_str}")
                        st.write(f"**Lugar:** {row.get('lugar') or '-'}")
                        st.write(f"**Descripción:**")
                        st.write(row.get("descripcion") or "_Sin notas_")
                        st.caption(f"ID: {row['id']} | Cargado por: {row.get('created_by_nombre','-')} el {row.get('created_at','-')}")
