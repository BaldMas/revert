#!/usr/bin/env python3
"""LP1 monitor - sends Telegram alerts on range status changes for wallet 1."""

import json, os, sys, urllib.request

_TG_ENV    = '/home/masus/tg_bot.env'
TG_TOKEN   = next((l.split('=',1)[1].strip() for l in open(_TG_ENV) if l.startswith('TELEGRAM_TOKEN=')), '')
TG_CHAT_ID = open('/home/masus/tg_chat_id.txt').read().strip()

WALLET1    = '0x9c16bc8f1104e4d2f72267eb981fa12de7cc4a6f'
CHAIN_ID   = 8453
API_BASE   = 'https://api.revert.finance/v1'
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, 'lp1_state.json')


def http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_weth_price():
    try:
        d = http_get('https://api.coingecko.com/api/v3/simple/price?ids=weth&vs_currencies=usd')
        return d['weth']['usd']
    except Exception:
        return None


def send_tg(text):
    url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    body = json.dumps({
        'chat_id': TG_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
    }).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_positions():
    url = f'{API_BASE}/positions?account={WALLET1}&chainId={CHAIN_ID}'
    data = http_get(url)
    result = {}
    for pos in data.get('data', []):
        if pos.get('exited'):
            continue
        if pos.get('exchange') != 'uniswapv3' or pos.get('network') != 'base':
            continue
        nft_id = str(pos['nft_id'])
        tmap = {k.lower(): v for k, v in pos.get('tokens', {}).items()}
        t0 = pos.get('token0', '').lower()
        t1 = pos.get('token1', '').lower()
        result[nft_id] = {
            'in_range':       bool(pos.get('in_range')),
            'token0_symbol':  tmap.get(t0, {}).get('symbol', '?'),
            'token1_symbol':  tmap.get(t1, {}).get('symbol', '?'),
            'underlying_value': round(float(pos.get('underlying_value', 0)), 2),
        }
    return result


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return None  # None = first run, don't send "new position" noise


def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def main():
    try:
        current = fetch_positions()
    except Exception as e:
        print(f'[notify] fetch error: {e}', file=sys.stderr)
        return

    prev = load_state()

    if prev is None:
        save_state(current)
        print('[notify] first run - state saved, no notification sent')
        return

    changes = []

    for nft_id, pos in current.items():
        sym = f"{pos['token0_symbol']}/{pos['token1_symbol']}"
        val = pos['underlying_value']
        cur_range = pos['in_range']

        if nft_id not in prev:
            status = 'в диапазоне' if cur_range else 'вне диапазона'
            changes.append(f'NEW #{nft_id} {sym} - {status} (${val:,.0f})')
        elif prev[nft_id].get('in_range') != cur_range:
            if cur_range:
                changes.append(f'✅ #{nft_id} {sym} - вошел в диапазон (${val:,.0f})')
            else:
                changes.append(f'⛔ #{nft_id} {sym} - вышел из диапазона (${val:,.0f})')

    for nft_id, pos in prev.items():
        if nft_id not in current:
            sym = f"{pos.get('token0_symbol','?')}/{pos.get('token1_symbol','?')}"
            changes.append(f'CLOSED #{nft_id} {sym}')

    save_state(current)

    if not changes:
        return

    weth = get_weth_price()
    price_line = f'WETH: ${weth:,.2f}' if weth else 'WETH: н/д'

    text = '<b>LP1 - изменения</b>\n' + '\n'.join(changes) + '\n\n' + price_line
    try:
        res = send_tg(text)
        if res.get('ok'):
            print(f'[notify] sent {len(changes)} change(s)')
        else:
            print(f'[notify] TG error: {res}', file=sys.stderr)
    except Exception as e:
        print(f'[notify] send error: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()
