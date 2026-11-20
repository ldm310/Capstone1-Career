#!/usr/bin/env bash
# Only the dedicated develop backend. No production service/schema/migrations.
set -euo pipefail
[[ "${GITHUB_REF_NAME:-}" == develop ]] || { echo 'Only develop may deploy the staging backend' >&2; exit 2; }
sha=${1:?commit SHA}
bundle=${2:?runtime and app bundle}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$(uname -m)" == x86_64 ]] || { echo 'The bundled runtime requires x86_64' >&2; exit 2; }
command -v python3 >/dev/null
command -v ss >/dev/null
sudo -n true
svc=career-backend-staging
base=$HOME/backend/staging
data=$HOME/career-data-staging
rel=$base/releases/$sha
unit=/etc/systemd/system/$svc.service
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$base/releases" "$data"
# A new service must not take a port already owned by something else.
if ! sudo test -f "$unit" && ss -ltnH 'sport = :18081' | grep -q .; then
  echo 'Port 18081 is already occupied; no service was changed' >&2; exit 1
fi
if [ ! -f "$rel/.ready" ]; then
  mkdir -p "$rel"
  tar -tzf "$bundle" | python3 -c 'import sys; from pathlib import PurePosixPath; names=sys.stdin.read().splitlines(); assert names and all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in names)'
  tar -xzf "$bundle" -C "$rel"
  test -x "$rel/runtime/bin/java"
  test -f "$rel/app.jar"
  "$rel/runtime/bin/java" -version
  touch "$rel/.ready"
fi
prev_rel=$(readlink -f "$base/current" 2>/dev/null || true)
prev_unit=false
prev_env=false
if sudo test -f "$unit"; then sudo cp "$unit" "$base/service.previous"; prev_unit=true; fi
if [ -f "$data/backend.env" ]; then cp -p "$data/backend.env" "$base/env.previous"; prev_env=true; fi
python3 "$script_dir/staging_config.py" backend-env --path "$data/backend.env"
rollback() {
  trap - ERR
  python3 "$script_dir/staging_config.py" diagnostics || true
  echo 'Staging backend failed; restoring its previous release' >&2
  if [ -n "$prev_rel" ]; then ln -sfn "$prev_rel" "$base/current"; else rm -f "$base/current"; fi
  if $prev_env; then cp -p "$base/env.previous" "$data/backend.env"; fi
  if $prev_unit; then
    sudo cp "$base/service.previous" "$unit"
    sudo systemctl daemon-reload
    sudo systemctl restart "$svc" || true
  else
    sudo systemctl stop "$svc" || true
    sudo systemctl disable "$svc" || true
    sudo rm -f "$unit"
    sudo systemctl daemon-reload
  fi
  exit 1
}
trap rollback ERR
ln -sfn "$rel" "$base/current.new"
mv -Tf "$base/current.new" "$base/current"
sudo tee "$unit" >/dev/null <<EOF
[Unit]
Description=Career staging backend (develop, read-only RDS)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$base/current
EnvironmentFile=$data/backend.env
Environment=SPRING_PROFILES_ACTIVE=docker,rds,staging-readonly
Environment=SERVER_ADDRESS=127.0.0.1
Environment=SERVER_PORT=18081
Environment=SPRING_JPA_HIBERNATE_DDL_AUTO=none
Environment=SPRING_SQL_INIT_MODE=never
Environment=SPRING_DATASOURCE_HIKARI_READ_ONLY=true
Environment="SPRING_DATASOURCE_HIKARI_CONNECTION_INIT_SQL=SET default_transaction_read_only = on"
Environment=APP_STORAGE_PROJECTFILEDIR=$data/backend-uploads
ExecStart=$base/current/runtime/bin/java -Xms64m -Xmx256m -jar $base/current/app.jar --spring.profiles.active=docker,rds,staging-readonly --server.address=127.0.0.1 --server.port=18081 --spring.jpa.hibernate.ddl-auto=none --spring.sql.init.mode=never --spring.datasource.hikari.read-only=true "--spring.datasource.hikari.connection-init-sql=SET default_transaction_read_only = on"
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --quiet "$svc"
sudo systemctl restart "$svc"
ready=false
for _ in $(seq 1 90); do
  if curl -fsS -o /dev/null http://127.0.0.1:18081/api/health 2>/dev/null; then ready=true; break; fi
  if sudo systemctl is-failed --quiet "$svc"; then break; fi
  sleep 2
done
$ready
python3 "$script_dir/staging_config.py" verify-backend
# Set the web bridge only after live RDS reads succeed. No address is guessed.
python3 "$script_dir/staging_config.py" web-env --path "$data/.env"
trap - ERR
echo "Staging backend ready at loopback port 18081, commit $sha"
