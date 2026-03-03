---
description: Standard post-session workflow - version bump, git push, build EXE, deploy to app/
---

# Post-Session Deploy Workflow

// turbo-all

## Steps:

1. Bump PATCH version in `source/version.json`
```powershell
cd C:\Users\admin\Desktop\Leomail\source
python -c "import json; d=json.load(open('version.json')); v=d['version'].split('.'); v[-1]=str(int(v[-1])+1); d['version']='.'.join(v); d['build_date']=__import__('datetime').date.today().isoformat(); json.dump(d,open('version.json','w'))"
```

2. Stage all changes
```powershell
cd C:\Users\admin\Desktop\Leomail\source
git add -A
```

3. Commit with version tag
```powershell
cd C:\Users\admin\Desktop\Leomail\source
git commit -m "v$(python -c "import json; print(json.load(open('version.json'))['version'])"): session update"
```

4. Push to remote
```powershell
cd C:\Users\admin\Desktop\Leomail\source
git push
```

5. Build new EXE
```powershell
cd C:\Users\admin\Desktop\Leomail\source
cmd /c BUILD_EXE.bat
```

6. Deploy to app/ (preserving user_data/)
```powershell
$src = "C:\Users\admin\Desktop\Leomail\source\dist"
$dst = "C:\Users\admin\Desktop\Leomail\app"
# Copy EXE
Copy-Item "$src\Leomail.exe" "$dst\Leomail.exe" -Force
# Copy _internal (if exists)
if (Test-Path "$src\_internal") { Copy-Item "$src\_internal" "$dst\_internal" -Recurse -Force }
# Verify user_data is intact
if (Test-Path "$dst\user_data\leomail.db") { Write-Host "✅ Database intact" } else { Write-Host "❌ WARNING: Database missing!" }
```
