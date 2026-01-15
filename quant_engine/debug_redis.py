import redis
import json
import time

try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    print("-" * 50)
    print("REDIS DEBUG CHECK")
    print("-" * 50)
    
    # 1. Check Gem Proposals
    proposals_json = r.get("gem:proposals")
    if proposals_json:
        proposals = json.loads(proposals_json)
        print(f"✅ gem:proposals found with {len(proposals)} items")
        if proposals:
            sample = proposals[0]
            print(f"Sample 'div_1h': {sample.get('div_1h')}")
            print(f"Sample 'div_4h': {sample.get('div_4h')}")
            print(f"Sample 'div_1d': {sample.get('div_1d')}")
            print(f"Sample 'div_2d': {sample.get('div_2d')}")
    else:
        print("❌ gem:proposals key NOT found or empty")

    # 2. Check Truth Ticks Inspect Keys
    inspect_keys = r.keys("truth_ticks:inspect:*")
    print(f"\n✅ Found {len(inspect_keys)} truth_ticks:inspect:* keys")
    if inspect_keys:
        sample_key = inspect_keys[0]
        data = json.loads(r.get(sample_key))
        print(f"Sample {sample_key}: {list(data.get('data', {}).keys())}")
        if 'temporal_analysis' in data.get('data', {}):
            print(f"✅ Temporal Analysis present in inspect data: {list(data['data']['temporal_analysis'].keys())}")
        else:
            print(f"❌ Temporal Analysis MISSING in inspect data")

    # 3. Check Job Results
    result_keys = r.keys("truth_ticks:job_result:*") # Correct prefix based on routes file
    # Actually route uses 'truth_ticks:' prefix for results?
    # File says: JOB_RESULT_PREFIX = "truth_ticks:"
    # But job_id makes it unique.
    # Worker says: result_key = f"{JOB_RESULT_PREFIX}{result['job_id']}"
    
    # Let's search for "truth_ticks:*" and filter
    all_truth_keys = r.keys("truth_ticks:*")
    job_results = [k for k in all_truth_keys if 'inspect' not in k and 'path_dataset' not in k and len(k.split(':')) == 2] # rough heuristic for UUIDs
    
    print(f"\nFound {len(job_results)} potential job result keys")
    for k in job_results[:5]:
        val = r.get(k)
        if "data" in val:
            print(f"Job Result {k}: Success/Data present")
        else:
            print(f"Job Result {k}: No data")

    # 4. Deep Inspect 'truth_ticks:None'
    none_key = "truth_ticks:None"
    if r.exists(none_key):
        print(f"\n✅ Found '{none_key}'")
        val = r.get(none_key)
        data = json.loads(val)
        print(f"Items in data: {len(data.get('data', {}))}")
        print(f"Job ID in payload: {data.get('job_id')}")
        if data.get('data'):
            first_sym = list(data['data'].keys())[0]
            print(f"Sample symbol: {first_sym}")
            print(f"Sample metrics keys: {list(data['data'][first_sym].keys())}")
    else:
        print(f"\n❌ '{none_key}' NOT found")

except Exception as e:
    print(f"Error: {e}")
