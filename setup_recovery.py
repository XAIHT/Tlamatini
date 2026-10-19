# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Bounded, installation-scoped recovery for the standalone setup clients.

The journal lives under the installation's Temp directory. It contains paths
and hashes, never configuration values. Backups remain private local files.
An unfinished transaction is restored before another operation starts.
"""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import time

RECOVERY_REL = "Temp/.setup-recovery"
FILE_ACCESS_RETRY_SECONDS = 5
JOURNAL_REPLACE_RETRY_SECONDS = 2


def retry_file_access(action, path, status):
    """Allow short-lived scanners/closing handles to release a file, then stop."""
    deadline = time.monotonic() + FILE_ACCESS_RETRY_SECONDS
    announced = False
    while True:
        try:
            return action()
        except PermissionError as exc:
            if not announced:
                status(f"Waiting briefly for Windows to release {Path(path).name}…")
                announced = True
            if time.monotonic() >= deadline:
                from setup_windows import file_lock_description
                owners = file_lock_description(path)
                raise PermissionError(
                    f"Windows is preventing access to:\n{path}\n\n"
                    + (f"Programs using this file: {owners}.\n" if owners else "")
                    + "Close programs using this installation, check the file's permissions, and retry. "
                    "No application files have been removed during recovery preparation."
                ) from exc
            time.sleep(min(.25, max(0, deadline - time.monotonic())))


def check_readable(path):
    # Test the open before copying gigabytes. A subsequent copy still checks
    # access and hashes: this is early diagnosis, not a promise against races.
    with open(path, "rb"):
        pass


def checked_path(root, relative):
    path = PurePosixPath(relative)
    if (not relative or path.is_absolute() or path.as_posix() != relative
            or any(p in (".", "..") or p.rstrip(" .") != p for p in path.parts)
            or any(c in relative for c in '\\:<>"|?*')
            or any(ord(c) < 32 for c in relative)):
        raise ValueError(f"Unsafe recovery path: {relative}")
    result = Path(root).joinpath(*path.parts)
    current = result
    while current != Path(root).parent:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise RuntimeError(f"Redirected setup path is not supported: {current}")
        current = current.parent
    return result


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, document):
    pending = path.with_suffix(".new")
    with open(pending, "w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    deadline = time.monotonic() + JOURNAL_REPLACE_RETRY_SECONDS
    while True:
        try:
            os.replace(pending, path)
            return
        except PermissionError:
            # Windows can briefly hold a just-written journal. Keep the old
            # durable document and the new one intact; never delete to replace.
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(.05, max(0, deadline-time.monotonic())))


@contextmanager
def setup_lock():
    """One operation per Windows session: the shell registrations are shared."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\XAIHT.Tlamatini.Setup.v1")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = False
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        # WAIT_ABANDONED also transfers ownership; the journal handles recovery.
        if result not in (0, 0x80):
            raise RuntimeError("Another Tlamatini installation or removal is running. Close it or wait for it to finish, then retry.")
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


