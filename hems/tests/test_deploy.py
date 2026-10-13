import importlib.util
import io
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy.py"
spec = importlib.util.spec_from_file_location("hems_deploy", DEPLOY)
deploy = importlib.util.module_from_spec(spec)
sys.modules["hems_deploy"] = deploy
spec.loader.exec_module(deploy)


def tar_bytes(files: dict[str, str]) -> bytes:
    """An in-memory tar of {relative path: text}, as the deploy streams it."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def install(target, files: dict[str, str]):
    """Run the remote install script locally with `sh` and a tar on stdin (the server side of a deploy)."""
    return subprocess.run(["sh", "-c", deploy.remote_install_script(target)], input=tar_bytes(files), capture_output=True)


def test_env_is_parsed_without_comments_and_quotes():
    """Comments and blank lines are skipped, quotes stripped."""
    env = deploy.parse_env('# note\nA=1\n\nB="two"\nC = \'three\'\n')
    assert env == {"A": "1", "B": "two", "C": "three"}


def test_target_comes_from_env_and_never_carries_a_password():
    """Host and user are read; a password in the env is ignored and cannot end up on the target."""
    env = {"HA_HOST": "http://192.168.1.135:8123", "HA_SSH_USER": "mark", "HA_SSH_PASSWORD": "secret"}
    target = deploy.target_from_env(env)
    assert (target.host, target.user) == ("192.168.1.135", "mark")
    assert "secret" not in repr(target) and not hasattr(target, "password")
    assert deploy.target_from_env({"HA_API_URL": "http://ha.local:8123/api", "HA_SSH_USER": "u"}).host == "ha.local"
    assert deploy.target_from_env(env, host="other", user="me") == deploy.Target("other", "me")
    with pytest.raises(SystemExit):
        deploy.target_from_env({"HA_HOST": "h"})


def test_files_to_deploy_are_tracked_or_new_but_never_caches(tmp_path):
    """Untracked-but-not-ignored files count; ignored caches and files elsewhere do not."""
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("__pycache__/\n")
    for name in ("custom_components/hems/a.py", "custom_components/hems/sub/b.json", "custom_components/hems/__pycache__/a.pyc", "docs/x.md"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("x")
    assert deploy.relative_files(repo) == ["a.py", "sub/b.json"]


def test_checksums_compare_into_missing_extra_and_different():
    """The verification names exactly which files are missing, unexpected or changed on the server."""
    remote = deploy.parse_sha256sum("aaa  ./a.py\nbbb  ./sub/b.json\nccc  ./stray.txt\n")
    assert deploy.compare({"a.py": "aaa", "sub/b.json": "xxx", "new.py": "n"}, remote) == (["new.py"], ["stray.txt"], ["sub/b.json"])


def test_ssh_shares_one_connection_and_only_the_first_call_is_a_master():
    """Only the first call opens the shared connection (and may prompt); the rest reuse it."""
    target = deploy.Target("h", "u")
    first = deploy.ssh_command(target, "/tmp/c", "true", master=True)
    later = deploy.ssh_command(target, "/tmp/c", "ls")
    assert "ControlMaster=yes" in first and "ControlPersist=300" in first and first[-2:] == ["u@h", "true"]
    assert "ControlMaster=no" in later and "ControlPersist=300" not in later and later[-2:] == ["u@h", "ls"]


def test_a_key_is_passed_by_path_and_batch_forbids_prompts():
    """The script hands ssh a key path (never contents or a password); --batch turns prompts into failures."""
    target = deploy.target_from_env({"HA_HOST": "h", "HA_SSH_USER": "u", "HA_SSH_KEY": "~/.ssh/ha_hems", "HA_SSH_PASSWORD": "secret"})
    assert target.key == str(Path("~/.ssh/ha_hems").expanduser())
    command = deploy.ssh_command(target, "/tmp/c", "true", master=True, batch=True)
    assert command[command.index("-i") + 1] == target.key and "IdentitiesOnly=yes" in command and "BatchMode=yes" in command
    assert "secret" not in " ".join(command)
    assert "-i" not in deploy.ssh_command(deploy.Target("h", "u"), "/tmp/c", "true") and "BatchMode=yes" not in deploy.ssh_command(deploy.Target("h", "u"), "/tmp/c", "true")


def test_install_swaps_the_integration_and_keeps_a_backup_of_the_old_one(tmp_path):
    """First deploy installs; the second replaces everything (stale files vanish) and archives the previous copy."""
    target = deploy.Target("h", "u", config_dir=str(tmp_path))
    assert install(target, {"manifest.json": "v1", "old.py": "x"}).returncode == 0
    assert (tmp_path / "custom_components/hems/old.py").exists()
    assert install(target, {"manifest.json": "v2"}).returncode == 0
    root = tmp_path / "custom_components/hems"
    assert (root / "manifest.json").read_text() == "v2" and not (root / "old.py").exists()
    backups = list((tmp_path / ".hems-backup").glob("hems-*.tar.gz"))
    assert len(backups) == 1
    with tarfile.open(backups[0]) as archive:
        assert "hems/old.py" in archive.getnames()
    assert not (tmp_path / "custom_components/.hems-new").exists()


def test_a_broken_transfer_leaves_the_running_copy_untouched(tmp_path):
    """If the tar stream is garbage the old directory is not replaced."""
    target = deploy.Target("h", "u", config_dir=str(tmp_path))
    assert install(target, {"manifest.json": "good"}).returncode == 0
    broken = subprocess.run(["sh", "-c", deploy.remote_install_script(target)], input=b"not a tar", capture_output=True)
    assert broken.returncode != 0
    assert (tmp_path / "custom_components/hems/manifest.json").read_text() == "good"


def test_only_the_newest_backups_are_kept(tmp_path):
    """Old backups are pruned to KEEP_BACKUPS."""
    target = deploy.Target("h", "u", config_dir=str(tmp_path))
    assert install(target, {"manifest.json": "v1"}).returncode == 0
    backup_dir = tmp_path / ".hems-backup"
    now = time.time()
    for age, name in enumerate(("hems-a.tar.gz", "hems-b.tar.gz", "hems-c.tar.gz", "hems-d.tar.gz"), start=1):
        path = backup_dir / name
        path.write_bytes(b"x")
        os.utime(path, (now - 1000 * age, now - 1000 * age))
    assert install(target, {"manifest.json": "v2"}).returncode == 0
    assert len(list(backup_dir.glob("hems-*.tar.gz"))) == deploy.KEEP_BACKUPS
    assert not (backup_dir / "hems-d.tar.gz").exists()


def test_dry_run_changes_nothing_and_never_connects():
    """--dry-run lists the files and exits before any ssh or test run."""
    done = subprocess.run([sys.executable, str(DEPLOY), "--dry-run", "--host", "192.0.2.1", "--user", "demo"], capture_output=True, text=True)
    assert done.returncode == 0 and "Nothing was changed" in done.stdout and "manifest.json" in done.stdout
