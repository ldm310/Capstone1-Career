"""Manage the daily crawler using an explicitly supplied private env file (never printed)."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path,required=True)
    p.add_argument('action',choices=('build','migrate','scan','once','start','status','logs'))
    args,extra=p.parse_known_args()
    if extra and args.action not in ('scan','once'):
        p.error('Extra CLI arguments are allowed only for scan/once')
    values={}
    for line in args.env_file.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);values[key.strip()]=value.strip().strip('\"').strip("'")
    dsn=values.get('DATABASE_URL') or values.get('EXTERNAL_DATABASE_URL')
    if not dsn:
        p.error('DATABASE_URL or EXTERNAL_DATABASE_URL is required in the private env file')
    env={**os.environ,'EXTERNAL_DATABASE_URL':dsn,'COMPOSE_IGNORE_ORPHANS':'true'}
    compose=['docker','compose','-p','capstone1-career-docker','-f',str(ROOT/'compose.external-pass.yaml'),'--profile','external-pass']
    service='external-pass-daily'
    if args.action=='build':command=[*compose,'build',service]
    elif args.action=='start':command=[*compose,'up','-d','--no-build','--no-deps',service]
    elif args.action=='status':command=[*compose,'ps',service]
    elif args.action=='logs':command=[*compose,'logs','--tail','50',service]
    elif args.action=='migrate':command=[*compose,'run','--rm','--no-deps','--entrypoint','python',service,'-m','external_pass_crawler.daily_migrate']
    else:
        command=[*compose,'run','--rm','--no-deps','--entrypoint','python',service,'-m','external_pass_crawler.daily']
        if args.action=='scan':command+=['--dry-run']
        command+=extra
    return subprocess.run(command,cwd=ROOT,env=env).returncode


if __name__=='__main__':
    raise SystemExit(main())
