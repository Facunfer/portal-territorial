VERTICALES_SEGMENTOS: list[str] = [
    "GENERACION_PLATEADA",
    "MIGRANTES",
    "CULTO",
    "CCAA",
    "PYMES",
    "JOVENES_EMPRESARIOS",
    "INNOVACION_TECNOLOGIA",
    "EDUCACION",
    "SALUD",
    "CULTURA",
]

# Lista canónica de tags asignables a personas (personas.tags es text[]).
# Fuente ÚNICA: alimenta el selector de alta/quita de tags en la ficha, el form de
# nueva persona y las opciones del filtro de tags de la tabla. Respetar mayúsculas/acentos
# exactos del literal (es lo que se guarda en personas.tags).
TAGS_FIJOS: list[str] = [
    "JUVENTUD",
    "LIBERTAD PLATEADA",
    "MIGRANTE",
    "PROFESIONAL",
    "FISCAL OCTUBRE",
    "FISCAL MAYO",
    "AFILIADO",
    "PARTE DEL EQUIPO",
    "FISCAL GENERAL",
    "CULTO",
    "PYME",
    "COMERCIANTE",
    "BASES",
    "UNIVERSIDAD",
    "VECINO EMBLEMATICO",
    "PORTERO/ENCARGADO",
    "EMPRENDEDOR",
    "EDUCACIÓN",
    "SALUD",
    "CULTURA",
    "PARTICIPANDO",
    "SACAR DE LA BASE",
]

# =============================================================================
# Tags controlados por vertical
# =============================================================================
# Fuente única. Clave = usuarios.vertical (mayúsculas exactas).
# Los sub-tags de PROFESIONALES llevan prefijo "PROF: " para no colisionar con
# los tags de visibilidad de las verticales SALUD y EDUCACION (que buscan los
# strings "SALUD" y "EDUCACIÓN" a secas). Migrantes usa "NAC: " por simetría.
TAGS_CONTROLADOS_POR_VERTICAL: dict[str, list[str]] = {
    "PROFESIONALES": [
        "PROF: ABOGADO",
        "PROF: INGENIERO",
        "PROF: ARQUITECTO",
        "PROF: ECONOMISTA",
        "PROF: CONTADOR",
        "PROF: PERIODISTA",
        "PROF: CIENCIAS SOCIALES",
        "PROF: SALUD",
        "PROF: EDUCACIÓN",
        "PROF: IT",
    ],
    "MIGRANTES": [
        "NAC: VENEZOLANO",
        "NAC: CHINO",
        "NAC: COREANO",
        "NAC: BOLIVIANO",
        "NAC: PERUANO",
        "NAC: URUGUAYO",
        "NAC: CHILENO",
    ],
}

# Labels visibles en la UI (Title Case). Para tags sin entrada, la UI muestra el string canónico.
TAGS_CONTROLADOS_LABELS: dict[str, str] = {
    "PROF: ABOGADO": "Abogado",
    "PROF: INGENIERO": "Ingeniero",
    "PROF: ARQUITECTO": "Arquitecto",
    "PROF: ECONOMISTA": "Economista",
    "PROF: CONTADOR": "Contador",
    "PROF: PERIODISTA": "Periodista",
    "PROF: CIENCIAS SOCIALES": "Ciencias Sociales",
    "PROF: SALUD": "Salud (Prof.)",
    "PROF: EDUCACIÓN": "Educación (Prof.)",
    "PROF: IT": "IT",
    "NAC: VENEZOLANO": "Venezolano",
    "NAC: CHINO": "Chino",
    "NAC: COREANO": "Coreano",
    "NAC: BOLIVIANO": "Boliviano",
    "NAC: PERUANO": "Peruano",
    "NAC: URUGUAYO": "Uruguayo",
    "NAC: CHILENO": "Chileno",
}

# Conjunto plano de todos los tags controlados (para detectar cuáles son "reservados").
TODOS_LOS_TAGS_CONTROLADOS: frozenset[str] = frozenset(
    t for tags in TAGS_CONTROLADOS_POR_VERTICAL.values() for t in tags
)

BARRIOS_POR_COMUNA: dict[int, list[str]] = {
    1: ["Retiro", "San Nicolás", "Puerto Madero", "San Telmo", "Montserrat", "Constitución"],
    2: ["Recoleta"],
    3: ["Balvanera", "San Cristóbal"],
    4: ["La Boca", "Barracas", "Parque Patricios", "Nueva Pompeya"],
    5: ["Almagro", "Boedo"],
    6: ["Caballito"],
    7: ["Flores", "Parque Chacabuco"],
    8: ["Villa Soldati", "Villa Riachuelo", "Villa Lugano"],
    9: ["Liniers", "Mataderos", "Parque Avellaneda"],
    10: ["Villa Real", "Monte Castro", "Versalles", "Floresta", "Vélez Sarsfield", "Villa Luro"],
    11: ["Villa General Mitre", "Villa Devoto", "Villa del Parque", "Villa Santa Rita"],
    12: ["Coghlan", "Saavedra", "Villa Pueyrredón", "Villa Urquiza"],
    13: ["Belgrano", "Colegiales", "Núñez"],
    14: ["Palermo"],
    15: ["Agronomía", "Chacarita", "La Paternal", "Villa Crespo", "Villa Ortúzar", "Parque Chas"],
}
