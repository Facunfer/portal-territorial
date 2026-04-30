# agenda_kpis_app.py
import pandas as pd
import plotly.express as px
import streamlit as st

from agenda_reuniones_app import (
    apply_reuniones_filters,
    fetch_reuniones,
    fetch_scope_options,
    prepare_reuniones_table,
    render_agenda_filters,
)


def _scope_counts(df: pd.DataFrame, scope_tipo: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["scope_valor", "cantidad"])

    scope_df = df[df["scope_tipo"].fillna("").astype(str).str.upper() == scope_tipo]
    if scope_df.empty:
        return pd.DataFrame(columns=["scope_valor", "cantidad"])

    counts = scope_df.groupby("scope_valor").size().reset_index(name="cantidad")
    return counts.sort_values("cantidad", ascending=False)


def _render_bar(df_counts: pd.DataFrame, title: str, x_label: str):
    if df_counts.empty:
        st.info("Sin datos para la seleccion actual.")
        return

    fig = px.bar(
        df_counts,
        x="scope_valor",
        y="cantidad",
        title=title,
        labels={"scope_valor": x_label, "cantidad": "Reuniones"},
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_timeline(df: pd.DataFrame):
    if df.empty:
        st.info("Sin reuniones para la seleccion actual.")
        return

    timeline = df.copy()
    timeline["dia"] = pd.to_datetime(timeline["fecha"], errors="coerce").dt.date
    timeline = timeline.dropna(subset=["dia"])
    if timeline.empty:
        st.info("Sin fechas validas para graficar.")
        return

    counts = timeline.groupby("dia").size().reset_index(name="cantidad")
    fig = px.line(
        counts,
        x="dia",
        y="cantidad",
        markers=True,
        title="Reuniones por Dia",
        labels={"dia": "Fecha", "cantidad": "Reuniones"},
    )
    st.plotly_chart(fig, use_container_width=True)


def render(user: dict, supabase):
    if (user.get("ambito") or "").strip().upper() != "AGENDA":
        st.warning("No tenes permisos para ver este modulo.")
        return

    st.header("Visualización de Reuniones")

    try:
        df = fetch_reuniones(supabase)
        vertical_options = fetch_scope_options(supabase, "VERTICAL")
        comuna_options = fetch_scope_options(supabase, "COMUNA")
    except Exception as exc:
        st.error(f"Error al obtener reuniones: {exc}")
        return

    fecha_desde, fecha_hasta, verticales, comunas = render_agenda_filters(
        df,
        vertical_options,
        comuna_options,
        key_prefix="agenda_kpis",
    )
    df_filtrado = apply_reuniones_filters(df, fecha_desde, fecha_hasta, verticales, comunas)

    c1, c2 = st.columns(2)
    with c1:
        # AGENDA cuenta comunas solo desde reuniones cuyo scope_tipo es COMUNA.
        _render_bar(_scope_counts(df_filtrado, "COMUNA"), "Reuniones por Comuna", "Comuna")
    with c2:
        # AGENDA cuenta verticales solo desde reuniones cuyo scope_tipo es VERTICAL.
        _render_bar(_scope_counts(df_filtrado, "VERTICAL"), "Reuniones por Vertical", "Vertical")

    _render_timeline(df_filtrado)

    st.markdown("### Reuniones filtradas")
    st.dataframe(prepare_reuniones_table(df_filtrado), use_container_width=True, hide_index=True)
