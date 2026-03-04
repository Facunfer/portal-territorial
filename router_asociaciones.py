# router_asociaciones.py
import streamlit as st

import permisos
import asociaciones_app


def render(user: dict):
    mods = permisos.allowed_modules(user)
    if "Asociaciones" not in mods:
        st.warning("No tenés permisos para ver Asociaciones.")
        return

    scope = permisos.asociaciones_scope(user)

    st.session_state["PERM_ASOC_SCOPE_KIND"] = scope.kind
    st.session_state["PERM_ASOC_SCOPE_VALUE"] = scope.value

    asociaciones_app.asociaciones_screen()
