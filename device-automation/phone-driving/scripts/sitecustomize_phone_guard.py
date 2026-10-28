# phone-guard-sitecustomize
"""sitecustomize loader for the phone install/IME/settings guard.

Installed as `sitecustomize.py` next to a Python's stdlib by scripts/install-guard.sh, together with
`_phone_guard.py` (a copy of phone/guard.py). Interpreter start only registers an import hook; the
guard patches adbutils and uiautomator2 the moment a script imports them, so raw uiautomator2 code
written by any agent is blocked from installs, IME changes, clipboard use and settings writes.

It then chains to any other sitecustomize that would have loaded, so it does not hide one.

If the guard cannot load it says so on stderr and lets Python continue: Python itself offers no way
for sitecustomize to refuse to start. Run `python -m _phone_guard selftest` to verify.
"""
import os
import sys


def _phone_guard_boot():
    here = os.path.dirname(os.path.abspath(__file__))
    allow = "/etc/phone-guard.allow"  # root-owned list of scripts exempt from the hook, one per line
    try:
        if sys.argv and sys.argv[0] not in ("", "-c", "-m", "-"):
            me = os.path.realpath(sys.argv[0])
            if os.path.exists(allow) and me in {
                    os.path.realpath(line.strip()) for line in open(allow)
                    if line.strip() and not line.startswith("#")}:
                return
    except OSError:
        pass
    try:
        if here not in sys.path:
            sys.path.insert(0, here)
        import _phone_guard
        _phone_guard.install(eager=False)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"phone guard failed to load: {type(exc).__name__}: {exc}\n")


def _chain():
    here = os.path.dirname(os.path.abspath(__file__))
    import importlib.machinery
    import importlib.util
    orig = os.path.join(here, "sitecustomize.py.phoneguard-orig")
    candidates = []
    if os.path.exists(orig):
        candidates.append(orig)
    spec = importlib.machinery.PathFinder.find_spec(
        "sitecustomize", [p for p in sys.path if os.path.abspath(p or ".") != here])
    if spec is not None and spec.origin and os.path.abspath(spec.origin) != os.path.abspath(__file__):
        candidates.append(spec.origin)
    for path in candidates:
        try:
            loader = importlib.machinery.SourceFileLoader("_phone_guard_chained_sitecustomize", path)
            mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
            loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"chained sitecustomize failed: {type(exc).__name__}: {exc}\n")


_phone_guard_boot()
_chain()
