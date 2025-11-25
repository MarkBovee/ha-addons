#!/usr/bin/env python3
import argparse
import os
import re
import sys
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent.resolve()


def find_addons():
    addons = []
    for child in ROOT.iterdir():
        if not child.is_dir():
            continue
        cfg = child / "config.yaml"
        if cfg.exists():
            slug = None
            name = None
            try:
                text = cfg.read_text(encoding="utf-8")
                m_slug = re.search(r"^\s*slug\s*:\s*(\S+)", text, re.MULTILINE)
                m_name = re.search(r"^\s*name\s*:\s*(.+)$", text, re.MULTILINE)
                if m_slug:
                    slug = m_slug.group(1).strip()
                if m_name:
                    name = m_name.group(1).strip()
            except Exception:
                pass
            addons.append({
                "path": child,
                "slug": slug or child.name,
                "name": name or child.name,
                "has_run_local": (child / "run_local.py").exists(),
                "has_main": (child / "app" / "main.py").exists(),
            })
    return addons


def load_env_file(env_path: Path):
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip()
    return env


def apply_env(env: dict):
    for k, v in env.items():
        os.environ[k] = v
    # Token normalization
    sup = os.environ.get("SUPERVISOR_TOKEN")
    ha = os.environ.get("HA_API_TOKEN")
    if sup and not ha:
        os.environ["HA_API_TOKEN"] = sup
    if ha and not sup:
        os.environ["SUPERVISOR_TOKEN"] = ha


REQUIRED_ENV = {
    "charge-amps-monitor": ["CHARGER_EMAIL", "CHARGER_PASSWORD", "SUPERVISOR_TOKEN", "HA_API_TOKEN"],
    # Extend as new add-ons are added
}


def validate_env(slug: str):
    reqs = REQUIRED_ENV.get(slug, [])
    missing = [k for k in reqs if not os.environ.get(k)]
    return missing


def run_addon(addon):
    # Prefer run_local.py; fallback to app/main.py
    cwd = addon["path"]
    if addon["has_run_local"]:
        cmd = [sys.executable, str(cwd / "run_local.py")]
    elif addon["has_main"]:
        # Ensure PYTHONPATH includes addon for `app` imports
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [sys.executable, str(cwd / "app" / "main.py")]
        return subprocess.call(cmd, cwd=str(cwd), env=env)
    else:
        print(f"No runnable script found in {cwd}")
        return 1
    return subprocess.call(cmd, cwd=str(cwd))


def mask(val: str, keep: int = 4):
    if not val:
        return ""
    if len(val) <= keep:
        return "*" * len(val)
    return val[:keep] + "*" * (len(val) - keep)


def main():
    parser = argparse.ArgumentParser(description="Universal add-on runner")
    parser.add_argument("--addon", help="Add-on slug or directory name")
    parser.add_argument("--env", help="Path to .env file to load")
    parser.add_argument("--list", action="store_true", help="List discovered add-ons")
    parser.add_argument("--init-env", action="store_true", help="If set, create a local .env from .env.example for the selected add-on and exit")
    parser.add_argument("--dry-run", action="store_true", help="Show resolved configuration without running")
    parser.add_argument("--once", action="store_true", help="Run only one iteration then exit (sets RUN_ONCE=1 env var)")
    args = parser.parse_args()

    addons = find_addons()
    if args.list:
        for a in addons:
            print(f"- {a['slug']}: {a['name']} ({a['path']})")
        return 0

    if not args.addon:
        print("--addon is required (use --list to see options)")
        return 2

    target = None
    for a in addons:
        if a["slug"] == args.addon or a["path"].name == args.addon:
            target = a
            break
    if not target:
        print(f"Addon '{args.addon}' not found. Use --list to see available.")
        return 2

    # One-time env bootstrap: copy <addon>/.env.example to <addon>/.env if missing
    if args.init_env:
        example = target["path"] / ".env.example"
        dest = target["path"] / ".env"
        if not example.exists():
            print(f"No .env.example found for add-on '{target['slug']}' at {example}")
            return 4
        if dest.exists():
            print(f".env already exists for add-on '{target['slug']}' at {dest}. Not overwriting.")
            return 0
        dest.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created {dest} from {example}. Please edit it to add your secrets.")
        return 0

    # Env loading precedence and merge (kept intentionally simple):
    # 1. Root .env (shared settings like HA_API_URL / HA_API_TOKEN)
    # 2. Optional explicit --env file (overrides root for this run)
    # 3. <addon>/.env (per-addon local overrides)
    merged_env = {}

    # 1. Root .env if present
    root_shared = ROOT / ".env"
    if root_shared.exists():
        merged_env.update(load_env_file(root_shared))

    # 2. Explicit env file, if provided
    if args.env:
        merged_env.update(load_env_file(Path(args.env)))

    # 3. Per-addon .env
    addon_env = target["path"] / ".env"
    if addon_env.exists():
        merged_env.update(load_env_file(addon_env))

    apply_env(merged_env)

    missing = validate_env(target["slug"])
    print(f"Running add-on: {target['name']} ({target['slug']}) at {target['path']}")
    # Show selective env summary
    sup = os.environ.get("SUPERVISOR_TOKEN", "")
    ha = os.environ.get("HA_API_TOKEN", "")
    print(f"Tokens: SUPERVISOR_TOKEN={mask(sup)} HA_API_TOKEN={mask(ha)}")

    if missing:
        print("Missing required env vars:")
        for k in missing:
            print(f" - {k}")
        return 3

    if args.dry_run:
        print("Dry run: not executing script.")
        return 0

    # Set RUN_ONCE env var if --once flag is used
    if args.once:
        os.environ["RUN_ONCE"] = "1"
        print("Running in single-iteration mode (--once)")

    rc = run_addon(target)
    return rc


if __name__ == "__main__":
    sys.exit(main())
