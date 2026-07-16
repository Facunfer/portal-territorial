# permisos.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from constants import TAGS_CONTROLADOS_POR_VERTICAL, TODOS_LOS_TAGS_CONTROLADOS


# =========================
# Constantes
# =========================
AMBITOS = ["GLOBAL", "COMUNA", "VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES", "SEGMENTOS", "AGENDA"]
ROLES = ["CABEZA", "MASTER", "EXTRACTO"]

VERT_PERSONAS = [
    "JUVENTUD", "GENERACION_PLATEADA", "MIGRANTES", "PROFESIONALES",
    "CCAA", "PYMES", "JOVENES_EMPRESARIOS", "INNOVACION_TECNOLOGIA",
    "EDUCACION", "SALUD", "CULTURA", "CULTO",
]
VERT_ASOC = ["CULTO", "CCAA", "CULTURA", "CLUBES"]  # CLUBES usa el scope ASOC_TIPO con tipo="Clubes".


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
    - kind="NONE"           -> sin acceso a datos de ese modulo
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


def is_segmentos(user: dict) -> bool:
    return get_ambito(user) == "SEGMENTOS"


def is_agenda_user(user: dict) -> bool:
    return get_ambito(user) == "AGENDA"


def is_vertical_personas(user: dict) -> bool:
    amb = get_ambito(user)
    vert = get_vertical(user)
    if amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"] and vert in VERT_PERSONAS:
        return True
    return False


def is_vertical_asoc(user: dict) -> bool:
    amb = get_ambito(user)
    vert = get_vertical(user)
    if amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"] and vert in VERT_ASOC:
        return True
    return False


# =========================
# Scopes por módulo
# =========================
def personas_scope(user: dict) -> Scope:
    if is_agenda_user(user):
        # AGENDA no tiene acceso ni scope sobre personas; sus modulos son solo de reuniones.
        return Scope(kind="NONE")

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
            "GENERACION_PLATEADA": "LIBERTAD PLATEADA",
            "MIGRANTES": "MIGRANTE",
            "PROFESIONALES": "PROFESIONAL",
            "CULTO": "CULTO",
            "CCAA": "COMERCIANTE",
            "PYMES": "PYME",
            "JOVENES_EMPRESARIOS": "EMPRENDEDOR",
            "INNOVACION_TECNOLOGIA": "INNOVACIÓN TECNOLÓGICA",
            "EDUCACION": "EDUCACIÓN",
            "SALUD": "SALUD",
            "CULTURA": "CULTURA",
        }
        return Scope(kind="TAG", value=tag_map.get(get_vertical(user)))

    return Scope(kind="ALL")


def asociaciones_scope(user: dict) -> Scope:
    """
    Vertical asociaciones:
      - CULTO  -> Espacios de Culto
      - CCAA   -> Local comercial
      - CULTURA -> Espacios Culturales
      - CLUBES -> Clubes
    """
    if is_agenda_user(user):
        # AGENDA no tiene acceso ni scope sobre asociaciones; ve reuniones globales read-only.
        return Scope(kind="NONE")

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
            "CULTO": "Espacios de Culto",
            "CCAA": "Local comercial",
            "CULTURA": "Espacios Culturales",
            "CLUBES": "Clubes",
        }
        return Scope(kind="ASOC_TIPO", value=tipo_map.get(v))

    return Scope(kind="ALL")


