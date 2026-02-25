"""Full integration test for Leomail v4 Campaign API."""
import requests
import json

API = 'http://127.0.0.1:8000/api'
CAMP = 'http://127.0.0.1:8000'  # campaigns router has /campaigns prefix directly
PASS = True

def test(name, fn):
    global PASS
    try:
        result = fn()
        print(f"  ✅ {name}")
        return result
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        PASS = False
        return None

print("=" * 50)
print("LEOMAIL v4 — FULL INTEGRATION TEST")
print("=" * 50)

# 1. Health
def t1():
    r = requests.get(f'{API}/health')
    d = r.json()
    assert d["status"] == "online"
    assert d["version"] == "4.0"
    return d
test("Health check (version=4.0)", t1)

# 2. Resource health
def t2():
    r = requests.get(f'{API}/health/resources')
    d = r.json()
    assert "overall" in d
    assert "sms" in d
    assert "proxies" in d
    return d
test("Resource health endpoint", t2)

# 3. Create campaign
cid = None
def t3():
    global cid
    r = requests.post(f'{API}/campaigns', json={
        'name': 'Test Brazil Nutra',
        'geo': 'BR',
        'niche': 'nutra',
        'name_pack': 'brazil_5k',
        'providers': ['yahoo', 'aol'],
        'birth_threads': 5,
        'send_threads': 10,
    })
    d = r.json()
    assert 'id' in d
    cid = d['id']
    return d
test("Create campaign", t3)

# 4. Import 3 templates
def t4():
    r = requests.post(f'{API}/campaigns/{cid}/templates/import', json={
        'content': '---TEMPLATE---\nSubject: Ola {first_name}\nBody:\n<p>Ola {first_name}, <a href="{link}">veja</a></p>\n---TEMPLATE---\nSubject: Oportunidade\nBody:\n<p>Vagas: <a href="{link}">acesse</a></p>\n---TEMPLATE---\nSubject: Nao perca {first_name}\nBody:\n<p>Hoje! <a href="{link}">clique</a></p>'
    })
    d = r.json()
    assert d['added'] == 3
    return d
test("Import 3 templates", t4)

# 5. Import 5 ESP links
def t5():
    r = requests.post(f'{API}/campaigns/{cid}/links/import', json={
        'content': 'https://esp.test/track/aB3x\nhttps://esp.test/track/cD4y\nhttps://esp.test/track/eF5z\nhttps://esp.test/track/gH6a\nhttps://esp.test/track/iJ7b',
        'max_uses': 50,
    })
    d = r.json()
    assert d['added'] == 5
    return d
test("Import 5 ESP links", t5)

# 6. Import 20 recipients
def t6():
    emails = '\n'.join([f'test{i}@example.com' for i in range(1, 21)])
    r = requests.post(f'{API}/campaigns/{cid}/recipients/import', json={'content': emails})
    d = r.json()
    assert d['added'] == 20
    return d
test("Import 20 recipients", t6)

# 7. Duplicate check (import same links again)
def t7():
    r = requests.post(f'{API}/campaigns/{cid}/links/import', json={
        'content': 'https://esp.test/track/aB3x\nhttps://esp.test/track/NEW1',
        'max_uses': 50,
    })
    d = r.json()
    assert d['added'] == 1  # only NEW1
    assert d['skipped'] == 1  # aB3x duplicate
    return d
test("Duplicate link detection", t7)

# 8. Pre-flight check
def t8():
    r = requests.get(f'{API}/campaigns/{cid}/preflight')
    d = r.json()
    assert d['templates']['count'] == 3
    assert d['links']['count'] == 6  # 5 + 1 new
    assert d['recipients']['count'] == 20
    assert 'ready' in d
    return d
test("Pre-flight check", t8)

# 9. Campaign details
def t9():
    r = requests.get(f'{API}/campaigns/{cid}')
    d = r.json()
    assert d['name'] == 'Test Brazil Nutra'
    assert d['geo'] == 'BR'
    assert d['recipients_total'] == 20
    assert len(d['templates']) == 3
    assert d['links_total'] == 6
    assert d['progress_pct'] == 0
    return d
test("Campaign details + stats", t9)

# 10. List campaigns
def t10():
    r = requests.get(f'{API}/campaigns')
    d = r.json()
    assert len(d) >= 1
    found = [c for c in d if c['id'] == cid]
    assert len(found) == 1
    return d
test("List all campaigns", t10)

# 11. Recipient stats
def t11():
    r = requests.get(f'{API}/campaigns/{cid}/recipients/stats')
    d = r.json()
    assert d['total'] == 20
    assert d['sent'] == 0
    assert d['remaining'] == 20
    return d
test("Recipient stats", t11)

# 12. List templates
def t12():
    r = requests.get(f'{API}/campaigns/{cid}/templates')
    d = r.json()
    assert len(d) == 3
    assert all(t['active'] for t in d)
    return d
test("List templates", t12)

# 13. List links
def t13():
    r = requests.get(f'{API}/campaigns/{cid}/links')
    d = r.json()
    assert d['total'] == 6
    assert d['active'] == 6
    return d
test("List ESP links", t13)

# 14. Update campaign
def t14():
    r = requests.put(f'{API}/campaigns/{cid}', json={'name': 'Updated Name', 'send_threads': 15})
    d = r.json()
    assert d['ok'] == True
    # Verify
    r2 = requests.get(f'{API}/campaigns/{cid}')
    d2 = r2.json()
    assert d2['name'] == 'Updated Name'
    assert d2['send_threads'] == 15
    return d
test("Update campaign settings", t14)

# 15. Dashboard stats
def t15():
    r = requests.get(f'{API}/dashboard/stats')
    d = r.json()
    assert 'total_accounts' in d
    assert 'mailing_stats' in d
    return d
test("Dashboard stats endpoint", t15)

# 16. Delete test campaign
def t16():
    r = requests.delete(f'{API}/campaigns/{cid}')
    d = r.json()
    assert d['ok'] == True
    # Verify deleted
    r2 = requests.get(f'{API}/campaigns/{cid}')
    assert r2.status_code == 404
    return d
test("Delete campaign + verify 404", t16)

print()
print("=" * 50)
if PASS:
    print("ALL 16 TESTS PASSED ✅")
else:
    print("SOME TESTS FAILED ❌")
print("=" * 50)
