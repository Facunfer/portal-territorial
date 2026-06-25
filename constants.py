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
