"""Hard gate: injected secrets never appear in any human or JSON report."""

import pytest

from conftest import fixture_system, run_cli
from jadis.redact import REDACTED, Redactor

SECRETS = {
    "github": "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "openai": "sk-proj-" + "Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk2Ji1",
    "aws": "AKIA" + "ABCDEFGHIJKLMNOP",
    "slack": "xoxb-" + "123456789012-abcdefABCDEF",
    "jwt": "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".SflKxwRJSMeKKF2QT4fwpMeJf36P",
    "custom": "s3cr3t-value-that-only-env-knows",
}
KEY_BLOCK = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ\n-----END " + "OPENSSH PRIVATE KEY-----"


def poisoned():
    s = fixture_system("debian13")
    s.environ.update(
        GITHUB_TOKEN=SECRETS["github"], OPENAI_API_KEY=SECRETS["openai"], MY_SERVICE_SECRET=SECRETS["custom"], JAVA_HOME="/usr/lib/jvm/" + SECRETS["aws"]
    )
    s.commands["/usr/bin/curl --version"] = {"rc": 0, "stdout": f"curl 8.14.1 token={SECRETS['slack']} https://user:{SECRETS['custom']}@host/\n"}
    s.commands["/usr/bin/git --version"] = {"rc": 0, "stdout": f"git version 2.47.3 {SECRETS['jwt']}\n{KEY_BLOCK}\n"}
    s.commands["git config --global --get user.name"] = {"rc": 0, "stdout": SECRETS["github"] + "\n"}
    s.files["/home/dev/.bashrc"] = f"export OPENAI_API_KEY={SECRETS['openai']}\nalias grep='rg'\n"
    return s


@pytest.mark.parametrize(
    "argv",
    [
        ["env"],
        ["env", "--json"],
        ["doctor", "--profile", "full"],
        ["doctor", "--profile", "full", "--json"],
        ["report", "--json"],
        ["git"],
        ["java", "--json"],
        ["info", "--json"],
    ],
)
def test_no_secret_reaches_any_output(argv):
    code, out = run_cli(argv, poisoned())
    text = out if isinstance(out, str) else __import__("json").dumps(out)
    for name, secret in SECRETS.items():
        assert secret not in text, (argv, name)
    assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ" not in text
    assert "/home/dev" not in text  # home is shown as ~


def test_redactor_patterns_directly():
    r = Redactor(home="/home/dev", secrets=[SECRETS["custom"]])
    assert r.text(f"Authorization: Bearer {SECRETS['github']}").count(REDACTED) >= 1
    assert REDACTED in r.text("https://u:" + "p4ssw0rd99" + "@example.com/x")
    assert r.text(KEY_BLOCK) == "[REDACTED PRIVATE KEY]"
    assert r.text("truncated -----BEGIN " + "RSA PRIVATE KEY-----\nAAAA") == "truncated [REDACTED PRIVATE KEY]"
    assert r.text("/home/dev/x and /home/devx") == "~/x and /home/devx"
    assert r.value({"nested": [SECRETS["custom"]]}) == {"nested": [REDACTED]}
    assert r.text("version 1.2.3 at /usr/bin/git") == "version 1.2.3 at /usr/bin/git"  # no false positives on ordinary output


def test_backup_skips_credential_files(tmp_path):
    from jadis import backup

    home = tmp_path
    (home / ".gitconfig").write_text("[user]\n name = x\n")
    (home / ".bashrc").write_text(f"export GITHUB_TOKEN={SECRETS['github']}\n")
    (home / ".git-credentials").write_text("https://x:y@github.com\n")
    env = {"HOME": str(home), "XDG_DATA_HOME": str(home / "data")}
    shell = backup.create(env, "shell")
    assert shell["files"] == [] and shell["skipped"][0]["path"] == ".bashrc"
    git = backup.create(env, "git")
    assert [f["path"] for f in git["files"]] == [".gitconfig"]
    assert not list((home / "data").rglob(".git-credentials"))
