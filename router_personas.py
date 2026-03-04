# router_personas.py
import streamlit as st

import permisos
import personas_app


def render(user: dict):
    # Permiso módulo
    mods = permisos.allowed_modules(user)
    if "Personas" not in mods:
        st.warning("No tenés permisos para ver Personas.")
        return

    # Scope (no rompe nada si personas_app no lo usa)
    scope = permisos.personas_scope(user)

    # Guardamos en session_state para que tus módulos (si ya los adaptaste) lo lean
    st.session_state["PERM_PERSONAS_SCOPE_KIND"] = scope.kind
    st.session_state["PERM_PERSONAS_SCOPE_VALUE"] = scope.value

    # Render módulo real
    personas_app.personas_screen()
