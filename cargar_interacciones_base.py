#!/usr/bin/env python3
"""
cargar_interacciones_base.py
============================
Lee el CSV de Respuesta Base y carga una interacción por cada persona
cuya columna D (RESPUESTA OCTUBRE) no esté vacía.

Mapeo de respuestas:
  POSITIVA → POSITIVO
  NEGATIVA → NEGATIVO
  REGULAR  → NEUTRO

Ejecutar desde la carpeta del proyecto:
    python cargar_interacciones_base.py
"""

import sys
import os
import csv
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_supabase

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
PATH_CSV        = r"C:\Users\usuario\Downloads\EXPORTACIÓN CRM - RESPUESTA BASE.csv"
FECHA           = "2026-10-26"
PARA_QUE        = "contactado para la fiscalización"
MEDIO           = "Otro"
TIPO            = "interacción"
CREATED_BY_USER_ID = 1   # ← Reemplazá con tu user ID de la tabla usuarios

BATCH_SIZE      = 500

RESPUESTA_MAP = {
    "POSITIVA": "POSITIVO",
    "NEGATIVA": "NEGATIVO",
    "REGULAR":  "NEUTRO",
}

# ==============================================================================
# HELPERS
# ==============================================================================
def leer_csv(path: str) -> list[dict]:
    """
    Lee el CSV y devuelve solo las filas válidas:
      - DNI no vacío
      - Columna D (RESPUESTA OCTUBRE) no vacía y reconocida
    """
    registros = []
    omitidos_sin_respuesta = 0
    omitidos_sin_dni       = 0
    omitidos_respuesta_inv = 0

    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    dni       = str(row.get("DNI", "") or "").strip().replace(".", "")
                    respuesta_raw = str(row.get("RESPUESTA OCTUBRE", "") or "").strip().upper()

                    if not dni or not dni.isdigit():
                        omitidos_sin_dni += 1
                        continue

                    if not respuesta_raw:
                        omitidos_sin_respuesta += 1
                        continue

                    respuesta_norm = RESPUESTA_MAP.get(respuesta_raw)
                    if not respuesta_norm:
                        omitidos_respuesta_inv += 1
                        print(f"  ⚠️  Respuesta no reconocida '{respuesta_raw}' para DNI {dni} — omitido")
                        continue

                    registros.append({
                        "dni":      dni,
                        "nombre":   str(row.get("Nombre y Apellido", "") or "").strip(),
                        "respuesta": respuesta_norm,
                    })
            break
        except UnicodeDecodeError:
            continue

    print(f"\n📋 CSV leído:")
    print(f"   Con interacción a cargar : {len(registros):,}")
    print(f"   Sin respuesta (col D vacía): {omitidos_sin_respuesta:,}")
    print(f"   Sin DNI válido            : {omitidos_sin_dni:,}")
    print(f"   Respuesta no reconocida   : {omitidos_respuesta_inv:,}")
    return registros


def cargar_interacciones(supabase, registros: list[dict]) -> None:
    """
    Para cada registro:
      1. Busca el persona_id por DNI
      2. Inserta la interacción
    """
    dnis = [r["dni"] for r in registros]
    dni_to_registro = {r["dni"]: r for r in registros}

    # ── Fetch personas por DNI en batches ──────────────────────────────────────
    print(f"\n🔍  Buscando {len(dnis):,} DNIs en personas ...")
    persona_map = {}  # dni → persona_id

    for i in range(0, len(dnis), BATCH_SIZE):
        batch = dnis[i : i + BATCH_SIZE]
        try:
            res = supabase.table("personas").select("id, dni").in_("dni", batch).execute()
            for p in (res.data or []):
                persona_map[str(p["dni"]).strip()] = p["id"]
        except Exception as e:
            print(f"  ❌ Error fetch lote {i}: {e}")

    encontrados    = len(persona_map)
    no_encontrados = len(dnis) - encontrados
    print(f"   Encontrados en BD  : {encontrados:,}")
    print(f"   No encontrados en BD: {no_encontrados:,}")

    # ── Construir payloads ─────────────────────────────────────────────────────
    payloads = []
    for dni, persona_id in persona_map.items():
        reg = dni_to_registro.get(dni)
        if not reg:
            continue
        payloads.append({
            "persona_id":       persona_id,
            "fecha":            FECHA,
            "respuesta":        reg["respuesta"],
            "medio":            MEDIO,
            "para_que_contacte": PARA_QUE,
            "tipo":             TIPO,
            "created_by":       CREATED_BY_USER_ID,
            "seguimiento_cerrado": False,
        })

    # ── Insertar en batches ────────────────────────────────────────────────────
    total   = len(payloads)
    errores = 0
    print(f"\n⬆️   Insertando {total:,} interacciones ...")

    for i in range(0, total, BATCH_SIZE):
        lote = payloads[i : i + BATCH_SIZE]
        try:
            supabase.table("interacciones_personas").insert(lote).execute()
            print(f"   {min(i + BATCH_SIZE, total):,}/{total:,}", end="\r")
        except Exception as e:
            print(f"\n  ❌ Error lote {i}–{i+BATCH_SIZE}: {e}")
            errores += 1

    print(f"\n   ✅ Insertadas: {total - errores * BATCH_SIZE:,}  |  Lotes con error: {errores}")

    # ── Distribución de respuestas insertadas ──────────────────────────────────
    from collections import Counter
    conteo = Counter(p["respuesta"] for p in payloads)
    print(f"\n📊  Distribución de respuestas cargadas:")
    for resp, cant in sorted(conteo.items()):
        print(f"   {resp:<12}: {cant:,}")


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 60)
    print("  CARGA DE INTERACCIONES — RESPUESTA BASE")
    print("=" * 60)

    registros = leer_csv(PATH_CSV)

    if not registros:
        print("\n  No hay registros válidos para cargar. Saliendo.")
        return

    print(f"\n{'─'*60}")
    print(f"  RESUMEN ANTES DE EJECUTAR:")
    print(f"    Fecha de interacción : {FECHA}")
    print(f"    Motivo               : {PARA_QUE}")
    print(f"    Interacciones a cargar: {len(registros):,}")
    print(f"    Creado por (user_id) : {CREATED_BY_USER_ID}")
    print(f"{'─'*60}")

    confirm = input("\n  ¿Ejecutar carga? (escribí SI para confirmar): ").strip().upper()
    if confirm != "SI":
        print("  Cancelado.")
        return

    supabase = get_supabase()
    cargar_interacciones(supabase, registros)

    print("\n" + "=" * 60)
    print("  ✅  CARGA COMPLETADA")
    print("=" * 60)


if __name__ == "__main__":
    main()
