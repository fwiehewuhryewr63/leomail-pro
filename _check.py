import py_compile, os
root = "backend"
for r, d, files in os.walk(root):
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(r, f)
            try:
                py_compile.compile(path, doraise=True)
                print(f"OK  {path}")
            except py_compile.PyCompileError as e:
                print(f"ERR {path}: {e}")
