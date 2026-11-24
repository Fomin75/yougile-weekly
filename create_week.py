"""Создание еженедельной доски YouGile (суббота 06:00 МСК)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

BASE = 'https://yougile.com/api-v2'
KEY = os.environ['YOUGILE_API_KEY'].strip()
if not KEY or '\n' in KEY or '\r' in KEY:
    raise ValueError('Проверьте YOUGILE_API_KEY в GitHub Secrets: ключ должен быть одной строкой.')
PROJECT = os.environ.get('YOUGILE_PROJECT_ID', '').strip()
PROJECT_TITLE = os.environ.get('YOUGILE_PROJECT_TITLE', 'Текущая работа элеватора')


def api(method, path, payload=None, params=None):
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method, headers={
        'Authorization': 'Bearer ' + KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode('utf-8', errors='replace')[:1200]
        raise RuntimeError(f'YouGile API: HTTP {exc.code}, {method} {path}: {details}') from None


def all_items(path, **filters):
    offset = 0
    while True:
        result = api('GET', path, params={'limit': 100, 'offset': offset, **filters})
        content = result.get('content', [])
        yield from content
        if not result.get('paging', {}).get('next'):
            break
        offset += 100


def get_project_id():
    if PROJECT:
        return PROJECT
    matches = [p for p in all_items('/projects') if p.get('title') == PROJECT_TITLE]
    if len(matches) != 1:
        raise RuntimeError(f'Проектов с названием {PROJECT_TITLE!r} найдено: {len(matches)}. Укажите YOUGILE_PROJECT_ID.')
    return matches[0]['id']


def target_monday():
    override = os.environ.get('YOUGILE_WEEK_START', '').strip()
    if override:
        monday = date.fromisoformat(override)
        if monday.weekday() != 0:
            raise ValueError('YOUGILE_WEEK_START должен быть понедельником в формате YYYY-MM-DD.')
        return monday
    today = datetime.now(ZoneInfo('Europe/Moscow')).date()
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def main():
    pid = get_project_id()
    monday = target_monday()
    friday = monday + timedelta(days=4)
    title = f'Неделя {monday.isocalendar().week} ({monday:%d.%m}–{friday:%d.%m.%Y})'
    print(f'Проект ID: {pid}; целевая доска: {title}', flush=True)
    boards = [b for b in all_items('/boards', projectId=pid) if b.get('title') == title]
    if len(boards) > 1:
        raise RuntimeError('Найдено несколько досок с таким названием; остановка во избежание дублирования.')
    if boards:
        board_id = boards[0]['id']
        print(f'Доска уже существует, ID: {board_id}', flush=True)
    else:
        # Новый UUID нужен, если ранее удалённая доска создавалась с прежним idempotencyKey.
        result = api('POST', '/boards', {
            'title': title, 'projectId': pid, 'idempotencyKey': str(uuid.uuid4()),
        })
        board_id = result['id']
        print(f'API вернул ID созданной доски: {board_id}', flush=True)
        # Проверка списка досок: не выдаём успешный результат, если доска не обнаружена.
        verified = any(b.get('id') == board_id for b in all_items('/boards', projectId=pid))
        if not verified:
            raise RuntimeError('API вернул ID, но доска не найдена в списке проекта. Проверьте ID проекта и YouGile.')

    names = ['Планы на неделю'] + [
        f'{day} {(monday + timedelta(days=i)):%d.%m}'
        for i, day in enumerate(['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница'])
    ]
    existing = {c['title'] for c in all_items('/columns', boardId=board_id)}
    # YouGile добавляет новую колонку слева: создаём в обратном порядке.
    for i in reversed(range(len(names))):
        name = names[i]
        if name in existing:
            continue
        api('POST', '/columns', {
            'title': name, 'boardId': board_id,
            'color': 8 if i == 0 else 7,
            'idempotencyKey': str(uuid.uuid4()),
        })
        print('Добавлена колонка:', name, flush=True)
    print('Готово. Доска:', title, 'ID:', board_id, flush=True)


if __name__ == '__main__':
    main()
