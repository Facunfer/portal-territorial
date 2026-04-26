# personas_scope_rules.py
import streamlit as st
import pandas as pd

# =========================
# CONFIG / CONSTANTES
# =========================
VERTICAL_TAGS_MAP = {
    # Existentes
    "CULTO": ["CULTO"],
    "JUVENTUD": ["JUVENTUD", "BASES", "UNIVERSIDAD"],
    "GENERACION_PLATEADA": ["GENERACIÓN PLATEADA"],
    "MIGRANTES": ["MIGRANTE"],
    "PROFESIONALES": ["PROFESIONAL"],
    # Nuevas
    "CCAA": ["COMERCIANTE"],
    "PYMES": ["PYME"],
    "JOVENES_EMPRESARIOS": ["EMPRENDEDOR"],
    "EDUCACION": ["EDUCACIÓN"],
    "SALUD": ["SALUD"],
    "CULTURA": ["CULTURA"],
}

def is_restricted_vertical(user_ctx: dict) -> bool:
    vertical = (user_ctx.get("vertical") or "").strip().upper()
    return vertical in VERTICAL_TAGS_MAP

def get_vertical_tags(user_ctx: dict) -> list:
    vertical = (user_ctx.get("vertical") or "").strip().upper()
    return VERTICAL_TAGS_MAP.get(vertical, [])

def _detect_tags_type(query):
    """
    Detecta si la columna 'tags' es array o string.
    Cachea el resultado en session_state para no repetir la consulta.
    """
    if "personas_tags_type" in st.session_state:
        return st.session_state["personas_tags_type"]

    # Hacemos una mini-consulta para detectar el tipo.
    # No usamos .select() extra porque query ya trae sus columnas.
    try:
        res = query.limit(1).execute()
        if res.data:
            val = res.data[0].get("tags")
            # Si es una lista, es ARRAY. Si es string o None, asumimos STRING para ilike.
            # Nota: Si es None en la primera fila, es ambiguo, pero ARRAY es más común en fallos.
            if isinstance(val, list):
                res_type = "ARRAY"
            else:
                res_type = "STRING"
            
            st.session_state["personas_tags_type"] = res_type
            return res_type
        else:
            # Si está vacío, no guardamos en session_state para re-intentar luego si hace falta,
            # pero devolvemos ARRAY que es lo más probable dado el error reportado.
            return "ARRAY"
    except Exception:
        # Si falla, devolvemos ARRAY como fallback seguro (el error del usuario confirma que es text[])
        return "ARRAY"

def apply_personas_visibility_filter(query, user_ctx: dict, force_filter: bool = True):
    """
    Aplica filtros de visibilidad a una query de Supabase para la tabla 'personas'.
    Soporta tags como string o como array text[].
    
    force_filter: si True, aplica el filtro de vertical si corresponde.
    """
    rol = (user_ctx.get("rol") or "").strip().upper()
    vertical = (user_ctx.get("vertical") or "").strip().upper()
    ambito = (user_ctx.get("ambito") or "").strip().upper()
    comuna_id = user_ctx.get("comuna_id")

    # 1. ADMIN / GLOBAL MASTER: No filtramos
    if ambito == "GLOBAL" and rol == "MASTER":
        return query

    # 2. Casos especiales: CULTO, CENTROS_COMERCIALES, etc.
    if vertical in VERTICAL_TAGS_MAP and force_filter:
        tags_to_filter = VERTICAL_TAGS_MAP[vertical]
        
        # Detectamos el tipo de la columna para usar el operador correcto
        col_type = _detect_tags_type(query)
        
        or_filters = []
        for tag in tags_to_filter:
            if col_type == "ARRAY":
                # Filtro array: tags.cs.{"VAL"}
                or_filters.append(f'tags.cs.{{"{tag}"}}')
            else:
                # Filtro string: tags.ilike.%VAL%
                or_filters.append(f"tags.ilike.%{tag}%")
            
        return query.or_(",".join(or_filters))

    # 3. Fallback a lógica existente (Comuna)
    if ambito == "COMUNA" and comuna_id is not None:
        return query.eq("comuna_id", int(comuna_id))

    return query
