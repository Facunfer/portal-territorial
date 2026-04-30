-- ============================================================
-- ÍNDICES DE PERFORMANCE - Portal Territorial
-- Ejecutar en Supabase > SQL Editor
-- Todos usan IF NOT EXISTS para ser seguros de re-ejecutar
-- ============================================================

-- ---- PERSONAS ----

-- Filtros por comuna (scope COMUNA y filtros de UI)
CREATE INDEX IF NOT EXISTS idx_personas_comuna_id
    ON personas (comuna_id);

-- Filtros por tags (necesita GIN porque es array)
CREATE INDEX IF NOT EXISTS idx_personas_tags
    ON personas USING gin (tags);

-- Búsquedas por DNI (unicidad y lookup al insertar)
CREATE INDEX IF NOT EXISTS idx_personas_dni
    ON personas (dni);

-- ---- INTERACCIONES_PERSONAS ----

-- Join principal: traer interacciones de una persona
CREATE INDEX IF NOT EXISTS idx_interacciones_personas_persona_id
    ON interacciones_personas (persona_id);

-- Orden por fecha (semáforos y resumen de última interacción)
CREATE INDEX IF NOT EXISTS idx_interacciones_personas_fecha
    ON interacciones_personas (fecha DESC);

-- Filtro por usuario creador (KPIs por ámbito)
CREATE INDEX IF NOT EXISTS idx_interacciones_personas_created_by
    ON interacciones_personas (created_by);

-- Índice compuesto: el más usado en get_interacciones_resumen
CREATE INDEX IF NOT EXISTS idx_interacciones_personas_pid_fecha
    ON interacciones_personas (persona_id, fecha DESC);

-- ---- ASOCIACIONES ----

-- Filtros por comuna
CREATE INDEX IF NOT EXISTS idx_asociaciones_comuna_id
    ON asociaciones (comuna_id);

-- Filtros por tipo (verticales)
CREATE INDEX IF NOT EXISTS idx_asociaciones_tipo
    ON asociaciones (tipo);

-- ---- INTERACCIONES_ASOCIACIONES ----

-- Join principal
CREATE INDEX IF NOT EXISTS idx_interacciones_asoc_asociacion_id
    ON interacciones_asociaciones (asociacion_id);

-- Orden por fecha
CREATE INDEX IF NOT EXISTS idx_interacciones_asoc_fecha
    ON interacciones_asociaciones (fecha DESC);

-- Filtro por usuario creador (KPIs)
CREATE INDEX IF NOT EXISTS idx_interacciones_asoc_created_by
    ON interacciones_asociaciones (created_by);

-- Índice compuesto: el más usado en resumen de asociaciones
CREATE INDEX IF NOT EXISTS idx_interacciones_asoc_aid_fecha
    ON interacciones_asociaciones (asociacion_id, fecha DESC);

-- ---- USUARIOS_ASIGNACIONES ----

-- Lookup de asignaciones por usuario (rol EXTRACTO)
CREATE INDEX IF NOT EXISTS idx_asignaciones_usuario_tipo
    ON usuarios_asignaciones (usuario_id, objeto_tipo);

-- Lookup inverso: qué usuarios tiene asignado un objeto
CREATE INDEX IF NOT EXISTS idx_asignaciones_objeto
    ON usuarios_asignaciones (objeto_id, objeto_tipo);

-- ---- REUNIONES ----

-- Filtros por fecha (agenda y KPIs)
CREATE INDEX IF NOT EXISTS idx_reuniones_fecha
    ON reuniones (fecha);

-- Filtro por scope (vertical / comuna)
CREATE INDEX IF NOT EXISTS idx_reuniones_scope
    ON reuniones (scope_tipo, scope_valor);

-- ---- MAPA_RELACIONAMIENTO ----

-- Filtro por creador (KPIs de segmentos)
CREATE INDEX IF NOT EXISTS idx_mapa_relacionamiento_created_by
    ON mapa_relacionamiento (created_by);
