import urllib.request
import json
import sys

try:
    url = 'http://127.0.0.1:8787/gatewayer'
    data = json.dumps({'event_type': 'OPTION_A', 'message': 'User selected Option A - Telegram notification'}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    response = urllib.request.urlopen(req, timeout=10)
    print('HTTP POST sent to Gatewayer for Option A')
    print(f'Response: {response.read().decode()}')
    sys.exit(0)
except Exception as e:
    print(f'Error sending to Gatewayer: {e}')
    sys.exit(1)
