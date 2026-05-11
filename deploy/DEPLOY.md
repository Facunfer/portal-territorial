# Guía de deploy — Portal Territorial

## Requisitos previos

- VPS Hostinger Ubuntu 22.04 o 24.04
- Acceso SSH como root
- Dominio apuntando a la IP del VPS (registro A en DNS de Hostinger)
- Puerto 80 y 443 abiertos en el firewall del VPS

---

## 🚀 Setup inicial (una sola vez)

### 1. Conectarse al VPS

```bash
ssh root@IP_DE_TU_VPS
```

### 2. Ejecutar el script de setup

```bash
# Descargar el script directamente desde GitHub
curl -fsSL https://raw.githubusercontent.com/Facunfer/portal-territorial/main/deploy/setup_server.sh -o setup_server.sh

# Ejecutar (reemplazá TU_DOMINIO.com con tu dominio real)
bash setup_server.sh TU_DOMINIO.com
```

### 3. Cargar la clave de Supabase

```bash
nano /opt/portal-territorial/.streamlit/secrets.toml
```

El archivo debe quedar así (reemplazá con tu anon key real):

```toml
[supabase]
url = "https://dxoarslfifotigcgokmf.supabase.co"
anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Guardar con `Ctrl+O`, `Enter`, `Ctrl+X`.

### 4. Iniciar la aplicación

```bash
sudo systemctl start portal-territorial
sudo systemctl status portal-territorial
```

Si el status dice `Active: active (running)` ✅, la app está corriendo.

### 5. Activar HTTPS con Let's Encrypt

```bash
sudo certbot --nginx -d TU_DOMINIO.com
```

Certbot modifica automáticamente el nginx.conf para redirigir HTTP → HTTPS y renovar el certificado automáticamente.

---

## 🔄 Actualizaciones (cada vez que haya cambios)

```bash
ssh root@IP_DE_TU_VPS
sudo bash /opt/portal-territorial/deploy/update.sh
```

El script hace:
1. `git pull` desde GitHub
2. Actualiza dependencias de Python
3. Reinicia el servicio systemd

---

## 🔍 Comandos de monitoreo

```bash
# Ver estado de la app
sudo systemctl status portal-territorial

# Ver logs en tiempo real
sudo journalctl -u portal-territorial -f

# Ver últimas 50 líneas de log
sudo journalctl -u portal-territorial -n 50 --no-pager

# Ver logs de nginx
sudo tail -f /var/log/nginx/portal-territorial.access.log
sudo tail -f /var/log/nginx/portal-territorial.error.log

# Reiniciar manualmente
sudo systemctl restart portal-territorial
```

---

## 🛠️ Troubleshooting

### La app no inicia

```bash
journalctl -u portal-territorial -n 100 --no-pager
```

Causa más común: `secrets.toml` no configurado o mal formateado.

### Error de conexión a Supabase

Verificar que la `anon_key` en `/opt/portal-territorial/.streamlit/secrets.toml` sea correcta.

### Nginx devuelve 502 Bad Gateway

La app de Streamlit no está corriendo. Ver logs con `journalctl`.

### El certificado SSL no renueva

```bash
sudo certbot renew --dry-run
```

La renovación automática está configurada como cron job por certbot.

---

## 📁 Estructura en el servidor

```
/opt/portal-territorial/       ← código de la app (git clone)
├── app.py
├── requirements.txt
├── .streamlit/
│   ├── config.toml            ← commiteado en git
│   └── secrets.toml           ← ⚠️ NO en git, crear manualmente
└── venv/                      ← virtualenv Python

/etc/systemd/system/
└── portal-territorial.service ← creado por setup_server.sh

/etc/nginx/sites-available/
└── portal-territorial         ← creado por setup_server.sh
```

---

## 🔐 Seguridad aplicada

| Medida | Estado |
|--------|--------|
| Corre como usuario sin privilegios (`appuser`) | ✅ |
| `secrets.toml` con permisos 600 | ✅ |
| Nginx como proxy reverso (no expone port 8501) | ✅ |
| HTTPS con Let's Encrypt + renovación automática | ✅ post-certbot |
| Headers de seguridad (X-Frame-Options, etc.) | ✅ |
| Supabase con anon key (no service_role) | ✅ |
| Bcrypt para contraseñas de usuarios | ✅ |
| Rate limiting en login (5 intentos / 15 min) | ✅ |
| CSRF protection activa (Streamlit) | ✅ |
