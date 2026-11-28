# LV 분석 작업자 배포 (스테이징 전용)

스테이징 웹(3001번)에서 받은 분석 요청을 처리하는 Python 작업자(`lv-stat/service/worker.py`)를 EC2에 띄운다. 웹과 작업자는 파일로 주고받는다(형식: [lv-stat/service/CONTRACT.md](../../lv-stat/service/CONTRACT.md)). 운영(main·3000번·`~/career-data`)에는 배포하지 않는다. 웹의 분석 칸·분석 API·공고 화면의 분석 결과 읽기도 스테이징 웹에서만 켠다: `deploy/web/deploy.sh`가 스테이징 웹 서비스에 `CAREER_LV_STAT=on`, 운영 웹에 `off`를 준다(꺼진 웹은 분석 API가 404, CONTRACT.md '스테이징 스위치').

## 무엇이 어디서 도나

- 언제: develop에 합쳐진 커밋이 `lv-stat/`·`deploy/lv-stat/`·`.github/workflows/cd.yml`을 바꾸면 CD의 `staging-lv-worker` 잡이 EC2 러너(`career-ec2`)에서 `deploy_worker.sh`를 부른다. main에서는 잡이 돌지 않고, 스크립트도 `GITHUB_REF_NAME`이 develop이 아니면 멈춘다.
- 서비스: systemd `career-lv-worker-staging`(러너와 같은 ubuntu 계정, 실패하면 다시 켬)
- 코드: `~/lv-stat/staging/releases/<커밋>/service`, 지금 판은 `~/lv-stat/staging/current`. 최근 5개 판만 남긴다. 지금 판과 바로 전 판은 그보다 오래돼도 남긴다.
- 데이터: `~/career-data-staging/lv-stat/`(jobs·profiles·work)
- 토큰 파일: `~/career-data-staging/lv-worker.env`(소유자만 읽음)
- 자원 한도(「Claude 임시값」, 실제 분석으로 맞출 값): `Nice=10`, `IOSchedulingClass=idle`, `CPUQuota=100%`, `MemoryHigh=400M`, `MemoryMax=512M`. 같은 EC2의 운영 웹과 스테이징 웹·백엔드보다 우선순위를 낮췄다.
- 메모리 한도의 까닭: 첫 배포 로그(`메모리(MB)` 줄)에서 서버 메모리 1905MB 중 사용 가능이 751MB였다. 운영 웹·스테이징 웹·백엔드가 같은 서버를 쓰므로 작업자가 그 남은 메모리를 다 쓰지 않게 묶는다. `MemoryHigh`를 넘으면 커널이 메모리를 거둬 느려지고, `MemoryMax`를 넘으면 그 프로세스가 죽는다. `OOMPolicy=continue`라 메모리 한도로 자식(색인·git) 하나가 죽어도 작업자는 계속 돌고 그 단계만 실패 메모로 남는다.
- 디스크: 작업자는 받기 전마다, 받기·색인 중에도 남은 공간을 본다. 2GiB(「Claude 임시값」) 밑이면 그 단계를 멈추고 메모를 남긴다(CONTRACT.md '작업자 실행'). 받기 전 점검이 받기를 멈추면 작업자 로그(journal)에 경고 한 줄(레포 수, 남은 공간 MiB. 경로·레포 이름은 없음)도 남긴다. 첫 배포 로그의 `디스크(HOME)` 줄은 `전체 19G, 남음 8.2G`여서 2GiB는 그대로 둔다. 배포 로그의 이 줄과 작업자 로그의 경고를 보고 다시 정한다.
- 배포 순서: 판 복사 → `worker.py --self-check`(Python 3.10 이상·git·데이터 폴더 쓰기·Linguist 자료 세 파일·서비스 폴더 모든 `.py`의 문법(메모리에서 compile)) → 토큰 파일 → `current` 교체 → 서비스 다시 켜기 → 10초 동안 active인지, 그 사이 systemd가 다시 켠 적(`NRestarts` 증가)이 없는지 확인한다. 자체 점검에 실패하면 도는 작업자를 건드리지 않는다. 다시 켠 뒤 멈추면 이전 판, 서비스 설정, 토큰 파일로 자동으로 되돌리고 잡은 실패로 끝난다. 같은 커밋으로 다시 돌리면 서비스만 다시 켠다.
- CI 로그: 팀 레포가 공개라 Actions 로그도 공개된다. 그래서 스크립트는 작업자 로그(분석한 계정·레포 이름이 들어 있음)와 git 판을 CI 로그에 남기지 않는다. 되돌릴 때는 systemd 상태 값(`ActiveState`·`Result`·`ExecMainStatus` 등)만 남긴다. 원인은 EC2에서 `journalctl -u career-lv-worker-staging -n 50`으로 본다. 자체 점검은 결과(`OK` 또는 `자체 점검 실패: …` 줄)만 CI 로그에 남기고, 작업자 로그(stderr)는 EC2의 `~/lv-stat/staging/self-check.log`(소유자만 읽음, 배포마다 새로 씀)에 둔다. git 판은 자체 점검이 찍지 않고 작업자 시작 로그(journal)에만 남는다.

