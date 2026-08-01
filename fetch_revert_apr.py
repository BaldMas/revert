#!/usr/bin/env python3
"""
Получает fee APR и total APR через Revert Finance API для заданных кошельков (base).
Сохраняет в apr.json рядом со скриптом.
"""

import json
import os
import sys
import time
import urllib.request

WALLETS = [
    '0x9c16bc8f1104e4d2f72267eb981fa12de7cc4a6f',
    '0x2534acb6365e902c986a7aAaB3e9761f92D97693',
    '0x9e309c439c118804d9c2cf5eac4dfc62cc6f95c2',
    '0xdd1fbdbbaaed09bcfdfb0b7a7d001ab5791c3511',
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'apr.json')
CHAIN_ID = 8453  # Base
API_BASE = 'https://api.revert.finance/v1'


def fetch_wallet(addr):
    url = f'{API_BASE}/positions?account={addr}&chainId={CHAIN_ID}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f'[{addr}] request error: {e}', file=sys.stderr)
        return {}

    if not data.get('success'):
        print(f'[{addr}] API error: {data}', file=sys.stderr)
        return {}

    result = {}
    for pos in data.get('data', []):
        nft_id = str(pos['nft_id'])
        perf = pos.get('performance', {}).get('hodl', {})
        total_apr = perf.get('apr')
        fee_apr = perf.get('fee_apr')
        if total_apr is None and fee_apr is None:
            continue
        entry = {
            'chain': pos.get('network', 'base'),
            'exchange': pos.get('exchange', 'uniswapv3'),
        }
        if total_apr is not None:
            entry['net_roi'] = round(float(total_apr), 2)
        if fee_apr is not None:
            entry['fee_apr'] = round(float(fee_apr), 2)
        result[nft_id] = entry

    print(f'[{addr}] {len(result)} positions', file=sys.stderr)
    return result


def main():
    all_data = {}
    for addr in WALLETS:
        data = fetch_wallet(addr)
        all_data.update(data)

    payload = {
        'updated_at': int(time.time()),
        'positions': all_data,
    }
    tmp = OUT_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, OUT_PATH)
    print(f'saved {OUT_PATH}: {len(all_data)} positions')


if __name__ == '__main__':
    main()
