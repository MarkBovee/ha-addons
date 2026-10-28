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


def test_the_tar_stream_contains_the_files_root_owned_and_relative(tmp_path):
    """Regression: GNU tar needs -C before -T, and entries must not carry the local user's uid."""
    root = tmp_path / "custom_components" / "hems"
    (root / "sub").mkdir(parents=True)
    (root / "a.py").write_text("a")
    (root / "sub" / "b.json").write_text("b")
    tar = deploy.stream_tar(["a.py", "sub/b.json"], root=tmp_path)
    with tarfile.open(fileobj=tar.stdout, mode="r|") as archive:
        entries = {m.name: (m.uid, m.gid) for m in archive}
    assert tar.wait() == 0
    assert entries == {"a.py": (0, 0), "sub/b.json": (0, 0)}


def test_privileged_wraps_the_script_for_sudo_without_a_password_prompt():
    """sudo runs with -n (never prompts) and the script survives quoting; without sudo it is unchanged."""
    script = deploy.remote_install_script(deploy.Target("h", "u"))
    wrapped = deploy.privileged(script, sudo=True)
    import shlex
    assert shlex.split(wrapped)[:4] == ["sudo", "-n", "sh", "-c"] and shlex.split(wrapped)[4] == script
    assert deploy.privileged(script, sudo=False) == script


def test_a_dropped_connection_during_restart_is_the_expected_outcome(monkeypatch):
    """HA closes the socket while shutting down; that must not abort the script, and it then waits for HA to return."""
    import http.client
    calls = []

    class Answer(io.BytesIO):
        """A urlopen result that is also a context manager."""
        status = 200

        def __enter__(self):
            """Return self for `with`."""
            return self

        def __exit__(self, *exc):
            """Nothing to release."""
            return False

    def fake_urlopen(request, timeout=0):
        """check_config answers; the restart call drops the connection."""
        calls.append(request.full_url)
        if request.full_url.endswith("/config/core/check_config"):
            return Answer(b'{"result": "valid"}')
        raise http.client.RemoteDisconnected("closed")

    monkeypatch.setattr(deploy.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(deploy, "wait_for_home_assistant", lambda base, token: True)
    deploy.restart_home_assistant({"HA_API_URL": "http://ha/api", "HA_API_TOKEN": "t"}, assume_yes=True)
    assert calls == ["http://ha/api/config/core/check_config", "http://ha/api/services/homeassistant/restart"]


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


def test_the_build_stamp_is_the_commit_and_says_when_the_code_is_not_committed(tmp_path):
    """BUILD carries the short commit of the deployed code; a changed tracked file in it adds '+dirty'."""
    git = lambda *args: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    code = tmp_path / "custom_components" / "hems" / "a.py"
    code.parent.mkdir(parents=True)
    code.write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-qm", "first")
    commit = git("rev-parse", "--short", "HEAD")
    assert deploy.write_build_stamp(tmp_path) == commit
    assert (tmp_path / "custom_components" / "hems" / "BUILD").read_text() == commit + "\n"
    code.write_text("x = 2\n")
    assert deploy.write_build_stamp(tmp_path) == commit + "+dirty"


def test_the_stamp_is_deployed_even_though_git_ignores_it():
    """BUILD is generated and ignored, so the file list must add it by name."""
    assert deploy.BUILD_FILE == "BUILD"
