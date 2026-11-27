#!/usr/bin/env bash
# CD(LV 분석 작업자): develop 커밋의 lv-stat/service 를 스테이징 EC2 에서 도는 작업자로 바꾼다.
#   부르는 곳: .github/workflows/cd.yml 의 staging-lv-worker 잡(EC2 러너 career-ec2, develop 만).
#   스테이징 전용 — 운영(main·3000번·~/career-data)·웹·백엔드 서비스는 건드리지 않는다.
#   판     ~/lv-stat/staging/releases/<커밋>/service   (current → 지금 판)
#   데이터 ~/career-data-staging/lv-stat               (웹 CAREER_DATA_DIR 아래, lv-stat/service/CONTRACT.md)
#   비밀   ~/career-data-staging/lv-worker.env          (LV_GITHUB_TOKEN 한 줄, 소유자만 읽음, 값은 어디에도 찍지 않음)
#   서비스 career-lv-worker-staging (systemd)
# 몇 번 돌려도 같은 결과(멱등): 같은 커밋이면 판·설정을 그대로 두고 서비스만 다시 켠다.
#   새 판이 몇 초 안에 멈추면 이전 판·서비스 설정·토큰 파일로 되돌리고 실패로 끝난다.
# 사용: GITHUB_REF_NAME=develop [LV_GITHUB_TOKEN=…] bash deploy_worker.sh <커밋 40자> <lv-stat/service 폴더>
# 시험용(평소에는 두지 않음): LV_UNIT_DIR(서비스 파일 폴더, 기본 /etc/systemd/system), LV_CHECK_ROUNDS(살아 있는지 2초 간격 확인 횟수)
{ set +x; } 2>/dev/null   # bash -x 로 불러도 토큰이 찍히지 않게
set -euo pipefail

# 0) 운영처럼 보이면 아무것도 하지 않고 멈춘다
[[ "${GITHUB_REF_NAME:-}" == develop ]] || { echo "LV 작업자는 develop(스테이징)만 배포합니다: GITHUB_REF_NAME=${GITHUB_REF_NAME:-없음}" >&2; exit 2; }
for v in "${TARGET:-}" "${DEPLOY_ENV:-}" "${CAREER_ENV:-}"; do
  [[ "$v" != production ]] || { echo "운영(production) 배포는 거부합니다 — LV 작업자는 스테이징 전용" >&2; exit 2; }
done
sha=${1:?커밋(40자)}
src=${2:?lv-stat/service 폴더}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "커밋은 40자 16진수여야 합니다" >&2; exit 2; }
[ -f "$src/worker.py" ] || { echo "$src 에 worker.py 가 없습니다 — 서비스는 그대로" >&2; exit 2; }

