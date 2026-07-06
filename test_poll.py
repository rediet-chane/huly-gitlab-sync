# test_poll.py
import asyncio
import json
from main import run_bridge

async def test_poll():
    ok, out = await run_bridge("--list-issues", timeout=60)
    print(f"Success: {ok}")
    print(f"Output length: {len(out)}")
    
    if ok:
        try:
            # Try to parse the JSON
            data = json.loads(out)
            print(f"Data keys: {data.keys()}")
            
            # Check if there's a 'result' key
            if 'result' in data:
                issues = data['result']
                print(f"Found {len(issues)} issues")
                for issue in issues[:3]:
                    print(f"  - {issue.get('identifier')}: {issue.get('title')}")
            else:
                print(f"Raw data: {out[:200]}")
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Raw output: {out[:200]}")
    else:
        print(f"Error: {out[:200]}")

asyncio.run(test_poll())