#!/usr/bin/env python3
"""
Парсит fee APR со страниц revert.finance для заданных кошельков (base),
сохраняет в apr.json рядом со скриптом. Использует headless-chromium
(системный snap chromium через playwright).
"""

import asyncio
import json
import os
import re
import sys
import time

from playwright.async_api import async_playwright

WALLETS = [
    '0x9c16bc8f1104e4d2f72267eb981fa12de7cc4a6f',
    '0x2534acb6365e902c986a7aAaB3e9761f92D97693',
    '0x9e309c439c118804d9c2cf5eac4dfc62cc6f95c2',
    '0xdd1fbdbbaaed09bcfdfb0b7a7d001ab5791c3511',
]

CHROMIUM = '/snap/bin/chromium'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(BASE_DIR, 'apr.json')
WAIT_SEC = 30

JS_EXTRACT = """() => {
    const wraps = document.querySelectorAll('[id^="pos-title-"]');
    const out = [];
    wraps.forEach(w => {
        const m = w.id.match(/^pos-title-([^-]+)-([^-]+)-(\\d+)$/);
        if (!m) return;
        const [_, chain, exch, nft] = m;
        const inner = w.querySelector('.position-cont') || w;
        const t = inner.innerText || '';
        out.push({chain, exch, nft, text: t});
    });
    return out;
}"""


def parse_percents(text):
    # Формат карточки: pair \n fee_tier% \n v3 \n $value \n $pnl [\n arrow $pnl_24h \n 24h] \n net_roi% [\n arrow d% \n 24h] \n fee_apr% [\n arrow d% \n 24h] ...
    # Отрезаем всё до "\nv3\n" чтобы убрать fee tier пула.
    idx = text.find('\nv3\n')
    body = text[idx + 4:] if idx >= 0 else text
    percents = re.findall(r'(-?\d+\.\d+)%', body)
    if not percents:
        return None
    # без 24h: [net_roi, fee_apr] → len 2, fee_apr = [1]
    # с 24h:   [net_roi, d_net, fee_apr, d_fee] → len 4, fee_apr = [2]
    net_roi = float(percents[0])
    if len(percents) >= 4:
        fee_apr = float(percents[2])
    elif len(percents) >= 2:
        fee_apr = float(percents[1])
    else:
        fee_apr = None
    out = {'net_roi': net_roi}
    if fee_apr is not None:
        out['fee_apr'] = fee_apr
    return out


async def fetch_wallet(browser, addr):
    ctx = await browser.new_context(viewport={'width': 1600, 'height': 1400})
    page = await ctx.new_page()
    url = f'https://revert.finance/#/account/{addr}?filter-network=base'
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
    except Exception as e:
        print(f'[{addr}] goto err: {e}', file=sys.stderr)
    await asyncio.sleep(WAIT_SEC)
    try:
        items = await page.evaluate(JS_EXTRACT)
    except Exception as e:
        print(f'[{addr}] extract err: {e}', file=sys.stderr)
        items = []
    await ctx.close()
    result = {}
    for it in items:
        parsed = parse_percents(it['text'])
        if parsed is None:
            continue
        result[it['nft']] = {
            'chain': it['chain'],
            'exchange': it['exch'],
            **parsed,
        }
    print(f'[{addr}] {len(result)} positions', file=sys.stderr)
    return result


async def main():
    all_data = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM,
            args=['--no-sandbox'],
        )
        try:
            for addr in WALLETS:
                data = await fetch_wallet(browser, addr)
                all_data.update(data)
        finally:
            await browser.close()

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
    asyncio.run(main())
