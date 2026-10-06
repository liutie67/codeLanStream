"""Disposable filesystem worker. No application imports or database access.

Run by disk_probe with JSON on stdin. A stuck NAS syscall can never hold the
ASGI event loop or consume an unbounded number of executor threads.
"""
import json
import os
import stat
import sys


def inspect(path: str, directory: bool = False) -> dict:
    try:
        info = os.stat(path)
        if directory:
            if not stat.S_ISDIR(info.st_mode):
                return {"status": "missing", "reason": "not_directory"}
            with os.scandir(path) as entries:
                next(entries, None)  # Confirm directory access, not just stat access.
        elif not stat.S_ISREG(info.st_mode):
            return {"status": "missing", "reason": "not_file"}
        elif not os.access(path, os.R_OK):
            return {"status": "unavailable", "reason": "permission"}
        return {"status": "available", "size": info.st_size}
    except (FileNotFoundError, NotADirectoryError):
        return {"status": "missing", "reason": "not_found"}
    except PermissionError:
        return {"status": "unavailable", "reason": "permission"}
    except OSError:
        return {"status": "unavailable", "reason": "io_error"}


def run(body: dict) -> dict:
    if body["action"] == "directories":
        path = body["path"]
        result = inspect(path, True)
        if result["status"] != "available":
            return result
        try:
            directories = []
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir():
                            directories.append({"name": entry.name, "path": os.path.realpath(entry.path)})
                    except OSError:
                        continue
            directories.sort(key=lambda entry: entry["name"].lower())
            return {"status": "available", "directories": directories}
        except PermissionError:
            return {"status": "unavailable", "reason": "permission"}
        except OSError:
            return {"status": "unavailable", "reason": "io_error"}

    root = body.get("root")
    root_result = inspect(root, True) if root else {"status": "available"}
    if root_result["status"] == "missing":
        root_result = {"status": "unavailable", "reason": "root_missing"}
    directories = {}
    files = {}
    for path in body.get("directories", []):
        directories[path] = inspect(path, True) if root_result["status"] == "available" else root_result
    for path in body.get("files", []):
        files[path] = inspect(path) if root_result["status"] == "available" else root_result
    # Reconfirm the source after probes to avoid calling a disconnect a deletion.
    if root and root_result["status"] == "available":
        final_root = inspect(root, True)
        if final_root["status"] != "available":
            root_result = {**final_root, "status": "unavailable"}
            directories = dict.fromkeys(directories, root_result)
            files = dict.fromkeys(files, root_result)
    return {"root": root_result, "directories": directories, "files": files}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