def users_scope(user: dict) -> Scope:
    """
    - GLOBAL MASTER: ve todo
    - COMUNA: ve usuarios con comuna_id = la suya
    - VERTICAL_*: ve usuarios con (ambito igual) y (vertical igual)
    """
    if is_agenda_user(user):
        # AGENDA no administra usuarios, por eso no recibe scope administrativo.
        return Scope(kind="NONE")

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
    - CABEZA/MASTER de COMUNA o VERTICAL: sí solo si es_original=True
    - EXTRACTO: no
    """
    if is_agenda_user(user):
        # AGENDA es EXTRACTO read-only y nunca ve el modulo Usuarios.
        return False

    if is_global_master(user):
        return True

    if get_ambito(user) in ["COMUNA", "VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
        # Usuarios creados por otros masters/cabezas no heredan administracion de usuarios.
        return get_rol(user) in ["CABEZA", "MASTER"] and bool(user.get("es_original", False))

    return get_rol(user) in ["CABEZA", "MASTER"]


def allowed_modules(user: dict) -> List[str]:
    """
    Determina qué módulos puede ver el usuario.
    """
    amb = get_ambito(user)
    rol = get_rol(user)

    if amb == "AGENDA":
        # AGENDA tiene sidebar aislado: solo consulta y visualizacion read-only de reuniones.
        return ["Agenda de Reuniones", "Visualización de Reuniones"]
    
    # SEGMENTOS: Reuniones/Actividades, Mapa Relacionamiento y Visualización
    if amb == "SEGMENTOS":
        return ["Reuniones/Actividades", "Mapa Relacionamiento", "Visualización"]
    
    # 1. Módulos base por ámbito
    if amb == "GLOBAL":
        out = ["Personas", "Asociaciones", "Master Global"]
    elif amb == "COMUNA":
        out = ["Personas", "Asociaciones"]
    elif amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
        out = []
        vert = get_vertical(user)
        if vert in VERT_PERSONAS:
            out.append("Personas")
        if vert in VERT_ASOC:
            out.append("Asociaciones")
    else:
        out = ["Personas", "Asociaciones"]

    # 2. Agregar 'Reuniones/Actividades', 'Visualización' e 'Consulta' para roles Master/Cabeza
    if rol in ["MASTER", "CABEZA"]:
        out.append("Reuniones/Actividades")
        # Mapa Relacionamiento SOLO para verticales
        if amb in ["VERTICAL_PERSONAS", "VERTICAL_ASOCIACIONES"]:
            out.append("Mapa Relacionamiento")
        
        # EXCEPCION: GLOBAL MASTER ya tiene su dashboard unificado, no necesita IA ni Visualización
        if not is_global_master(user):
            out.append("Visualización")
            out.append("Consultas")

    # 3. Agregar 'Usuarios' si tiene permiso de admin
    if can_manage_users(user):
        out.append("Usuarios")

    return out


# =========================
# Tags controlados por vertical
# =========================

def tags_controlados_del_usuario(user: dict) -> set:
    """Tags controlados que este usuario puede crear, asignar y quitar.
    El Global Master puede gestionar todos. Una vertical específica solo los suyos.
    Cualquier otro usuario devuelve set vacío (no puede crear/quitar tags controlados)."""
    if is_global_master(user):
        return set(TODOS_LOS_TAGS_CONTROLADOS)
    vertical = _up(user.get("vertical"))
    return set(TAGS_CONTROLADOS_POR_VERTICAL.get(vertical, []))


def puede_gestionar_tag(user: dict, tag: str) -> bool:
    """True si el usuario puede agregar/quitar este tag.
    Tags generales (no controlados): cualquier usuario con permiso de edición puede.
    Tags controlados: solo el dueño de la vertical (o GM)."""
    if tag not in TODOS_LOS_TAGS_CONTROLADOS:
        return True
    return tag in tags_controlados_del_usuario(user)


def creatable_roles(user: dict) -> Dict[str, Any]:
    """
    Devuelve un dict con reglas de creación:
      - ambito_fijo: str o None (si puede elegir)
      - vertical_fijo: str o None
      - comuna_fija: int o None
      - roles_permitidos: lista de roles asignables al nuevo usuario
      - tipo_usuario_fijo: str o None
    """
    if is_agenda_user(user):
        # AGENDA no puede crear usuarios desde el sistema.
        return {
            "ambito_fijo": None,
            "vertical_fijo": None,
            "comuna_fija": None,
            "roles_permitidos": [],
            "tipo_usuario_fijo": None,
        }

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
