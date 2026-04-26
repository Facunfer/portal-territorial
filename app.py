# app.py
import streamlit as st
import datetime

from db import get_supabase
import permisos
import router_personas
import router_asociaciones
import usuarios_admin
import dashboard_master_global
import reuniones_app
import mapa_relacionamiento_app
import kpis_app
import ia_app # <--- Modulo IA
import styles  # <--- Importamos el modulo de estilos

# =========================
# Auth
# =========================
def get_user(username: str, password: str):
    supabase = get_supabase()
    res = (
        supabase.table("usuarios")
        .select("id, username, tipo_usuario, comuna_id, ambito, vertical, rol")
        .eq("username", username)
        .eq("password_hash", password)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return None

    r = rows[0]
    return {
        "id": r.get("id"),
        "username": r.get("username"),
        "tipo_usuario": r.get("tipo_usuario"),
        "comuna_id": r.get("comuna_id"),
        "ambito": r.get("ambito"),
        "vertical": r.get("vertical"),
        "rol": r.get("rol"),
    }


_MAX_INTENTOS = 5
_BLOQUEO_SEGUNDOS = 300


def show_login():
    styles.load_css()
    st.title("PORTAL TERRITORIAL – LOGIN")

    # Inicializar contadores de rate limiting
    if "login_intentos" not in st.session_state:
        st.session_state["login_intentos"] = 0
        st.session_state["login_bloqueado_hasta"] = None

    ahora = datetime.datetime.now()
    bloqueado_hasta = st.session_state.get("login_bloqueado_hasta")

    if bloqueado_hasta and ahora < bloqueado_hasta:
        restante = int((bloqueado_hasta - ahora).total_seconds())
        st.error(f"Demasiados intentos fallidos. Intentá de nuevo en {restante} segundos.")
        return

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("INGRESAR"):
        if not username or not password:
            st.error("Completá usuario y contraseña.")
            return

        user = get_user(username, password)
        if not user:
            st.session_state["login_intentos"] += 1
            intentos = st.session_state["login_intentos"]
            if intentos >= _MAX_INTENTOS:
                st.session_state["login_bloqueado_hasta"] = ahora + datetime.timedelta(seconds=_BLOQUEO_SEGUNDOS)
                st.session_state["login_intentos"] = 0
                st.error("Demasiados intentos fallidos. Acceso bloqueado por 5 minutos.")
            else:
                restantes = _MAX_INTENTOS - intentos
                st.error(f"Credenciales incorrectas. Intentos restantes: {restantes}")
            return

        st.session_state["login_intentos"] = 0
        st.session_state["login_bloqueado_hasta"] = None
        st.session_state["user"] = user
        st.rerun()


# =========================
# App
# =========================
def main():
    st.set_page_config(page_title="Portal Territorial", layout="wide")
    
    # Cargar estilos globales (LLA)
    styles.load_css()

    # Login
    if "user" not in st.session_state or not st.session_state["user"]:
        show_login()
        return

    user = st.session_state["user"]

    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {user.get('username','').upper()}")
        st.markdown("---")

        mods = permisos.allowed_modules(user)
        if not mods:
            mods = ["Personas"]

        modulo = st.radio("Módulo", mods, index=0)

        st.markdown("---")
        if st.button("CERRAR SESIÓN"):
            st.session_state.pop("user", None)
            st.session_state.pop("selected_persona_id", None)
            st.session_state.pop("selected_asoc_id", None)

            # scopes/permisos
            st.session_state.pop("PERM_PERSONAS_SCOPE_KIND", None)
            st.session_state.pop("PERM_PERSONAS_SCOPE_VALUE", None)
            st.session_state.pop("PERM_ASOC_SCOPE_KIND", None)
            st.session_state.pop("PERM_ASOC_SCOPE_VALUE", None)

            st.rerun()

    # Render módulo
    if modulo == "Personas":
        router_personas.render(user)
    elif modulo == "Asociaciones":
        router_asociaciones.render(user)
    elif modulo == "Usuarios":
        usuarios_admin.render(user)
    elif modulo == "Master Global":
        dashboard_master_global.render(user)
    elif modulo == "Reuniones/Actividades":
        reuniones_app.render_reuniones_screen(user, get_supabase())
    elif modulo == "Mapa Relacionamiento":
        mapa_relacionamiento_app.render(user)
    elif modulo == "Visualización":
        kpis_app.render(user, get_supabase())
    elif modulo == "Consultas":
        ia_app.render(user)
    else:
        st.warning("Módulo no reconocido.")


if __name__ == "__main__":
    main()