class Recovery:
    def __init__(self, target, status=lambda _message: None, progress=lambda _fraction: None,
                 rollback_progress=lambda _fraction: None):
        self.target = Path(os.path.abspath(target))
        self.folder = checked_path(self.target, RECOVERY_REL)
        self.journal = self.folder / "journal.json"
        self.status = status
        self.progress = progress
        self.rollback_progress = rollback_progress
        self.cleanup_deadline = None
        self.data = None

    @classmethod
    def pending(cls, target):
        try:
            recovery = cls(target)
            recovery.load()
            return recovery.data["state"] in ("active", "restoring")
        except (OSError, ValueError, KeyError, RuntimeError):
            return False

    @classmethod
    def removal_cleanup_pending(cls, target):
        try:
            recovery = cls(target)
            recovery.load()
            return (recovery.data.get("mode") == "removal"
                    and recovery.data["state"] == "committed"
                    and recovery.data.get("outcome") == "removed")
        except (OSError, ValueError, KeyError, RuntimeError):
            return False

    def load(self):
        with open(self.journal, encoding="utf-8") as stream:
            data = json.load(stream)
        if (data.get("schema") not in (1, 2)
                or os.path.normcase(data.get("target", "")) != os.path.normcase(str(self.target))
                or data.get("state") not in ("preparing", "active", "restoring", "committed")):
            raise RuntimeError(f"Unrecognized recovery journal. Keep it for inspection: {self.folder}")
        for name in data["files"]:
            if name.casefold().startswith(RECOVERY_REL.casefold()):
                raise RuntimeError("Recovery journal cannot target itself")
            checked_path(self.target, name)
            checked_path(self.folder / "files", name)
        for name in data["directories"]:
            checked_path(self.target, name)
        for name in data.get("restore_directories", []):
            checked_path(self.target, name)
        if data.get("schema") == 2:
            if data.get("mode") != "removal" or not isinstance(data.get("moves"), dict):
                raise RuntimeError("Unrecognized removal recovery journal")
            for name, record in data["moves"].items():
                if len(PurePosixPath(name).parts) != 1 or name.casefold() in {"temp", "agents"}:
                    raise RuntimeError(f"Unsafe removal recovery entry: {name}")
                checked_path(self.target, name)
                checked_path(self.folder / "quarantine", name)
                if record.get("state") not in {"waiting", "moving", "staged", "restored"}:
                    raise RuntimeError("Unrecognized removal move state")
                identity = record.get("identity")
                if not isinstance(identity, list) or len(identity) != 2 or not all(isinstance(x, int) for x in identity):
                    raise RuntimeError("Invalid removal file identity")
        self.data = data

    def recover_previous(self):
        if not self.folder.exists():
            return False
        if not self.journal.is_file():
            raise RuntimeError(f"An incomplete recovery folder needs inspection: {self.folder}")
        self.load()
        if self.data["state"] in ("active", "restoring"):
            self.status("Restoring the interrupted operation before continuing…")
            self.rollback()
        else:
            # 'preparing' has never mutated the installation; 'committed' is done.
            self.discard()
        self.data = None
        return True

    def prepare(self, names, *, required_space=0, windows=True, restore_directories=(), created_directories=()):
        """Finish and verify ALL backup copies before allowing any mutation."""
        if self.folder.exists():
            raise RuntimeError("Recover the previous operation before starting another")
        names = sorted(set(names), key=str.casefold)
        records, directories, inspected_directories = {}, set(), set()
        total = 0
        # ZIPs carry intentionally empty folders too. They have no file receipt
        # entry, but must still be removed if this installation rolls back.
        for name in created_directories:
            path = checked_path(self.target, name)
            if path.exists() and not path.is_dir():
                raise RuntimeError(f"A directory destination is occupied by a file: {path}")
            relative = PurePosixPath(name)
            for item in (relative, *relative.parents):
                if item.as_posix() != "." and not checked_path(self.target, item.as_posix()).exists():
                    directories.add(item.as_posix())
        for index, name in enumerate(names, 1):
            path = checked_path(self.target, name)
            if name.casefold().startswith(RECOVERY_REL.casefold()):
                raise RuntimeError("A package cannot overwrite setup recovery data")
            if path.is_dir():
                raise RuntimeError(f"A file destination is occupied by a directory: {path}")
            exists = path.is_file()
            records[name] = {"existed": exists}
            if exists:
                retry_file_access(lambda: check_readable(path), path, self.status)
                total += path.stat().st_size
            for parent in PurePosixPath(name).parents:
                relative = parent.as_posix()
                # File paths are still independently checked for redirections.
                # Only deduplicate the unchanged parent-existence inventory.
                if relative != "." and relative not in inspected_directories:
                    inspected_directories.add(relative)
                    if not checked_path(self.target, relative).exists():
                        directories.add(relative)
            if index == 1 or index % 250 == 0 or index == len(names):
                self.status(f"Checking destination… {index:,} / {len(names):,} files")
                self.progress(.3 * index / max(len(names), 1))
        anchor = self.target
        while not anchor.exists():
            anchor = anchor.parent
        if shutil.disk_usage(anchor).free < total + required_space + 32*1024*1024:
            raise RuntimeError("Not enough free disk space for setup and its recovery copy. Free space on the destination drive and retry.")
        target_existed = self.target.exists()
        temp_existed = (self.target / "Temp").exists()
        self.folder.mkdir(parents=True)
        self.data = {"schema": 1, "target": str(self.target), "state": "preparing",
                     "files": records, "directories": sorted(directories),
                     "restore_directories": list(restore_directories),
                     "target_existed": target_existed, "temp_existed": temp_existed}
        for name in self.data["restore_directories"]:
            checked_path(self.target, name)
        atomic_json(self.journal, self.data)
        try:
            copied_bytes = 0
            self.status(f"Preparing recovery copy… 0 / {total / (1024*1024):,.1f} MB")
            for i, (name, record) in enumerate(records.items(), 1):
                if record["existed"]:
                    source = checked_path(self.target, name)
                    backup = checked_path(self.folder / "files", name)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    retry_file_access(lambda: shutil.copy2(source, backup), source, self.status)
                    mode = backup.stat().st_mode
                    backup.chmod(mode | stat.S_IWRITE)
                    with open(backup, "r+b") as durable:
                        os.fsync(durable.fileno())
                    backup.chmod(mode)
                    record["sha256"] = digest(backup)
                    if digest(source) != record["sha256"]:
                        raise RuntimeError(f"File changed while preparing recovery: {name}")
                    copied_bytes += source.stat().st_size
                if i == 1 or i % 100 == 0 or i == len(records):
                    self.status(f"Preparing recovery… {i:,} / {len(records):,} files · "
                                f"{copied_bytes / (1024*1024):,.1f} / {total / (1024*1024):,.1f} MB")
                    fraction = copied_bytes / total if total else i / max(len(records), 1)
                    self.progress(.3 + .7 * fraction)
            if windows:
                from setup_windows import WindowsSnapshot
                WindowsSnapshot(self.folder).capture()
                self.data["windows"] = True
            self.data["state"] = "active"
            atomic_json(self.journal, self.data)
            self.progress(1)
        except Exception:
            self.discard()
            raise

    def prepare_removal(self, kept_names, *, windows=True):
        """Journal same-volume renames; never copy/hash the installed payload.

        Only metadata edited by setup is copied. Temp is disposable cleanup,
        handled AFTER commit, so a cache-directory lock cannot undo removal.
        Schema 2 makes older setup clients refuse this journal, not discard it.
        """
        kept = {name.casefold() for name in kept_names} | {"temp", "agents"}
        moves = {}
        for item in self.target.iterdir():
            if item.name.casefold() in kept:
                continue
            path = checked_path(self.target, item.name)
            info = path.stat(follow_symlinks=False)
            moves[item.name] = {"state": "waiting", "identity": [info.st_dev, info.st_ino]}
        metadata = ["Tlamatini.lnk"]
        if (self.target / "agents").is_dir():
            metadata += ["agents/.tlamatini-preserved-agents.json",
                         "agents/_tlamatini_agents_manifest.json"]
        self.prepare(metadata, windows=windows)
        self.data.update(schema=2, mode="removal", moves=moves)
        atomic_json(self.journal, self.data)
        self.status(f"Recovery ready: {len(moves):,} application entries; no payload copy needed")

    @staticmethod
    def _identity(path):
        info = path.stat(follow_symlinks=False)
        return [info.st_dev, info.st_ino]

    def stage_removal(self, name):
        """Atomically set aside one validated root entry, retaining its identity."""
        if self.data.get("mode") != "removal" or name not in self.data["moves"]:
            raise RuntimeError(f"Removal entry was not prepared: {name}")
        source = checked_path(self.target, name)
        destination = checked_path(self.folder / "quarantine", name)
        record = self.data["moves"][name]
        if self._identity(source) != record["identity"]:
            raise RuntimeError(f"Installation entry changed during removal: {source}")
        if destination.exists():
            raise RuntimeError(f"Recovery destination is already occupied: {destination}")
        destination.parent.mkdir(exist_ok=True)
        if source.stat().st_dev != destination.parent.stat().st_dev:
            raise RuntimeError("Removal recovery must remain on the installation drive")
        record["state"] = "moving"
        atomic_json(self.journal, self.data)
        # No copy fallback, no replacement of an existing destination.
        source.rename(destination)
        record["state"] = "staged"
        atomic_json(self.journal, self.data)

    def _restore_moves(self):
        moves = list(self.data.get("moves", {}).items())
        failures = []
        for index, (name, record) in enumerate(reversed(moves), 1):
            if record["state"] in {"moving", "staged"}:
                try:
                    source = checked_path(self.folder / "quarantine", name)
                    destination = checked_path(self.target, name)
                    if source.exists():
                        if destination.exists():
                            raise RuntimeError("Restoration destination is occupied; existing content was kept")
                        if self._identity(source) != record["identity"]:
                            raise RuntimeError("Recovery entry identity changed")
                        source.rename(destination)
                    elif not destination.exists() or self._identity(destination) != record["identity"]:
                        raise RuntimeError("Neither the original entry nor its recovery copy was found")
                    record["state"] = "restored"
                    atomic_json(self.journal, self.data)
                except OSError as exc:
                    failures.append(f"{name}: {exc}")
                except RuntimeError as exc:
                    failures.append(f"{name}: {exc}")
            self.status(f"Restoring application entries… {index:,} / {len(moves):,}")
            self.rollback_progress(.8 * index / max(len(moves), 1))
        if failures:
            raise RuntimeError("Recovery needs attention. Retained data: " + str(self.folder)
                               + "\n\n" + "\n".join(failures[:10]))

    def rollback(self):
        if self.data is None:
            self.load()
        if self.data["state"] not in ("active", "restoring"):
            return
        self.data["state"] = "restoring"
        atomic_json(self.journal, self.data)
        self.rollback_progress(0)
        self._restore_moves()
        failures = []
        for name in self.data.get("restore_directories", []):
            try:
                checked_path(self.target, name).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                failures.append(f"{name}: {exc}")
        for i, (name, record) in enumerate(self.data["files"].items(), 1):
            try:
                path = checked_path(self.target, name)
                if record["existed"]:
                    backup = checked_path(self.folder / "files", name)
                    if not backup.is_file() or digest(backup) != record["sha256"]:
                        raise RuntimeError("Recovery copy is missing or damaged")
                    if not path.is_file() or digest(path) != record["sha256"]:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if path.exists():
                            path.chmod(stat.S_IWRITE | stat.S_IREAD)
                        shutil.copy2(backup, path)
                        if digest(path) != record["sha256"]:
                            raise RuntimeError("Restored file did not pass verification")
                elif path.is_file():
                    path.chmod(stat.S_IWRITE | stat.S_IREAD)
                    path.unlink()
            except Exception as exc:
                failures.append(f"{name}: {exc}")
            if i == 1 or i % 100 == 0 or i == len(self.data["files"]):
                self.status(f"Restoring previous files… {i:,} / {len(self.data['files']):,}")
                base = .8 if self.data.get("moves") else 0
                self.rollback_progress(base + (.9-base) * i / max(len(self.data["files"]), 1))
        if self.data.get("windows"):
            self.status("Restoring Windows registrations…")
            self.rollback_progress(.9)
            try:
                from setup_windows import WindowsSnapshot
                WindowsSnapshot(self.folder).restore()
            except Exception as exc:
                failures.append(f"Windows integration: {exc}")
        for name in sorted(self.data["directories"], key=len, reverse=True):
            try:
                checked_path(self.target, name).rmdir()
            except OSError:
                pass  # Never recursively erase a directory created by another actor.
        if failures:
            raise RuntimeError("Recovery needs attention. Its copies are retained at "
                               + str(self.folder) + "\n\n" + "\n".join(failures[:10]))
        self.status("Finishing recovery cleanup…")
        self.rollback_progress(.95)
        # Restoration is complete. An interruption during housekeeping must
        # retry housekeeping, not require backup files already deleted here.
        self.data["state"] = "committed"
        self.data["outcome"] = "restored"
        atomic_json(self.journal, self.data)
        self.discard()
        self.rollback_progress(1)

    def commit(self, *, defer_cleanup=False):
        self.data["state"] = "committed"
        self.data["outcome"] = "removed" if self.data.get("mode") == "removal" else "installed"
        atomic_json(self.journal, self.data)
        if defer_cleanup:
            return ""
        try:
            self.discard()
            return ""
        except OSError as exc:
            # Never roll a completed installation back just because housekeeping failed.
            return (f"Temporary recovery copy could not be cleared: {self.folder}. "
                    f"{exc}. Cleanup will be retried on the next setup run.")

    def discard(self):
        folder = checked_path(self.target, RECOVERY_REL)
        if folder.exists():
            # Keep the durable journal until every payload has been cleared.
            # A locked file must not leave an unrecognizable partial journal.
            for child in folder.iterdir():
                if child.name == "journal.json":
                    continue
                remove_tree(child, self.status, deadline=self.cleanup_deadline)
            self.journal.unlink(missing_ok=True)
            folder.rmdir()
        if self.data and not self.data.get("temp_existed", True):
            try:
                (self.target / "Temp").rmdir()
            except OSError:
                pass
        if self.data and not self.data.get("target_existed", True):
            try:
                self.target.rmdir()
            except OSError:
                pass


