# Portal Territorial — Documentación del Sistema

## Descripción General

Portal web interno de gestión territorial para la organización **La Libertad Avanza CABA**.
Desarrollado en Python con Streamlit, conectado a Supabase (PostgreSQL) como base de datos.

URL de producción: `https://portal.alianzalalibertadavanzacaba.com/`

Stack tecnológico:
- **Frontend/Backend:** Python 3.11/3.12 + Streamlit 1.51
- **Base de datos:** Supabase (PostgreSQL 17 vía PostgREST), proyecto `dxoarslfifotigcgokmf`
- **Servidor:** Ubuntu VPS Hostinger (145.223.92.253)
- **Proxy:** nginx + Let's Encrypt SSL
- **Proceso:** systemd service (`portal-territorial.service`)
- **Repositorio:** https://github.com/Facunfer/portal-territorial
- **Librerías clave:** `streamlit-aggrid 1.2.1` (tablas), `plotly 5.24` (gráficos), `bcrypt` (passwords), `supabase-py` (cliente PostgREST)

---

## Estructura de Archivos

```
app.py                      # Punto de entrada: auth, sesiones, sidebar y routing de módulos
permisos.py                 # Lógica de ámbitos, roles, scopes y módulos permitidos
db.py                       # Cliente Supabase (singleton, anon key)
styles.py                   # CSS global (tema claro forzado, colores LLA)
constants.py                # Constantes compartidas (VERTICALES_SEGMENTOS, BARRIOS_POR_COMUNA)

router_personas.py          # Router del módulo Personas
router_asociaciones.py      # Router del módulo Asociaciones
personas_app.py             # Vista tabla + filtros + carga masiva de Personas
personas_edicion.py         # Ficha individual, interacciones, seguimientos, TAGS_SUGERIDOS
personas_scope_rules.py     # Filtro de visibilidad server-side de Personas (por tag/comuna)
asociaciones_app.py         # Vista tabla de Asociaciones
asociaciones_edicion.py     # Ficha individual de Asociaciones
usuarios_admin.py           # Administración de usuarios (crear, asignar, borrar, password)
dashboard_master_global.py  # Dashboard analítico del Global Master
kpis_app.py                 # Visualización de KPIs con scope del usuario
reuniones_app.py            # Módulo Reuniones/Actividades
agenda_reuniones_app.py     # Agenda de Reuniones (solo ámbito AGENDA)
agenda_kpis_app.py          # Visualización de Reuniones (solo ámbito AGENDA)
mapa_relacionamiento_app.py # Mapa de relacionamiento (verticales)
ia_app.py                   # Módulo Consultas con IA

sql/                        # Migraciones SQL sueltas (se corren a mano en Supabase)
deploy/migrations/          # Migraciones SQL versionadas
exportar_personas.py        # Script para exportar la tabla personas a CSV
.streamlit/config.toml      # Configuración de Streamlit (puerto, tema)
```

> **Nota:** las migraciones SQL **no** se ejecutan desde la app (usa la `anon` key). Se corren
> a mano en el **SQL Editor de Supabase** con rol `service_role`.

---

## Autenticación y Sesiones

### Login (`app.py`)
- El usuario ingresa `username` y `password`.
- La contraseña se verifica con **bcrypt** contra `usuarios.password_hash`.
- Contraseñas legacy en texto plano: se migran automáticamente a bcrypt en el primer login OK.
- **Rate limiting** server-side: 5 intentos fallidos → bloqueo de 5 minutos, compartido entre
  todas las sesiones vía `@st.cache_resource`.

### Sesiones persistentes (sobreviven al F5)
- Al loguear se genera un token UUID que se guarda en la tabla `sesiones` (con `user_data` jsonb
  y `expires_at`, TTL 12 horas) y se coloca en la URL como `?sid=<token>`.
- Al refrescar, `main()` restaura la sesión desde la URL si el token sigue vigente.
- Al cerrar sesión se borra el token de `sesiones`, se limpia la URL y el `session_state`.

> **Importante (tipos de id):** `usuarios.id` es **entero**. El `user["id"]` de la sesión es ese
> entero. En cambio `reuniones.id` es **UUID** — nunca castear a `int`.

---

## Sistema de Permisos (`permisos.py`)

El acceso se define por la combinación **ámbito + rol** del usuario, más su `comuna_id` o `vertical`.

### Ámbitos (`usuarios.ambito`)

