"""Connect only the backend container to the shared RDS, using a private PG env file."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True,
                        help='Private file containing PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD')
    parser.add_argument('--no-build', action='store_true', help='Use the existing backend image')
    args = parser.parse_args()
    values = {}
    for line in args.env_file.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if separator and key.strip().startswith('PG'):
            values[key.strip()] = value.strip().strip('\"').strip("'")
    required = ('PGHOST', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')
    missing = [key for key in required if not values.get(key)]
    if missing:
        parser.error('Missing settings: ' + ', '.join(missing))
    values.setdefault('PGPORT', '5432')
    # Validate URL components before interpolation. Password stays in the subprocess
    # environment; it is never included in command arguments or printed.
    for key in ('PGHOST', 'PGPORT', 'PGDATABASE'):
        if any(char in values[key] for char in '/?&# \t\r\n'):
            parser.error('Invalid URL component: ' + key)
    if not values['PGPORT'].isdigit():
        parser.error('PGPORT must be numeric')
    env = {**os.environ, **values,
           'POSTGRES_USER': values['PGUSER'], 'POSTGRES_PASSWORD': values['PGPASSWORD']}
    root = Path(__file__).resolve().parents[2]
    command = ['docker', 'compose', '-f', str(root / 'compose.yaml'),
               '-f', str(root / 'compose.rds.yaml'), 'up', '-d', '--no-deps']
    if not args.no_build:
        command.append('--build')
    command.append('backend')
    print(f"Connecting backend to {values['PGHOST']}:{values['PGPORT']}/{values['PGDATABASE']} (read only)", flush=True)
    return subprocess.run(command, cwd=root, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
