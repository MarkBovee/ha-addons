#!/usr/bin/env python3
"""Deploy custom_components/hems to the local Home Assistant server over SSH.

Steps: checks (core tests, engine copy in sync) -> back up the current copy on the server -> stream the
tracked files as a tar -> swap the directory -> verify every file by sha256 -> optional restart.

Authentication stays with the human or with a key: the script reads HA_HOST, HA_SSH_USER and the PATH of an SSH key
(HA_SSH_KEY) from .env, never a password. With a key and --batch nothing is typed or shown; without a key ssh asks
for the password once and the connection is shared for the remaining steps. Standard library only.

Usage:
  python3 hems/deploy.py --dry-run          # show what would happen, change nothing
  python3 hems/deploy.py                    # checks, deploy, verify
  python3 hems/deploy.py --restart          # ... and restart Home Assistant after a confirmation
Options: --host H --user U --key PATH (override .env), --batch (never prompt; needs a key or agent), --no-sudo, --skip-checks,
         --yes (no confirmation for --restart).
"""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import http.client
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = Path("custom_components") / "hems"
REMOTE_CONFIG = "/config"
KEEP_BACKUPS = 3


@dataclass(frozen=True)
class Target:
    host: str
    user: str
    config_dir: str = REMOTE_CONFIG
    key: str | None = None          # path to a private key; ssh reads it, this script never does
    sudo: bool = True               # run the install steps through `sudo -n` (the SSH user cannot write in /config; needs passwordless sudo)

    @property
    def remote_dir(self) -> str:
        """Where the integration lives on the server."""
        return f"{self.config_dir}/custom_components/hems"

    @property
    def backup_dir(self) -> str:
        """Where timestamped backups of the previous copy are kept (outside custom_components, so HA never loads them)."""
        return f"{self.config_dir}/.hems-backup"


def parse_env(text: str) -> dict[str, str]:
    """KEY=value pairs of a .env file; comments and blank lines are ignored, surrounding quotes are stripped."""
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("\"'")
    return env


def target_from_env(env: dict[str, str], host: str | None = None, user: str | None = None, key: str | None = None) -> Target:
    """Host, SSH user and key path from options or .env (HA_HOST, falling back to the host of HA_API_URL; HA_SSH_USER; HA_SSH_KEY).

    Raises SystemExit with a readable message when host or user is missing; a password is never read."""
    resolved_host = host or env.get("HA_HOST") or urlparse(env.get("HA_API_URL", "")).hostname
    resolved_user = user or env.get("HA_SSH_USER")
    if not resolved_host or not resolved_user:
        raise SystemExit("No SSH target: set HA_HOST and HA_SSH_USER in .env or pass --host and --user.")
    resolved_key = key or env.get("HA_SSH_KEY")
    return Target(_bare_host(resolved_host), resolved_user, key=str(Path(resolved_key).expanduser()) if resolved_key else None)


def _bare_host(value: str) -> str:
    """The host name of a value that may be a bare host or a URL like http://homeassistant.local:8123."""
    return urlparse(value).hostname or value if "//" in value else value


def relative_files(root: Path = ROOT) -> list[str]:
    """Files to deploy, relative to custom_components/hems: tracked and untracked-but-not-ignored, no caches."""
    out = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z", "--", str(INTEGRATION)], cwd=root,
                         capture_output=True, check=True).stdout.decode().split("\0")
    prefix = INTEGRATION.as_posix() + "/"
    return sorted(p[len(prefix):] for p in out if p.startswith(prefix) and "__pycache__" not in p)


BUILD_FILE = "BUILD"


