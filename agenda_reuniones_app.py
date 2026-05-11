# agenda_reuniones_app.py
import datetime

import pandas as pd
import streamlit as st


AGENDA_REUNIONES_COLUMNS = [
    "fecha",
    "hora",
    "tipo",
    "subtipo_reunion",
    "titulo",
    "lugar",
    "scope_tipo",
    "scope_valor",
    "participantes_estimados",
    "realizada",
]


def _fetch_all(query) -> pd.DataFrame:
    rows = []
    page = 0
    page_size = 1000
    while True:
        res = query.range(page * page_size, (page + 1) * page_size - 1).execute()
        data = res.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        page += 1
    return pd.DataFrame(rows)


def fetch_scope_options(supabase, scope_tipo: str) -> list[str]:
    # AGENDA arma filtros desde reuniones reales; no usa listas hardcodeadas.
    q = supabase.table("reuniones").select("scope_valor").eq("scope_tipo", scope_tipo)
    df = _fetch_all(q)
    if df.empty or "scope_valor" not in df.columns:
        return []
    valores = {
        str(v).strip()
        for v in df["scope_valor"].dropna().tolist()
        if str(v).strip()
    }
    return sorted(valores)


def fetch_reuniones(supabase) -> pd.DataFrame:
    # AGENDA ve todas las reuniones sin aplicar scope de usuario.
    q = supabase.table("reuniones").select(", ".join(AGENDA_REUNIONES_COLUMNS))
    df = _fetch_all(q)
    if df.empty:
        return pd.DataFrame(columns=AGENDA_REUNIONES_COLUMNS)
    return df


def _date_bounds(df: pd.DataFrame) -> tuple[datetime.date, datetime.date]:
    if df.empty or "fecha" not in df.columns:
        today = datetime.date.today()
        return today - datetime.timedelta(days=30), today

    fechas = pd.to_datetime(df["fecha"], errors="coerce").dropna()
    if fechas.empty:
        today = datetime.date.today()
        return today - datetime.timedelta(days=30), today
    return fechas.min().date(), fechas.max().date()


def normalize_date_range(rango) -> tuple[datetime.date, datetime.date]:
    today = datetime.date.today()
    if isinstance(rango, tuple) and len(rango) == 2:
        return rango[0], rango[1]
    if isinstance(rango, list) and len(rango) == 2:
        return rango[0], rango[1]
    if isinstance(rango, datetime.date):
        return rango, rango
    return today, today


def render_agenda_filters(
    df: pd.DataFrame,
    vertical_options: list[str],
    comuna_options: list[str],
    key_prefix: str,
) -> tuple[datetime.date, datetime.date, list[str], list[str]]:
    min_fecha, max_fecha = _date_bounds(df)

    with st.container(border=True):
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            rango = st.date_input(
                "Rango de fechas",
                value=(min_fecha, max_fecha),
                key=f"{key_prefix}_fechas",
            )
        with c2:
            verticales = st.multiselect(
                "Vertical",
                vertical_options,
                key=f"{key_prefix}_verticales",
            )
        with c3:
            comunas = st.multiselect(
                "Comuna",
                comuna_options,
                key=f"{key_prefix}_comunas",
            )

    fecha_desde, fecha_hasta = normalize_date_range(rango)
    return fecha_desde, fecha_hasta, verticales, comunas


def apply_reuniones_filters(
    df: pd.DataFrame,
    fecha_desde: datetime.date,
    fecha_hasta: datetime.date,
    verticales: list[str],
    comunas: list[str],
) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    fechas = pd.to_datetime(out["fecha"], errors="coerce").dt.date
    out = out[(fechas >= fecha_desde) & (fechas <= fecha_hasta)]

    scope_masks = []
    if verticales:
        # AGENDA filtra vertical solo en filas con scope_tipo="VERTICAL".
        scope_masks.append(
            (out["scope_tipo"].fillna("").astype(str).str.upper() == "VERTICAL")
            & out["scope_valor"].fillna("").astype(str).isin(verticales)
        )
    if comunas:
        # AGENDA filtra comuna solo en filas con scope_tipo="COMUNA".
        scope_masks.append(
            (out["scope_tipo"].fillna("").astype(str).str.upper() == "COMUNA")
            & out["scope_valor"].fillna("").astype(str).isin(comunas)
        )

    if scope_masks:
        mask = scope_masks[0]
        for extra_mask in scope_masks[1:]:
            mask = mask | extra_mask
        out = out[mask]

    return out


def prepare_reuniones_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=AGENDA_REUNIONES_COLUMNS)

    out = df.copy()
    out = out[[c for c in AGENDA_REUNIONES_COLUMNS if c in out.columns]]
    out["fecha_sort"] = pd.to_datetime(out["fecha"], errors="coerce")
    out = out.sort_values("fecha_sort", ascending=False).drop(columns=["fecha_sort"])
    return out


def render(user: dict, supabase):
    if (user.get("ambito") or "").strip().upper() != "AGENDA":
        st.warning("No tenes permisos para ver este modulo.")
        return

    st.header("Agenda de Reuniones")

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
        key_prefix="agenda_reuniones",
    )
    df_filtrado = apply_reuniones_filters(df, fecha_desde, fecha_hasta, verticales, comunas)
    df_show = prepare_reuniones_table(df_filtrado)

    # Renombrar columnas para visualización
    cols_rename = {
        "fecha": "Fecha",
        "hora": "Hora",
        "tipo": "Tipo",
        "subtipo_reunion": "Subtipo",
        "titulo": "Título",
        "lugar": "Lugar",
        "scope_tipo": "Ámbito",
        "scope_valor": "Valor Ámbito",
        "participantes_estimados": "Participantes",
        "realizada": "Realizada",
    }
    df_show = df_show.rename(columns={k: v for k, v in cols_rename.items() if k in df_show.columns})

    st.dataframe(df_show, use_container_width=True, hide_index=True)
