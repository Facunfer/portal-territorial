# permisos.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# =========================
# Constantes
# =========================
AMBITOS = ["GLOBAL", "COMUNA", "VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]
ROLES = ["CABEZA", "MASTER", "EXTRACTO"]

VERT_PERSONAS = ["JUVENTUD", "GENERACION_PLATEADA", "MIGRANTES", "PROFESIONALES"]
VERT_ASOC = ["ASOCIACIONES_CIVILES", "CENTROS_COMERCIALES", "CULTO"]


def _up(s: Optional[str]) -> str:
    return (s or "").strip().upper()


@dataclass(frozen=True)
class Scope:
    """
    Scope describe cómo restringir acceso:
    - kind="ALL"            -> sin filtro
    - kind="COMUNA"         -> filtrar por comuna_id = user.comuna_id
    - kind="TAG"            -> filtrar personas por tag (value)
    - kind="ASOC_TIPO"      -> filtrar asociaciones por tipo (value: string con "|" )
    - kind="USERS_VERTICAL" -> filtrar usuarios por (ambito+vertical)
    - kind="ASSIGNED"       -> ver solo lo asignado (usuarios_asignaciones)
    """
    kind: str
    value: Optional[str] = None


# =========================
# Helpers: leer esquema nuevo
# =========================
def get_ambito(user: dict) -> str:
    return _up(user.get("ambito"))


def get_rol(user: dict) -> str:
    return _up(user.get("rol"))


def get_vertical(user: dict) -> str:
    return _up(user.get("vertical"))


def is_global_master(user: dict) -> bool:
    return get_ambito(user) == "GLOBAL" and get_rol(user) == "MASTER"


def is_comuna_user(user: dict) -> bool:
    return get_ambito(user) == "COMUNA"


def is_vertical_personas(user: dict) -> bool:
    return get_ambito(user) == "VERTICAL_PERSONAS" and get_vertical(user) in VERT_PERSONAS


def is_vertical_asoc(user: dict) -> bool:
    return get_ambito(user) == "VERTICAL_ASOCIACIONES" and get_vertical(user) in VERT_ASOC


# =========================
# Scopes por módulo
# =========================
def personas_scope(user: dict) -> Scope:
    # EXTRACTO: siempre ve SOLO lo asignado (independiente del ámbito)
    if get_rol(user) == "EXTRACTO":
        return Scope(kind="ASSIGNED")

    if is_global_master(user):
        return Scope(kind="ALL")

    if is_comuna_user(user):
        return Scope(kind="COMUNA")

    if is_vertical_personas(user):
        tag_map = {
            "JUVENTUD": "JUVENTUD|BASES|UNIVERSIDAD",
            "GENERACION_PLATEADA": "GENERACIÓN PLATEADA",
            "MIGRANTES": "MIGRANTE",
            "PROFESIONALES": "PROFESIONAL",
            "CULTO": "CULTO",
            "CENTROS_COMERCIALES": "PYME|COMERCIANTE",
        }
        return Scope(kind="TAG", value=tag_map.get(get_vertical(user)))

    return Scope(kind="ALL")


def asociaciones_scope(user: dict) -> Scope:
    """
    Vertical asociaciones:
      - ASOCIACIONES_CIVILES -> Centros de Jubilados, Clubes, Espacios Culturales
      - CULTO               -> Espacios de Culto
      - CENTROS_COMERCIALES -> Local comercial
    """
    # EXTRACTO: siempre ve SOLO lo asignado (independiente del ámbito)
    if get_rol(user) == "EXTRACTO":
        return Scope(kind="ASSIGNED")

    if is_global_master(user):
        return Scope(kind="ALL")

    if is_comuna_user(user):
        return Scope(kind="COMUNA")

    if is_vertical_asoc(user):
        v = get_vertical(user)
        tipo_map = {
            "ASOCIACIONES_CIVILES": "Centros de Jubilados|Clubes|Espacios Culturales",
            "CULTO": "Espacios de Culto",
            "CENTROS_COMERCIALES": "Local comercial",
        }
        return Scope(kind="ASOC_TIPO", value=tipo_map.get(v))

    return Scope(kind="ALL")


def users_scope(user: dict) -> Scope:
    """
    - GLOBAL MASTER: ve todo
    - COMUNA: ve usuarios con comuna_id = la suya
    - VERTICAL_*: ve usuarios con (ambito igual) y (vertical igual)
    """
    if is_global_master(user):
        return Scope(kind="ALL")

    if is_comuna_user(user):
        return Scope(kind="COMUNA")

    if is_vertical_personas(user) or is_vertical_asoc(user):
        # value guarda "AMBITO|VERTICAL"
        return Scope(kind="USERS_VERTICAL", value=f"{get_ambito(user)}|{get_vertical(user)}")

    # fallback seguro: no debería entrar
    return Scope(kind="ALL")


# =========================
# Permisos de administración de usuarios
# =========================
def can_manage_users(user: dict) -> bool:
    """
    Quién puede administrar usuarios:
    - GLOBAL MASTER: sí (todo)
    - CABEZA: sí (su ámbito)
    - MASTER: sí (su ámbito)
    - EXTRACTO: no
    """
    if is_global_master(user):
        return True
    return get_rol(user) in ["CABEZA", "MASTER"]


def allowed_modules(user: dict) -> List[str]:
    """
    Determina qué módulos puede ver el usuario.
    """
    amb = get_ambito(user)
    rol = get_rol(user)
    
    # 1. Módulos base por ámbito
    if amb == "GLOBAL":
        out = ["Personas", "Asociaciones", "Master Global"]
    elif amb == "COMUNA":
        out = ["Personas", "Asociaciones"]
    elif amb == "VERTICAL_PERSONAS":
        out = ["Personas"]
    elif amb == "VERTICAL_ASOCIACIONES":
        out = ["Asociaciones"]
        # Especial: CULTO y CENTROS_COMERCIALES ven Personas también (por tags)
        if get_vertical(user) in ["CULTO", "CENTROS_COMERCIALES"]:
            out.append("Personas")
    else:
        out = ["Personas", "Asociaciones"]

    # 2. Agregar 'Reuniones', 'Visualización' e 'Consulta' para roles Master/Cabeza
    if rol in ["MASTER", "CABEZA"]:
        out.append("Reuniones")
        
        # EXCEPCION: GLOBAL MASTER ya tiene su dashboard unificado, no necesita IA ni Visualización
        if not is_global_master(user):
            out.append("Visualización")
            out.append("Consultas")

    # 3. Agregar 'Usuarios' si tiene permiso de admin
    if can_manage_users(user):
        out.append("Usuarios")

    return out


def creatable_roles(user: dict) -> Dict[str, Any]:
    """
    Devuelve un dict con reglas de creación:
      - ambito_fijo: str o None (si puede elegir)
      - vertical_fijo: str o None
      - comuna_fija: int o None
      - roles_permitidos: lista de roles asignables al nuevo usuario
      - tipo_usuario_fijo: str o None
    """
    if is_global_master(user):
        return {
            "ambito_fijo": None,
            "vertical_fijo": None,
            "comuna_fija": None,
            "roles_permitidos": ["CABEZA", "MASTER", "EXTRACTO"],
            "tipo_usuario_fijo": None,
        }

    # COMUNA (referentes / masters de comuna)
    if is_comuna_user(user):
        return {
            "ambito_fijo": "COMUNA",
            "vertical_fijo": None,
            "comuna_fija": user.get("comuna_id"),
            "roles_permitidos": ["MASTER", "EXTRACTO"],
            "tipo_usuario_fijo": "REFERENTE",
        }

    # Verticales: pueden crear dentro de su vertical
    if is_vertical_personas(user):
        return {
            "ambito_fijo": "VERTICAL_PERSONAS",
            "vertical_fijo": get_vertical(user),
            "comuna_fija": None,
            "roles_permitidos": ["MASTER", "EXTRACTO"],
            "tipo_usuario_fijo": "MASTER",
        }

    if is_vertical_asoc(user):
        return {
            "ambito_fijo": "VERTICAL_ASOCIACIONES",
            "vertical_fijo": get_vertical(user),
            "comuna_fija": None,
            "roles_permitidos": ["MASTER", "EXTRACTO"],
            "tipo_usuario_fijo": "MASTER",
        }

    # fallback
    return {
        "ambito_fijo": None,
        "vertical_fijo": None,
        "comuna_fija": None,
        "roles_permitidos": [],
        "tipo_usuario_fijo": None,
    }