def remove_tree(path, status=lambda _message: None, *, deadline=None):
    """Delete an explicit tree once, without following links or junctions.

    Count actual removals while traversing, without a preliminary content scan,
    copy or hash pass. Callers retain their journal on failure/interruption.
    """
    path = Path(os.path.abspath(path))
    stack = [(path, False)]
    removed = 0
    last = time.monotonic()
    while stack:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"Cleanup time limit reached; remaining files are at {path}")
        current, visited = stack.pop()
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        redirected = stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        directory = stat.S_ISDIR(info.st_mode)
        if directory and not redirected and not visited:
            stack.append((current, True))
            with os.scandir(current) as entries:
                stack.extend((Path(item.path), False) for item in entries)
            continue
        action = current.rmdir if directory else current.unlink
        try:
            action()
        except PermissionError:
            if redirected:
                raise
            current.chmod(stat.S_IWRITE | stat.S_IREAD)
            action()
        removed += 1
        now = time.monotonic()
        if removed == 1 or removed % 250 == 0 or now-last >= 1:
            status(f"Deleting files and folders… {removed:,} removed ({path.name})")
            last = now
    status(f"Deleted {removed:,} files and folders ({path.name})")


def removal_files(target, kept_names):
    """Enumerate rollback files without traversing redirected directories."""
    target = Path(target)
    kept = {name.casefold() for name in kept_names}
    names = []
    for parent, dirs, files in os.walk(target, followlinks=False):
        relative = Path(parent).relative_to(target)
        dirs[:] = [name for name in dirs if not (
            (relative == Path('.') and name.casefold() in kept)
            or (relative.as_posix().casefold() == "temp" and name.casefold() == ".setup-recovery"))]
        for name in dirs + files:
            checked_path(target, (relative / name).as_posix())
        names.extend((relative / name).as_posix() for name in files)
    for name in ("agents/.tlamatini-preserved-agents.json", "agents/_tlamatini_agents_manifest.json"):
        if (target / "agents").is_dir():
            names.append(name)
    return names


def removal_directories(target, kept_names):
    """Remember original empty directories as well as directories holding files."""
    target = Path(target)
    kept = {name.casefold() for name in kept_names}
    names = []
    for parent, dirs, _files in os.walk(target, followlinks=False):
        relative = Path(parent).relative_to(target)
        dirs[:] = [name for name in dirs if not (
            (relative == Path('.') and name.casefold() in kept)
            or (relative.as_posix().casefold() == "temp" and name.casefold() == ".setup-recovery"))]
        for name in dirs:
            item = (relative / name).as_posix()
            checked_path(target, item)
            names.append(item)
    return names
