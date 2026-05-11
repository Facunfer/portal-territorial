#!/usr/bin/env python3
"""
tag_csv_update.py
=================
Lee los 3 CSVs y agrega los tags correspondientes a las personas
que tengan el DNI coincidente en la tabla personas de Supabase.

  AFILIADOS.csv        → tag: AFILIADO        (columna: Matrícula)
  FISCALES MAYO.csv    → tag: FISCAL MAYO     (columna: DNI)
  FISCALES OCTUBRE.csv → tag: FISCAL OCTUBRE  (columna: DNI)

Ejecutar desde la carpeta del proyecto:
    python tag_csv_update.py
"""

import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_supabase

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================
PATH_AFILIADOS       = r"C:\Users\usuario\Downloads\EXPORTACIÓN CRM - AFILIADOS.csv"
PATH_FISCALES_MAYO   = r"C:\Users\usuario\Downloads\EXPORTACIÓN CRM - FISCALES MAYO.csv"
PATH_FISCALES_OCTUBRE= r"C:\Users\usuario\Downloads\EXPORTACIÓN CRM - FISCALES OCTUBRE.csv"

BATCH_SIZE = 500   # DNIs por request de fetch


# ==============================================================================
# HELPERS
# ==============================================================================
def _abrir_csv(path: str):
    """Abre un CSV detectando encoding (utf-8 → latin-1)."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            f = open(path, encoding=enc)
            f.read(1024)
            f.seek(0)
            return f, enc
        except UnicodeDecodeError:
            f.close()
    raise RuntimeError(f"No se pudo leer el archivo: {path}")


def leer_dnis(path: str, columna: str) -> set:
    """Extrae DNIs únicos y numéricos de una columna del CSV."""
    f, enc = _abrir_csv(path)
    dnis = set()
    with f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = str(row.get(columna, "") or "").strip().replace(".", "")
            if raw.isdigit():
                dnis.add(raw)
    return dnis


# ==============================================================================
# CORE: agregar tag a los DNIs que matcheen en personas
# ==============================================================================
def agregar_tag(supabase, dnis: set, tag: str):
    """
    Para cada DNI del set que exista en personas:
      - Si el tag ya está → lo ignora
      - Si no está → lo agrega sin tocar el resto de los tags
    """
    dnis_lista = list(dnis)
    total_dnis = len(dnis_lista)
    actualizados = 0
    ya_tenian    = 0
    no_en_bd     = 0
    errores      = 0

    print(f"\n🏷️  Tag '{tag}' — {total_dnis:,} DNIs a cruzar contra personas ...")

    for i in range(0, total_dnis, BATCH_SIZE):
        batch = dnis_lista[i : i + BATCH_SIZE]

        # ── Fetch del batch ────────────────────────────────────────────────
        try:
            res = supabase.table("personas") \
                          .select("id, dni, tags") \
                          .in_("dni", batch) \
                          .execute()
        except Exception as e:
            print(f"\n  ❌ Error al consultar lote {i}–{i+BATCH_SIZE}: {e}")
            errores += 1
            continue

        personas = res.data or []
        no_en_bd += len(batch) - len(personas)

        # ── Por cada persona encontrada ────────────────────────────────────
        for p in personas:
            tags_actuales = p.get("tags") or []
            if not isinstance(tags_actuales, list):
                tags_actuales = []

            if tag in tags_actuales:
                ya_tenian += 1
                continue

            nuevos_tags = tags_actuales + [tag]

            try:
                supabase.table("personas") \
                        .update({"tags": nuevos_tags}) \
                        .eq("id", p["id"]) \
                        .execute()
                actualizados += 1
            except Exception as e:
                print(f"\n  ❌ Error al actualizar persona id={p['id']}: {e}")
                errores += 1

        pct = min(i + BATCH_SIZE, total_dnis)
        print(f"    {pct:,}/{total_dnis:,}", end="\r")

    print(
        f"  ✅ Actualizados: {actualizados:,}  |  "
        f"Ya tenían el tag: {ya_tenian:,}  |  "
        f"DNI no encontrado en BD: {no_en_bd:,}  |  "
        f"Errores: {errores}"
    )
    return actualizados, ya_tenian, no_en_bd, errores


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 60)
    print("  TAG UPDATE DESDE CSVs")
    print("=" * 60)

    # ── Leer los 3 archivos ────────────────────────────────────────────────
    print("\n📂 Leyendo CSVs ...")
    try:
        dnis_afiliados       = leer_dnis(PATH_AFILIADOS,        "Matrícula")
        dnis_fiscales_mayo   = leer_dnis(PATH_FISCALES_MAYO,    "DNI")
        dnis_fiscales_octubre= leer_dnis(PATH_FISCALES_OCTUBRE, "DNI")
    except Exception as e:
        print(f"  ❌ Error al leer CSV: {e}")
        sys.exit(1)

    print(f"  AFILIADOS        → {len(dnis_afiliados):>8,} DNIs únicos")
    print(f"  FISCALES MAYO    → {len(dnis_fiscales_mayo):>8,} DNIs únicos")
    print(f"  FISCALES OCTUBRE → {len(dnis_fiscales_octubre):>8,} DNIs únicos")

    # ── Dry-run: overlap entre listas ─────────────────────────────────────
    overlap_mayo_oct = dnis_fiscales_mayo & dnis_fiscales_octubre
    if overlap_mayo_oct:
        print(f"\n  ℹ️  {len(overlap_mayo_oct):,} DNIs están en AMBAS listas de fiscales "
              f"(recibirán los 2 tags, es correcto).")

    print(f"\n{'─'*60}")
    print(f"  RESUMEN:")
    print(f"    tag AFILIADO        → hasta {len(dnis_afiliados):,} personas")
    print(f"    tag FISCAL MAYO     → hasta {len(dnis_fiscales_mayo):,} personas")
    print(f"    tag FISCAL OCTUBRE  → hasta {len(dnis_fiscales_octubre):,} personas")
    print(f"{'─'*60}")
    print(f"\n  Los tags se AGREGAN sin borrar los existentes.")
    print(f"  Solo se actualiza si el DNI existe en la tabla personas.\n")

    confirm = input("  ¿Ejecutar? (escribí SI para confirmar): ").strip().upper()
    if confirm != "SI":
        print("  Cancelado.")
        return

    supabase = get_supabase()

    # ── Ejecutar los 3 tags ────────────────────────────────────────────────
    resultados = {}
    for tag, dnis in [
        ("AFILIADO",        dnis_afiliados),
        ("FISCAL MAYO",     dnis_fiscales_mayo),
        ("FISCAL OCTUBRE",  dnis_fiscales_octubre),
    ]:
        resultados[tag] = agregar_tag(supabase, dnis, tag)

    # ── Resumen final ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ✅ PROCESO COMPLETADO — RESUMEN FINAL")
    print("=" * 60)
    print(f"  {'Tag':<20} {'Actualizados':>14} {'Ya tenían':>12} {'No en BD':>10}")
    print(f"  {'─'*20} {'─'*14} {'─'*12} {'─'*10}")
    for tag, (act, ya, no_bd, err) in resultados.items():
        print(f"  {tag:<20} {act:>14,} {ya:>12,} {no_bd:>10,}")

    print(f"\n  Verificá en Supabase SQL Editor:")
    print("""
  SELECT tag, COUNT(*) AS personas
  FROM (SELECT unnest(tags) AS tag FROM personas) t
  WHERE tag IN ('AFILIADO', 'FISCAL MAYO', 'FISCAL OCTUBRE')
  GROUP BY tag ORDER BY personas DESC;
    """)


if __name__ == "__main__":
    main()
