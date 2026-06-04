from supabase_client import get_liq_stats
import json

try:
    stats = get_liq_stats()
    print(json.dumps(stats, ensure_ascii=False))
except Exception as e:
    print('ERROR:', type(e).__name__, str(e))
