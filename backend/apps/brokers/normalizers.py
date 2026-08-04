import hashlib
from datetime import datetime
from decimal import Decimal
from dateutil import parser


def to_str(v):
    if v is None:
        return ''
    if isinstance(v, Decimal):
        return format(v, 'f')
    return str(v)


def parse_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return parser.isoparse(value)


def build_execution_dedupe_key(row: dict) -> str:
    stable_execution_id = row.get('execution_id')
    if stable_execution_id:
        raw = f"ibkr|{to_str(row.get('account'))}|exec|{stable_execution_id}"
        return hashlib.sha256(raw.encode()).hexdigest()

    parts = [
        'ibkr',
        to_str(row.get('account')),
        to_str(row.get('perm_id')),
        to_str(row.get('order_id')),
        to_str(row.get('symbol')),
        to_str(row.get('side')),
        to_str(row.get('quantity')),
        to_str(row.get('price')),
        to_str(row.get('executed_at')),
    ]
    raw = '|'.join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()
