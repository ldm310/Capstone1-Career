#!/usr/bin/env bash
# CD(웹): EC2 의 웹을 그 커밋으로 바꾼다. GitHub Actions 가 ssh 로 부른다(.github/workflows/cd.yml).
#   staging    = 3001번, develop, 데이터 ~/career-data-staging
#   production = 3000번, main,    데이터 ~/career-data(지금 운영 데이터 그대로)
# 몇 번 돌려도 같은 결과(멱등):
#   - 그 커밋에 웹 코드(frontend/package.json)가 없으면 아무것도 하지 않는다(지금 사이트를 건드리지 않음)
#   - 이미 그 커밋이 떠 있으면 아무것도 하지 않는다
#   - 판마다 따로 빌드(~/web/<env>/releases/<커밋>)한 뒤 current 를 한 번에 바꾸고, 안 뜨면 이전 판으로 되돌린다
# 사용: bash deploy.sh staging|production <커밋>   (REPO 를 바꾸면 다른 저장소로 시험할 수 있음)
set -euo pipefail

env=${1:?staging 또는 production}
sha=${2:?커밋}
REPO=${REPO:-https://github.com/ldm310/Capstone1-Career.git}
case "$env" in
  staging)    svc=career-web-staging; port=3001; data=$HOME/career-data-staging ;;
  production) svc=career-web;         port=3000; data=$HOME/career-data ;;
  *) echo "staging 또는 production 만 됩니다: $env" >&2; exit 2 ;;
esac
base=$HOME/web/$env
mirror=$base/repo.git
rel=$base/releases/$sha
unit=/etc/systemd/system/$svc.service

mkdir -p "$base/releases" "$data"
[ -d "$mirror" ] || git clone --quiet --bare "$REPO" "$mirror"
git -C "$mirror" fetch --quiet origin '+refs/heads/*:refs/heads/*'
if ! git -C "$mirror" cat-file -e "$sha:frontend/package.json" 2>/dev/null; then
  echo "이 커밋(${sha:0:7})에는 웹 코드(frontend/)가 없어 배포하지 않습니다 — $svc 는 그대로"
  exit 0
fi
if [ "$(readlink -f "$base/current" 2>/dev/null || true)" = "$rel" ] && systemctl is-active --quiet "$svc"; then
  echo "$svc 는 이미 ${sha:0:7} — 바꾼 것 없음"
  exit 0
fi

# 1) 새 판 빌드(이미 빌드한 판이면 그대로 씀) — 실패하면 여기서 멈추고 도는 서버는 그대로
if [ ! -f "$rel/.built" ]; then
  rm -rf "$rel"
  git -C "$mirror" worktree prune
  git -C "$mirror" worktree add --quiet --detach "$rel" "$sha"
  (cd "$rel/frontend" && npm ci --no-audit --no-fund && npm run build)
  touch "$rel/.built"
fi

# 2) 서비스 설정: 이 환경의 current/frontend 에서, 이 환경의 데이터·포트로(처음 한 번 만들거나 고침)
prev_dir=$(sudo sed -n 's/^WorkingDirectory=//p' "$unit" 2>/dev/null || true)
prev_rel=$(readlink -f "$base/current" 2>/dev/null || true)
want="[Unit]
Description=Career web ($env, Next.js) — deploy/web/deploy.sh 가 관리
After=network.target

[Service]
User=$(id -un)
WorkingDirectory=$base/current/frontend
Environment=NODE_ENV=production
Environment=CAREER_DATA_DIR=$data
Environment=NEXT_TELEMETRY_DISABLED=1
ExecStart=$(command -v npm) start -- -p $port -H 127.0.0.1
Restart=always

[Install]
WantedBy=multi-user.target"
[ -f "$unit" ] && sudo cp "$unit" "$base/$svc.service.prev"

# 3) current 를 새 판으로 한 번에 바꾸고 다시 켜기
ln -sfn "$rel" "$base/current.new" && mv -Tf "$base/current.new" "$base/current"
printf '%s\n' "$want" | sudo tee "$unit" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --quiet "$svc"
sudo systemctl restart "$svc"

wait_up() {   # 그 포트가 답할 때까지 최대 90초
  for _ in $(seq 1 45); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$port"; then return 0; fi
    sleep 2
  done
  return 1
}
if ! wait_up; then
  echo "새 판(${sha:0:7})이 뜨지 않아 이전 판으로 되돌립니다" >&2
  if [ -n "$prev_rel" ]; then ln -sfn "$prev_rel" "$base/current.new" && mv -Tf "$base/current.new" "$base/current"; fi
  if [ -f "$base/$svc.service.prev" ]; then sudo cp "$base/$svc.service.prev" "$unit"; fi   # 처음 바꿀 때는 옛 폴더(prev_dir)로
  sudo systemctl daemon-reload
  if [ -n "$prev_dir$prev_rel" ]; then
    sudo systemctl restart "$svc"
    if wait_up; then echo "이전 판으로 되돌렸습니다(정상)" >&2; else echo "되돌린 판도 뜨지 않습니다 — 서버를 확인하세요" >&2; fi
  else
    sudo systemctl stop "$svc"   # 처음 배포라 되돌릴 판이 없음
  fi
  exit 1
fi

# 4) 판 정리: 지금 판과 바로 전 판만 남긴다
for d in "$base"/releases/*; do
  [ -d "$d" ] || continue
  case "$(readlink -f "$d")" in "$rel"|"$prev_rel") continue ;; esac
  git -C "$mirror" worktree remove --force "$d" 2>/dev/null || rm -rf "$d"
done
echo "$svc → ${sha:0:7} (http://127.0.0.1:$port)"
