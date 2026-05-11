#!/usr/bin/env bash
# =============================================================
# ACTUALIZACIÓN DE LA APP — Ejecutar en cada nuevo deploy
#
# Uso:
#   sudo bash /opt/portal-territorial/deploy/update.sh
#
# Qué hace:
#   1. git pull (trae los últimos cambios)
#   2. pip install -r requirements.txt (actualiza dependencias)
#   3. systemctl restart (reinicia la app)
# =============================================================
set -euo pipefail

APP_DIR="/opt/portal-territorial"
APP_USER="appuser"
SERVICE_NAME="portal-territorial"

echo "======================================================"
echo " Portal Territorial — Deploy / Update"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

# ── 1. Git pull ────────────────────────────────────────────
echo "[1/3] Actualizando código desde GitHub..."
sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin main
BEHIND=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-list HEAD..origin/main --count)
if [[ "$BEHIND" -eq 0 ]]; then
  echo "  → Código ya está actualizado. No hay cambios."
else
  echo "  → $BEHIND commit(s) nuevo(s). Actualizando..."
  sudo -u "$APP_USER" git -C "$APP_DIR" merge --ff-only origin/main
fi

# ── 2. Dependencias ────────────────────────────────────────
echo "[2/3] Actualizando dependencias Python..."
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# ── 3. Reiniciar servicio ──────────────────────────────────
echo "[3/3] Reiniciando servicio..."
systemctl restart "$SERVICE_NAME"
sleep 3
STATUS=$(systemctl is-active "$SERVICE_NAME" 2>&1)
if [[ "$STATUS" == "active" ]]; then
  echo "  ✅  Servicio activo y corriendo."
else
  echo "  ❌  El servicio no arrancó. Ver logs:"
  echo "      journalctl -u $SERVICE_NAME -n 50 --no-pager"
  exit 1
fi

echo ""
echo "======================================================"
echo " ✅  Deploy completado exitosamente."
echo "======================================================"
