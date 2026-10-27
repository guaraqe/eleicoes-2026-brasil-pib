#!/usr/bin/env python3
"""GDP-weighted 2026 Brazilian presidential runoff; Python standard library only."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'data'
OUT = ROOT / 'results'
TSE = 'https://resultados.tse.jus.br/oficial/ele2026/6258'
GDP = 'https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2023?formato=json'


def fetch(url, headers=None):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=90) as r:
                return r.read(), r.headers, r.status
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def cached(name, url):
    path = CACHE / name
    if not path.exists():
        data = fetch(url)[0]
        json.loads(data)  # Validate before adding a response to the cache.
        temp = path.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_bytes(data)
        temp.replace(path)
        path.with_suffix(path.suffix + '.source.json').write_text(json.dumps({
            'url': url, 'retrieved_utc': datetime.now(timezone.utc).isoformat(),
            'sha256': hashlib.sha256(data).hexdigest(),
        }, indent=2) + '\n')
    return path.read_bytes()


def candidates(result):
    if result['ele'] != '6258' or result['t'] != '2' or result['and'] != 'f':
        raise ValueError('Expected completed 2026 second-round result')
    return {c['n']: c for cargo in result['carg'] if cargo['cd'] == '1'
            for group in cargo['agr'] for party in group['par'] for c in party['cand']}


def write_csv(name, rows):
    with (OUT / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Remove cached source files and download again')
    parser.add_argument('--workers', type=int, default=32, help='Concurrent downloads (default: 32)')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    CACHE.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    if args.refresh:
        for path in CACHE.iterdir():
            if path.is_file():
                path.unlink()
    gdp_data = json.loads(cached('gdp_2023.json', GDP))
    config = json.loads(cached('municipalities.json', f'{TSE}/config/mun-e006258-cm.json'))
    national = json.loads(cached('national.json', f'{TSE}/dados/br/br-c0001-e006258-u.json'))
    cand = candidates(national)
    if set(cand) != {'13', '22'}:
        raise ValueError(f'Unexpected runoff candidates: {cand.keys()}')
    domestic = [(uf['cd'], m) for uf in config['abr'] if uf['cd'] != 'zz' for m in uf['mu']]
    votes = {}
    foreign = defaultdict(int)
    zz = candidates(json.loads(cached('foreign.json', f'{TSE}/dados/zz/zz-c0001-e006258-u.json')))
    for c in cand:
        foreign[c] = int(zz[c]['vap'])
    # State files give a useful cross-check independent of the municipality sums.
    state_results = {}
    for uf in sorted({uf for uf, m in domestic}):
        state_results[uf.upper()] = candidates(json.loads(cached(f'state_{uf}.json', f'{TSE}/dados/{uf}/{uf}-c0001-e006258-u.json')))
    def load_municipality(item):
        uf, m = item
        data = json.loads(cached(f'municipality_{uf}_{m["cd"]}.json', f'{TSE}/dados/{uf}/{uf}{m["cd"]}-c0001-e006258-u.json'))
        cs = candidates(data)
        if set(cs) != set(cand):
            raise ValueError(f'Unexpected candidates in {m}')
        return m['cdi'], {c: int(cs[c]['vap']) for c in cand}
    print(f'Loading {len(domestic)} municipality results (cached after first run)...', flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (code, counts) in enumerate(pool.map(load_municipality, domestic), 1):
            if code in votes:
                raise ValueError(f'Duplicate municipality: {code}')
            votes[code] = counts
            if i % 250 == 0:
                print(f'  {i}/{len(domestic)}', flush=True)
    for c in cand:
        actual = sum(v[c] for v in votes.values()) + foreign[c]
        if actual != int(cand[c]['vap']):
            raise ValueError(f'{cand[c]["nmu"]}: municipal+foreign votes {actual} != official national {cand[c]["vap"]}')
    gdp = {}
    for r in gdp_data[1:]:
        if r['D3C'] != '2023' or r['D2C'] != '37' or r['MC'] != '40':
            raise ValueError('Unexpected GDP year, variable, or units')
        if r['D1C'] in gdp:
            raise ValueError('Duplicate GDP municipality')
        gdp[r['D1C']] = {'gdp_thousand_brl': float(r['V']), 'name': r['D1N']}
    # IBGE: https://educa.ibge.gov.br/criancas/voce-sabia/22741-novo-municipio.html
    # Boa Esperança do Norte (2025) came from Sorriso and Nova Ubiratã.
    # Pool all three voting areas against the two parents' 2023 GDP.
    boundary_group = ['5101837', '5106240', '5107925']
    combined_votes = {c: sum(votes[code][c] for code in boundary_group) for c in cand}
    combined_gdp = sum(gdp[code]['gdp_thousand_brl'] for code in boundary_group[1:])
    for code in boundary_group:
        votes.pop(code)
        gdp.pop(code, None)
    votes['5106240+5107925+5101837'] = combined_votes
    gdp['5106240+5107925+5101837'] = {
        'name': 'Nova Ubiratã + Sorriso + Boa Esperança do Norte - MT',
        'gdp_thousand_brl': combined_gdp,
    }
    missing_gdp = set(votes) - set(gdp)
    missing_votes = set(gdp) - set(votes)
    if missing_gdp or missing_votes:
        raise ValueError(f'Unmatched municipalities; GDP missing for {sorted(missing_gdp)}; votes missing for {sorted(missing_votes)}. Boundary reconciliation required; no rows silently dropped.')
    details = []
    states = {}
    capitals = {m['cdi'] for uf, m in domestic if m['c'] == 's'}
    for code, econ in sorted(gdp.items()):
        v = votes[code]
        valid = sum(v.values())
        if valid <= 0 or econ['gdp_thousand_brl'] <= 0:
            raise ValueError(f'Nonpositive votes/GDP for {code}')
        uf = econ['name'].rsplit(' - ', 1)[1]
        state = states.setdefault(uf, {'uf': uf, 'gdp_thousand_brl': 0, 'votes_13': 0, 'votes_22': 0})
        detail = {'ibge_code': code, 'municipality': econ['name'], 'uf': uf, **v,
                  'is_capital': code in capitals,
                  'gdp_thousand_brl': econ['gdp_thousand_brl']}
        for c in cand:
            detail[f'weighted_gdp_{c}'] = econ['gdp_thousand_brl'] * v[c] / valid
            state[f'votes_{c}'] += v[c]
        state['gdp_thousand_brl'] += econ['gdp_thousand_brl']
        details.append(detail)
    if len(states) != 27:
        raise ValueError(f'Expected 27 states/DF, got {len(states)}')
    for uf, state in states.items():
        for c in cand:
            if state[f'votes_{c}'] != int(state_results[uf][c]['vap']):
                raise ValueError(f'Municipal totals disagree with state result: {uf}, {c}')
    total_gdp = sum(r['gdp_thousand_brl'] for r in details)
    methods = {}
    for method in ['state_winner_takes_all', 'state_proportional', 'municipality_proportional']:
        allocation = dict.fromkeys(cand, 0.0)
        for r in details if method == 'municipality_proportional' else states.values():
            counts = {c: r[c] if method == 'municipality_proportional' else r[f'votes_{c}'] for c in cand}
            valid = sum(counts.values())
            for c in cand:
                share = counts[c] / valid
                if method == 'state_winner_takes_all':
                    winners = [k for k, count in counts.items() if count == max(counts.values())]
                    share = 1 / len(winners) if c in winners else 0
                allocation[c] += r['gdp_thousand_brl'] * share
        if abs(sum(allocation.values()) / total_gdp - 1) > 1e-10:
            raise ValueError('GDP allocation does not conserve total GDP')
        methods[method] = {cand[c]['nmu']: 100 * allocation[c] / total_gdp for c in cand}
    capital_breakdown = {}
    for label, is_capital in [('capitals', True), ('other_areas', False)]:
        subset = [r for r in details if r['is_capital'] == is_capital]
        subtotal = sum(r['gdp_thousand_brl'] for r in subset)
        capital_breakdown[label] = {
            'gdp_percent_of_brazil': 100 * subtotal / total_gdp,
            'gdp_weighted_vote_percent': {cand[c]['nmu']: 100 * sum(r[f'weighted_gdp_{c}'] for r in subset) / subtotal for c in cand},
        }
    summary = {'election_date': '2026-10-25', 'gdp_year': 2023,
               'electoral_municipalities': len(domestic), 'analysis_areas': len(details),
               'boundary_reconciliation': 'Boa Esperança do Norte, Nova Ubiratã and Sorriso pooled into one area',
               'states_including_df': len(states), 'total_gdp_brl': total_gdp * 1000,
               'official_national_valid_vote_percent': {v['nmu']: 100 * int(v['vap']) / sum(int(x['vap']) for x in cand.values()) for v in cand.values()},
               'foreign_votes_excluded_from_gdp_weighting': dict(foreign),
               'methods_percent': methods, 'capital_breakdown': capital_breakdown}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    write_csv('municipalities.csv', details)
    write_csv('states.csv', sorted(states.values(), key=lambda r: r['uf']))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