## GitHub 토큰 (Secret `STAGING_LV_GITHUB_TOKEN`)

공개 레포를 읽기만 하는 토큰을 넣는다(fine-grained, Public repositories 읽기 전용, 추가 권한 없음). 토큰이 없어도 작업자는 돈다. 다만 GitHub API를 시간당 60번만 부를 수 있다.

```
gh secret set STAGING_LV_GITHUB_TOKEN --repo ldm310/Capstone1-Career
```

명령을 실행하면 값을 묻는다. 그때 붙여 넣는다. 값은 명령줄, 채팅, 파일에 적지 않는다. 다음 develop 배포 때 서버 파일에 들어간다. 바로 넣으려면 Actions에서 CD를 develop으로 손으로 돌린다(workflow_dispatch).

- Secret이 비어 있으면 서버의 기존 토큰 파일을 그대로 둔다. 토큰을 그만 쓰려면 먼저 Secret `STAGING_LV_GITHUB_TOKEN`을 지운다(지우지 않으면 다음 develop 배포가 파일을 다시 쓴다). 그다음 EC2에서 `rm ~/career-data-staging/lv-worker.env && sudo systemctl restart career-lv-worker-staging`를 실행한다.
- 스크립트는 토큰 값을 출력하지 않고 자식 프로세스에도 넘기지 않는다. 형식이 영문·숫자·밑줄이 아니면 아무것도 바꾸지 않고 멈춘다.

## 로그·상태

```
journalctl -u career-lv-worker-staging -f        # 실시간 로그
systemctl status career-lv-worker-staging        # 상태
readlink -f ~/lv-stat/staging/current            # 지금 판(커밋)
```

## 되돌리기

배포가 실패하면 자동으로 되돌린다. 성공한 판을 손으로 되돌리려면 EC2에서 다음을 실행한다.

```
ls -1t ~/lv-stat/staging/releases                # 남아 있는 판(최근 순)
cd ~/lv-stat/staging && ln -sfn "$PWD/releases/<되돌릴 커밋 40자>" current.new && mv -Tf current.new current
sudo systemctl restart career-lv-worker-staging
```

잠깐 멈추려면 `sudo systemctl stop career-lv-worker-staging`를 실행한다. 작업자는 SIGTERM을 받으면 하던 분석의 자식 프로세스(git·색인)를 끝내고 받은 레포(`work/<요청 id>`)를 지운 뒤 종료 코드 143으로 끝난다. 서비스 설정의 `SuccessExitStatus=143`이 이 코드를 성공으로 보므로, 멈춘 서비스는 `failed`가 아니라 `inactive`로 남는다. 그 요청은 다음에 켤 때 `작업자가 다시 시작되어 중단됐습니다. 다시 요청해 주세요.`로 닫힌다. 다음 배포 때 다시 켜진다.

## 시험

```
bash -n deploy/lv-stat/deploy_worker.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s deploy/lv-stat/tests -v
```

시험은 가짜 HOME, sudo, systemctl, journalctl만 쓰고 실제 서비스·EC2·GitHub에는 닿지 않는다. 스크립트가 PATH로 부르는 명령은 기록용 껍데기를 거친다. 그래서 돌릴 때마다 토큰 값이 출력, 명령 인자, 자식 환경에 없는지 본다(절대 경로로 부르는 명령은 못 봄). `test_web_lv_switch.py`는 팀 웹 배포 스크립트 `deploy/web/deploy.sh`를 돌리지 않고 글로 읽는다(팀이 다른 단계를 고쳐도 깨지지 않게). `staging` 갈래는 `on`, `production` 갈래는 `off`를 주고, 웹 서비스 파일 글의 `Environment=CAREER_LV_STAT=` 줄이 그 갈래가 정한 변수를 쓰는지 본다. 확인하는 것은 운영 거부, 서비스 파일(메모리 한도 줄, `SuccessExitStatus=143`), 토큰 파일 권한(600), 토큰을 바꾼 뒤 옛 사본이 남지 않는 것, 같은 커밋 재실행(판을 다시 복사하지 않음), 되돌리기(판·서비스 설정·토큰 파일), 확인하는 사이 다시 켜진 판의 되돌리기(`NRestarts` 증가), CI 로그에 작업자 로그와 git 판이 없는 것(자체 점검의 로그는 서버 파일, 권한 600), 판 5개 유지(지금 판·바로 전 판은 오래돼도 남김)다. CI의 `lv-stat` 잡이 Python 3.10으로 같은 시험을 돌린다. `PYTHONDONTWRITEBYTECODE=1`을 붙이면 `__pycache__`가 생기지 않는다(`deploy/lv-stat/.gitignore`에도 넣었다).
