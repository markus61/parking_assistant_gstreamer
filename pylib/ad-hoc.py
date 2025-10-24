#!/usr/bin/env python3

# this script takes two parmeters:
# 1. the name of a brand
# 2. path to json file
# the script will use the brand name to search for a matching config in /etc/api-proxy
# it will then use the json file to update redis

import sys
import json
#import redis
import configparser


if len(sys.argv) < 3:
    print("Usage: ad-hoc.py <brand> <json_file>")
    sys.exit(1)
BRAND = sys.argv[1].lower() or "edeka"
JSON_FILE = sys.argv[2]

config_file = f"/etc/api-proxy/{BRAND}-main-prod.ini"

try:
    config = configparser.ConfigParser()
    config.read(config_file)
    redis_url = config["own"]["redis_url"]
except Exception as e:
    print(f"Error reading config file: {e}")
    sys.exit(1)

print(f"using config file: {config_file}")
print(f"found redis_url: {redis_url}")

try:
    with open(JSON_FILE) as f:
        data = json.load(f)
except Exception as e:
    print(f"Error reading json file: {e}")
    sys.exit(1)

if "contentVersion" not in data.keys():
    print("Error: 'contentVersion' not found in json file")
    sys.exit(1)

try:
#    r = redis.StrictRedis().from_url(redis_url)
#    r.set(f"{BRAND}_adhoc", json.dumps(data))
    print(f"Updated redis with {BRAND}_adhoc")
except Exception as e:
    print(f"Error updating redis: {e}")
    sys.exit(1)
