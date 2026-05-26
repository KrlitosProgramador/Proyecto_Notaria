from fastapi.testclient import TestClient
import traceback

from app import app

client = TestClient(app)

try:
    res = client.get('/api/liq/stats')
    print('STATUS', res.status_code)
    try:
        print(res.json())
    except Exception:
        print(res.text)
except Exception as e:
    print('EXCEPTION calling test client')
    traceback.print_exc()
