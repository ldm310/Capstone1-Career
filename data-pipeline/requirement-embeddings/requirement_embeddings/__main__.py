import argparse
import json
import os
import math
from .batch import run
from .client import OpenAIClient,SafeFailure
from .config import Config


def main(argv=None):
    p=argparse.ArgumentParser(description='Shadow embeddings only; dry-run by default, no keyword ranking changes')
    p.add_argument('--apply',action='store_true',help='Explicitly generate missing embeddings and write owned tables')
    p.add_argument('--limit',type=int,default=100000)
    args=p.parse_args(argv)
    if not 1<=args.limit<=100000:p.error('limit must be 1..100000')
    try:
        import psycopg
        from psycopg.rows import dict_row
        config=Config.from_env()
        client=OpenAIClient(config) if args.apply else None
        options='' if args.apply else '-c default_transaction_read_only=on'
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,row_factory=dict_row,connect_timeout=10,options=options) as conn:
            price=os.environ.get('EMBEDDING_PRICE_PER_MILLION_TOKENS')
            price=float(price) if price is not None else None
            if price is not None and (not math.isfinite(price) or price<0):raise ValueError('INVALID_PRICE')
            report=run(conn,config,client,apply=args.apply,limit=args.limit,price=price)
            print(json.dumps(report))
        return 0 if report.get('status')!='PARTIAL' else 1
    except SafeFailure as exc:
        print(json.dumps({'error_code':exc.code}));return 1
    except Exception:
        print(json.dumps({'error_code':'EMBEDDING_BATCH_FAILED'}));return 1


if __name__=='__main__':raise SystemExit(main())