# 토큰은 셸 변수로만 들고, 자식 프로세스(cp·git·sudo·python)에는 넘기지 않는다
token=${LV_GITHUB_TOKEN:-}
unset LV_GITHUB_TOKEN
token=${token#"${token%%[![:space:]]*}"}   # 앞뒤 공백·줄바꿈만 걷어 냄(붙여 넣기 실수)
token=${token%"${token##*[![:space:]]}"}
if [ -n "$token" ] && ! [[ "$token" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "STAGING_LV_GITHUB_TOKEN 형식이 GitHub 토큰(영문·숫자·밑줄)이 아닙니다(값은 찍지 않음) — 서비스는 그대로" >&2; exit 2
fi

svc=career-lv-worker-staging
base=$HOME/lv-stat/staging
data=$HOME/career-data-staging
lvdata=$data/lv-stat
envfile=$data/lv-worker.env
rel=$base/releases/$sha
unit_dir=${LV_UNIT_DIR:-/etc/systemd/system}
unit=$unit_dir/$svc.service
keep=5                                   # 남길 판 수
rounds=${LV_CHECK_ROUNDS:-5}             # 2초 × 5 = 10초 동안 계속 active 여야 성공
# systemd 설정 줄에 그대로 넣으므로 경로에 공백·특수문자가 있으면 멈춘다
for p in "$base" "$data" "$unit_dir"; do
  [[ "$p" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "경로에 쓸 수 없는 글자가 있습니다: $p" >&2; exit 2; }
done
py=$(command -v python3) || { echo "python3 가 없습니다" >&2; exit 1; }
[[ "$py" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "python3 경로가 절대 경로가 아닙니다: $py" >&2; exit 1; }
command -v git >/dev/null || { echo "git 이 없습니다" >&2; exit 1; }
sudo -n true || { echo "비밀번호 없는 sudo 가 필요합니다(러너 계정)" >&2; exit 1; }
# 서버 상태를 로그에 남긴다(Python 판, 남은 디스크·메모리) — 상한값을 맞출 때 쓴다.
#   git 판은 남기지 않는다: CI 로그는 공개되고, git 은 남이 고른 레포를 받으므로 그 판에 맞는 약점을 고르기 쉽다
echo "서버: $("$py" -c 'import sys; print("Python", sys.version.split()[0])' 2>/dev/null)"
df -h "$HOME" 2>/dev/null | tail -1 | awk '{print "디스크(HOME): 전체 " $2 ", 남음 " $4}' || true
command -v free >/dev/null && free -m | awk '/^Mem:/ {print "메모리(MB): 전체 " $2 ", 사용 가능 " $7}' || true

tmp_rel=''; tmp_env=''
cleanup() { [ -z "$tmp_rel" ] || rm -rf "$tmp_rel"; [ -z "$tmp_env" ] || rm -f "$tmp_env"; }
trap cleanup EXIT
swap_current() {   # current 를 한 번에 바꿈(rename 은 링크 자체를 바꾸므로 GNU·BSD 모두 원자적)
  ln -sfn "$1" "$base/current.new" && "$py" -I -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$base/current.new" "$base/current"
}
with_timeout() { if command -v timeout >/dev/null; then timeout "$@"; else shift; "$@"; fi; }

# 1) 새 판(이미 있으면 그대로) — 임시 폴더에 복사한 뒤 이름만 바꿔, 반쯤 복사된 판을 쓰지 않는다
mkdir -p "$base/releases" "$lvdata"
if [ ! -f "$rel/.ready" ]; then
  tmp_rel=$(mktemp -d "$base/releases/.new-${sha:0:12}.XXXXXX")
  cp -RL "$src" "$tmp_rel/service"
  find "$tmp_rel" -name __pycache__ -type d -prune -exec rm -rf {} +
  rm -rf "$rel"
  mv "$tmp_rel" "$rel"
  tmp_rel=''
  touch "$rel/.ready"
fi
rel=$(cd "$rel" && pwd -P)

# 2) 자체 점검(Python ≥3.10·git·데이터 폴더 쓰기) — 실패하면 여기서 멈추고 도는 작업자는 그대로
if ! check=$(cd "$rel" && with_timeout 60 "$py" -I "$rel/service/worker.py" --self-check --data-dir "$lvdata" 2>&1); then
  printf '%s\n' "$check" >&2
  echo "새 판(${sha:0:7}) 자체 점검 실패 — $svc 는 그대로" >&2; exit 1
fi
printf '%s\n' "$check"

# 3) 지금 상태를 적어 둔다(되돌릴 때 씀)
prev_rel=''
if [ -L "$base/current" ]; then prev_rel=$(readlink -f "$base/current" 2>/dev/null || true); fi
[ -z "$prev_rel" ] || [ -d "$prev_rel" ] || prev_rel=''
had_unit=false
if [ -f "$unit" ]; then cp "$unit" "$base/$svc.service.prev"; had_unit=true; fi
env_state=kept   # kept | same | created | replaced

want="[Unit]
Description=Career LV analysis worker (staging, lv-stat) — deploy/lv-stat/deploy_worker.sh 가 관리
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$base/current
Environment=LANG=C.UTF-8
Environment=GIT_TERMINAL_PROMPT=0
EnvironmentFile=-$envfile
ExecStart=$py -I -u $base/current/service/worker.py --data-dir $lvdata
Restart=on-failure
RestartSec=10
# 「Claude 임시값」: 같은 EC2 의 운영 웹(3000)·스테이징 웹(3001)·스테이징 백엔드보다 뒤로 미루는 값.
#   Nice·CPUQuota·MemoryMax 숫자는 실제 분석 시간·메모리를 재 보고 맞춘다.
Nice=10
IOSchedulingClass=idle
CPUQuota=100%
MemoryMax=1500M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
UMask=0077

[Install]
WantedBy=multi-user.target"

write_env() {   # 토큰이 있을 때만 쓴다. 값은 printf(셸 내장)로 파일에만 — 명령줄·로그에 안 나옴
  if [ -z "$token" ]; then
    if [ -f "$envfile" ]; then chmod 600 "$envfile" || return 1; echo "토큰 파일 그대로 둠(Secret 비어 있음): $envfile"; fi
    return 0
  fi
  tmp_env=$(umask 077 && mktemp "$data/.lv-worker.env.XXXXXX") || return 1
  (umask 077 && printf 'LV_GITHUB_TOKEN=%s\n' "$token" > "$tmp_env") || return 1
  chmod 600 "$tmp_env" || return 1
  if [ -f "$envfile" ] && cmp -s "$tmp_env" "$envfile"; then
    rm -f "$tmp_env"; tmp_env=''; chmod 600 "$envfile" || return 1
    env_state=same; echo "토큰 파일 그대로(같은 값): $envfile"; return 0
  fi
  if [ -f "$envfile" ]; then
    (umask 077 && cp -p "$envfile" "$base/lv-worker.env.prev") || return 1
    env_state=replaced
  else
    env_state=created
  fi
  mv -f "$tmp_env" "$envfile" || return 1
  tmp_env=''
  echo "토큰 파일을 썼습니다(소유자만 읽음, 값은 찍지 않음): $envfile"
}

healthy() {   # 몇 초 동안 계속 active 이고, 그 사이 다시 켜진 적(NRestarts 증가)이 없어야 성공
  local before after
  before=$(systemctl show -p NRestarts --value "$svc" 2>/dev/null || echo 0)
  for _ in $(seq 1 "$rounds"); do
    sleep 2
    systemctl is-active --quiet "$svc" || return 1
  done
  after=$(systemctl show -p NRestarts --value "$svc" 2>/dev/null || echo 0)
  [ "$before" = "$after" ]
}

activate() {   # if 안에서 불리므로 set -e 가 안 먹음 — 줄마다 || return 1
  write_env || return 1
  swap_current "$rel" || return 1
  if ! [ -f "$unit" ] || [ "$(cat "$unit")" != "$want" ]; then
    printf '%s\n' "$want" | sudo tee "$unit" >/dev/null || return 1
  fi
  sudo systemctl daemon-reload || return 1
  sudo systemctl enable --quiet "$svc" || return 1
  sudo systemctl restart "$svc" || return 1
  healthy
}

rollback() {
  echo "새 판(${sha:0:7})이 돌지 않아 이전 상태로 되돌립니다" >&2
  # CI 로그는 공개된다(공개 레포). 작업자 로그(분석한 계정·레포 이름)는 옮기지 않고 systemd 상태 값만 남긴다
  systemctl show -p ActiveState,SubState,Result,ExecMainStatus,NRestarts "$svc" >&2 2>/dev/null || true
  echo "작업자 로그는 EC2 에서 보세요: journalctl -u $svc -n 50 --no-pager" >&2
  case "$env_state" in
    replaced) mv -f "$base/lv-worker.env.prev" "$envfile" || true ;;
    created)  rm -f "$envfile" || true ;;
  esac
  if [ -n "$prev_rel" ]; then swap_current "$prev_rel" || true; else rm -f "$base/current"; fi
  if $had_unit; then
    sudo tee "$unit" >/dev/null < "$base/$svc.service.prev" || true
    sudo systemctl daemon-reload || true
    if [ -n "$prev_rel" ] && sudo systemctl restart "$svc" && healthy; then
      echo "이전 판(${prev_rel##*/})으로 되돌렸습니다(정상)" >&2
    else
      echo "되돌린 판도 돌지 않습니다 — journalctl -u $svc 로 확인하세요" >&2
    fi
  else   # 처음 배포라 되돌릴 판이 없음 — 서비스를 없앤다
    sudo systemctl stop "$svc" 2>/dev/null || true
    sudo systemctl disable --quiet "$svc" 2>/dev/null || true
    sudo rm -f "$unit"
    sudo systemctl daemon-reload || true
  fi
  exit 1
}

# 4) 토큰 파일·current·서비스 설정을 바꾸고 다시 켠다. 안 돌면 모두 되돌린다
if ! activate; then rollback; fi
rm -f "$base/lv-worker.env.prev"   # 옛 토큰 사본은 성공하면 남기지 않는다
touch "$rel/.ready"   # 판 정리 순서: 마지막으로 배포한 때

# 5) 판 정리: 최근에 배포한 5개만 남긴다(지금 판·바로 전 판은 늘 남김)
n=0
for marker in $(ls -1t "$base"/releases/*/.ready 2>/dev/null); do
  d=${marker%/.ready}
  n=$((n + 1))
  [ "$n" -gt "$keep" ] || continue
  case "$(readlink -f "$d")" in "$rel"|"$prev_rel") continue ;; esac
  rm -rf "$d"
done
for d in "$base"/releases/.new-*; do [ ! -d "$d" ] || rm -rf "$d"; done   # 끊긴 배포가 남긴 복사 중 폴더

if [ "$prev_rel" = "$rel" ]; then
  echo "$svc 같은 판(${sha:0:7})으로 다시 켰습니다"
else
  echo "$svc → ${sha:0:7} (데이터 $lvdata)"
fi
