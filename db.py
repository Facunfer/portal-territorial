import streamlit as st
import httpx
from supabase import create_client, Client


@st.cache_resource
def get_supabase() -> Client:
    """
    Cliente Supabase compartido entre todos los usuarios (cache_resource = singleton global).
    Forzamos HTTP/1.1 reemplazando el httpx.Client interno del postgrest client.
    HTTP/1.1 usa connection pooling por request en vez de una sola conexión HTTP/2
    multiplexada — evita ConnectionTerminated cuando el servidor cierra el stream.
    """
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    client = create_client(url, key)

    # Forzar HTTP/1.1 en el cliente postgrest interno
    try:
        session = client.postgrest.session
        client.postgrest.session = httpx.Client(
            base_url=str(session.base_url),
            headers=dict(session.headers),
            http2=False,          # ← desactiva HTTP/2
            timeout=30.0,
        )
    except Exception:
        pass  # Si falla el patch, sigue con el cliente default

    return client
