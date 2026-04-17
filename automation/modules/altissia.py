import json
import subprocess
import os
import time
import random
import shutil
from pathlib import Path

try:
    from automation.modules.dropbox_sync import sync_to_dropbox, load_from_dropbox

    DROPBOX_AVAILABLE = True
except ImportError:
    DROPBOX_AVAILABLE = False

LOCK_BRANCH = "refs/heads/.lock"
LOCK_TIMEOUT = 300


def run_git(cmd, cwd, capture=True):
    res = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    return res


def append_and_push_links(links: list[str], use_git: bool = False) -> None:
    if not links:
        return

    default_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    altissia_path = os.environ.get("ALTISSIA_DIR", default_path)
    altissia_dir = Path(altissia_path)
    links_file = altissia_dir / "automation" / "data" / "links.json"
    credentials_file = altissia_dir / "automation" / "data" / "credentials.json"
    pid = os.getpid()

    links_file.parent.mkdir(parents=True, exist_ok=True)
    if not links_file.exists():
        links_file.write_text("[]\n", encoding="utf-8")

    if not use_git:
        data = []
        try:
            data = json.loads(links_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        if not isinstance(data, list):
            data = []
        added = False
        for link in links:
            if link not in data:
                data.append(link)
                added = True
        if added:
            links_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"[*] Written {len(links)} links locally.")

        if DROPBOX_AVAILABLE:
            try:
                existing_links = load_from_dropbox(
                    "zai-farms", "links.json", default=[]
                )
                if not isinstance(existing_links, list):
                    existing_links = []

                new_count = 0
                for link in data:
                    if link not in existing_links:
                        existing_links.append(link)
                        new_count += 1

                if new_count > 0:
                    sync_to_dropbox(existing_links, "zai-farms", "links.json")
                    print(f"[*] Synced {len(existing_links)} total links to Dropbox")
            except Exception as e:
                print(f"[!] Dropbox sync failed: {e}")

        return

    lock_acquired = False
    start = time.time()

    while time.time() - start < LOCK_TIMEOUT:
        run_git(["git", "fetch", "origin", LOCK_BRANCH], cwd=altissia_dir)

        lock_res = run_git(
            ["git", "show-ref", "--verify", "--quiet", "refs/heads/.lock"],
            cwd=altissia_dir,
        )

        if lock_res.returncode != 0:
            res = run_git(
                [
                    "git",
                    "push",
                    "origin",
                    f"HEAD:refs/heads/.lock",
                    "-o",
                    f"message=lock by pid {pid}",
                ],
                cwd=altissia_dir,
            )
            if res.returncode == 0:
                lock_acquired = True
                print(f"[*] Lock acquired (pid {pid})")
                break
        else:
            lock_content = run_git(["git", "show", "origin/.lock"], cwd=altissia_dir)
            print(
                f"[*] Lock held by another runner, waiting... ({lock_content.stdout.strip()})"
            )

        time.sleep(1)

    if not lock_acquired:
        print(
            "[!] Could not acquire git lock. Another workflow is pushing. Saving to Dropbox anyway..."
        )

        if DROPBOX_AVAILABLE:
            try:
                existing_links = load_from_dropbox(
                    "zai-farms", "links.json", default=[]
                )
                if not isinstance(existing_links, list):
                    existing_links = []

                new_count = 0
                for link in links:
                    if link not in existing_links:
                        existing_links.append(link)
                        new_count += 1

                if new_count > 0:
                    sync_to_dropbox(existing_links, "zai-farms", "links.json")
                    print(
                        f"[*] Dropbox backup: {new_count} new links synced (total: {len(existing_links)})"
                    )
            except Exception as e:
                print(f"[!] Dropbox backup failed: {e}")

        return

    tmp_creds = None
    try:
        if credentials_file.exists():
            tmp_creds = credentials_file.with_suffix(".json.tmp")
            shutil.copy(credentials_file, tmp_creds)

        run_git(["git", "fetch", "origin", "master"], cwd=altissia_dir)
        run_git(["git", "reset", "--hard", "origin/master"], cwd=altissia_dir)

        if tmp_creds and tmp_creds.exists():
            shutil.move(str(tmp_creds), credentials_file)

        try:
            data = json.loads(links_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

        added = False
        for link in links:
            if link not in data:
                data.append(link)
                added = True

        if not added:
            print("[*] No new links to add.")
            return

        run_git(["git", "fetch", "origin", "master"], cwd=altissia_dir)
        run_git(["git", "reset", "--hard", "origin/master"], cwd=altissia_dir)

        data = json.loads(links_file.read_text(encoding="utf-8"))
        for link in links:
            if link not in data:
                data.append(link)

        links_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        git_email = os.environ.get("GIT_USER_EMAIL", "bot@web-metrics-sync.local")
        git_name = os.environ.get("GIT_USER_NAME", "Metrics Bot")

        run_git(["git", "config", "user.email", git_email], cwd=altissia_dir)
        run_git(["git", "config", "user.name", git_name], cwd=altissia_dir)
        run_git(
            [
                "git",
                "add",
                "automation/data/links.json",
                "automation/data/credentials.json",
            ],
            cwd=altissia_dir,
            capture=False,
        )
        run_git(
            [
                "git",
                "commit",
                "-m",
                f"chore: sync {len(links)} new links and credentials (pid {pid})",
            ],
            cwd=altissia_dir,
        )

        push_res = run_git(["git", "push", "origin", "master"], cwd=altissia_dir)
        if push_res.returncode == 0:
            print(f"[*] Successfully pushed {len(links)} links and credentials.")
        else:
            print(f"[!] Push failed: {push_res.stderr.strip()}")

        if DROPBOX_AVAILABLE:
            try:
                existing_links = load_from_dropbox(
                    "zai-farms", "links.json", default=[]
                )
                if not isinstance(existing_links, list):
                    existing_links = []

                new_count = 0
                for link in links:
                    if link not in existing_links:
                        existing_links.append(link)
                        new_count += 1

                if new_count > 0:
                    sync_to_dropbox(existing_links, "zai-farms", "links.json")
                    print(
                        f"[*] Dropbox: {new_count} new links synced (total: {len(existing_links)})"
                    )
            except Exception as e:
                print(f"[!] Dropbox sync failed: {e}")

    finally:
        if tmp_creds and tmp_creds.exists():
            tmp_creds.unlink()
        run_git(["git", "push", "origin", "--delete", LOCK_BRANCH], cwd=altissia_dir)
        print(f"[*] Lock released (pid {pid})")
