"""Staging-only deployment settings. Secrets stay in env/private files, never logs."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import quote

BACKEND_URL = 'http://127.0.0.1:18081'


class ConfigError(ValueError):
    pass


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.staging-')
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def quoted(value):
    if any(char in value for char in '\r\n\0'):
        raise ConfigError('Multiline/NUL environment values are not supported')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def backend_env(path, environment):
    host = environment.get('RDS_HOST', '')
    password = environment.get('RDS_PASSWORD', '')
    if not host and not password:
        if Path(path).is_file() and Path(path).stat().st_size:
            return
        raise ConfigError('Set repository RDS_HOST and RDS_PASSWORD, or provision the staging backend.env')
    if not host or not password:
        raise ConfigError('Both RDS_HOST and RDS_PASSWORD are required; existing settings were preserved')
    database = environment.get('RDS_DATABASE') or 'career'
    user = environment.get('RDS_USERNAME') or 'career'
    port = environment.get('RDS_PORT') or '5432'
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host) or not re.fullmatch(r'[A-Za-z0-9_]+', database):
        raise ConfigError('Invalid database address/name')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ConfigError('Invalid database port')
    values = {
        'JDBC_DATABASE_URL': f'jdbc:postgresql://{host}:{port}/{database}?sslmode=require&ApplicationName=career-staging',
        'POSTGRES_USER': user, 'POSTGRES_PASSWORD': password,
    }
    text = ''.join(f'{key}={quoted(value)}\n' for key, value in values.items())
    atomic_write(path, text)


def web_env(path):
    path = Path(path)
    original = path.read_text(encoding='utf-8') if path.exists() else ''
    lines = [line for line in original.splitlines() if not re.match(r'^\s*(?:export\s+)?BACKEND_URL\s*=', line)]
    lines.append('BACKEND_URL=' + BACKEND_URL)
    atomic_write(path, '\n'.join(lines) + '\n')


def profile_env(path, ca_path, environment):
    """Reuse the designated staging RDS credentials, without logging or shell sourcing."""
    if environment.get('GITHUB_REF_NAME') != 'develop':
        raise ConfigError('Only develop may configure the staging profile database')
    required = ('RDS_HOST', 'RDS_PASSWORD', 'RDS_USERNAME', 'RDS_DATABASE')
    if any(not environment.get(key) for key in required):
        raise ConfigError('Existing staging RDS host, password, username and database are required')
    for key in required:
        quoted(environment[key])
    host, database = environment['RDS_HOST'], environment['RDS_DATABASE']
    port = environment.get('RDS_PORT') or '5432'
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host) or not re.fullmatch(r'[A-Za-z0-9_]+', database) or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ConfigError('Invalid staging database address/name/port')
    with urllib.request.urlopen('https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem', timeout=30) as response:
        ca = response.read(1_000_001)
    if len(ca) > 1_000_000 or b'-----BEGIN CERTIFICATE-----' not in ca:
        raise ConfigError('Invalid AWS RDS certificate bundle')
    original = Path(path).read_text(encoding='utf-8') if Path(path).exists() else ''
    owned = ('CAREER_PROFILE_DATABASE_URL', 'CAREER_PROFILE_CA_FILE', 'CAREER_PROFILE_NAMESPACE')
    lines = [line for line in original.splitlines() if not any(re.match(r'^\s*(?:export\s+)?' + key + r'\s*=', line) for key in owned)]
    user, password = quote(environment['RDS_USERNAME'], safe=''), quote(environment['RDS_PASSWORD'], safe='')
    values = {'CAREER_PROFILE_DATABASE_URL': f'postgresql://{user}:{password}@{host}:{port}/{database}',
              'CAREER_PROFILE_CA_FILE': str(Path(ca_path).resolve()), 'CAREER_PROFILE_NAMESPACE': 'staging'}
    atomic_write(ca_path, ca.decode('ascii'))
    lines += [f'{key}={quoted(value)}' for key, value in values.items()]
    atomic_write(path, '\n'.join(lines) + '\n')


def read_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def verify_backend():
    assert read_json(BACKEND_URL + '/api/health')['status'] == 'UP', 'Backend is not healthy'
    postings = read_json(BACKEND_URL + '/api/postings?size=1')
    assert postings['totalElements'] > 0 and postings['content'], 'RDS postings are not available'
    assert len(read_json(BACKEND_URL + '/api/skill-categories')['categories']) == 10, 'Unexpected category contract'
    return {'rdsPostings': postings['totalElements']}


def verify_web():
    base = 'http://127.0.0.1:3001'
    assert len(read_json(base + '/api/skill-categories')['categories']) == 10, 'Web/backend bridge failed'
    jobs = read_json(base + '/api/jobs?limit=24')
    count = sum(job['id'].startswith('be:') for job in jobs['jobs'])
    assert count > 0, 'Staging still shows no backend postings'
    return {'backendJobsOnPage': count, 'filteredFeedTotal': jobs['total']}


def verify_profile():
    notices = read_json('http://127.0.0.1:3001/api/notices')
    assert isinstance(notices.get('notices'), list), 'Staging notice database is unavailable'
    return {'stagingNotices': len(notices['notices'])}


def wait_for_web(attempts=4, delay=15):
    # The first feed fetch can fail while the app warms up. Its failure cache
    # expires after 30 seconds; retry without accepting a dummy-only response.
    for attempt in range(1, attempts + 1):
        try:
            return {**verify_web(), 'verificationAttempt': attempt}
        except (AssertionError, OSError, ValueError):
            if attempt == attempts:
                raise
            time.sleep(delay)


def sanitized_causes(text, environment):
    for key in ('RDS_PASSWORD', 'RDS_HOST', 'RDS_USERNAME', 'POSTGRES_PASSWORD', 'JDBC_DATABASE_URL'):
        value = environment.get(key)
        if value:
            text = text.replace(value, '[redacted]')
    text = re.sub(r'(?:jdbc:)?postgres(?:ql)?://[^\s]+', '[database URL]', text, flags=re.I)
    lines = [line[:1200] for line in text.splitlines()
             if re.search(r'Caused by:|Exception|\bERROR\b|\bFATAL\b|failed|denied|oom|out.of.memory|Description:|Action:', line, re.I)]
    return lines[-20:]


def diagnostics():
    service = 'career-backend-staging'
    # Scope strictly to this service. Do not inspect process environments or env files.
    status = subprocess.run(['sudo', 'systemctl', 'show', service,
                             '--property=ActiveState,SubState,Result,ExecMainStatus,NRestarts,MemoryCurrent'],
                            capture_output=True, text=True, timeout=15)
    journal = subprocess.run(['sudo', 'journalctl', '-u', service, '--since=-5min', '-n', '200',
                              '--no-pager', '-o', 'cat'], capture_output=True, text=True, timeout=15)
    allowed = {'ActiveState', 'SubState', 'Result', 'ExecMainStatus', 'NRestarts', 'MemoryCurrent'}
    properties = dict(line.split('=', 1) for line in status.stdout.splitlines()
                      if '=' in line and line.split('=', 1)[0] in allowed)
    return {'stagingService': properties, 'sanitizedStartupCauses': sanitized_causes(journal.stdout, os.environ)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backend-env', 'web-env', 'profile-env', 'verify-profile', 'verify-backend', 'verify-web', 'diagnostics'])
    parser.add_argument('--path', type=Path)
    parser.add_argument('--ca-path', type=Path)
    args = parser.parse_args()
    if args.action in ('backend-env', 'web-env') and not args.path:
        parser.error('--path is required')
    if args.action == 'backend-env':
        backend_env(args.path, os.environ)
    elif args.action == 'web-env':
        web_env(args.path)
    elif args.action == 'profile-env':
        if not args.path or not args.ca_path:
            parser.error('--path and --ca-path are required')
        profile_env(args.path, args.ca_path, os.environ)
    elif args.action == 'verify-profile':
        print(json.dumps(verify_profile()))
    elif args.action == 'diagnostics':
        print(json.dumps(diagnostics()))
    else:
        print(json.dumps(verify_backend() if args.action == 'verify-backend' else wait_for_web()))


if __name__ == '__main__':
    try:
        main()
    except ConfigError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        # Do not print environment values, connection strings or server error bodies.
        raise SystemExit(f'Staging configuration/health check failed ({type(error).__name__})') from None