| Ámbito | Descripción |
|--------|-------------|
| `GLOBAL` | Acceso total a todos los datos |
| `COMUNA` | Acceso limitado a su `comuna_id` |
| `VERTICAL_PERSONAS` | Acceso a personas de su vertical (por tag) |
| `VERTICAL_ASOCIACIONES` | Acceso a asociaciones de su vertical (por tipo) |
| `SEGMENTOS` | Reuniones, Mapa Relacionamiento y Visualización (sin reuniones de COMUNA) |
| `AGENDA` | Solo lectura de reuniones (sidebar aislado) |

### Roles (`usuarios.rol`)

| Rol | Descripción |
|-----|-------------|
| `CABEZA` | Rol más alto dentro de su ámbito |
| `MASTER` | Administrador del ámbito |
| `EXTRACTO` | Solo ve lo asignado explícitamente en `usuarios_asignaciones` |

### Scopes de datos (server-side)

`personas_scope(user)` / `asociaciones_scope(user)` / `users_scope(user)` devuelven un `Scope`:

- `ALL` — sin filtro (Global Master)
- `COMUNA` — filtra por `comuna_id` del usuario
- `TAG` — filtra personas por tag (verticales de personas)
- `ASOC_TIPO` — filtra asociaciones por tipo (verticales de asociaciones)
- `ASSIGNED` — solo lo asignado (rol EXTRACTO)
- `USERS_VERTICAL` — para admin de usuarios: filtra por `ambito` + `vertical`
- `NONE` — sin acceso

### Módulos permitidos por ámbito (`allowed_modules`)

| Ámbito | Módulos |
|--------|---------|
| GLOBAL (MASTER) | Personas, Asociaciones, **Master Global** |
| COMUNA (CABEZA/MASTER) | Personas, Asociaciones, Reuniones/Actividades, Visualización, Consultas, Usuarios* |
| VERTICAL_PERSONAS (MASTER) | Personas, Reuniones, Mapa Relacionamiento, Visualización, Consultas, Usuarios* |
| VERTICAL_ASOCIACIONES (MASTER) | Asociaciones, Reuniones, Mapa Relacionamiento, Visualización, Consultas, Usuarios* |
| SEGMENTOS | Reuniones/Actividades, Mapa Relacionamiento, Visualización |
| AGENDA | Agenda de Reuniones, Visualización de Reuniones |

\* "Usuarios" solo aparece si `can_manage_users(user)` es verdadero.

### Verticales

- **Personas** (código interno en `usuarios.vertical`): `JUVENTUD`, `GENERACION_PLATEADA`,
  `MIGRANTES`, `PROFESIONALES`, `CCAA`, `PYMES`, `JOVENES_EMPRESARIOS`, `INNOVACION_TECNOLOGIA`,
  `EDUCACION`, `SALUD`, `CULTURA`, `CULTO`.
- **Asociaciones:** `CULTO`, `CCAA`, `CULTURA`, `CLUBES`.

> El código interno `GENERACION_PLATEADA` **no cambia** (es identificador). Lo que se renombró fue
> el **tag** en `personas.tags`: `GENERACIÓN PLATEADA` → **`LIBERTAD PLATEADA`**, y su etiqueta
> visible "Libertad Plateada". El mapeo vertical→tag (`permisos.py`, `personas_scope_rules.py`,
> `dashboard_master_global.py`) apunta a `LIBERTAD PLATEADA`.

### Doble guard de permisos
Aunque el sidebar solo ofrece los módulos permitidos, `main()` revalida server-side el módulo
solicitado contra `allowed_modules()` (y `can_manage_users` / `is_global_master` donde aplica)
antes de renderizar, para que manipular el `session_state` no abra módulos fuera de scope.

---

## Módulos del Sistema

### 1. Personas
Gestión del padrón (~31.000 registros).

- Tabla AgGrid con filtros: sexo, fiscalizó, **Semáforo de Tiempo**, **Termómetro** (semáforo de
  respuesta), tags, barrio, estado de asignación, origen y rango de último contacto.
- Búsqueda por nombre, DNI o teléfono.
- Ficha individual (`personas_edicion.py`): datos, historial de interacciones, seguimientos, asignaciones.
- Carga individual y **carga masiva por CSV** (CABEZA/MASTER) vía la función Postgres `fn_importar_personas`.
- **Carga de interacción masiva:** seleccionás varias personas con checkbox y cargás una interacción
  para todas. La selección se **acumula en `session_state["mass_selected_ids"]`** y se restaura tras
  cada rerun (no se pierde al tildar rápido); botón "🧹 Limpiar selección".

