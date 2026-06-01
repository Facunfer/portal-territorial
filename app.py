# app.py
import streamlit as st
import datetime
import bcrypt
import uuid

from db import get_supabase
import permisos
import router_personas
import router_asociaciones
import usuarios_admin
import dashboard_master_global
import reuniones_app
import agenda_reuniones_app
import agenda_kpis_app
import mapa_relacionamiento_app
import kpis_app
import ia_app # <--- Modulo IA
import styles  # <--- Importamos el modulo de estilos

# =========================
# Auth
# =========================
def _is_missing_es_original_error(exc: Exception) -> bool:
    msg = str(exc)
    return "es_original" in msg and ("schema cache" in msg or "does not exist" in msg or "column" in msg)


def _query_user_by_username(username: str, cols: str):
    """Busca usuario solo por username (la verificación de contraseña se hace en Python)."""
    supabase = get_supabase()
    return (
        supabase.table("usuarios")
        .select(cols)
        .eq("username", username)
        .eq("activo", True)
        .limit(1)
        .execute()
    )


def _upgrade_password_hash(user_id: int, new_hash: str) -> None:
    """Actualiza un hash de contraseña en texto plano a bcrypt silenciosamente."""
    try:
        get_supabase().table("usuarios").update(
            {"password_hash": new_hash}
        ).eq("id", user_id).execute()
    except Exception:
        pass  # No bloquear el login si falla el upgrade


def get_user(username: str, password: str):
    """
    Autentica un usuario comparando la contraseña localmente con bcrypt.
    Soporta contraseñas en texto plano (legacy) y las migra automáticamente
    a bcrypt en el primer login exitoso.
    """
    cols_base = "id, username, tipo_usuario, comuna_id, ambito, vertical, rol, password_hash"
    try:
        res = _query_user_by_username(username, f"{cols_base}, es_original")
    except Exception as exc:
        if not _is_missing_es_original_error(exc):
            raise
        res = _query_user_by_username(username, cols_base)

    rows = res.data or []
    if not rows:
        return None

    r = rows[0]
    stored_hash = r.get("password_hash") or ""

    # ── Verificación de contraseña ───────────────────────────────────────────
    is_bcrypt = stored_hash.startswith(("$2b$", "$2a$", "$2y$"))

    if is_bcrypt:
        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except Exception:
            ok = False
    else:
        # Hash en texto plano (legacy) — comparación directa
        ok = (stored_hash == password)
        if ok:
            # Auto-upgrade silencioso a bcrypt en el primer login exitoso
            new_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            _upgrade_password_hash(r["id"], new_hash)

    if not ok:
        return None

    return {
        "id": r.get("id"),
        "username": r.get("username"),
        "tipo_usuario": r.get("tipo_usuario"),
        "comuna_id": r.get("comuna_id"),
        "ambito": r.get("ambito"),
        "vertical": r.get("vertical"),
        "rol": r.get("rol"),
        "es_original": bool(r.get("es_original", False)),
    }


# =========================
# Sesiones persistentes (sobreviven al refresh del navegador)
# =========================
@st.cache_resource
def _get_session_store() -> dict:
    """
    Almacena sesiones activas: { sid (UUID str) → user dict }.
    Persiste mientras el proceso de Streamlit esté vivo (sobrevive a refreshes).
    Se pierde solo si el servidor reinicia — en ese caso el usuario debe volver a loguearse.
    """
    return {}


def _create_session(user: dict) -> str:
    sid = str(uuid.uuid4())
    _get_session_store()[sid] = user
    return sid


def _restore_session(sid: str):
    return _get_session_store().get(sid)


def _destroy_session(sid: str) -> None:
    _get_session_store().pop(sid, None)


# =========================
# Sesiones persistentes (sobreviven a F5)
# =========================
_SESSION_TTL_HORAS = 12


def _create_session(user_data: dict) -> str:
    """Guarda la sesión en Supabase y devuelve el token UUID."""
    token = str(uuid.uuid4())
    expires_at = (
        datetime.datetime.utcnow() + datetime.timedelta(hours=_SESSION_TTL_HORAS)
    ).isoformat()
    try:
        get_supabase().table("sesiones").insert(
            {"id": token, "user_data": user_data, "expires_at": expires_at}
        ).execute()
    except Exception:
        pass
    return token


