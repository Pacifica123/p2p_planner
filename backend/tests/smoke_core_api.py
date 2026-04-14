import json
import os
import sys
import urllib.error
import urllib.request
import http.cookiejar

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:18080/api/v1').rstrip('/')
TIMEOUT = float(os.environ.get('TIMEOUT', '10'))
SMOKE_USER_EMAIL = os.environ.get('SMOKE_USER_EMAIL', 'smoke-user@local.test')
SMOKE_USER_PASSWORD = os.environ.get('SMOKE_USER_PASSWORD', 'SmokePass123!')
SMOKE_USER_DISPLAY_NAME = os.environ.get('SMOKE_USER_DISPLAY_NAME', 'Smoke Test User')

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
ACCESS_TOKEN = None


def parse_payload(raw: str):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def request(method: str, path: str, body=None, expected_status: int = 200, include_auth: bool = True):
    global ACCESS_TOKEN
    url = f"{BASE_URL}{path}"
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if include_auth and ACCESS_TOKEN:
        req.add_header('Authorization', f'Bearer {ACCESS_TOKEN}')

    status = None
    payload = None
    try:
        with OPENER.open(req, timeout=TIMEOUT) as resp:
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


def ensure_smoke_session():
    global ACCESS_TOKEN
    sign_up_payload = {
        'email': SMOKE_USER_EMAIL,
        'password': SMOKE_USER_PASSWORD,
        'displayName': SMOKE_USER_DISPLAY_NAME,
    }
    status, payload = request('POST', '/auth/sign-up', sign_up_payload, expected_status=201, include_auth=False)
    data = api_data(payload)
    if status == 201:
        ACCESS_TOKEN = data['accessToken']
        return data


def ensure_smoke_session_fallback_sign_in():
    global ACCESS_TOKEN
    _, payload = request('POST', '/auth/sign-in', {
        'email': SMOKE_USER_EMAIL,
        'password': SMOKE_USER_PASSWORD,
    }, expected_status=200, include_auth=False)
    data = api_data(payload)
    ACCESS_TOKEN = data['accessToken']
    return data


def ensure_authenticated_user():
    try:
        return ensure_smoke_session()
    except RuntimeError:
        return ensure_smoke_session_fallback_sign_in()


def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"SMOKE_USER_EMAIL={SMOKE_USER_EMAIL}")

    created = {
        'workspace_id': None,
        'board_id': None,
        'column_id': None,
        'card_id': None,
    }

    try:
        request('GET', '/health', include_auth=False)
        ensure_authenticated_user()
        _, session_payload = request('GET', '/auth/session')
        session_data = api_data(session_payload)
        assert_true(session_data['authenticated'], 'session authenticated')
        assert_equal(session_data['user']['email'], SMOKE_USER_EMAIL.lower(), 'session user email')

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

        _, me_payload = request('GET', '/me')
        me = api_data(me_payload)
        assert_equal(me['email'], SMOKE_USER_EMAIL.lower(), 'me email')

        _, devices_payload = request('GET', '/me/devices')
        devices = api_data(devices_payload)
        assert_true(len(devices) >= 1, 'at least one device registered')

        _, sign_out_all_payload = request('POST', '/auth/sign-out-all')
        sign_out_all_data = api_data(sign_out_all_payload)
        assert_true(sign_out_all_data['signedOut'], 'sign out all result')
        ACCESS_TOKEN = None

        _, unauthorized_workspaces = request('GET', '/workspaces', expected_status=401, include_auth=False)
        assert_error(unauthorized_workspaces, 'unauthorized', 'Authentication is required', 'anonymous workspaces blocked')

        ensure_smoke_session_fallback_sign_in()
        request('GET', '/workspaces')

        print('[DONE] smoke_core_api.py finished successfully')
    except Exception as e:
        print(f"\n[SMOKE FAILED] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
