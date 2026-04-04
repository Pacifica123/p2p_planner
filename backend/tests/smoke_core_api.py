import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:18080/api/v1').rstrip('/')
USER_ID = os.environ.get('USER_ID', '11111111-1111-7111-8111-111111111111')
TIMEOUT = float(os.environ.get('TIMEOUT', '10'))

HEADERS = {
    'Content-Type': 'application/json',
    'X-User-Id': USER_ID,
}


def parse_payload(raw: str):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def request(method: str, path: str, body=None, expected_status: int = 200, user_id: Optional[str] = None):
    url = f"{BASE_URL}{path}"
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')

    req = urllib.request.Request(url, data=data, method=method)
    for k, v in HEADERS.items():
        if k.lower() == 'x-user-id' and user_id is not None:
            req.add_header(k, user_id)
        else:
            req.add_header(k, v)

    status = None
    payload = None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            payload = parse_payload(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        status = e.code
        payload = parse_payload(e.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"[FAIL] {method} {path} -> {e}")
        raise

    if status != expected_status:
        print(f"[FAIL] {method} {path} -> expected {expected_status}, got {status}\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
        raise RuntimeError(f"Unexpected status for {method} {path}: expected {expected_status}, got {status}")

    suffix = "" if status < 400 else " (expected error)"
    print(f"[OK] {method} {path} -> {status}{suffix}")
    return status, payload


def api_data(payload):
    if isinstance(payload, dict) and 'data' in payload:
        return payload['data']
    return payload


def data_id(payload):
    data = api_data(payload)
    if isinstance(data, dict) and 'id' in data:
        return data['id']
    raise RuntimeError(f'Could not extract id from payload: {payload}')


def assert_equal(actual, expected, label: str):
    if actual != expected:
        raise RuntimeError(f"Assertion failed for {label}: expected {expected!r}, got {actual!r}")
    print(f"[ASSERT] {label} == {expected!r}")


def assert_true(value, label: str):
    if value is not True:
        raise RuntimeError(f"Assertion failed for {label}: expected True, got {value!r}")
    print(f"[ASSERT] {label} is True")


def assert_false(value, label: str):
    if value is not False:
        raise RuntimeError(f"Assertion failed for {label}: expected False, got {value!r}")
    print(f"[ASSERT] {label} is False")


def assert_error(payload, code: str, message_substring: str, label: str):
    error = payload.get('error') if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        raise RuntimeError(f"Assertion failed for {label}: expected error payload, got {payload!r}")
    assert_equal(error.get('code'), code, f"{label}.code")
    message = error.get('message', '')
    if message_substring not in message:
        raise RuntimeError(
            f"Assertion failed for {label}.message: expected substring {message_substring!r}, got {message!r}"
        )
    print(f"[ASSERT] {label}.message contains {message_substring!r}")


def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"USER_ID={USER_ID}")

    created = {
        'workspace_id': None,
        'board_id': None,
        'column_id': None,
        'card_id': None,
    }

    try:
        request('GET', '/health')

        _, ws = request('POST', '/workspaces', {
            'name': 'Smoke Workspace',
            'visibility': 'private',
        }, expected_status=201)
        created['workspace_id'] = data_id(ws)

        request('GET', '/workspaces')

        _, board = request('POST', f"/workspaces/{created['workspace_id']}/boards", {
            'name': 'Smoke Board',
            'boardType': 'kanban',
        }, expected_status=201)
        created['board_id'] = data_id(board)

        _, column = request('POST', f"/boards/{created['board_id']}/columns", {
            'name': 'Todo',
        }, expected_status=201)
        created['column_id'] = data_id(column)

        request('GET', f"/boards/{created['board_id']}/columns")

        _, card = request('POST', f"/boards/{created['board_id']}/cards", {
            'title': 'First smoke card',
            'columnId': created['column_id'],
        }, expected_status=201)
        created['card_id'] = data_id(card)

        request('GET', f"/cards/{created['card_id']}")

        request('PATCH', f"/cards/{created['card_id']}", {
            'title': 'Renamed smoke card',
            'priority': 'high',
        })

        request('POST', f"/cards/{created['card_id']}/move", {
            'targetColumnId': created['column_id'],
            'position': 2048.0,
        })

        request('POST', f"/cards/{created['card_id']}/archive")
        request('POST', f"/cards/{created['card_id']}/unarchive")
        request('GET', f"/boards/{created['board_id']}/cards")

        _, board_activity_payload = request('GET', f"/boards/{created['board_id']}/activity")
        board_activity = api_data(board_activity_payload)
        assert_true(len(board_activity['items']) >= 4, 'board activity has several entries')

        _, card_activity_payload = request('GET', f"/cards/{created['card_id']}/activity")
        card_activity = api_data(card_activity_payload)
        assert_true(len(card_activity['items']) >= 4, 'card activity has several entries')

        _, audit_payload = request('GET', f"/workspaces/{created['workspace_id']}/audit-log")
        audit_items = api_data(audit_payload)['items']
        assert_true(len(audit_items) >= 3, 'workspace audit has several entries')

        _, me_before_payload = request('GET', '/me/appearance')
        me_before = api_data(me_before_payload)
        assert_true(isinstance(me_before['isCustomized'], bool), 'me appearance before isCustomized is bool')
        assert_true(me_before['appTheme'] in ['system', 'light', 'dark'], 'me appearance before appTheme is supported')
        assert_true(me_before['density'] in ['comfortable', 'compact'], 'me appearance before density is supported')
        assert_true(isinstance(me_before['reduceMotion'], bool), 'me appearance before reduceMotion is bool')

        me_target_theme = 'dark' if me_before['appTheme'] != 'dark' else 'light'
        me_target_density = 'compact' if me_before['density'] != 'compact' else 'comfortable'
        me_target_reduce_motion = not me_before['reduceMotion']

        _, me_updated_payload = request('PUT', '/me/appearance', {
            'appTheme': me_target_theme,
            'density': me_target_density,
            'reduceMotion': me_target_reduce_motion,
        })
        me_updated = api_data(me_updated_payload)
        assert_true(me_updated['isCustomized'], 'me appearance updated isCustomized')
        assert_equal(me_updated['appTheme'], me_target_theme, 'me appearance updated appTheme')
        assert_equal(me_updated['density'], me_target_density, 'me appearance updated density')
        assert_equal(me_updated['reduceMotion'], me_target_reduce_motion, 'me appearance updated reduceMotion')

        _, me_reloaded_payload = request('GET', '/me/appearance')
        me_reloaded = api_data(me_reloaded_payload)
        assert_true(me_reloaded['isCustomized'], 'me appearance reloaded isCustomized')
        assert_equal(me_reloaded['appTheme'], me_target_theme, 'me appearance reloaded appTheme')
        assert_equal(me_reloaded['density'], me_target_density, 'me appearance reloaded density')
        assert_equal(me_reloaded['reduceMotion'], me_target_reduce_motion, 'me appearance reloaded reduceMotion')

        _, board_default_payload = request('GET', f"/boards/{created['board_id']}/appearance")
        board_default = api_data(board_default_payload)
        assert_false(board_default['isCustomized'], 'board appearance default isCustomized')
        assert_equal(board_default['themePreset'], 'system', 'board appearance default themePreset')
        assert_equal(board_default['wallpaper']['kind'], 'none', 'board appearance default wallpaper.kind')
        assert_equal(board_default['wallpaper']['value'], None, 'board appearance default wallpaper.value')
        assert_equal(board_default['columnDensity'], 'comfortable', 'board appearance default columnDensity')
        assert_equal(board_default['cardPreviewMode'], 'expanded', 'board appearance default cardPreviewMode')
        assert_true(board_default['showCardDescription'], 'board appearance default showCardDescription')
        assert_true(board_default['showCardDates'], 'board appearance default showCardDates')
        assert_true(board_default['showChecklistProgress'], 'board appearance default showChecklistProgress')
        assert_equal(board_default['customProperties'], {}, 'board appearance default customProperties')

        _, board_updated_payload = request('PUT', f"/boards/{created['board_id']}/appearance", {
            'themePreset': 'midnight-blue',
            'wallpaper': {
                'kind': 'gradient',
                'value': 'sunset-mesh',
            },
            'columnDensity': 'compact',
            'cardPreviewMode': 'compact',
            'showCardDescription': False,
            'showCardDates': False,
            'showChecklistProgress': False,
            'customProperties': {
                'accentColor': 'violet',
                'columnHeaderStyle': 'glass',
            },
        })
        board_updated = api_data(board_updated_payload)
        assert_true(board_updated['isCustomized'], 'board appearance updated isCustomized')
        assert_equal(board_updated['themePreset'], 'midnight-blue', 'board appearance updated themePreset')
        assert_equal(board_updated['wallpaper']['kind'], 'gradient', 'board appearance updated wallpaper.kind')
        assert_equal(board_updated['wallpaper']['value'], 'sunset-mesh', 'board appearance updated wallpaper.value')
        assert_equal(board_updated['columnDensity'], 'compact', 'board appearance updated columnDensity')
        assert_equal(board_updated['cardPreviewMode'], 'compact', 'board appearance updated cardPreviewMode')
        assert_false(board_updated['showCardDescription'], 'board appearance updated showCardDescription')
        assert_false(board_updated['showCardDates'], 'board appearance updated showCardDates')
        assert_false(board_updated['showChecklistProgress'], 'board appearance updated showChecklistProgress')
        assert_equal(
            board_updated['customProperties'],
            {'accentColor': 'violet', 'columnHeaderStyle': 'glass'},
            'board appearance updated customProperties',
        )

        _, board_partial_payload = request('PUT', f"/boards/{created['board_id']}/appearance", {
            'cardPreviewMode': 'expanded',
            'showCardDates': True,
        })
        board_partial = api_data(board_partial_payload)
        assert_equal(board_partial['themePreset'], 'midnight-blue', 'board appearance partial keeps themePreset')
        assert_equal(board_partial['wallpaper']['kind'], 'gradient', 'board appearance partial keeps wallpaper.kind')
        assert_equal(board_partial['wallpaper']['value'], 'sunset-mesh', 'board appearance partial keeps wallpaper.value')
        assert_equal(board_partial['columnDensity'], 'compact', 'board appearance partial keeps columnDensity')
        assert_equal(board_partial['cardPreviewMode'], 'expanded', 'board appearance partial updates cardPreviewMode')
        assert_false(board_partial['showCardDescription'], 'board appearance partial keeps showCardDescription')
        assert_true(board_partial['showCardDates'], 'board appearance partial updates showCardDates')
        assert_false(board_partial['showChecklistProgress'], 'board appearance partial keeps showChecklistProgress')
        assert_equal(
            board_partial['customProperties'],
            {'accentColor': 'violet', 'columnHeaderStyle': 'glass'},
            'board appearance partial keeps customProperties',
        )

        _, invalid_theme_payload = request('PUT', '/me/appearance', {
            'appTheme': 'neon',
        }, expected_status=400)
        assert_error(invalid_theme_payload, 'bad_request', 'appTheme has unsupported value', 'invalid app theme')

        _, invalid_density_payload = request('PUT', f"/boards/{created['board_id']}/appearance", {
            'columnDensity': 'ultra',
        }, expected_status=400)
        assert_error(
            invalid_density_payload,
            'bad_request',
            'columnDensity has unsupported value',
            'invalid board column density',
        )

        _, missing_wallpaper_value_payload = request('PUT', f"/boards/{created['board_id']}/appearance", {
            'wallpaper': {
                'kind': 'gradient',
            },
        }, expected_status=400)
        assert_error(
            missing_wallpaper_value_payload,
            'bad_request',
            'wallpaper.value is required for non-none wallpapers',
            'missing wallpaper value',
        )

        _, invalid_custom_properties_payload = request('PUT', f"/boards/{created['board_id']}/appearance", {
            'customProperties': ['not', 'an', 'object'],
        }, expected_status=400)
        assert_error(
            invalid_custom_properties_payload,
            'bad_request',
            'customProperties must be a JSON object',
            'invalid customProperties',
        )

        print('\nSmoke flow completed successfully.')
        return 0
    finally:
        # cleanup in reverse order; ignore cleanup errors so we can still inspect the original failure above
        for path in [
            f"/cards/{created['card_id']}" if created['card_id'] else None,
            f"/columns/{created['column_id']}" if created['column_id'] else None,
            f"/boards/{created['board_id']}" if created['board_id'] else None,
            f"/workspaces/{created['workspace_id']}" if created['workspace_id'] else None,
        ]:
            if not path:
                continue
            try:
                request('DELETE', path)
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