def _restore_session(token: str) -> dict | None:
    """Intenta restaurar una sesión desde Supabase. Devuelve user_data o None."""
    if not token:
        return None
    try:
        res = (
            get_supabase()
            .table("sesiones")
            .select("user_data, expires_at")
            .eq("id", token)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        row = rows[0]
        expires_at = row.get("expires_at")
        if expires_at:
            import pandas as pd
            exp_dt = pd.to_datetime(expires_at, utc=True)
            now_dt = pd.Timestamp.utcnow()
            if now_dt > exp_dt:
                get_supabase().table("sesiones").delete().eq("id", token).execute()
                return None
        return row.get("user_data")
    except Exception:
        return None


def _delete_session(token: str) -> None:
    """Elimina la sesión de Supabase al cerrar sesión."""
    if not token:
        return
    try:
        get_supabase().table("sesiones").delete().eq("id", token).execute()
    except Exception:
        pass


# =========================
# Rate limiting (server-side — compartido entre TODAS las sesiones)
# =========================
_MAX_INTENTOS = 5
_BLOQUEO_SEGUNDOS = 300


@st.cache_resource
def _get_login_tracker() -> dict:
    """
    Singleton compartido entre todas las sesiones de Streamlit.
    Estructura: { username_lower: {"attempts": int, "blocked_until": datetime | None} }
    Usar st.cache_resource garantiza que persiste mientras el proceso viva,
    a diferencia de st.session_state que es por pestaña del navegador.
    """
    return {}


def _rl_is_blocked(username: str) -> tuple[bool, int]:
    """Devuelve (bloqueado, segundos_restantes)."""
    tracker = _get_login_tracker()
    entry = tracker.get(username.strip().lower(), {})
    blocked_until = entry.get("blocked_until")
    if blocked_until and datetime.datetime.now() < blocked_until:
        restante = int((blocked_until - datetime.datetime.now()).total_seconds())
        return True, restante
    return False, 0


def _rl_register_failure(username: str) -> int:
    """Registra un intento fallido. Devuelve intentos acumulados."""
    tracker = _get_login_tracker()
    key = username.strip().lower()
    entry = tracker.setdefault(key, {"attempts": 0, "blocked_until": None})
    # Limpiar bloqueo expirado antes de contar
    if entry.get("blocked_until") and datetime.datetime.now() >= entry["blocked_until"]:
        entry["attempts"] = 0
        entry["blocked_until"] = None
    entry["attempts"] += 1
    if entry["attempts"] >= _MAX_INTENTOS:
        entry["blocked_until"] = datetime.datetime.now() + datetime.timedelta(seconds=_BLOQUEO_SEGUNDOS)
        entry["attempts"] = 0
    return entry["attempts"]


def _rl_clear(username: str) -> None:
    """Limpia el contador tras un login exitoso."""
    _get_login_tracker().pop(username.strip().lower(), None)


def show_login():
    styles.load_css()
    st.title("PORTAL TERRITORIAL – LOGIN")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("INGRESAR"):
        if not username or not password:
            st.error("Completá usuario y contraseña.")
            return

        # ── Chequeo de bloqueo ANTES de tocar la DB ─────────────────────────
        bloqueado, restante = _rl_is_blocked(username)
        if bloqueado:
            st.error(f"Demasiados intentos fallidos. Intentá de nuevo en {restante} segundos.")
            return

        try:
            user = get_user(username, password)
        except Exception:
            st.error("No se pudo conectar con el servidor. Verificá tu conexión e intentá de nuevo.")
            return

        if not user:
            intentos = _rl_register_failure(username)
            bloqueado, _ = _rl_is_blocked(username)
            if bloqueado:
                st.error("Demasiados intentos fallidos. Acceso bloqueado por 5 minutos.")
            else:
                restantes = _MAX_INTENTOS - intentos
                st.error(f"Credenciales incorrectas. Intentos restantes: {restantes}")
            return

        _rl_clear(username)
        st.session_state["user"] = user
        sid = _create_session(user)
        st.query_params["sid"] = sid
        st.rerun()


# =========================
# App
# =========================
def main():
    st.set_page_config(page_title="Portal Territorial", layout="wide")
    
    # Cargar estilos globales (LLA)
    styles.load_css()

    # Restaurar sesión desde URL si el session_state está vacío (ej: refresh de página)
    if "user" not in st.session_state or not st.session_state["user"]:
        sid = st.query_params.get("sid", "")
        if sid:
            restored = _restore_session(sid)
            if restored:
                st.session_state["user"] = restored

    # Login
    if "user" not in st.session_state or not st.session_state["user"]:
        show_login()
        return

    user = st.session_state["user"]

    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {user.get('username','').upper()}")
        st.markdown("---")

        if permisos.get_ambito(user) == "AGENDA":
            # AGENDA usa un sidebar aislado y read-only, sin heredar modulos existentes.
            mods = ["Agenda de Reuniones", "Visualización de Reuniones"]
        else:
            mods = permisos.allowed_modules(user)
            if not mods:
                mods = ["Personas"]

        modulo = st.radio("Módulo", mods, index=0)

        st.markdown("---")

        # Botón mapa — solo para usuarios de ámbito COMUNA
        if permisos.get_ambito(user) == "COMUNA":
            st.markdown(
                """
                <a href="https://mapa.alianzalalibertadavanzacaba.com/login"
                   target="_blank"
                   style="display:block; text-align:center; padding:8px 12px;
                          background-color:#371959; color:#FFFFFF;
                          border-radius:4px; font-weight:700;
                          text-decoration:none; font-size:0.85rem;
                          text-transform:uppercase; letter-spacing:0.5px;
                          border: 1px solid #A6E3FF;">
                    RECLAMOS/SUGERENCIAS
                </a>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("---")

        if st.button("CERRAR SESIÓN"):
            # Invalidar token de sesión
            sid = st.query_params.get("sid", "")
            if sid:
                _delete_session(sid)
            st.query_params.clear()

            st.session_state.pop("user", None)
            st.session_state.pop("selected_persona_id", None)
            st.session_state.pop("selected_asoc_id", None)

            # scopes/permisos
            st.session_state.pop("PERM_PERSONAS_SCOPE_KIND", None)
            st.session_state.pop("PERM_PERSONAS_SCOPE_VALUE", None)
            st.session_state.pop("PERM_ASOC_SCOPE_KIND", None)
            st.session_state.pop("PERM_ASOC_SCOPE_VALUE", None)

            st.rerun()

    # ── Guard de permisos server-side ───────────────────────────────────────
    # Doble verificación: aunque el radio button esté restringido en la UI,
    # se valida en el servidor para que una manipulación del session_state
    # no permita acceder a módulos fuera del scope del usuario.
    modulos_permitidos = permisos.allowed_modules(user)
    if modulo not in modulos_permitidos:
        st.error("⛔ No tenés permisos para acceder a este módulo.")
        st.stop()

    # Render módulo
    try:
        if modulo == "Personas":
            router_personas.render(user)
        elif modulo == "Asociaciones":
            router_asociaciones.render(user)
        elif modulo == "Usuarios":
            session_user = st.session_state.get("user") or user
            if not permisos.can_manage_users(session_user):
                st.error("⛔ No tenés permisos para administrar usuarios.")
                st.stop()
            ambito_user = permisos.get_ambito(session_user)
            requiere_original = ambito_user in ["COMUNA", "VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]
            if requiere_original and not session_user.get("es_original", False):
                st.warning("No tenés permisos para acceder a este módulo.")
                st.stop()
            usuarios_admin.render(session_user)
        elif modulo == "Master Global":
            if not permisos.is_global_master(user):
                st.error("⛔ Este módulo es exclusivo del Master Global.")
                st.stop()
            dashboard_master_global.render(user)
        elif modulo == "Reuniones/Actividades":
            reuniones_app.render_reuniones_screen(user, get_supabase())
        elif modulo == "Agenda de Reuniones":
            agenda_reuniones_app.render(user, get_supabase())
        elif modulo == "Visualización de Reuniones":
            agenda_kpis_app.render(user, get_supabase())
        elif modulo == "Mapa Relacionamiento":
            mapa_relacionamiento_app.render(user)
        elif modulo == "Visualización":
            kpis_app.render(user, get_supabase())
        elif modulo == "Consultas":
            ia_app.render(user)
        else:
            st.warning("Módulo no reconocido.")
    except Exception as _e:
        st.error(
            "Ocurrió un error inesperado en este módulo. "
            "Intentá recargar la página. Si el problema persiste, contactá al administrador."
        )
        with st.expander("Detalle técnico (para el administrador)"):
            st.code(str(_e))


if __name__ == "__main__":
    main()
