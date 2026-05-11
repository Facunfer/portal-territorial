#!/usr/bin/env bash
# =============================================================
# SETUP INICIAL DEL SERVIDOR — Ejecutar UNA SOLA VEZ como root
# VPS Ubuntu 22.04 / 24.04 — Hostinger
#
# Uso:
#   chmod +x setup_server.sh
#   sudo bash setup_server.sh TU_DOMINIO.com
#
# Al finalizar:
#   1. Editar /opt/portal-territorial/.streamlit/secrets.toml
#      con la anon_key de Supabase
#   2. sudo systemctl start portal-territorial
#   3. sudo certbot --nginx -d TU_DOMINIO.com
# =============================================================
set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "❌  Uso: sudo bash setup_server.sh TU_DOMINIO.com"
  exit 1
fi

APP_USER="appuser"
APP_DIR="/opt/portal-territorial"
REPO_URL="https://github.com/Facunfer/portal-territorial.git"
PYTHON_BIN="python3.11"
SERVICE_NAME="portal-territorial"

echo "======================================================"
echo " Portal Territorial — Setup de servidor"
echo " Dominio : $DOMAIN"
echo " Directorio : $APP_DIR"
echo "======================================================"

# ── 1. Paquetes del sistema ────────────────────────────────
echo "[1/8] Actualizando paquetes del sistema..."
apt-get update -q
apt-get install -y -q \
  python3.11 python3.11-venv python3.11-dev \
  git nginx certbot python3-certbot-nginx \
  build-essential libpq-dev \
  curl wget unzip

# ── 2. Usuario de aplicación ───────────────────────────────
echo "[2/8] Creando usuario $APP_USER..."
if ! id "$APP_USER" &>/dev/null; then
  useradd --system --shell /bin/bash --home-dir "$APP_DIR" --create-home "$APP_USER"
else
  echo "  → Usuario ya existe, continuando."
fi

# ── 3. Clonar repositorio ──────────────────────────────────
echo "[3/8] Clonando repositorio..."
if [[ -d "$APP_DIR/.git" ]]; then
  echo "  → Repositorio ya existe. Haciendo git pull."
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  # Clonar en directorio temporal y mover (el home ya fue creado por useradd)
  rm -rf "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
fi

# ── 4. Entorno virtual Python ──────────────────────────────
echo "[4/8] Creando virtualenv..."
sudo -u "$APP_USER" $PYTHON_BIN -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip wheel
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# ── 5. Secrets (placeholder — editar manualmente) ──────────
echo "[5/8] Creando .streamlit/secrets.toml (placeholder)..."
mkdir -p "$APP_DIR/.streamlit"
SECRETS_FILE="$APP_DIR/.streamlit/secrets.toml"
if [[ ! -f "$SECRETS_FILE" ]]; then
  cat > "$SECRETS_FILE" <<SECRETS
[supabase]
url = "https://dxoarslfifotigcgokmf.supabase.co"
anon_key = "PEGAR_AQUI_LA_ANON_KEY"
SECRETS
  chown "$APP_USER":"$APP_USER" "$SECRETS_FILE"
  chmod 600 "$SECRETS_FILE"
  echo "  ⚠️  IMPORTANTE: editar $SECRETS_FILE con la anon_key real antes de iniciar."
else
  echo "  → secrets.toml ya existe, no se sobreescribe."
fi

# ── 6. Servicio systemd ────────────────────────────────────
echo "[6/8] Instalando servicio systemd..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<SERVICE
[Unit]
Description=Portal Territorial Streamlit
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.headless=true --server.port=8501
Restart=on-failure
RestartSec=5
# Variables de entorno de seguridad
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo "  → Servicio instalado y habilitado (no iniciado aún)."

# ── 7. Nginx ───────────────────────────────────────────────
echo "[7/8] Configurando Nginx..."
NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"
cat > "$NGINX_CONF" <<NGINX
upstream streamlit {
    server 127.0.0.1:8501;
}

server {
    listen 80;
    server_name $DOMAIN;

    # Seguridad básica
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logs
    access_log /var/log/nginx/${SERVICE_NAME}.access.log;
    error_log  /var/log/nginx/${SERVICE_NAME}.error.log;

    location / {
        proxy_pass http://streamlit;
        proxy_http_version 1.1;

        # WebSockets (obligatorio para Streamlit)
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_read_timeout 86400;
        proxy_buffering off;
    }

    # Health-check liviano (no pasa por Streamlit)
    location /health {
        access_log off;
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
NGINX

# Activar sitio
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t
systemctl reload nginx
echo "  → Nginx configurado para $DOMAIN (HTTP, sin SSL aún)."

# ── 8. Instrucciones finales ───────────────────────────────
echo ""
echo "======================================================"
echo " ✅  Setup completado. Pasos restantes:"
echo ""
echo "  1. Editar el secrets.toml con la clave real:"
echo "     nano $SECRETS_FILE"
echo ""
echo "  2. Iniciar la aplicación:"
echo "     sudo systemctl start $SERVICE_NAME"
echo "     sudo systemctl status $SERVICE_NAME"
echo ""
echo "  3. Obtener certificado SSL (Let's Encrypt):"
echo "     sudo certbot --nginx -d $DOMAIN"
echo ""
echo "  4. Verificar que funciona:"
echo "     https://$DOMAIN"
echo "======================================================"
