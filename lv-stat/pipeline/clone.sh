#!/usr/bin/env bash
# clone.sh <out_dir> owner/repo ...   (설계한 받기 설정 그대로: https만, 512KB 필터, 빈 파일 대체, 다시 받기 차단)
R="$1"; shift; mkdir -p "$R"; cd "$R" || exit 1
export GIT_TERMINAL_PROMPT=0 GIT_LFS_SKIP_SMUDGE=1
# macOS에는 timeout 명령이 없음: timeout -> gtimeout -> (둘 다 없으면) 시간 제한 없이 git 실행
if command -v timeout >/dev/null 2>&1; then TMO="timeout 600"; elif command -v gtimeout >/dev/null 2>&1; then TMO="gtimeout 600"; else TMO=""; fi
for u in "$@"; do
  d=$(echo "$u" | sed 's#/#__#'); [ -d "$d" ] && continue
  $TMO git -c protocol.allow=never -c protocol.https.allow=always clone -q --no-checkout --filter=blob:limit=512k "https://github.com/$u" "$d" 2>&1 | tail -1
  cd "$d" 2>/dev/null || { echo "FAIL $u"; continue; }
  E=$(git hash-object -w --stdin </dev/null)
  git rev-list --objects --all --missing=print | sed -n "s/^?\(.*\)/create refs\/replace\/\1 $E/p" | git update-ref --stdin
  git config --unset remote.origin.promisor; git config --unset remote.origin.partialclonefilter; git remote set-url origin file:///dev/null
  echo "$u | commits $(git rev-list --count HEAD) | files $(git ls-tree -r --name-only HEAD | wc -l) | authors $(git log --format=%an | sort -u | wc -l)"
  cd ..
done