**Interacciones** (`interacciones_personas`): resultado POSITIVO / NEUTRO / NEGATIVO / NO RESPONDIÓ /
NÚMERO INEXISTENTE-EQUIVOCADO / NO CONTACTADO, con fecha, medio, observaciones y usuario que cargó.

**Semáforos:**
- **Tiempo:** 🟢 <30 días / 🟡 30–60 días / 🔴 >60 días / ⚫ SIN CONTACTO
- **Termómetro** (respuesta): 🟢 POSITIVO / 🟡 NEUTRO / 🔴 NEGATIVO / 🟠 NÚM. INEXISTENTE / ⚫ NO RESPONDIÓ / ⚫ NO CONTACTADO

> El cálculo y los emojis no cambiaron; "Termómetro" es solo el **rótulo visible** del antes llamado
> "Semáforo Respuesta". "Semáforo de Tiempo" mantiene su nombre.

**Caché:** TTL 30 s; se invalida al guardar una interacción (`personas_edicion._clear_interacciones_cache()`).

### 2. Asociaciones
Clubes, locales comerciales, espacios culturales y de culto.

- Tabla con filtros por tipo, **Termómetro** (antes "Feedback"), estado de asignación.
- Ficha individual: datos, referente, historial de visitas.
- Interacciones (`interacciones_asociaciones`): POSITIVO / NEUTRO / NEGATIVO / NO VISITADO.

> La **columna de DB sigue siendo `asociaciones.feedback`** (con su CHECK
> `positivo/negativo/neutro`); solo cambió el rótulo visible a "Termómetro".

### 3. Reuniones / Actividades (`reuniones_app.py`)
Registro y gestión de actividades. El scope de cada reunión se calcula del usuario
(`scope_tipo` = COMUNA / VERTICAL / GLOBAL, `scope_valor`).

**Alta de actividad:**
- **Tipo de actividad:** Reunión, Caminata, Charla, **Capacitación**, Otro.
- Campo condicional (mismo lugar, junto al tipo):
  - si **Reunión** → selector **Tipo de Reunión** (`subtipo_reunion`) + campo "Descripción / Notas".
  - si **otro tipo** → campo **"Detalle de la actividad"**, que se guarda en `reuniones.descripcion`
    (para esos tipos se oculta "Descripción / Notas" para no tener dos inputs hacia `descripcion`).
- Selector de asistentes con búsqueda (mín. 3 caracteres, máx. 200 resultados); la selección se
  acumula en `session_state`. Al guardar, cada asistente genera una fila en `reuniones_asistentes`
  y una interacción "Participó de reunión" en `interacciones_personas`.

**Estado de una actividad** (`reuniones.realizada`):
- `NULL` = programada / pendiente
- `True` = realizada (se marca con "✅ Se realizó")
- `False` = no se hizo ("❌ No se hizo")

**Pestañas:**
- **📅 Programadas:** todas las `realizada IS NULL`, **sin filtro de fecha**. Las **vencidas**
  (fecha pasada y sin confirmar) **permanecen acá** con badge "⚠️ Vencida — pendiente de confirmar"
  hasta que se resuelvan. Salen solo al marcarlas Se realizó / No se hizo.
- **📋 Historial:** **solo** las `realizada = True`. (Las "No se hizo" no figuran en ninguna pestaña.)

**Eliminar reuniones propias:** botón con confirmación en dos pasos, en Programadas (por tarjeta) y
en Historial (selector). `delete_reunion()` verifica autoría (Global Master borra cualquiera) y borra,
en orden: interacciones autogeneradas (`reunion_id`), `reuniones_asistentes`, y la reunión con guard
`.eq("created_by_user_id", user.id)`.

### 4. Master Global — Dashboard (`dashboard_master_global.py`)
Solo Global Master. Datos cacheados 300 s (`@st.cache_data`); botón "🔄 Refrescar datos".

**Filtros globales:** Comunas, Barrios, Verticales de Segmento, Tags de Personas, Tipo de Asociación,
Rango de Interacciones. Todo reacciona a estos filtros.

**KPIs:** Total Personas, Total Asociaciones, % Personas Contactadas, % Asociaciones Visitadas.

**Tabs:**
- **📍 Territorial:** semáforos de gestión (resultado y última fecha) de personas y asociaciones.
- **🏷️ Temático:** top tags de personas, asociaciones por tipo.
- **📈 Tendencias:** líneas de interacciones por día/comuna y, **debajo de cada línea**, barras de
  totales **por comuna** (Personas y Asociaciones).
