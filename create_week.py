import os, json, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = 'https://yougile.com/api-v2'
KEY = os.environ['YOUGILE_API_KEY'].strip()
if '\n' in KEY or '\r' in KEY:
    raise ValueError('YOUGILE_API_KEY содержит перенос строки. Исправьте GitHub Secret.')
PROJECT = os.environ.get('YOUGILE_PROJECT_ID', '').strip()
PROJECT_TITLE = os.environ.get('YOUGILE_PROJECT_TITLE', 'Текущая работа элеватора')

def api(method, path, payload=None, params=None):
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def all_items(path, **filters):
    offset = 0
    while True:
        result = api('GET', path, params={'limit': 100, 'offset': offset, **filters})
        yield from result.get('content', [])
        if not result.get('paging', {}).get('next'):
            break
        offset += 100

def project_id():
    if PROJECT:
        return PROJECT
    matches = [p for p in all_items('/projects') if p.get('title') == PROJECT_TITLE]
    if len(matches) != 1:
        raise RuntimeError(f'Найдено проектов с названием {PROJECT_TITLE!r}: {len(matches)}. Укажите YOUGILE_PROJECT_ID.')
    return matches[0]['id']

def main():
    pid = project_id()
    today = datetime.now(ZoneInfo('Europe/Moscow')).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    # On Saturday/Sunday choose next Monday; Monday-Friday manual runs choose coming Monday.
    if today.weekday() < 5:
        monday += timedelta(days=7 if today.weekday() == 0 else 0)
    friday = monday + timedelta(days=4)
    week = monday.isocalendar().week
    title = f'Неделя {week} ({monday:%d.%m}–{friday:%d.%m.%Y})'
    boards = [b for b in all_items('/boards', projectId=pid, title=title) if b.get('title') == title]
    if len(boards) > 1:
        raise RuntimeError('Обнаружены дубли доски: ' + title)
    if boards:
        board_id = boards[0]['id']
        print('Доска уже существует:', title)
    else:
        board_id = api('POST', '/boards', {'title': title, 'projectId': pid,
                      'idempotencyKey': f'weekly-{pid}-{monday.isoformat()}'})['id']
        print('Создана доска:', title)
    names = ['Планы на неделю'] + [f'{day} {(monday + timedelta(days=i)):%d.%m}' for i, day in enumerate(
        ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница'])]
    existing = {c['title'] for c in all_items('/columns', boardId=board_id)}
    for i in reversed(range(len(names))):
        name = names[i]
        if name in existing:
            continue
        api('POST', '/columns', {'title': name, 'boardId': board_id,
            'color': 8 if i == 0 else 7,
            'idempotencyKey': f'weekly-column-{board_id}-{i}'})
        print('Создана колонка:', name)
    print('Готово.')

if __name__ == '__main__':
    main()
