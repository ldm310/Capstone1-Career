"""Configure an existing Airflow env file without changing secrets or starting a DAG."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import tempfile

def configure(path:Path, namespace:str):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",namespace):
        raise ValueError("Invalid namespace")
    if not path.is_file():
        raise ValueError("Existing Airflow .env is required; missing credentials will not be invented")
    original=path.read_text(encoding="utf-8-sig")
    lines=[line for line in original.splitlines() if not re.match(r"^\s*(?:export\s+)?CAREER_PIPELINE_NAMESPACE\s*=",line)]
    updated="\n".join([*lines,"CAREER_PIPELINE_NAMESPACE="+namespace])+"\n"
    descriptor,temporary=tempfile.mkstemp(prefix=".review-env-",dir=path.parent)
    try:
        os.chmod(temporary,0o600)
        with os.fdopen(descriptor,"w",encoding="utf-8",newline="\n") as output:
            output.write(updated)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file",required=True,type=Path)
    parser.add_argument("--namespace",required=True)
    args=parser.parse_args()
    configure(args.env_file,args.namespace)
    print("Airflow review namespace configured; existing credentials preserved")

if __name__ == "__main__": main()
