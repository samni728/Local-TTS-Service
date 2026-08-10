import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGER_SCRIPT = PROJECT_ROOT / "scripts" / "tts-vps-manager.sh"


def run(command, cwd=None, env=None, check=True):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=check,
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class VpsManagerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.deployment = self.root / "deployment"
        self.backups = self.root / "backups"
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()

        run(["git", "init", "--bare", str(self.remote)])
        run(["git", "init", str(self.seed)])
        run(["git", "config", "user.name", "LocalTTS Test"], cwd=self.seed)
        run(["git", "config", "user.email", "test@example.invalid"], cwd=self.seed)

        shutil.copy2(MANAGER_SCRIPT, self.seed / "tts-vps-manager.sh")
        (self.seed / "docker-compose.yml").write_text(
            "services:\n  tts-service:\n    image: example.invalid/local-tts:test\n",
            encoding="utf-8",
        )
        (self.seed / "config.json").write_text(
            json.dumps({"private": "repository-default"}),
            encoding="utf-8",
        )
        (self.seed / ".env.example").write_text("OLD_VAR=\n", encoding="utf-8")
        run(["git", "add", "."], cwd=self.seed)
        run(["git", "commit", "-m", "base"], cwd=self.seed)
        run(["git", "branch", "-M", "main"], cwd=self.seed)
        run(["git", "remote", "add", "origin", str(self.remote)], cwd=self.seed)
        run(["git", "push", "-u", "origin", "main"], cwd=self.seed)
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=self.remote)
        self.base_commit = run(["git", "rev-parse", "HEAD"], cwd=self.seed).stdout.strip()

        run(["git", "clone", str(self.remote), str(self.deployment)])
        (self.deployment / "config.json").write_text(
            json.dumps({"private": "runtime-value"}),
            encoding="utf-8",
        )
        (self.deployment / ".env").write_text("OLD_VAR=keep-me\n", encoding="utf-8")

        (self.seed / "app-version.txt").write_text("version-2\n", encoding="utf-8")
        (self.seed / ".env.example").write_text(
            "OLD_VAR=\nNEW_VAR=default-value\n",
            encoding="utf-8",
        )
        run(["git", "add", "."], cwd=self.seed)
        run(["git", "commit", "-m", "update"], cwd=self.seed)
        run(["git", "push", "origin", "main"], cwd=self.seed)
        self.updated_commit = run(["git", "rev-parse", "HEAD"], cwd=self.seed).stdout.strip()

        fake_docker = self.fake_bin / "docker"
        fake_docker.write_text(
            """#!/usr/bin/env bash
set -u
if [[ "${1:-}" == "compose" ]]; then
    shift
    case "${1:-}" in
        version|config|logs) exit 0 ;;
        up)
            if [[ -n "${FAKE_DOCKER_FAIL_ONCE_FILE:-}" && ! -f "$FAKE_DOCKER_FAIL_ONCE_FILE" ]]; then
                : >"$FAKE_DOCKER_FAIL_ONCE_FILE"
                exit 1
            fi
            exit 0
            ;;
        ps) printf 'fake-container\\n'; exit 0 ;;
    esac
elif [[ "${1:-}" == "inspect" ]]; then
    if [[ "$*" == *State.Health* ]]; then
        printf 'healthy\\n'
    else
        printf 'running\\n'
    fi
    exit 0
fi
exit 1
""",
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def manager(self, *arguments, check=True, extra_env=None):
        env = {**self.env, **(extra_env or {})}
        return run(
            [
                "bash",
                str(MANAGER_SCRIPT),
                *arguments,
                "--repo",
                str(self.deployment),
                "--backup-dir",
                str(self.backups),
                "--timeout",
                "3",
            ],
            env=env,
            check=check,
        )

    def test_update_preserves_private_config_and_restore_returns_to_backup(self):
        result = self.manager("update")

        self.assertIn("更新成功", result.stderr)
        self.assertEqual(
            run(["git", "rev-parse", "HEAD"], cwd=self.deployment).stdout.strip(),
            self.updated_commit,
        )
        self.assertEqual(
            json.loads((self.deployment / "config.json").read_text(encoding="utf-8")),
            {"private": "runtime-value"},
        )
        env_text = (self.deployment / ".env").read_text(encoding="utf-8")
        self.assertIn("OLD_VAR=keep-me", env_text)
        self.assertIn("NEW_VAR=default-value", env_text)
        self.assertTrue(list(self.backups.glob("*-pre-update-*")))

        restore_result = self.manager("restore", "latest")

        self.assertIn("恢复成功", restore_result.stderr)
        self.assertEqual(
            run(["git", "rev-parse", "HEAD"], cwd=self.deployment).stdout.strip(),
            self.base_commit,
        )
        self.assertFalse((self.deployment / "app-version.txt").exists())
        self.assertEqual(
            json.loads((self.deployment / "config.json").read_text(encoding="utf-8")),
            {"private": "runtime-value"},
        )

    def test_failed_container_update_rolls_back_code_and_configuration(self):
        fail_marker = self.root / "fail-once.marker"
        result = self.manager(
            "update",
            check=False,
            extra_env={"FAKE_DOCKER_FAIL_ONCE_FILE": str(fail_marker)},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("开始自动回滚", result.stderr)
        self.assertIn("已恢复到更新前版本", result.stderr)
        self.assertEqual(
            run(["git", "rev-parse", "HEAD"], cwd=self.deployment).stdout.strip(),
            self.base_commit,
        )
        self.assertEqual(
            json.loads((self.deployment / "config.json").read_text(encoding="utf-8")),
            {"private": "runtime-value"},
        )


if __name__ == "__main__":
    unittest.main()
