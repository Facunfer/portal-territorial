#!/usr/bin/env python3
"""
migrate_personas.py
===================
Ejecutar desde la carpeta del proyecto:
    python migrate_personas.py

PASOS QUE REALIZA:
  1. Limpia personas.csv  → elimina IDs duplicados (33214, 33215)
  2. Limpia CRM CSV       → deduplica DNIs con reglas específicas
  3. UPSERT en Supabase   → actualiza/inserta personas en lotes
  4. INSERT CRM           → inserta registros nuevos del CRM
"""

import sys
import os
import csv
import json
import re
import datetime
from collections import defaultdict

# ── path del proyecto ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_supabase

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
PATH_PERSONAS = r"C:\Users\usuario\Downloads\personas - personas.csv"
PATH_CRM      = r"C:\Users\usuario\Downloads\EXPORTACIÓN CRM - EXPORTACIÓN TABLA.csv"
CRM_ENCODING  = "latin-1"
BATCH_SIZE    = 500

# IDs a eliminar de personas.csv (Facundo Fernicola duplicado)
IDS_EXCLUIR_PERSONAS = {"33214", "33215"}

# Reglas especiales para duplicados en CRM (DNI → acción)
# keep_keyword: conservar la fila cuyo nombre contenga este substring (case-insensitive)
# discard_both: eliminar ambas filas
CRM_REGLAS_ESPECIALES = {
    "49316027": {"accion": "keep_keyword", "keyword": "daniela"},      # Daniela vs Ursula
    "47297376": {"accion": "keep_keyword", "keyword": "francisco"},     # Francisco vs Augusto
    "12341234": {"accion": "discard_both"},                             # DNI falso
    "93962434": {"accion": "keep_keyword", "keyword": "meza"},          # nombre más completo
    "42659124": {"accion": "keep_keyword", "keyword": "schvartzer"},    # nombre más completo
    "13416605": {"accion": "keep_keyword", "keyword": "francisco"},     # nombre más completo
}

# ==============================================================================
# HELPERS
# ==============================================================================
def vacio(v) -> None:
    """Devuelve None si el valor es vacío, sino el string limpio."""
    s = (v or "").strip()
    return s if s else None

def parse_int(v):
    """Convierte a int tolerando floats y strings vacíos."""
    try:
        s = str(v).strip()
        return int(float(s)) if s else None
    except (ValueError, TypeError):
        return None

def parse_tags(v):
    """Parsea el campo tags desde JSON string a lista Python."""
    s = (v or "").strip()
    if not s or s == "[]":
        return []
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def extraer_comuna_id(v):
    """'COMUNA 3' → 3,  '3' → 3,  '' → None."""
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None

def capitalizar(v):
    """Capitaliza cada palabra respetando tildes."""
    return " ".join(w.capitalize() for w in (v or "").strip().split())

