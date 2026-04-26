# mapa_relacionamiento_app.py
import streamlit as st
import pandas as pd
import datetime
import io

try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False


from supabase import create_client, Client
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# Reutilizamos funciones de geocodificación y constantes desde personas_app
from personas_app import (
    sugerir_direcciones_caba,
    normalizar_domicilio_caba,
    geocodificar_con_reintentos,
    BARRIOS_POR_COMUNA,
    LOCALE_ES
)

# Verticales que pueden seleccionar instituciones existentes (asociaciones)
# Key: vertical del usuario, Value: tipo(s) de asociación que puede ver
VERTICAL_ASOC_TIPO_MAP = {
    "CCAA": ["Local comercial"],
    "CULTO": ["Espacios de Culto"],
    "CULTURA": ["Espacios Culturales"],
    "ASOCIACIONES_CIVILES": ["Centros de Jubilados", "Clubes", "Espacios Culturales"],
}

TIPOS_INTERACCION_REL = ["Reunión", "Llamada", "WhatsApp", "Email", "Presencial", "Otro"]
RESULTADOS_INTERACCION_REL = ["POSITIVO", "NEUTRO", "NEGATIVO"]

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)

# =========================
# Helpers
# =========================
def get_ultima_interaccion_rel(supabase, contacto_id: int):
    res = (
        supabase.table("interacciones_mapa_relacionamiento")
        .select("fecha, resultado")
        .eq("contacto_id", int(contacto_id))
        .order("fecha", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None, None
    return rows[0].get("fecha"), rows[0].get("resultado")

def insert_interaccion_rel(supabase, payload: dict):
    supabase.table("interacciones_mapa_relacionamiento").insert(payload).execute()

def get_interacciones_rel(supabase, contacto_id: int):
    res = (
        supabase.table("interacciones_mapa_relacionamiento")
        .select("*")
        .eq("contacto_id", int(contacto_id))
        .order("fecha", desc=True)
        .limit(100)
        .execute()
    )
    return pd.DataFrame(res.data or [])

def semaforo_tiempo_label(ultima_fecha):
    if ultima_fecha is None or pd.isna(ultima_fecha):
        return "⚫ SIN FECHA"
    hoy = datetime.date.today()
    try:
        # Check if ultima_fecha is a string (e.g. from DB) and parse it
        if isinstance(ultima_fecha, str):
            ultima_fecha = pd.to_datetime(ultima_fecha).date()
        elif isinstance(ultima_fecha, pd.Timestamp):
            ultima_fecha = ultima_fecha.date()

        dias = (hoy - ultima_fecha).days
    except Exception:
        return "⚫ SIN FECHA"

    if dias < 30:
        return "🟢 <30 días"
    if 30 <= dias <= 60:
        return "🟡 30–60 días"
    return "🔴 >60 días"

def normalizar_nivel_influencia(v):
    v_norm = str(v).strip().upper()
    if v_norm in ["ALTO", "ALTA"]: return "Alto"
    if v_norm in ["MEDIO", "MEDIA"]: return "Medio"
    if v_norm in ["BAJO", "BAJA"]: return "Bajo"
    return "Medio" # fallback

def normalizar_nivel_vinculo(v):
    v_norm = str(v).strip().upper()
    if "SIN" in v_norm: return "SIN CONTACTO"
    if "INICIAL" in v_norm: return "CONTACTO INICIAL"
    if "CONSOLIDADO" in v_norm: return "VÍNCULO CONSOLIDADO"
    return "SIN CONTACTO" # fallback

def _color_por_vinculo(nivel_vinculo: str) -> str:
    """Color del marcador según nivel de vínculo."""
    v = (nivel_vinculo or "").strip().upper()
    if "CONSOLIDADO" in v:
        return "green"
    if "INICIAL" in v:
        return "orange"
    return "gray"  # SIN CONTACTO o desconocido

# =========================
# Data Load
# =========================
def get_mapa_relacionamiento(user):
    supabase = get_supabase()
    
    # SEGMENTOS ve todo el mapa sin filtros
    ambito = (user.get("ambito") or "").strip().upper()
    if ambito == "SEGMENTOS":
        kind = "ALL"
    else:
        kind = st.session_state.get("PERM_PERSONAS_SCOPE_KIND", "ALL").strip().upper()
    
    q = supabase.table("mapa_relacionamiento").select("*")
    
    # 2g. Scope/permisos
    # COMUNA: ve solo registros de su comuna_id
    if kind == "COMUNA":
        q = q.eq("comuna_id", user.get("comuna_id", 1))
    
    # Traer en páginas
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
        return pd.DataFrame(columns=[
            "id", "institucion", "nombre_apellido", "rol", "telefono", "nivel_influencia",
            "nivel_vinculo", "comuna_id", "direccion", "latitud", "longitud",
            "observaciones", "created_by", "created_at", "ultima_fecha", "Semaforo"
        ])

    contacto_ids = df["id"].tolist()
    
    int_rows, ipage = [], 0
    while True:
        iq = supabase.table("interacciones_mapa_relacionamiento").select("contacto_id, fecha, resultado")
        res_i = iq.range(ipage * 1000, (ipage + 1) * 1000 - 1).execute()
        idata = res_i.data or []
        int_rows.extend(idata)
        if len(idata) < 1000:
            break
        ipage += 1
    
    df_int = pd.DataFrame(int_rows) if int_rows else pd.DataFrame(columns=["contacto_id", "fecha", "resultado"])
    
    if not df_int.empty:
        df_int["fecha_dt"] = pd.to_datetime(df_int["fecha"], errors="coerce")
        last_int = df_int.sort_values("fecha_dt", ascending=False).drop_duplicates("contacto_id")
        df = df.merge(
            last_int[["contacto_id", "fecha", "resultado"]].rename(columns={"fecha": "ultima_fecha", "resultado": "ultimo_resultado"}),
            left_on="id", right_on="contacto_id", how="left"
        )
        df.drop(columns=["contacto_id"], inplace=True, errors="ignore")
    else:
        df["ultima_fecha"] = None
        df["ultimo_resultado"] = None
    
    df["ultima_fecha_dt"] = pd.to_datetime(df["ultima_fecha"], errors="coerce")
    df["Semaforo"] = df["ultima_fecha_dt"].apply(semaforo_tiempo_label)
    df.drop(columns=["ultima_fecha_dt"], inplace=True, errors="ignore")
    
    return df

def get_instituciones_sugeridas(user):
    """
    Retorna un dict {nombre: {direccion, latitud, longitud, comuna_id}}
    con las asociaciones visibles según la vertical del usuario.
    Retorna dict vacío si la vertical no tiene asociaciones.
    """
    supabase = get_supabase()
    
    ambito = (user.get("ambito") or "").strip().upper()
    rol = (user.get("rol") or "").strip().upper()
    vertical = (user.get("vertical") or "").strip().upper()
    
    qa = supabase.table("asociaciones").select("nombre, direccion, latitud, longitud, comuna_id")
    
    # GLOBAL MASTER: ve todas
    if ambito == "GLOBAL" and rol == "MASTER":
        pass
    
    # COMUNA: ve asociaciones de su comuna
    elif ambito == "COMUNA":
        comuna_id = user.get("comuna_id")
        if comuna_id:
            qa = qa.eq("comuna_id", int(comuna_id))
    
    # VERTICAL: solo si está en el mapeo
    elif vertical in VERTICAL_ASOC_TIPO_MAP:
        tipos = VERTICAL_ASOC_TIPO_MAP[vertical]
        qa = qa.in_("tipo", tipos)
    
    else:
        return {}
    
    try:
        res = qa.order("nombre").limit(1000).execute()
        resultado = {}
        for r in (res.data or []):
            nom = (r.get("nombre") or "").strip()
            if nom and nom not in resultado:
                resultado[nom] = {
                    "direccion": (r.get("direccion") or "").strip(),
                    "latitud": r.get("latitud"),
                    "longitud": r.get("longitud"),
                    "comuna_id": r.get("comuna_id"),
                }
        return resultado
    except Exception:
        return {}

# =========================
# Render Central
# =========================
def render(user: dict):
    st.header("Mapa de Relacionamiento")
    supabase = get_supabase()

    kind = st.session_state.get("PERM_PERSONAS_SCOPE_KIND", "ALL").strip().upper()

    # Session State
    if "rel_show_new" not in st.session_state:
        st.session_state["rel_show_new"] = False
    if "rel_show_csv" not in st.session_state:
        st.session_state["rel_show_csv"] = False
    
    # Botones principales (Ocultos para SEGMENTOS)
    es_segmentos = (user.get("ambito") or "").strip().upper() == "SEGMENTOS"
    if not es_segmentos:
        col_bt1, col_bt2, _ = st.columns([2, 2, 6])
        with col_bt1:
            if st.button("➕ Agregar contacto visual"):
                st.session_state["rel_show_new"] = not st.session_state["rel_show_new"]
                st.session_state["rel_show_csv"] = False
        with col_bt2:
            if st.button("📄 Cargar CSV masivo"):
                st.session_state["rel_show_csv"] = not st.session_state["rel_show_csv"]
                st.session_state["rel_show_new"] = False
        st.markdown("---")

    # ==========================================
    # ALTA MANUAL
    # ==========================================
    if st.session_state["rel_show_new"]:
        st.subheader("Alta Manual")
        
        # --- Selector de Institución (FUERA del form) ---
        instituciones_dict = get_instituciones_sugeridas(user)  # dict {nombre: {direccion, lat, lon, comuna_id}}
        
        # Valores por defecto para dirección/coordenadas (se llenan si elige existente)
        dir_autocompletada = ""
        lat_autocompletada = None
        lon_autocompletada = None
        comuna_autocompletada = None
        
        if instituciones_dict:
            # Vertical con asociaciones: ofrecer seleccionar o ingresar nueva
            st.markdown("#### 🏢 Institución")
            opcion_inst = st.radio(
                "¿Cómo querés cargar la institución?",
                ["Seleccionar existente", "Ingresar nueva"],
                horizontal=True,
                key="rel_inst_modo"
            )
            
            if opcion_inst == "Seleccionar existente":
                nombres_lista = sorted(instituciones_dict.keys())
                institucion_seleccionada = st.selectbox(
                    "Seleccionar institución",
                    options=[""] + nombres_lista,
                    index=0,
                    key="rel_inst_select"
                )
                
                # Autocompletar datos si seleccionó una institución
                if institucion_seleccionada and institucion_seleccionada in instituciones_dict:
                    datos_inst = instituciones_dict[institucion_seleccionada]
                    dir_autocompletada = datos_inst.get("direccion", "")
                    lat_autocompletada = datos_inst.get("latitud")
                    lon_autocompletada = datos_inst.get("longitud")
                    comuna_autocompletada = datos_inst.get("comuna_id")
                    
                    if dir_autocompletada:
                        st.caption(f"📍 Dirección asociada: {dir_autocompletada}")
            else:
                institucion_seleccionada = st.text_input(
                    "Nombre de la nueva institución *",
                    value="",
                    key="rel_inst_nueva"
                )
            
            st.markdown("---")
        else:
            # Vertical sin asociaciones: solo campo libre
            institucion_seleccionada = None  # se define dentro del form
        
        # --- Form con el resto de campos ---
        with st.form("form_alta_rel"):
            col1, col2 = st.columns(2)
            with col1:
                if instituciones_dict:
                    st.text_input("Institución", value=institucion_seleccionada or "", disabled=True, key="rel_inst_display")
                else:
                    institucion_seleccionada = st.text_input("Institución *", key="rel_inst")
                
                nombre_apellido = st.text_input("Nombre y Apellido *", key="rel_nom")
                rol = st.text_input("Rol / Cargo", key="rel_rol")
                telefono = st.text_input("Teléfono de contacto", key="rel_tel")
                
                niv_inf = st.selectbox("Nivel de Influencia", ["Alto", "Medio", "Bajo"], key="rel_inf")
                niv_vinc = st.selectbox("Nivel de Vínculo", ["SIN CONTACTO", "CONTACTO INICIAL", "VÍNCULO CONSOLIDADO"], key="rel_vinc")
            
            with col2:
                # Dirección: pre-llenada si eligió institución existente, editable si no
                direccion = st.text_input(
                    "Dirección (CABA)",
                    value=dir_autocompletada,
                    key="rel_dir"
                )
                
                # Comuna: pre-seleccionada si eligió institución existente
                opciones_comunas = ["Sin comuna"] + list(range(1, 16))
                if kind == "COMUNA":
                    com_id = int(user.get("comuna_id") or 1)
                    comuna_id_new = st.selectbox("Comuna", opciones_comunas, index=opciones_comunas.index(com_id), disabled=True)
                else:
                    # Determinar index por defecto
                    default_index = 0  # "Sin comuna"
                    if comuna_autocompletada is not None:
                        try:
                            default_index = opciones_comunas.index(int(comuna_autocompletada))
                        except (ValueError, TypeError):
                            default_index = 0
                    
                    comuna_id_new = st.selectbox("Comuna", opciones_comunas, index=default_index, key="rel_comuna")
                
                observaciones = st.text_area("Observaciones", key="rel_obs")
            
            submitted = st.form_submit_button("Guardar Contacto")
        
        if submitted:
            inst_final = (institucion_seleccionada or "").strip()
            if not inst_final:
                st.error("Debes seleccionar o ingresar una institución.")
            else:
                # Si la dirección viene autocompletada Y no fue modificada, usar las coordenadas originales
                # Si fue modificada o es nueva, geocodificar
                lat_final = None
                lon_final = None
                dir_final = direccion.strip()
                
                if dir_autocompletada and dir_final == dir_autocompletada:
                    # No cambió la dirección → usar coordenadas de la asociación
                    lat_final = lat_autocompletada
                    lon_final = lon_autocompletada
                elif dir_final:
                    # Dirección nueva o modificada → geocodificar
                    dom_normalizado, err_norm = normalizar_domicilio_caba(dir_final)
                    if dom_normalizado and not err_norm:
                        dir_final = dom_normalizado
                        lat_final, lon_final = geocodificar_con_reintentos(dom_normalizado)
                
                data_insert = {
                    "institucion": inst_final,
                    "nombre_apellido": nombre_apellido.strip(),
                    "rol": rol.strip(),
                    "telefono": telefono.strip() if telefono else None,
                    "nivel_influencia": niv_inf,
                    "nivel_vinculo": niv_vinc,
                    "fecha_relacionamiento": None,
                    "comuna_id": int(comuna_id_new) if comuna_id_new != "Sin comuna" else None,
                    "direccion": dir_final or None,
                    "latitud": lat_final,
                    "longitud": lon_final,
                    "observaciones": observaciones.strip(),
                    "created_by": user.get("id"),
                }
                
                try:
                    supabase.table("mapa_relacionamiento").insert(data_insert).execute()
                    st.success("Contacto agregado correctamente.")
                    st.session_state["rel_show_new"] = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

    # Si se cargó una dirección (fuera del form) sugerimos
    # En este diseño simple lo mantuve dentro del form, como se suele hacer para no recargar.

    # ==========================================
    # CARGA MASIVA CSV
    # ==========================================
    if st.session_state["rel_show_csv"]:
        st.subheader("Carga Masiva (CSV)")
        st.info("El CSV debe tener las siguientes columnas (en este orden): ID, INSTITUCION, NOMBRE Y APELLIDO, ROL, TELÉFONO, NIVEL INFLUENCIA, NIVEL DE VINCULO ACTUAL")
        uploaded_file = st.file_uploader("Seleccionar archivo", type=["csv"])
        if uploaded_file is not None:
            try:
                df_csv = pd.read_csv(uploaded_file)
                st.write("**Vista previa de datos (5 filas):**")
                st.dataframe(df_csv.head(5))
                
                if st.button("Procesar e Importar CSV"):
                    exitosos, errores = 0, 0
                    errores_detalle = []
                    
                    # Normalizar nombres de columnas del CSV
                    df_csv.columns = df_csv.columns.str.strip().str.upper()
                    
                    # Mapeo de columnas esperadas
                    col_map = {
                        "ID": None,  # Se ignora, no se inserta (es referencia del usuario)
                        "INSTITUCION": "institucion",
                        "NOMBRE Y APELLIDO": "nombre_apellido",
                        "ROL": "rol",
                        "TELÉFONO": "telefono",
                        "TELEFONO": "telefono",  # Sin tilde también
                        "NIVEL INFLUENCIA": "nivel_influencia",
                        "NIVEL DE VINCULO ACTUAL": "nivel_vinculo",
                        "NIVEL DE VÍNCULO ACTUAL": "nivel_vinculo",  # Con tilde también
                    }
                    
                    # Verificar que las columnas mínimas existan
                    required = ["INSTITUCION", "NOMBRE Y APELLIDO"]
                    missing = [r for r in required if r not in df_csv.columns]
                    if missing:
                        st.error(f"Faltan columnas requeridas en el CSV: {', '.join(missing)}")
                    else:
                        progress_bar = st.progress(0)
                        total = len(df_csv)
                        
                        for idx, row in df_csv.iterrows():
                            try:
                                inst = str(row.get("INSTITUCION", "")).strip() if pd.notna(row.get("INSTITUCION")) else "Sin Nombre"
                                nom = str(row.get("NOMBRE Y APELLIDO", "")).strip() if pd.notna(row.get("NOMBRE Y APELLIDO")) else ""
                                rol_txt = str(row.get("ROL", "")).strip() if "ROL" in df_csv.columns and pd.notna(row.get("ROL")) else ""
                                
                                # Teléfono (probar con y sin tilde)
                                tel_raw = row.get("TELÉFONO") if "TELÉFONO" in df_csv.columns else row.get("TELEFONO")
                                tel = str(tel_raw).strip() if pd.notna(tel_raw) else None
                                
                                # Nivel influencia
                                inf_raw = row.get("NIVEL INFLUENCIA")
                                inf = normalizar_nivel_influencia(inf_raw) if pd.notna(inf_raw) else "Medio"
                                
                                # Nivel vínculo (probar con y sin tilde)
                                vinc_raw = row.get("NIVEL DE VÍNCULO ACTUAL") if "NIVEL DE VÍNCULO ACTUAL" in df_csv.columns else row.get("NIVEL DE VINCULO ACTUAL")
                                vinc = normalizar_nivel_vinculo(vinc_raw) if pd.notna(vinc_raw) else "SIN CONTACTO"
                                
                                ins_data = {
                                    "institucion": inst,
                                    "nombre_apellido": nom,
                                    "rol": rol_txt,
                                    "telefono": tel,
                                    "nivel_influencia": inf,
                                    "nivel_vinculo": vinc,
                                    "fecha_relacionamiento": None,
                                    "comuna_id": None,
                                    "created_by": user.get("id"),
                                }
                                supabase.table("mapa_relacionamiento").insert(ins_data).execute()
                                exitosos += 1
                            except Exception as e:
                                errores += 1
                                errores_detalle.append(f"Fila {idx + 2}: {e}")
                            
                            progress_bar.progress((idx + 1) / total)
                        
                        st.success(f"Finalizado. Exitosos: {exitosos} | Errores: {errores}")
                        if errores_detalle:
                            with st.expander("Ver detalle de errores"):
                                for err in errores_detalle:
                                    st.caption(err)
                        st.session_state["rel_show_csv"] = False
            except Exception as e:
                st.error(f"Error procesando el archivo CSV: {e}")

    # ==========================================
    # DATA Y FILTROS
    # ==========================================
    df = get_mapa_relacionamiento(user)
    
    if df.empty:
        st.info("No hay contactos en el mapa de relacionamiento.")
        return

    # Inicializar filtros
    if "flt_rel_inst" not in st.session_state: st.session_state["flt_rel_inst"] = "Todas"
    if "flt_rel_inf" not in st.session_state: st.session_state["flt_rel_inf"] = "Todos"
    if "flt_rel_vinc" not in st.session_state: st.session_state["flt_rel_vinc"] = "Todos"
    if "flt_rel_com" not in st.session_state: st.session_state["flt_rel_com"] = "Todas"
    if "flt_rel_sem" not in st.session_state: st.session_state["flt_rel_sem"] = "Todos"
    if "flt_rel_txt" not in st.session_state: st.session_state["flt_rel_txt"] = ""
    
    def limpiar_filtros():
        st.session_state["flt_rel_inst"] = "Todas"
        st.session_state["flt_rel_inf"] = "Todos"
        st.session_state["flt_rel_vinc"] = "Todos"
        st.session_state["flt_rel_com"] = "Todas"
        st.session_state["flt_rel_sem"] = "Todos"
        st.session_state["flt_rel_txt"] = ""

    # UI Filtros
    with st.expander("🔍 Buscador y Filtros", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        
        # Opciones dinámicas
        list_inst = ["Todas"] + sorted(df["institucion"].dropna().unique().tolist())
        
        with c1:
            st.selectbox("Institución", list_inst, key="flt_rel_inst")
        with c2:
            st.selectbox("Influencia", ["Todos", "Alto", "Medio", "Bajo"], key="flt_rel_inf")
        with c3:
            st.selectbox("Vínculo", ["Todos", "SIN CONTACTO", "CONTACTO INICIAL", "VÍNCULO CONSOLIDADO"], key="flt_rel_vinc")
        with c4:
            if kind == "COMUNA":
                st.selectbox("Comuna", ["Todas"], disabled=True)
            else:
                list_com = ["Todas"] + sorted(df["comuna_id"].dropna().unique().tolist())
                st.selectbox("Comuna", list_com, key="flt_rel_com")
        with c5:
            st.selectbox("Semáforo", ["Todos", "🟢 <30 días", "🟡 30–60 días", "🔴 >60 días", "⚫ SIN FECHA"], key="flt_rel_sem")
            
        st.text_input("Búsqueda libre...", key="flt_rel_txt")
        
        st.button("Limpiar filtros", on_click=limpiar_filtros)

    # Aplico Filtros
    df_f = df.copy()
    if st.session_state["flt_rel_inst"] != "Todas":
        df_f = df_f[df_f["institucion"] == st.session_state["flt_rel_inst"]]
    if st.session_state["flt_rel_inf"] != "Todos":
        df_f = df_f[df_f["nivel_influencia"] == st.session_state["flt_rel_inf"]]
    if st.session_state["flt_rel_vinc"] != "Todos":
        df_f = df_f[df_f["nivel_vinculo"] == st.session_state["flt_rel_vinc"]]
    if st.session_state["flt_rel_com"] != "Todas":
        df_f = df_f[df_f["comuna_id"] == st.session_state["flt_rel_com"]]
    if st.session_state["flt_rel_sem"] != "Todos":
        df_f = df_f[df_f["Semaforo"] == st.session_state["flt_rel_sem"]]
        
    txt = st.session_state["flt_rel_txt"].strip().lower()
    if txt:
        mask = (
            df_f["institucion"].astype(str).str.lower().str.contains(txt) |
            df_f["nombre_apellido"].astype(str).str.lower().str.contains(txt) |
            df_f["rol"].astype(str).str.lower().str.contains(txt)
        )
        df_f = df_f[mask]

    # ==========================================
    # KPIS (Mejorados visualmente)
    # ==========================================
    st.markdown("---")
    
    with st.container(border=True):
        st.markdown("#### 📊 Métricas de Relacionamiento")
        
        total_contactos = len(df_f)
        inf_alta = len(df_f[df_f["nivel_influencia"] == "Alto"])
        inf_media = len(df_f[df_f["nivel_influencia"] == "Medio"])
        inf_baja = len(df_f[df_f["nivel_influencia"] == "Bajo"])
        
        vinc_cons = len(df_f[df_f["nivel_vinculo"] == "VÍNCULO CONSOLIDADO"])
        vinc_ini = len(df_f[df_f["nivel_vinculo"] == "CONTACTO INICIAL"])
        vinc_sin = len(df_f[df_f["nivel_vinculo"] == "SIN CONTACTO"])
        
        # Fila 1: Influencia
        st.caption("Nivel de Influencia")
        ki1, ki2, ki3, ki4 = st.columns(4)
        ki1.metric("👥 Total Contactos", total_contactos)
        ki2.metric("🔥 Influencia Alta", inf_alta)
        ki3.metric("🟡 Influencia Media", inf_media)
        ki4.metric("🔵 Influencia Baja", inf_baja)
        
        st.markdown("---")
        
        # Fila 2: Vínculo
        st.caption("Nivel de Vínculo Actual")
        kv1, kv2, kv3, kv4 = st.columns(4)
        kv1.metric("🤝 Vínculo Consolidado", vinc_cons)
        kv2.metric("👋 Contacto Inicial", vinc_ini)
        kv3.metric("⚫ Sin Contacto", vinc_sin)
        
        with kv4:
            st.write("") # Spacer vertical
            if not df_f.empty:
                csv_export = df_f.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Exportar Data (CSV)",
                    data=csv_export,
                    file_name=f"mapa_relacionamiento_{datetime.date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    # ==========================================
    # MAPA GEOLOCALIZADO
    # ==========================================
    st.markdown("---")
    
    # Filtrar solo contactos con coordenadas válidas
    df_map = df_f.copy()
    df_map = df_map.dropna(subset=["latitud", "longitud"])
    df_map = df_map[df_map["latitud"].astype(str).str.strip() != ""]
    df_map = df_map[df_map["longitud"].astype(str).str.strip() != ""]
    
    # Convertir a float (por si vienen como string)
    try:
        df_map["latitud"] = df_map["latitud"].astype(float)
        df_map["longitud"] = df_map["longitud"].astype(float)
        # Filtrar coordenadas inválidas (0,0 o fuera de rango CABA)
        df_map = df_map[(df_map["latitud"] != 0) & (df_map["longitud"] != 0)]
    except Exception:
        df_map = pd.DataFrame()
    
    if df_map.empty:
        st.info("No hay contactos con geolocalización para mostrar en el mapa.")
    else:
        st.subheader(f"🗺️ Mapa ({len(df_map)} contactos geolocalizados)")
        
        if not HAS_FOLIUM:
            # Fallback: mapa básico de Streamlit
            df_map_plot = df_map.rename(columns={"latitud": "lat", "longitud": "lon"})
            st.map(df_map_plot[["lat", "lon"]])
        else:
            # Mapa interactivo con Folium
            try:
                center_lat = float(df_map["latitud"].mean())
                center_lon = float(df_map["longitud"].mean())
            except Exception:
                center_lat, center_lon = -34.6037, -58.3816  # CABA centro
            
            m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
            
            for _, row in df_map.iterrows():
                institucion = (row.get("institucion") or "").strip()
                nombre = (row.get("nombre_apellido") or "").strip()
                rol_txt = (row.get("rol") or "").strip()
                telefono = (row.get("telefono") or "").strip()
                vinculo = (row.get("nivel_vinculo") or "").strip()
                influencia = (row.get("nivel_influencia") or "").strip()
                direccion = (row.get("direccion") or "").strip()
                semaforo = (row.get("Semaforo") or "").strip()
                
                tooltip_html = f"""
                <div style="font-size:12px;">
                  <b>{institucion}</b><br/>
                  👤 {nombre} {("— " + rol_txt) if rol_txt else ""}<br/>
                  📞 {telefono or "-"}<br/>
                  📍 {direccion or "-"}<br/>
                  🔗 Vínculo: {vinculo}<br/>
                  ⭐ Influencia: {influencia}<br/>
                  {semaforo}
                </div>
                """
                
                color = _color_por_vinculo(vinculo)
                
                folium.CircleMarker(
                    location=[float(row["latitud"]), float(row["longitud"])],
                    radius=6,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.85,
                    tooltip=folium.Tooltip(tooltip_html, sticky=True),
                ).add_to(m)
            
            st_folium(m, height=480, width=None)
        
        # Leyenda
        st.caption("🟢 Vínculo Consolidado · 🟠 Contacto Inicial · ⚪ Sin Contacto")
    
    st.markdown("---")

    # ==========================================
    # AGGRID TABLA
    # ==========================================
    # Mostrar sólo columnas necesarias y mapeadas
    cols_to_show = [
        "id", "institucion", "nombre_apellido", "rol", "telefono", "nivel_influencia", 
        "nivel_vinculo", "ultima_fecha", "Semaforo", "comuna_id", "direccion", "observaciones"
    ]
    df_grid = df_f[cols_to_show].copy() if not df_f.empty else pd.DataFrame(columns=cols_to_show)

    gb = GridOptionsBuilder.from_dataframe(df_grid)
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=50)
    
    # IMPORTANTE: No ocultar la columna ID o AgGrid no la devolverá en row_sel
    gb.configure_column("id", header_name="ID", width=60)
    gb.configure_column("institucion", header_name="Institución")
    gb.configure_column("nombre_apellido", header_name="Nombre y Apellido")
    gb.configure_column("rol", header_name="Rol")
    gb.configure_column("nivel_influencia", header_name="Nivel Influencia")
    gb.configure_column("nivel_vinculo", header_name="Nivel Vínculo actual")
    gb.configure_column("telefono", header_name="Teléfono")
    gb.configure_column("ultima_fecha", header_name="Última fecha")
    gb.configure_column("Semaforo", header_name="Tiempo")
    gb.configure_column("comuna_id", header_name="Comuna", width=100)
    gb.configure_column("direccion", header_name="Dirección")
    gb.configure_column("observaciones", header_name="Notas")

    go = gb.build()
    
    grid_response = AgGrid(
        df_grid,
        gridOptions=go,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        locale_es=LOCALE_ES,
        theme='streamlit',
        height=500,
        fit_columns_on_grid_load=False,
    )
    
    # --- Extracción Segura de Fila Seleccionada (Soporte Multi-Versión AgGrid) ---
    selected_rows = grid_response.get('selected_rows', [])
    if isinstance(selected_rows, pd.DataFrame):
        selected_dict = selected_rows.to_dict('records')
    elif not isinstance(selected_rows, list) and hasattr(grid_response, "selected_rows"):
        selected_dict = grid_response.selected_rows
    else:
        selected_dict = selected_rows
        
    # ==========================================
    # FICHA DEL CONTACTO (al seleccionar en la grilla)
    # ==========================================
    if selected_dict and len(selected_dict) > 0:
        row_sel = selected_dict[0]
        if not isinstance(row_sel, dict):
            row_sel = dict(row_sel)
            
        r_id = row_sel.get("id")
        if r_id is None or pd.isna(r_id):
            return
            
        r_id = int(r_id) 
        db_matches = df[df["id"] == r_id]
        
        if db_matches.empty:
            st.warning("No se pudo cargar el detalle de esta fila (recarregue la página).")
            return
            
        row_db = db_matches.iloc[0]
        
        st.markdown("---")
        st.markdown(f"### 📌 Ficha: {row_db.get('nombre_apellido', '')} — {row_db.get('institucion', '')}")
        
        # Info rápida
        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        col_info1.markdown(f"**Vínculo:** {row_db.get('nivel_vinculo', '-')}")
        col_info2.markdown(f"**Influencia:** {row_db.get('nivel_influencia', '-')}")
        col_info3.markdown(f"**Última fecha:** {row_db.get('ultima_fecha', 'Sin interacciones')}")
        col_info4.markdown(f"**Semáforo:** {row_db.get('Semaforo', '-')}")
        
        # --- Toggles para secciones ---
        edit_key = f"rel_show_edit_{r_id}"
        int_key = f"rel_show_int_{r_id}"
        
        if edit_key not in st.session_state:
            st.session_state[edit_key] = False
        if int_key not in st.session_state:
            st.session_state[int_key] = False
        
        btn_col1, btn_col2, _ = st.columns([1.5, 1.5, 6])
        with btn_col1:
            if st.button("✏️ Editar datos", key=f"btn_edit_{r_id}"):
                st.session_state[edit_key] = not st.session_state[edit_key]
                st.session_state[int_key] = False
        with btn_col2:
            if st.button("📌 Cargar interacción", key=f"btn_int_{r_id}"):
                st.session_state[int_key] = not st.session_state[int_key]
                st.session_state[edit_key] = False
        
        # =============================
        # 1) EDICIÓN DE DATOS
        # =============================
        if st.session_state[edit_key]:
            st.markdown("#### ✏️ Editar datos del contacto")
            with st.form(f"form_edit_rel_{r_id}"):
                c_e1, c_e2 = st.columns(2)
                
                with c_e1:
                    e_inst = st.text_input("Institución", value=row_db.get("institucion", ""))
                    e_nom = st.text_input("Nombre y Apellido", value=row_db.get("nombre_apellido", ""))
                    e_rol = st.text_input("Rol / Cargo", value=row_db.get("rol", ""))
                    e_tel = st.text_input("Teléfono", value=row_db.get("telefono", "") or "")
                    
                    inf_opts = ["Alto", "Medio", "Bajo"]
                    c_inf = row_db.get("nivel_influencia", "Medio")
                    e_inf = st.selectbox("Nivel de Influencia", inf_opts, 
                                         index=inf_opts.index(c_inf) if c_inf in inf_opts else 1)
                    
                    vinc_opts = ["SIN CONTACTO", "CONTACTO INICIAL", "VÍNCULO CONSOLIDADO"]
                    c_vinc = row_db.get("nivel_vinculo", "SIN CONTACTO")
                    e_vinc = st.selectbox("Nivel de Vínculo", vinc_opts,
                                          index=vinc_opts.index(c_vinc) if c_vinc in vinc_opts else 0)
                
                with c_e2:
                    opciones_c = ["Sin comuna"] + list(range(1, 16))
                    c_com_raw = row_db.get("comuna_id")
                    c_com = int(c_com_raw) if pd.notna(c_com_raw) and c_com_raw is not None else "Sin comuna"
                    if kind == "COMUNA":
                        e_com = st.selectbox("Comuna", opciones_c,
                                             index=opciones_c.index(c_com) if c_com in opciones_c else 0,
                                             disabled=True)
                    else:
                        e_com = st.selectbox("Comuna", opciones_c,
                                             index=opciones_c.index(c_com) if c_com in opciones_c else 0)
                    
                    e_dir = st.text_input("Dirección (CABA)", value=row_db.get("direccion", ""))
                    e_obs = st.text_area("Observaciones", value=row_db.get("observaciones", ""))
                
                btn_save = st.form_submit_button("💾 Guardar Cambios")
            
            if btn_save:
                update_data = {
                    "institucion": e_inst.strip(),
                    "nombre_apellido": e_nom.strip(),
                    "rol": e_rol.strip(),
                    "telefono": e_tel.strip() if e_tel else None,
                    "nivel_influencia": e_inf,
                    "nivel_vinculo": e_vinc,
                    "comuna_id": int(e_com) if e_com != "Sin comuna" else None,
                    "observaciones": e_obs.strip()
                }
                
                # Regeocodificar si cambió la dirección
                old_dir = str(row_db.get("direccion", ""))
                if e_dir.strip() != old_dir.strip():
                    d_norm, err_n = normalizar_domicilio_caba(e_dir)
                    update_data["direccion"] = d_norm or e_dir
                    if d_norm and not err_n:
                        e_lat, e_lon = geocodificar_con_reintentos(d_norm)
                        update_data["latitud"] = e_lat
                        update_data["longitud"] = e_lon
                
                try:
                    supabase.table("mapa_relacionamiento").update(update_data).eq("id", r_id).execute()
                    st.success("Cambios guardados.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        # =============================
        # 2) CARGAR INTERACCIÓN
        # =============================
        if st.session_state[int_key]:
            st.markdown("#### 📌 Cargar interacción")
            
            c3, c4, c5 = st.columns(3)
            with c3:
                int_fecha = st.date_input("Fecha", value=datetime.date.today(), key=f"rel_int_fecha_{r_id}")
            with c4:
                int_tipo = st.selectbox("Tipo de contacto", TIPOS_INTERACCION_REL, index=0, key=f"rel_int_tipo_{r_id}")
            with c5:
                int_resultado = st.selectbox("Resultado", RESULTADOS_INTERACCION_REL, index=0, key=f"rel_int_res_{r_id}")
            
            int_obs = st.text_area("Observaciones", value="", key=f"rel_int_obs_{r_id}")
            
            if st.button("✅ Guardar interacción", key=f"rel_int_save_{r_id}"):
                try:
                    insert_interaccion_rel(supabase, {
                        "contacto_id": int(r_id),
                        "fecha": str(int_fecha),
                        "tipo": int_tipo,
                        "resultado": int_resultado,
                        "observaciones": int_obs,
                        "created_by": user.get("id"),
                    })
                    
                    # Actualizar fecha_relacionamiento en la tabla principal (para compatibilidad)
                    supabase.table("mapa_relacionamiento").update({
                        "fecha_relacionamiento": str(int_fecha)
                    }).eq("id", r_id).execute()
                    
                    st.success("Interacción guardada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        # =============================
        # 3) HISTORIAL DE INTERACCIONES
        # =============================
        st.markdown("#### 📋 Historial de interacciones")
        df_hist_int = get_interacciones_rel(supabase, r_id)
        
        if df_hist_int.empty:
            st.info("Este contacto no tiene interacciones registradas.")
        else:
            hist_cols = ["fecha", "tipo", "resultado", "observaciones", "created_at"]
            hist_cols = [c for c in hist_cols if c in df_hist_int.columns]
            hist_map = {
                "fecha": "Fecha",
                "tipo": "Tipo",
                "resultado": "Resultado",
                "observaciones": "Observaciones",
                "created_at": "Creado"
            }
            st.dataframe(
                df_hist_int[hist_cols].rename(columns=hist_map),
                use_container_width=True,
                hide_index=True
            )
