import requests
B = 'http://localhost:8555/api'
errors = []
for name, url in [
    ("Dashboard", f"{B}/dashboard"),
    ("Dashboard Stats", f"{B}/dashboard/stats"),
    ("Resources Batch", f"{B}/resources/batch"),
    ("Farms", f"{B}/farms/"),
    ("Databases", f"{B}/databases/"),
    ("Templates", f"{B}/templates/"),
    ("Links", f"{B}/links/"),
    ("Proxies", f"{B}/proxies/"),
    ("Names", f"{B}/names/"),
    ("Campaigns", f"{B}/campaigns"),
    ("Settings", f"{B}/settings/"),
    ("Health", f"{B}/health"),
    ("Health Resources", f"{B}/health/resources"),
]:
    try:
        r = requests.get(url, timeout=10)
        tag = "OK" if r.status_code == 200 else f"FAIL {r.status_code}"
        print(f"  {tag:8s} {name}")
        if r.status_code != 200:
            errors.append(name)
    except Exception as e:
        print(f"  FAIL     {name}: {e}")
        errors.append(name)
print(f"\n{'ALL OK!' if not errors else f'{len(errors)} ERRORS: ' + ', '.join(errors)}")
