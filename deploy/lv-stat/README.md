# LV 분석 작업자 배포 (스테이징 전용)

스테이징 웹(3001번)에서 받은 분석 요청을 처리하는 Python 작업자(`lv-stat/service/worker.py`)를 EC2에 띄운다. 웹과 작업자는 파일로 주고받는다(형식: [lv-stat/service/CONTRACT.md](../../lv-stat/service/CONTRACT.md)). 운영(main·3000번·`~/career-data`)에는 배포하지 않는다.

## 무엇이 어디서 도나

- 언제: develop에 합쳐진 커밋이 `lv-stat/`·`deploy/lv-stat/`·`.github/workflows/cd.yml`을 바꾸면 CD의 `staging-lv-worker` 잡이 EC2 러너(`career-ec2`)에서 `deploy_worker.sh`를 부른다. main에서는 잡이 돌지 않고, 스크립트도 `GITHUB_REF_NAME`이 develop이 아니면 멈춘다.
- 서비스: systemd `career-lv-worker-staging`(러너와 같은 ubuntu 계정, 실패하면 다시 켬)
- 코드: `~/lv-stat/staging/releases/<커밋>/service`, 지금 판은 `~/lv-stat/staging/current`. 최근 5개 판만 남긴다.
- 데이터: `~/career-data-staging/lv-stat/`(jobs·profiles·work)
- 토큰 파일: `~/career-data-staging/lv-worker.env`(소유자만 읽음)
- 자원 한도(「Claude 임시값」, 실제 분석으로 맞출 값): `Nice=10`, `IOSchedulingClass=idle`, `CPUQuota=100%`, `MemoryMax=1500M`. 같은 EC2의 운영 웹과 스테이징 웹·백엔드보다 우선순위를 낮췄다.
- 배포 순서: 판 복사 → `worker.py --self-check`(Python 3.10 이상·git·데이터 폴더 쓰기) → 토큰 파일 → `current` 교체 → 서비스 다시 켜기 → 10초 동안 active인지 확인한다. 자체 점검에 실패하면 도는 작업자를 건드리지 않는다. 다시 켠 뒤 멈추면 이전 판, 서비스 설정, 토큰 파일로 자동으로 되돌리고 잡은 실패로 끝난다. 같은 커밋으로 다시 돌리면 서비스만 다시 켠다.

## GitHub 토큰 (Secret `STAGING_LV_GITHUB_TOKEN`)

공개 레포를 읽기만 하는 토큰을 넣는다(fine-grained, Public repositories 읽기 전용, 추가 권한 없음). 토큰이 없어도 작업자는 돈다. 다만 GitHub API를 시간당 60번만 부를 수 있다.

```
gh secret set STAGING_LV_GITHUB_TOKEN --repo ldm310/Capstone1-Career
```

명령을 실행하면 값을 묻는다. 그때 붙여 넣는다. 값은 명령줄, 채팅, 파일에 적지 않는다. 다음 develop 배포 때 서버 파일에 들어간다. 바로 넣으려면 Actions에서 CD를 develop으로 손으로 돌린다(workflow_dispatch).

- Secret이 비어 있으면 서버의 기존 토큰 파일을 그대로 둔다. 토큰을 그만 쓰려면 EC2에서 `rm ~/career-data-staging/lv-worker.env && sudo systemctl restart career-lv-worker-staging`를 실행한다.
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

잠깐 멈추려면 `sudo systemctl stop career-lv-worker-staging`를 실행한다. 다음 배포 때 다시 켜진다.

## 시험

```
bash -n deploy/lv-stat/deploy_worker.sh
python3 -m unittest discover -s deploy/lv-stat/tests -v
```

시험은 가짜 HOME, sudo, systemctl만 쓰고 실제 서비스·EC2·GitHub에는 닿지 않는다. 확인하는 것은 운영 거부, 토큰 파일 권한(600), 값이 출력되지 않는 것, 같은 커밋 재실행, 되돌리기, 판 5개 유지다. CI의 `lv-stat` 잡이 Python 3.10으로 같은 시험을 돌린다.