- **🤝 Reuniones:** línea de reuniones por ámbito y, debajo, barras de **Reuniones por Comuna**
  (solo scope COMUNA).
- **🔍 Auditoría y Calidad:** datos faltantes y ritmo de carga.

**Barras por comuna:** incluyen **todas las comunas** en el eje X (las del filtro activo, o las 15 del
sistema si no hay filtro; las sin datos quedan en 0) y se ordenan **de mayor a menor**. Técnicamente,
el eje se fuerza a `type="category"` (si no, plotly trata los números de comuna como eje lineal e
ignora el orden) y se usa `categoryorder="total descending"`.

### 5. Visualización (KPIs) — `kpis_app.py`
Como el dashboard pero con el scope del usuario. Para MASTER/CABEZA de cualquier ámbito (no Global Master).

### 6–7. Agenda / Visualización de Reuniones
Solo ámbito `AGENDA`: vista read-only de la agenda y sus estadísticas.

### 8. Mapa Relacionamiento
Mapa visual de relaciones, para verticales con rol MASTER/CABEZA.

### 9. Consultas (IA)
Consultas asistidas por IA, para MASTER/CABEZA (excepto Global Master, que tiene su dashboard).

### 10. Usuarios (`usuarios_admin.py`)
Administración de usuarios dentro del scope (`can_manage_users`: Global Master siempre; CABEZA/MASTER
de comuna/vertical solo si `es_original = true`).

- **Ver usuarios** de su ámbito (grilla filtrada por scope).
- **Crear usuarios** con los roles permitidos; se registra `creado_por` (auditoría) y, para EXTRACTO,
  sus asignaciones en `usuarios_asignaciones`.
- **Eliminar usuario:** botón con confirmación en dos pasos. Un referente puede borrar **cualquier
  usuario de su ámbito** (comuna o vertical), **nunca a sí mismo**; el Global Master, a cualquiera.
  El guard server-side (`_apply_users_scope_guard`) re-aplica el filtro de comuna/vertical al `DELETE`.
  Si el usuario tiene **datos históricos** que lo referencian (FK `NO ACTION`/`RESTRICT`), el borrado
  en duro falla → **se degrada a desactivación** (`activo=false`) sin destruir datos.
- **Cambiar contraseña de un usuario:** bloque **exclusivo del Global Master**.

---

## Base de Datos (Supabase)

### Tablas principales

| Tabla | Descripción |
|-------|-------------|
| `personas` | Padrón principal (~31.000). `tags` es `text[]` |
| `asociaciones` | Asociaciones (~2.000). Columna `feedback` con CHECK `positivo/negativo/neutro` |
| `interacciones_personas` | Contactos a personas (incluye `reunion_id`, `created_by`) |
| `interacciones_asociaciones` | Visitas a asociaciones |
| `usuarios` | Usuarios. `id` entero. Incluye `creado_por` (FK a usuarios), `es_original`, `activo` |
| `sesiones` | Sesiones persistentes (`id` text/uuid, `user_data` jsonb, `expires_at`) |
| `reuniones` | Reuniones. **`id` es UUID.** `created_by_user_id` bigint, `realizada` bool/null, scope |
| `reuniones_asistentes` | Asistentes de cada reunión (`reunion_id`, `persona_id`) |
| `usuarios_asignaciones` | Asignaciones persona/asoc → usuario (rol EXTRACTO) |
| `seguimientos_personas` / `seguimientos_asociaciones` | Seguimientos pendientes |
| `mapa_relacionamiento` | Datos del módulo Mapa |

### Claves foráneas relevantes (delete rules)
- Hijos de `reuniones`: `reuniones_asistentes.reunion_id` = **CASCADE**;
  `interacciones_personas.reunion_id` = **SET NULL** (por eso `delete_reunion` borra primero esas
  interacciones, para no dejarlas colgadas y falsear el semáforo).
- Hacia `usuarios(id)`: `usuarios_asignaciones.usuario_id` = **CASCADE**;
  `interacciones_personas.created_by/usuario_id` = **SET NULL**; pero `asociaciones.creado_por`/
  `asignado_a`, `interacciones_asociaciones.created_by`, `mapa_relacionamiento.created_by`,
  `seguimientos_*.*` y `usuarios.creado_por` son **NO ACTION/RESTRICT** → bloquean el hard delete
  (de ahí la degradación a desactivación).

