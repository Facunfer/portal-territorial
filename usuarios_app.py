import streamlit as st
import pandas as pd

from db import get_supabase


# =========================
# Constantes
# =========================
from permisos import AMBITOS, ROLES, VERT_PERSONAS, VERT_ASOC


# =========================
# Permisos creación
# =========================
def puede_administrar_usuarios(user: dict) -> bool:
    amb = (user.get("ambito") or "").strip().upper()
    rol = (user.get("rol") or "").strip().upper()

    if amb == "GLOBAL" and rol == "MASTER":
        return True
    if rol in ["CABEZA", "MASTER"]:
        return True
    return False


def roles_permitidos_para_crear(user: dict):
    """
    Reglas:
    - CABEZA puede crear MASTER y EXTRACTO (en su ámbito)
    - MASTER puede crear solo EXTRACTO (en su ámbito)
    - GLOBAL MASTER puede crear todo (incluye CABEZAS)
    """
    amb = (user.get("ambito") or "").strip().upper()
    rol = (user.get("rol") or "").strip().upper()

    if amb == "GLOBAL" and rol == "MASTER":
        return ["CABEZA", "MASTER", "EXTRACTO"]

    if rol == "CABEZA":
        return ["MASTER", "EXTRACTO"]

    if rol == "MASTER":
        return ["EXTRACTO"]

    return []


def scope_creacion(user: dict):
    """
    Devuelve (ambito_target, vertical_target, comuna_target) para el creador.
    - GLOBAL puede elegir cualquier scope
    - COMUNA fija comuna del user
    - VERTICAL fija su vertical
    """
    amb = (user.get("ambito") or "").strip().upper()

    if amb == "GLOBAL":
        return ("GLOBAL", None, None)  # significa "puede elegir"

    if amb == "COMUNA":
        return ("COMUNA", None, int(user.get("comuna_id") or 0))

    if amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
        return (amb, (user.get("vertical") or "").strip().upper() or None, None)

    # fallback
    return ("COMUNA", None, int(user.get("comuna_id") or 0))


def tipo_usuario_legacy(ambito: str) -> str:
    """
    Para no romper compatibilidad:
    - COMUNA -> REFERENTE
    - el resto -> MASTER
    """
    a = (ambito or "").strip().upper()
    return "REFERENTE" if a == "COMUNA" else "MASTER"


# =========================
# DB
# =========================
def get_users_scope(user: dict):
    """
    Lista usuarios visibles según alcance del administrador:
    - GLOBAL: todos
    - COMUNA: solo su comuna + (solo ambito COMUNA)
    - VERTICAL: solo su vertical + mismo ambito vertical
    """
    supabase = get_supabase()

    amb = (user.get("ambito") or "").strip().upper()
    rol = (user.get("rol") or "").strip().upper()

    q = supabase.table("usuarios").select(
        "id, username, tipo_usuario, comuna_id, activo, ambito, vertical, rol, creado_por"
    )

    if amb == "GLOBAL" and rol == "MASTER":
        res = q.order("id").execute()
        return res.data or []

    if amb == "COMUNA":
        q = q.eq("ambito", "COMUNA").eq("comuna_id", int(user.get("comuna_id") or 0))
        res = q.order("id").execute()
        return res.data or []

    if amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
        q = q.eq("ambito", amb).eq("vertical", (user.get("vertical") or "").strip().upper())
        res = q.order("id").execute()
        return res.data or []

    # fallback: nada
    return []


def username_existe(username: str) -> bool:
    supabase = get_supabase()
    res = supabase.table("usuarios").select("id").eq("username", username).limit(1).execute()
    return bool(res.data or [])


def crear_usuario(payload: dict):
    supabase = get_supabase()
    supabase.table("usuarios").insert(payload).execute()


def set_activo(user_id: int, activo: bool):
    supabase = get_supabase()
    supabase.table("usuarios").update({"activo": bool(activo)}).eq("id", int(user_id)).execute()


