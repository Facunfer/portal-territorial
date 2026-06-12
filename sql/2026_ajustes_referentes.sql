-- =============================================================================
-- 2026_ajustes_referentes.sql
-- Migración de apoyo para los ajustes de Referentes / Master Global.
--
-- Cómo correr: ejecutar este archivo en el SQL Editor de Supabase ANTES de
-- reiniciar el servicio (systemctl restart portal-territorial). Es idempotente.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- M1. Columna de autoría en `usuarios`
-- -----------------------------------------------------------------------------
-- Permite que un referente administre/borre SOLO los usuarios que él creó.
-- NOTA: en la base actual esta columna YA EXISTE (verificado vía MCP), por lo
-- que este ALTER es un no-op seguro. Se deja por completitud / otros entornos.
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS creado_por integer REFERENCES usuarios(id);

-- creado_por se completa al crear usuarios desde la UI (auditoría: quién lo creó).
-- El código (usuarios_admin._insert_usuario) tolera que esta columna no exista:
-- si PostgREST responde que falta, reintenta el insert sin ella.
--
-- NOTA sobre el BORRADO de usuarios: el guard NO usa creado_por, usa el SCOPE del
-- que administra (permisos.users_scope): un referente de COMUNA puede borrar
-- cualquier usuario de su comuna (filtro comuna_id), un referente VERTICAL los de
-- su ambito+vertical, y el Global Master cualquiera. Nunca a sí mismo. Por eso
-- los usuarios históricos (creado_por = NULL) TAMBIÉN son borrables por el
-- referente del ámbito correspondiente.


-- =============================================================================
-- DOCUMENTACIÓN: FKs y RLS verificadas en Supabase (proyecto dxoarslfifotigcgokmf)
-- NO se ejecuta nada acá abajo; es referencia para entender el comportamiento
-- de los borrados implementados en el código.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- A) BORRADO DE REUNIONES (reuniones_app.delete_reunion)  → OK sin cambios DDL
-- -----------------------------------------------------------------------------
-- FKs hacia reuniones(id):
--   * reuniones_asistentes.reunion_id      -> ON DELETE CASCADE
--   * interacciones_personas.reunion_id    -> ON DELETE SET NULL
--
-- El código borra explícitamente, EN ESTE ORDEN, los hijos antes que el padre:
--   1) interacciones_personas WHERE reunion_id = X  (las "Participó de reunión";
--      si no se borraran, el SET NULL las dejaría colgadas y falsearían el
--      semáforo de contacto de cada persona).
--   2) reuniones_asistentes WHERE reunion_id = X.
--   3) reuniones WHERE id = X [+ created_by_user_id = user.id salvo Global Master].
-- No hace falta tocar el esquema: ninguna FK bloquea el borrado.

-- -----------------------------------------------------------------------------
-- B) BORRADO DE USUARIOS (usuarios_admin.delete_usuario)  → degradación a soft
-- -----------------------------------------------------------------------------
-- FKs hacia usuarios(id) y su delete_rule:
--   usuarios_asignaciones.usuario_id            -> CASCADE     (se borran solas)
--   interacciones_personas.created_by           -> SET NULL    (no bloquea)
--   interacciones_personas.usuario_id           -> SET NULL    (no bloquea)
--   asociaciones.creado_por                     -> NO ACTION   (BLOQUEA)
--   asociaciones.asignado_a                     -> NO ACTION   (BLOQUEA)
--   interacciones_asociaciones.created_by       -> NO ACTION   (BLOQUEA)
--   mapa_relacionamiento.created_by             -> NO ACTION   (BLOQUEA)
--   seguimientos_asociaciones.created_by        -> NO ACTION   (BLOQUEA)
--   seguimientos_asociaciones.assigned_to       -> NO ACTION   (BLOQUEA)
--   seguimientos_personas.created_by            -> RESTRICT    (BLOQUEA)
--   seguimientos_personas.assigned_to           -> RESTRICT    (BLOQUEA)
--   usuarios.creado_por                         -> NO ACTION   (BLOQUEA si creó otros)
--   (No existe FK reuniones.created_by_user_id -> usuarios)
--
-- DECISIÓN (acordada): NO destruir datos históricos para forzar el borrado. Por
-- eso el código intenta el HARD DELETE y, si falla por constraint FK, DEGRADA a
-- desactivación (activo = false) con el mismo guard de scope.
-- El caso típico (un EXTRACTO recién creado sin historial) sí se borra de verdad.
--
-- Si en el futuro querés que ciertos usuarios SÍ se puedan borrar en duro sin
-- perder historial, la opción no destructiva sería pasar las FKs de auditoría a
-- ON DELETE SET NULL (NUNCA CASCADE sobre tablas de datos). NO se aplica acá;
-- queda como propuesta a evaluar:
--
--   -- ALTER TABLE asociaciones DROP CONSTRAINT asociaciones_creado_por_fkey,
--   --   ADD CONSTRAINT asociaciones_creado_por_fkey FOREIGN KEY (creado_por)
--   --   REFERENCES usuarios(id) ON DELETE SET NULL;
--   -- ... (ídem asignado_a, interacciones_asociaciones.created_by,
--   --       mapa_relacionamiento.created_by, seguimientos_*.*)

-- -----------------------------------------------------------------------------
-- C) RLS
-- -----------------------------------------------------------------------------
-- RLS está DESHABILITADO en: usuarios, usuarios_asignaciones, reuniones,
-- reuniones_asistentes, interacciones_personas. Por lo tanto el DELETE/UPDATE
-- con la anon key funciona sin políticas. La protección real de "solo lo propio"
-- es el filtro server-side .eq(creado_por / created_by_user_id, user.id) que
-- aplica el código en cada borrado.
