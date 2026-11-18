#!/usr/bin/env python3
"""
물때 앱용 자료 수집 (GitHub Actions에서 실행)

  python scripts/fetch.py tides   # 조석예보(고·저조): 어제~5일 뒤, 하루 1번
  python scripts/fetch.py obs     # 조위관측소 최신 관측(수온·기온·바람): 1시간마다

인증키는 저장소 Secret `KHOA_KEY` (공공데이터포털 일반 인증키, Encoding/Decoding 아무거나).
결과: data/tide/<관측소>.json, data/obs/<관측소>.json
앱은 키 없이 raw.githubusercontent.com 에서 이 파일만 읽음.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIDE_URL = 'https://apis.data.go.kr/1192136/tideFcstHghLw/GetTideFcstHghLwApiService'
OBS_URL = 'https://apis.data.go.kr/1192136/dtRecent/GetDTRecentApiService'

KEY = os.environ.get('KHOA_KEY', '').strip()
if '%' in KEY:
    KEY = urllib.parse.unquote(KEY)

STATIONS = json.load(open(os.path.join(ROOT, 'scripts', 'stations.json'), encoding='utf-8'))


def call(base, **params):
    """포털 호출 → items 리스트. 오류면 예외."""
    q = urllib.parse.urlencode(params)
    url = f'{base}?serviceKey={urllib.parse.quote(KEY, safe="")}&{q}'
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                text = r.read().decode('utf-8')
            break
        except urllib.error.HTTPError as e:
            text = e.read().decode('utf-8', 'replace')
            break
        except Exception as e:  # 네트워크 일시 오류는 재시도
            last = e
            time.sleep(2 + attempt * 3)
    else:
        raise RuntimeError(f'network: {last}')
    if text.lstrip().startswith('<'):
        import re
        code = re.search(r'<returnReasonCode>(\d+)', text) or re.search(r'<resultCode>(\d+)', text)
        msg = re.search(r'<returnAuthMsg>([^<]+)', text) or re.search(r'<resultMsg>([^<]+)', text)
        c = code.group(1) if code else '?'
        if c.lstrip('0') in ('', '3') and 'NODATA' in text.upper():
            return []
        if c.lstrip('0') == '':
            return []
        raise RuntimeError(f'API {c} {msg.group(1) if msg else ""}')
    body = json.loads(text)
    resp = body.get('response', body)
    header = resp.get('header', {})
    cmm = body.get('OpenAPI_ServiceResponse', {}).get('cmmMsgHeader')
    if cmm:
        raise RuntimeError(f"API {cmm.get('returnReasonCode')} {cmm.get('returnAuthMsg')}")
    code = str(header.get('resultCode', '')).lstrip('0') or '0'
    if code == '3':
        return []
    if code != '0':
        raise RuntimeError(f"API {header.get('resultCode')} {header.get('resultMsg')}")
    items = (resp.get('body') or {}).get('items')
    if isinstance(items, dict):
        items = items.get('item')
    if not items:
        return []
    return items if isinstance(items, list) else [items]


def num(v):
    try:
        return None if v in (None, '') else float(v)
    except (TypeError, ValueError):
        return None


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def tides():
    today = datetime.now(KST).date()
    dates = [(today + timedelta(days=d)).strftime('%Y%m%d') for d in range(-1, 6)]
    fails = 0
    for st in STATIONS:
        events, name, err = [], st['name'], ''
        for d in dates:
            try:
                for it in call(TIDE_URL, obsCode=st['code'], reqDate=d, type='json', pageNo=1, numOfRows=20):
                    kind = int(num(it.get('extrSe')) or 0)
                    h = num(it.get('predcTdlvVl'))
                    if not it.get('predcDt') or kind not in (1, 2, 3, 4) or h is None:
                        continue
                    name = it.get('obsvtrNm') or name
                    events.append({'dt': str(it['predcDt'])[:16], 'h': h, 'high': kind in (1, 3)})
            except Exception as e:  # noqa: BLE001
                err = str(e)
        if not events and err:
            fails += 1
            print(f"{st['code']} {st['name']}: {err}", file=sys.stderr)
            continue  # 실패하면 기존 파일 유지
        events = list({e['dt']: e for e in events}.values())
        events.sort(key=lambda e: e['dt'])
        write(os.path.join(ROOT, 'data', 'tide', f"{st['code']}.json"),
              {'updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M'), 'name': name, 'events': events})
    print(f'tides done, {len(STATIONS) - fails}/{len(STATIONS)} ok')
    if fails == len(STATIONS):
        sys.exit(1)


def obs():
    today = datetime.now(KST).strftime('%Y%m%d')
    fails = 0
    for st in STATIONS:
        try:
            latest = None
            for it in call(OBS_URL, obsCode=st['code'], reqDate=today, min=10, type='json', pageNo=1, numOfRows=300):
                if latest is None or str(it.get('obsrvnDt')) > str(latest.get('obsrvnDt')):
                    latest = it
            data = {
                'updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
                'obs': None if latest is None else {
                    'at': str(latest.get('obsrvnDt')),
                    'wtem': num(latest.get('wtem')),
                    'artmp': num(latest.get('artmp')),
                    'wspd': num(latest.get('wspd')),
                    'tide': num(latest.get('bscTdlvHgt')),
                },
                'error': '' if latest else '오늘 관측값 없음',
            }
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"{st['code']} {st['name']}: {e}", file=sys.stderr)
            data = {'updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M'), 'obs': None, 'error': str(e)[:80]}
        write(os.path.join(ROOT, 'data', 'obs', f"{st['code']}.json"), data)
    print(f'obs done, {len(STATIONS) - fails}/{len(STATIONS)} ok')
    if fails == len(STATIONS):
        sys.exit(1)


if __name__ == '__main__':
    if not KEY:
        sys.exit('KHOA_KEY 가 없습니다 (저장소 Settings → Secrets → Actions 에 등록)')
    {'tides': tides, 'obs': obs}[sys.argv[1] if len(sys.argv) > 1 else 'tides']()