# ==============================================================================
# PASO 1 — Limpiar personas.csv
# ==============================================================================
def cargar_personas():
    print("📂  Cargando personas.csv ...")
    with open(PATH_PERSONAS, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    records = []
    omitidos = 0
    for r in filas:
        if r["id"].strip() in IDS_EXCLUIR_PERSONAS:
            omitidos += 1
            continue
        records.append({
            "id":             int(r["id"]),
            "nombre_apellido": vacio(r["nombre_apellido"]),
            "dni":            vacio(r["dni"]),
            "telefono":       vacio(r["telefono"]),
            "barrio":         vacio(r["barrio"]),
            "comuna_id":      parse_int(r["comuna_id"]),
            "domicilio":      vacio(r["domicilio"]),
            "email":          vacio(r["email"]),
            "sexo":           vacio(r["sexo"]),
            "edad":           parse_int(r["edad"]),
            "de_donde_salio": vacio(r["de_donde_salio"]),
            "fiscalizo":      vacio(r["fiscalizo"]),
            "creado_en":      vacio(r["creado_en"]),
            "actualizado_en": vacio(r["actualizado_en"]),
            "tags":           parse_tags(r["tags"]),
            "asignado_en":    vacio(r["asignado_en"]),
            "latitud":        vacio(r["latitud"]),
            "longitud":       vacio(r["longitud"]),
        })

    print(f"    ✅ {len(records):,} personas válidas  |  {omitidos} omitidas (IDs {IDS_EXCLUIR_PERSONAS})")
    return records


# ==============================================================================
# PASO 2 — Limpiar CRM y mapear al schema de personas
# ==============================================================================
def cargar_crm(dnis_existentes: set):
    print("📂  Cargando CRM CSV ...")
    with open(PATH_CRM, encoding=CRM_ENCODING) as f:
        filas = list(csv.DictReader(f))

    # Agrupar por DNI para aplicar reglas especiales
    por_dni = defaultdict(list)
    for r in filas:
        dni = r["DNI"].strip()
        if dni:
            por_dni[dni].append(r)

    dnis_descartar = {
        dni for dni, regla in CRM_REGLAS_ESPECIALES.items()
        if regla["accion"] == "discard_both"
    }

    records = []
    dnis_vistos = set()
    omitidos_existentes = 0
    omitidos_dup = 0
    omitidos_descarte = 0

    for r in filas:
        dni = r["DNI"].strip()

        if not dni:
            continue

        # Ya existe en personas → ignorar
        if dni in dnis_existentes:
            omitidos_existentes += 1
            continue

        # Regla: descartar ambos
        if dni in dnis_descartar:
            omitidos_descarte += 1
            continue

        # Ya procesamos este DNI en esta corrida
        if dni in dnis_vistos:
            omitidos_dup += 1
            continue

        # Regla especial: elegir la fila con el keyword correcto
        fila = r
        if dni in CRM_REGLAS_ESPECIALES:
            regla = CRM_REGLAS_ESPECIALES[dni]
            kw = regla.get("keyword", "").lower()
            candidatos = por_dni[dni]
            elegido = next(
                (c for c in candidatos if kw in c["Nombre y Apellido"].lower()),
                None
            )
            if elegido:
                fila = elegido

        dnis_vistos.add(dni)

        records.append({
            "nombre_apellido": capitalizar(fila.get("Nombre y Apellido", "")),
            "dni":             dni,
            "telefono":        vacio(fila.get("Teléfono", "")),
            "barrio":          vacio(fila.get("Barrio", "")),
            "comuna_id":       extraer_comuna_id(fila.get("Comuna", "")),
            "domicilio":       vacio(fila.get("Domicilio", "")),
            "email":           vacio(fila.get("Email", "")),
            "sexo":            vacio(fila.get("Sexo", "")),
            "edad":            parse_int(fila.get("Edad", "")),
            "de_donde_salio":  vacio(fila.get("De Donde Salió", "")),
            "fiscalizo":       None,
            "creado_en":       datetime.date.today().isoformat(),
            "actualizado_en":  datetime.datetime.utcnow().isoformat() + "+00:00",
            "tags":            [],
            "asignado_en":     None,
            "latitud":         None,
            "longitud":        None,
            # Sin 'id' → Supabase asigna el siguiente de la secuencia
        })

    print(f"    ✅ {len(records):,} registros CRM a insertar")
    print(f"       Omitidos (ya en personas): {omitidos_existentes}")
    print(f"       Omitidos (dup internos):   {omitidos_dup}")
    print(f"       Omitidos (DNI inválido):   {omitidos_descarte}")
    return records


# ==============================================================================
# PASO 3 — UPSERT personas en Supabase
# ==============================================================================
def upsert_personas(supabase, records):
    total = len(records)
    print(f"\n🔄  Upsertando {total:,} personas en Supabase (lotes de {BATCH_SIZE}) ...")
    errores = 0

    for i in range(0, total, BATCH_SIZE):
        lote = records[i : i + BATCH_SIZE]
        try:
            supabase.table("personas").upsert(lote, on_conflict="id").execute()
            pct = min(i + BATCH_SIZE, total)
            print(f"    {pct:,}/{total:,}", end="\r")
        except Exception as e:
            print(f"\n    ❌ Error lote {i}–{i+BATCH_SIZE}: {e}")
            errores += 1

    estado = "✅" if errores == 0 else f"⚠️  ({errores} lotes con error)"
    print(f"\n    {estado} Upsert de personas finalizado.")


# ==============================================================================
# PASO 4 — INSERT CRM en Supabase
# ==============================================================================
def insertar_crm(supabase, records):
    total = len(records)
    print(f"\n➕  Insertando {total:,} registros del CRM (lotes de {BATCH_SIZE}) ...")
    errores = 0

    for i in range(0, total, BATCH_SIZE):
        lote = records[i : i + BATCH_SIZE]
        try:
            supabase.table("personas").insert(lote).execute()
            pct = min(i + BATCH_SIZE, total)
            print(f"    {pct:,}/{total:,}", end="\r")
        except Exception as e:
            print(f"\n    ❌ Error lote {i}–{i+BATCH_SIZE}: {e}")
            errores += 1

    estado = "✅" if errores == 0 else f"⚠️  ({errores} lotes con error)"
    print(f"\n    {estado} Insert del CRM finalizado.")


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 60)
    print("  MIGRACIÓN DE PERSONAS")
    print("=" * 60)

    supabase = get_supabase()

    # Cargar y limpiar datos
    personas  = cargar_personas()
    dnis_en_personas = {str(r["dni"]) for r in personas if r["dni"]}
    crm       = cargar_crm(dnis_en_personas)

    total_final = len(personas) + len(crm)

    print(f"\n{'─'*60}")
    print(f"  RESUMEN ANTES DE EJECUTAR:")
    print(f"    UPSERT personas.csv : {len(personas):>8,} registros")
    print(f"    INSERT CRM          : {len(crm):>8,} registros")
    print(f"    TOTAL final         : {total_final:>8,} personas")
    print(f"{'─'*60}")
    print(f"\n  ⚠️  IMPORTANTE: Antes de correr este script asegurate de")
    print(f"     haber ejecutado el backup en Supabase SQL Editor:")
    print(f"     CREATE TABLE personas_bkp AS SELECT * FROM personas;\n")

    confirm = input("  ¿Ejecutar migración? (escribí SI para confirmar): ").strip().upper()
    if confirm != "SI":
        print("  Migración cancelada.")
        return

    upsert_personas(supabase, personas)
    insertar_crm(supabase, crm)

    print("\n" + "=" * 60)
    print("  ✅  MIGRACIÓN COMPLETADA")
    print("=" * 60)
    print("\n  Último paso — corré esto en Supabase SQL Editor:")
    print("""
    SELECT setval(
        pg_get_serial_sequence('personas', 'id'),
        (SELECT MAX(id) FROM personas)
    );
    """)
    print("  Esto garantiza que los próximos IDs autogenerados")
    print("  no colisionen con los que ya existen.\n")


if __name__ == "__main__":
    main()
