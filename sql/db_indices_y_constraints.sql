-- ============================================================
-- ÍNDICES DE PERFORMANCE
-- Ejecutar en Supabase SQL Editor (Settings → SQL Editor)
-- ============================================================

-- Interacciones personas: lookup por persona + orden cronológico
CREATE INDEX IF NOT EXISTS idx_ip_persona_fecha
    ON interacciones_personas (persona_id, fecha DESC);

-- Interacciones personas: filtro por fecha (semáforo temporal)
CREATE INDEX IF NOT EXISTS idx_ip_fecha
    ON interacciones_personas (fecha);

-- Interacciones personas: filtro por usuario que cargó
CREATE INDEX IF NOT EXISTS idx_ip_created_by
    ON interacciones_personas (created_by);

-- Interacciones asociaciones
CREATE INDEX IF NOT EXISTS idx_ia_asoc_fecha
    ON interacciones_asociaciones (asociacion_id, fecha DESC);

-- Personas: lookup por DNI (import, deduplicación)
CREATE INDEX IF NOT EXISTS idx_personas_dni
    ON personas (dni);

-- Personas: filtro por comuna
CREATE INDEX IF NOT EXISTS idx_personas_comuna
    ON personas (comuna_id);

-- Personas: búsqueda por tags (array GIN)
CREATE INDEX IF NOT EXISTS idx_personas_tags
    ON personas USING GIN (tags);


-- ============================================================
-- CONSTRAINT DE INTEGRIDAD: DNI único
-- ⚠️  ANTES de ejecutar esto, verificar que no haya DNIs
--     duplicados en la tabla. Correr primero:
--
--   SELECT dni, COUNT(*) FROM personas
--   GROUP BY dni HAVING COUNT(*) > 1;
--
-- Si hay duplicados, resolverlos antes de agregar el constraint.
-- ============================================================

-- Eliminar constraint anterior si existe (idempotente)
ALTER TABLE personas
    DROP CONSTRAINT IF EXISTS personas_dni_unique;

-- Agregar constraint UNIQUE
ALTER TABLE personas
    ADD CONSTRAINT personas_dni_unique UNIQUE (dni);


-- ============================================================
-- FUNCIÓN RPC: última interacción por persona (chunked)
-- Necesaria para el módulo de personas (personas_app.py)
-- ============================================================

CREATE OR REPLACE FUNCTION get_ultima_interaccion_personas(ids BIGINT[])
RETURNS TABLE (persona_id BIGINT, fecha TEXT, respuesta TEXT, created_by BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (persona_id)
           persona_id,
           fecha::TEXT,
           respuesta,
           created_by
    FROM interacciones_personas
    WHERE persona_id = ANY(ids)
    ORDER BY persona_id, fecha DESC, id DESC;
$$;