def write_build_stamp(root: Path = ROOT) -> str:
    """Write the commit the deployed code comes from into custom_components/hems/BUILD and return it ('abc1234', '+dirty' when tracked files differ).

    The integration puts this in every decision record and event, so a log line says which code made it; without it a
    reviewer cannot tell a decision of an old version from one of the current version."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", str(INTEGRATION), "hems/core"], cwd=root,
                           capture_output=True, text=True, check=True).stdout.strip()
    stamp = head + ("+dirty" if dirty else "")
    (root / INTEGRATION / BUILD_FILE).write_text(stamp + "\n")
    return stamp


def local_digests(files: list[str], root: Path = ROOT) -> dict[str, str]:
    """sha256 per relative file of the local copy."""
    return {f: hashlib.sha256((root / INTEGRATION / f).read_bytes()).hexdigest() for f in files}


def parse_sha256sum(output: str) -> dict[str, str]:
    """{relative path: digest} from `sha256sum` output (paths may start with './')."""
    digests = {}
    for line in output.splitlines():
        if line.strip():
            digest, path = line.split(None, 1)
            digests[path.strip().removeprefix("./")] = digest
    return digests


def compare(local: dict[str, str], remote: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """(missing on the server, unexpected on the server, different content)."""
    missing = sorted(set(local) - set(remote))
    extra = sorted(set(remote) - set(local))
    different = sorted(f for f in set(local) & set(remote) if local[f] != remote[f])
    return missing, extra, different


def remote_install_script(target: Target, keep: int = KEEP_BACKUPS) -> str:
    """POSIX sh run on the server: back up the old copy, unpack stdin next to it, swap, prune old backups.

    The new copy is unpacked completely before the old one is replaced, so a broken transfer leaves the
    running integration untouched. Written for BusyBox (the SSH add-on), so no GNU-only flags."""
    d, b, parent = target.remote_dir, target.backup_dir, f"{target.config_dir}/custom_components"
    return " && ".join([
        f"mkdir -p '{b}' '{parent}'",
        f"if [ -d '{d}' ]; then tar -C '{parent}' -czf '{b}/hems-'$(date +%Y%m%d-%H%M%S)'.tar.gz' hems; fi",
        f"rm -rf '{parent}/.hems-new' && mkdir '{parent}/.hems-new'",
        f"tar -C '{parent}/.hems-new' -xf -",
        f"rm -rf '{d}' && mv '{parent}/.hems-new' '{d}'",
        f"ls -1t '{b}' | tail -n +{keep + 1} | while read f; do rm -f '{b}'/\"$f\"; done",
    ])


def privileged(script: str, sudo: bool) -> str:
    """The remote command for `script`: run by `sudo -n sh -c` when needed. stdin (the tar stream) passes straight through.

    `-n` makes sudo fail instead of asking for a password, so nothing here can prompt for one."""
    return f"sudo -n sh -c {shlex.quote(script)}" if sudo else script


def ssh_command(target: Target, control_path: str, *remote: str, master: bool = False, batch: bool = False) -> list[str]:
    """ssh invocation that shares one authenticated connection (ControlMaster): the first call may prompt.

    A key is passed by path only; `batch` forbids any prompt, so an unauthorised key fails instead of asking."""
    options = ["-o", f"ControlPath={control_path}", "-o", "ControlMaster=yes" if master else "ControlMaster=no"]
    if target.key:
        options += ["-i", target.key, "-o", "IdentitiesOnly=yes"]
    if batch:
        options += ["-o", "BatchMode=yes"]
    if master:
        options += ["-o", "ControlPersist=300"]
    return ["ssh", *options, f"{target.user}@{target.host}", *remote]


def run_checks(root: Path = ROOT) -> None:
    """Abort unless the core tests pass and the vendored engine matches hems/core."""
    sync = subprocess.run([sys.executable, str(root / "scripts" / "sync_hems_core.py"), "--check"], cwd=root)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=root / "hems" / "core")
    if sync.returncode or tests.returncode:
        raise SystemExit("Checks failed; nothing was deployed. Fix them (or use --skip-checks if you know why).")


def stream_tar(files: list[str], root: Path = ROOT) -> subprocess.Popen:
    """Start tar writing the files (paths relative to the integration folder) to its stdout."""
    # -C must come before -T; entries are root-owned so the server copy matches the other components regardless of local uids
    tar = subprocess.Popen(["tar", "-C", str(root / INTEGRATION), "--owner=0", "--group=0", "--numeric-owner", "--null", "-T", "-", "-cf", "-"],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    tar.stdin.write(("\0".join(files) + "\0").encode())
    tar.stdin.close()
    return tar


def deploy(target: Target, files: list[str], control_path: str, batch: bool = False) -> None:
    """Open the shared connection (a password prompt, if any, happens here), install, and verify by checksum."""
    ssh = lambda *remote, master=False: ssh_command(target, control_path, *remote, master=master, batch=batch)
    subprocess.run(ssh("true", master=True), check=True)
    try:
        tar = stream_tar(files)
        subprocess.run(ssh(privileged(remote_install_script(target), target.sudo)), stdin=tar.stdout, check=True)
        tar.stdout.close()
        if tar.wait():
            raise SystemExit("tar failed locally; verify the server copy before restarting anything.")
        listing = subprocess.run(ssh(f"cd '{target.remote_dir}' && find . -type f -exec sha256sum {{}} +"),
                                 capture_output=True, text=True, check=True).stdout
        missing, extra, different = compare(local_digests(files), parse_sha256sum(listing))
        if missing or extra or different:
            raise SystemExit(f"Verification failed. missing={missing} unexpected={extra} different={different}")
        print(f"Deployed and verified {len(files)} files in {target.remote_dir}")
    finally:
        subprocess.run(["ssh", "-O", "exit", "-o", f"ControlPath={control_path}", f"{target.user}@{target.host}"], capture_output=True)


def wait_for_home_assistant(base: str, token: str, timeout_s: int = 300, poll_s: int = 5) -> bool:
    """Poll the REST API until it answers 200 again after a restart (it first goes away, then comes back)."""
    request = urllib.request.Request(base + "/", headers={"Authorization": f"Bearer {token}"})
    time.sleep(poll_s)   # let the shutdown start so an answer from the old instance is not mistaken for the new one
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    return True
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(poll_s)
    return False


def restart_home_assistant(env: dict[str, str], assume_yes: bool) -> None:
    """Validate the HA configuration and restart Home Assistant over its REST API, after a confirmation.

    Uses the same HA_API_URL/HA_API_TOKEN as scripts/hems_collect.py; the token is never printed."""
    base, token = env.get("HA_API_URL", "").rstrip("/"), env.get("HA_API_TOKEN", "")
    if not base or not token:
        raise SystemExit("HA_API_URL and HA_API_TOKEN are needed for --restart.")
    if not assume_yes and input("Restart Home Assistant now? Automations are down for 1-5 minutes. [y/N] ").strip().lower() != "y":
        print("Not restarting. A new integration is only found after a restart.")
        return

    def call(path: str) -> dict:
        """POST to the HA API with the bearer token and return the JSON answer."""
        request = urllib.request.Request(base + path, data=b"{}", method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or "{}")

    check = call("/config/core/check_config")
    if check.get("result") != "valid":
        raise SystemExit(f"HA reports an invalid configuration, not restarting: {check.get('errors')}")
    try:
        call("/services/homeassistant/restart")
    except (TimeoutError, ConnectionError, http.client.HTTPException, urllib.error.URLError):
        pass   # HA drops the connection while it shuts down; that is the expected outcome
    print("Restart requested, waiting for Home Assistant...")
    print("Home Assistant is back." if wait_for_home_assistant(base, token) else "Home Assistant did not answer within 5 minutes; check it.")


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", help="override HA_HOST")
    parser.add_argument("--user", help="override HA_SSH_USER")
    parser.add_argument("--key", help="path to an SSH private key (override HA_SSH_KEY)")
    parser.add_argument("--no-sudo", action="store_true", help="do not use sudo on the server (the SSH user can write in /config itself)")
    parser.add_argument("--batch", action="store_true", help="never prompt (needs a key or agent); fails instead of asking for a password")
    parser.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    parser.add_argument("--skip-checks", action="store_true", help="do not run the core tests and the engine-sync check first")
    parser.add_argument("--restart", action="store_true", help="validate the HA config and restart Home Assistant after a confirmation")
    parser.add_argument("--yes", action="store_true", help="with --restart: do not ask for confirmation")
    args = parser.parse_args()
    env = parse_env((ROOT / ".env").read_text()) if (ROOT / ".env").exists() else {}
    target, files = target_from_env(env, args.host, args.user, args.key), relative_files()
    files = sorted({*files, BUILD_FILE}) if files else files
    target = replace(target, sudo=not args.no_sudo)
    if not files:
        raise SystemExit("No files found under custom_components/hems.")
    print(f"Target {target.user}@{target.host}:{target.remote_dir}  ({len(files)} files, backups kept in {target.backup_dir}, "
          f"{'key ' + target.key if target.key else 'no key: ssh will ask for the password'}, {'sudo' if target.sudo else 'no sudo'})")
    if args.dry_run:
        print("\n".join(f"  {f}" for f in files))
        print("Dry run: would run the checks" + (" (skipped)" if args.skip_checks else "") + ", back up, deploy, verify. Nothing was changed.")
        return 0
    if not args.skip_checks:
        run_checks()
    print(f"Build {write_build_stamp()}")
    with tempfile.TemporaryDirectory() as tmp:
        deploy(target, files, os.path.join(tmp, "ssh-%C"), args.batch)
    if args.restart:
        restart_home_assistant(env, args.yes)
    else:
        print("Next: restart Home Assistant (a new or changed integration is loaded after a restart), then add or reload HEMS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
