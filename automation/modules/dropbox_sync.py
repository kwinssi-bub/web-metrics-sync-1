import json
import time
import requests
from pathlib import Path


DROPBOX_APP_KEY = "2uswcj7kbg3sb8x"
DROPBOX_APP_SECRET = "e7eu41fdk2vm67v"
DROPBOX_REFRESH_TOKEN = (
    "pO79DuN9AWEAAAAAAAAAAayfLkmNeQBUfwqCHBd1-c0OD9ZBGDQl70a1imnB7Pp4"
)

ACCESS_TOKEN = None
TOKEN_EXPIRES_AT = 0


def get_access_token():
    global ACCESS_TOKEN, TOKEN_EXPIRES_AT
    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRES_AT - 60:
        return ACCESS_TOKEN

    response = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": DROPBOX_REFRESH_TOKEN,
        },
        auth=(DROPBOX_APP_KEY, DROPBOX_APP_SECRET),
    )
    response.raise_for_status()
    data = response.json()
    ACCESS_TOKEN = data["access_token"]
    TOKEN_EXPIRES_AT = time.time() + data.get("expires_in", 14400)
    return ACCESS_TOKEN


def upload_file(content: bytes, dropbox_path: str, overwrite: bool = True) -> dict:
    token = get_access_token()
    mode = "overwrite" if overwrite else "add"

    response = requests.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps(
                {
                    "path": dropbox_path,
                    "mode": mode,
                    "autorename": False,
                    "mute": True,
                }
            ),
            "Content-Type": "application/octet-stream",
        },
        data=content,
    )
    response.raise_for_status()
    return response.json()


def download_file(dropbox_path: str) -> bytes:
    token = get_access_token()
    response = requests.post(
        "https://content.dropboxapi.com/2/files/download",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": dropbox_path}),
            "Content-Type": "application/octet-stream",
        },
    )
    response.raise_for_status()
    return response.content


def list_folder(dropbox_path: str = "") -> list:
    token = get_access_token()
    response = requests.post(
        "https://api.dropboxapi.com/2/files/list_folder",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"path": dropbox_path} if dropbox_path else {"path": ""},
    )
    if response.status_code == 409:
        return []
    response.raise_for_status()
    return response.json().get("entries", [])


def sync_to_dropbox(data: dict, folder: str, filename: str) -> None:
    content = json.dumps(data, indent=2).encode("utf-8")
    path = f"/{folder}/{filename}"
    result = upload_file(content, path, overwrite=True)
    print(f"[*] Uploaded {filename} to Dropbox: {result['path_display']}")


def load_from_dropbox(folder: str, filename: str, default=None) -> dict:
    path = f"/{folder}/{filename}"
    try:
        content = download_file(path)
        return json.loads(content.decode("utf-8"))
    except Exception as e:
        print(f"[*] No existing {filename} in Dropbox, starting fresh")
        return default if default is not None else {}


def merge_and_upload_links(
    existing_links: list, new_links: list, folder: str = "zai-farms"
) -> list:
    all_links = list(set(existing_links + new_links))
    new_count = len(all_links) - len(existing_links)

    if new_count > 0:
        sync_to_dropbox(all_links, folder, "links.json")
        print(f"[*] Merged {new_count} new links. Total: {len(all_links)}")
    else:
        print("[*] No new links to sync")

    return all_links


if __name__ == "__main__":
    print("[*] Testing Dropbox connection...")
    print(f"[*] Connected user: {get_access_token()[:20]}...")

    test_data = {"test": "hello from zai automation", "timestamp": time.time()}
    sync_to_dropbox(test_data, "zai-test", "test.json")

    loaded = load_from_dropbox("zai-test", "test.json")
    print(f"[*] Downloaded: {loaded}")