### RLS
RLS está **deshabilitado** en `usuarios`, `usuarios_asignaciones`, `reuniones`,
`reuniones_asistentes`, `interacciones_personas`. Los `DELETE`/`UPDATE` con la `anon` key funcionan;
la protección de "solo lo propio/de mi ámbito" la dan los filtros `.eq(...)` server-side del código.

### Paginación
PostgREST limita a 1.000 filas por consulta. Las queries grandes usan paginación con `.range()` en
un loop (patrón `fetch_reuniones`, `fetch_global_data`, etc.).

### Función de importación
`fn_importar_personas` (dos overloads) inserta personas desde JSON, asigna tags automáticos por DNI
(`< 10M` → **LIBERTAD PLATEADA**; `> 90M` → MIGRANTE; `42M–90M` → JUVENTUD) y deduplica por `dni`.

---

## Deployment

### Infraestructura
- VPS Hostinger, dominio `portal.alianzalalibertadavanzacaba.com`, SSL Let's Encrypt, nginx → `:8501`.
- systemd `portal-territorial.service`, `WorkingDirectory=/opt/portal-territorial`,
  venv en `/opt/portal-territorial/venv`. `ExecStart`: `streamlit run app.py --server.port=8501`.

### Flujo de actualización
1. Editar y commitear en local; `git push origin <branch>`.
2. En el VPS:
   ```bash
   cd /opt/portal-territorial && git pull && sudo systemctl restart portal-territorial.service
   ```
3. Si hay migración SQL pendiente, correrla **antes** en el SQL Editor de Supabase.
4. En el navegador, **Ctrl+Shift+R** (recarga dura) para evitar caché vieja.

> El service file incluye `ExecStartPre=... fuser -k 8501/tcp ...` para liberar el puerto 8501
> automáticamente si quedó ocupado.

### Diagnóstico
```bash
systemctl status portal-territorial.service --no-pager -l   # ver Active: running + hora de arranque
journalctl -u portal-territorial -n 100 --no-pager          # logs
```

---

## Estilos y Navegación

- Tema forzado a `light` (`.streamlit/config.toml`) + `color-scheme: light only` para evitar el dark
  mode del navegador. Colores de marca en `styles.py` (#371959 violeta). AgGrid usa tema `"alpine"`.
- Sidebar: username, selector de módulos (solo los permitidos), botón **RECLAMOS/SUGERENCIAS**
  (solo ámbito COMUNA) y **CERRAR SESIÓN**.

---

## Seguridad (resumen)

- Passwords con bcrypt (auto-migración desde texto plano).
- Rate limiting server-side (5 intentos → 5 min) compartido vía `@st.cache_resource`.
- Doble guard de permisos: UI + revalidación server-side en `main()`.
- Borrados con guard `.eq(...)` por autoría/scope; no se destruye historial (degradación a
  desactivación cuando una FK lo impide).
- Sesiones con TTL 12 h, invalidadas en logout. La app usa la `anon` key de Supabase.

---

## Operaciones SQL frecuentes

Cambiar la comuna de una persona:
```sql
UPDATE personas SET comuna_id = 15 WHERE id = 33482;
```

Resetear contraseña (hash bcrypt generado aparte):
```sql
UPDATE usuarios SET password_hash = '$2b$12$...' WHERE id = <uid>;
```

Generar un hash bcrypt desde Python:
```python
import bcrypt
print(bcrypt.hashpw('contraseña'.encode(), bcrypt.gensalt()).decode())
```

---

## Historial de cambios recientes (branch `feature/referentes-master-ajustes`)

- **Personas:** selección persistente en carga de interacción masiva.
- **Usuarios:** un referente puede borrar usuarios de su ámbito (guard por scope; degradación a
  desactivación si hay historial); "Cambiar contraseña" solo Global Master; columna `creado_por`.
- **Reuniones:** eliminar reuniones propias; las pendientes vencidas ya **no** pasan solas al
  Historial (Historial = solo `realizada=True`); badge de vencidas; tipo **"Capacitación"**; campo
  "Detalle de la actividad" para tipos ≠ Reunión.
- **Dashboard:** barras por comuna en Tendencias y Reuniones, con todas las comunas en el eje y
  ordenadas de mayor a menor.
- **Etiquetas (solo UI):** "Semáforo Respuesta" → **"Termómetro"**; "Feedback" (asociaciones) →
  **"Termómetro"**.
- **Datos/funciones:** tag `GENERACIÓN PLATEADA` → **`LIBERTAD PLATEADA`** (migración en
  `deploy/migrations/202606_rename_generacion_a_libertad_plateada.sql`).