# =========================
# UI
# =========================
def usuarios_screen():
    user = st.session_state.get("user") or {}
    if not puede_administrar_usuarios(user):
        st.warning("No tenés permisos para administrar usuarios.")
        return

    st.header("Usuarios — Administración")

    amb_user = (user.get("ambito") or "").strip().upper()
    rol_user = (user.get("rol") or "").strip().upper()

    # =========================
    # Form crear usuario
    # =========================
    with st.container(border=True):
        st.subheader("➕ Crear usuario")

        roles_creables = roles_permitidos_para_crear(user)
        if not roles_creables:
            st.info("Con tu rol actual no podés crear usuarios.")
        else:
            # Scope del creador
            scope_amb, scope_vertical, scope_comuna = scope_creacion(user)

            col1, col2, col3 = st.columns(3)
            with col1:
                username = st.text_input("Username *", key="u_new_username")
                password = st.text_input("Password *", type="password", key="u_new_password")

            with col2:
                rol = st.selectbox("Rol *", roles_creables, index=0, key="u_new_rol")

                # ambito target
                if scope_amb == "GLOBAL":
                    ambito = st.selectbox("Ámbito *", AMBITOS, index=0, key="u_new_ambito")
                else:
                    ambito = scope_amb
                    st.text_input("Ámbito", value=ambito, disabled=True, key="u_new_ambito_ro")

            with col3:
                vertical = None
                comuna_id = None

                if scope_amb == "GLOBAL":
                    # elegir vertical/comuna según ambito elegido
                    if st.session_state.get("u_new_ambito") == "COMUNA":
                        comuna_id = st.number_input("Comuna (1–15) *", min_value=1, max_value=15, value=1, key="u_new_comuna")
                    elif st.session_state.get("u_new_ambito") == "VERTICAL_PERSONAS":
                        vertical = st.selectbox("Vertical Personas *", VERT_PERSONAS, index=0, key="u_new_vertical_p")
                    elif st.session_state.get("u_new_ambito") == "VERTICAL_ASOCIACIONES":
                        vertical = st.selectbox("Vertical Asociaciones *", VERT_ASOC, index=0, key="u_new_vertical_a")
                else:
                    # scope fijo
                    if ambito == "COMUNA":
                        comuna_id = scope_comuna
                        st.text_input("Comuna", value=str(comuna_id), disabled=True, key="u_new_comuna_ro")

                    if ambito == "VERTICAL_PERSONAS":
                        vertical = scope_vertical
                        st.text_input("Vertical", value=str(vertical), disabled=True, key="u_new_vertical_ro_p")

                    if ambito == "VERTICAL_ASOCIACIONES":
                        vertical = scope_vertical
                        st.text_input("Vertical", value=str(vertical), disabled=True, key="u_new_vertical_ro_a")

            # Resolver valores cuando scope_amb == GLOBAL
            if scope_amb == "GLOBAL":
                ambito_sel = st.session_state.get("u_new_ambito") or "GLOBAL"
                ambito = ambito_sel

                if ambito == "VERTICAL_PERSONAS":
                    vertical = st.session_state.get("u_new_vertical_p")
                elif ambito == "VERTICAL_ASOCIACIONES":
                    vertical = st.session_state.get("u_new_vertical_a")
                elif ambito == "COMUNA":
                    comuna_id = int(st.session_state.get("u_new_comuna") or 1)

            # Validación especial: quién puede crear CABEZAS
            if not (amb_user == "GLOBAL" and rol_user == "MASTER"):
                if rol == "CABEZA":
                    st.error("Solo un MASTER GLOBAL puede crear CABEZAS.")
                    st.stop()

            # Crear
            cbtn1, cbtn2 = st.columns([1, 6])
            with cbtn1:
                if st.button("✅ Crear usuario", use_container_width=True, key="u_btn_crear"):
                    if not username.strip() or not password.strip():
                        st.error("Completá username y password.")
                    elif username_existe(username.strip()):
                        st.error("Ese username ya existe.")
                    else:
                        # tipo_usuario legacy para compat
                        tipo_legacy = tipo_usuario_legacy(ambito)

                        payload = {
                            "username": username.strip(),
                            "password_hash": password.strip(),  # (mantenemos tu esquema actual)
                            "tipo_usuario": tipo_legacy,
                            "activo": True,
                            "ambito": ambito,
                            "vertical": vertical,
                            "rol": rol,
                            "comuna_id": comuna_id if ambito == "COMUNA" else None,
                            "creado_por": int(user.get("id")) if user.get("id") else None,
                        }

                        try:
                            crear_usuario(payload)
                            st.success("Usuario creado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creando usuario: {e}")

    st.markdown("---")

    # =========================
    # Lista usuarios
    # =========================
    st.subheader("📋 Usuarios visibles")

    rows = get_users_scope(user)
    if not rows:
        st.info("No hay usuarios para mostrar en tu alcance.")
        return

    df = pd.DataFrame(rows)

    # Orden más prolijo
    for c in ["ambito", "vertical", "rol", "username"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)

    # Tabla
    cols_show = ["id", "username", "activo", "ambito", "vertical", "rol", "comuna_id", "tipo_usuario", "creado_por"]
    cols_show = [c for c in cols_show if c in df.columns]

    st.dataframe(df[cols_show], use_container_width=True, height=320)

    st.markdown("### Activar / Desactivar")

    # Selector usuario
    opciones = [(int(r["id"]), r["username"]) for r in rows if r.get("id") is not None]
    elegido = st.selectbox("Seleccioná usuario", opciones, format_func=lambda x: f"{x[1]} (id={x[0]})", key="u_pick")

    user_row = next((r for r in rows if int(r.get("id") or 0) == int(elegido[0])), None)
    if user_row:
        activo_actual = bool(user_row.get("activo", True))
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("🟢 Activar", use_container_width=True, key="u_btn_on"):
                try:
                    set_activo(int(elegido[0]), True)
                    st.success("Usuario activado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        with c2:
            if st.button("🔴 Desactivar", use_container_width=True, key="u_btn_off"):
                try:
                    set_activo(int(elegido[0]), False)
                    st.success("Usuario desactivado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        st.caption(f"Estado actual: {'ACTIVO ✅' if activo_actual else 'INACTIVO ⛔'}")
