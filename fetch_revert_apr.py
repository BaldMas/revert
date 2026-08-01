#!/usr/bin/env python3
"""
Получает APR через Revert Finance API для заданных кошельков.
Проверяет залоговые позиции (NFT в Revert lending vault) и добавляет данные о долге.
"""

import json
import os
import sys
import time
import urllib.request
from Crypto.Hash import keccak

WALLETS = [
    '0x9c16bc8f1104e4d2f72267eb981fa12de7cc4a6f',
    '0x2534acb6365e902c986a7aAaB3e9761f92D97693',
    '0x9e309c439c118804d9c2cf5eac4dfc62cc6f95c2',
    '0xdd1fbdbbaaed09bcfdfb0b7a7d001ab5791c3511',
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'apr.json')
CHAIN_ID = 8453
API_BASE = 'https://api.revert.finance/v1'
RPC_BASE = 'https://base.drpc.org'
PM_BASE  = '0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1'


def sel4(sig):
    h = keccak.new(digest_bits=256)
    h.update(sig.encode())
    return '0x' + h.hexdigest()[:8]


def eth_call(to, data):
    body = json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call',
        'params': [{'to': to, 'data': data}, 'latest'],
    }).encode()
    req = urllib.request.Request(
        RPC_BASE, data=body,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())
    if res.get('error'):
        return ''
    return res.get('result', '') or ''


def get_owner(nft_id):
    result = eth_call(PM_BASE, sel4('ownerOf(uint256)') + hex(nft_id)[2:].zfill(64))
    if not result or len(result) < 42:
        return None
    return '0x' + result[-40:]


def get_loan_debt_usdc(vault, nft_id):
    shares_hex = eth_call(vault, sel4('loans(uint256)') + hex(nft_id)[2:].zfill(64))
    if not shares_hex or int(shares_hex, 16) == 0:
        return 0.0
    shares = int(shares_hex, 16)
    debt_hex = eth_call(vault, sel4('convertToAssets(uint256)') + hex(shares)[2:].zfill(64))
    if debt_hex and int(debt_hex, 16) > 0:
        return round(int(debt_hex, 16) / 1e6, 2)
    return round(shares / 1e6, 2)


def fetch_wallet(addr):
    url = f'{API_BASE}/positions?account={addr}&chainId={CHAIN_ID}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f'[{addr}] error: {e}', file=sys.stderr)
        return {}, []

    if not data.get('success'):
        return {}, []

    positions = {}
    collateral_nfts = []

    for pos in data.get('data', []):
        nft_id = str(pos['nft_id'])
        perf = pos.get('performance', {}).get('hodl', {})

        entry = {
            'chain':    pos.get('network', 'base'),
            'exchange': pos.get('exchange', 'uniswapv3'),
        }
        if perf.get('apr') is not None:
            entry['net_roi'] = round(float(perf['apr']), 2)
        if perf.get('fee_apr') is not None:
            entry['fee_apr'] = round(float(perf['fee_apr']), 2)

        # Collateral check only for Base chain (our RPC)
        if pos.get('network') == 'base':
            try:
                owner = get_owner(int(nft_id))
                if owner and owner.lower() != addr.lower():
                    vault = owner
                    debt = get_loan_debt_usdc(vault, int(nft_id))
                    entry['collateral'] = True
                    entry['debt_usdc']  = debt
                    entry['vault']      = vault
                    collateral_nfts.append(int(nft_id))
                    print(f'  [collateral] nft={nft_id} vault={vault[:10]}... debt=${debt}', file=sys.stderr)
            except Exception as e:
                print(f'  [collateral check error] nft={nft_id}: {e}', file=sys.stderr)

        if entry.get('net_roi') is not None or entry.get('fee_apr') is not None or entry.get('collateral'):
            positions[nft_id] = entry

    print(f'[{addr}] {len(positions)} positions ({len(collateral_nfts)} collateral)', file=sys.stderr)
    return positions, collateral_nfts


def main():
    all_positions = {}
    wallet_collateral = {}

    for addr in WALLETS:
        positions, collateral_ids = fetch_wallet(addr)
        all_positions.update(positions)
        if collateral_ids:
            wallet_collateral[addr.lower()] = collateral_ids

    payload = {
        'updated_at': int(time.time()),
        'positions': all_positions,
        'wallet_collateral': wallet_collateral,
    }
    tmp = OUT_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, OUT_PATH)
    total_coll = sum(len(v) for v in wallet_collateral.values())
    print(f'saved {OUT_PATH}: {len(all_positions)} positions, {total_coll} collateral')


if __name__ == '__main__':
    main()
