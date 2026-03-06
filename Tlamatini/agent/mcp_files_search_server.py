import os
import sys
import json
import fnmatch
from concurrent import futures
import time
import logging
import grpc
import filesearch_pb2
import filesearch_pb2_grpc
try:
    from win32com.shell import shell, shellcon
except ImportError:
    print("ERROR: 'pywin32' library not found.")
    print("Please install it on the server: pip install pywin32")
    exit(1)

def _get_known_folder_path(folder_id):
    try:
        path = shell.SHGetKnownFolderPath(folder_id, 0, None)
        return path
    except Exception as e:
        logging.error(f"Failed to get known folder path for FOLDERID {folder_id}: {e}")
        return None

def get_application_root():
    """Derive the application root automatically, supporting both frozen (PyInstaller)
    and not-frozen (development) modes.
    - Frozen: executable lives directly at the app root.
    - Not frozen: script is at <app_root>/Tlamatini/agent/, so go up 2 levels."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(os.path.dirname(script_dir))

def load_config():
    try:
        # Determine the absolute path to config.json (supports frozen/PyInstaller mode)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        config_path = os.path.join(base_dir, "config.json")

        if not os.path.exists(config_path):
             logging.warning(f"Config file not found at {config_path}. Using defaults.")
             return {}

        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading config.json: {e}")
        return {}

CONFIG = load_config()
APPLICATION_ROOT = get_application_root()

NO_CONFIG_ERROR = (
    "There are not a valid configuration for accessing files in the local machine"
)

# Map of well-known folder names to their shell folder IDs
_KNOWN_FOLDER_MAP = {
    "application": None,  # special: resolves to APPLICATION_ROOT
    "docs": shellcon.FOLDERID_Documents,
    "downloads": shellcon.FOLDERID_Downloads,
    "desktop": shellcon.FOLDERID_Desktop,
    "pictures": shellcon.FOLDERID_Pictures,
    "videos": shellcon.FOLDERID_Videos,
    "music": shellcon.FOLDERID_Music,
}

def _build_allowed_paths(config):
    """Build ALLOWED_PATHS exclusively from config.json 'allowed_paths'.
    No defaults: if the key is missing or the list is empty, returns {}."""
    entries = config.get("allowed_paths", [])
    if not entries:
        return {}

    result = {}
    for entry in entries:
        entry_lower = entry.strip().lower() if isinstance(entry, str) else ""
        if not entry_lower:
            continue

        # Check if the entry is a well-known folder name
        if entry_lower in _KNOWN_FOLDER_MAP:
            if entry_lower == "application":
                path = APPLICATION_ROOT
            else:
                path = _get_known_folder_path(_KNOWN_FOLDER_MAP[entry_lower])
            if path and os.path.isdir(path):
                result[entry_lower] = path
        else:
            # Treat the entry as a raw filesystem path
            raw_path = entry.strip()
            if os.path.isdir(raw_path):
                result[raw_path] = raw_path
            else:
                logging.warning(f"Configured allowed_path is not a valid directory: {raw_path}")
    return result

ALLOWED_PATHS = _build_allowed_paths(CONFIG)

class FileSearcherServicer(filesearch_pb2_grpc.FileSearcherServicer):

    def _perform_search(self, root_dir, pattern, include_hidden):
        found = []
        pattern_lower = pattern.lower()
        try:
            for root, dirs, files in os.walk(root_dir, topdown=True):
                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    files = [f for f in files if not f.startswith('.')]
                for filename in files:
                    if fnmatch.fnmatch(filename.lower(), pattern_lower):
                        full_path = os.path.join(root, filename)
                        found.append(full_path)
                for dirname in dirs:
                    if fnmatch.fnmatch(dirname.lower(), pattern_lower):
                        full_path = os.path.join(root, dirname)
                        found.append(full_path)
        except Exception as e:
            logging.warning(f"Error searching {root_dir}: {e}")
            pass 
        return found

    def SearchFiles(self, request, context):
        print("\n--- DEBUG (gRPC): Server received a new request. ---")

        if not ALLOWED_PATHS:
            response = filesearch_pb2.SearchResponse()
            response.error_message = NO_CONFIG_ERROR
            print("--- DEBUG (gRPC): No allowed paths configured. Sending error response. ---")
            return response

        pattern = request.file_pattern
        include_hidden = request.include_hidden
        base_path_key = None
        if request.HasField('base_path_key'):
            base_path_key = request.base_path_key.lower()

        print(f"--- DEBUG (gRPC): Request details: {{pattern: '{pattern}', key: '{base_path_key}', hidden: {include_hidden}}} ---")

        response = filesearch_pb2.SearchResponse()
        all_found_files = []
        
        if ".." in pattern or pattern.startswith(("/", "\\")):
            logging.warning(f"Client sent potentially malicious pattern: {pattern}")
            response.error_message = "Invalid pattern."
            print("--- DEBUG (gRPC): Rejected malicious pattern. Sending error response. ---")
            return response

        if base_path_key:
            if base_path_key not in ALLOWED_PATHS:
                logging.warning(f"Client requested invalid base path key: {request.base_path_key}")
                response.error_message = f"Invalid base path key. Allowed keys are: {list(ALLOWED_PATHS.keys())}"
                print(f"--- DEBUG (gRPC): Invalid key '{base_path_key}'. Sending error response. ---")
                return response
            
            root_dir_to_search = ALLOWED_PATHS[base_path_key]
            logging.info(f"Starting specific search in '{root_dir_to_search}' for pattern '{pattern}'")
            all_found_files = self._perform_search(root_dir_to_search, pattern, include_hidden)
            
        else:
            logging.info(f"Starting global search for pattern '{pattern}' in all {len(ALLOWED_PATHS)} allowed paths.")
            for key, root_dir in ALLOWED_PATHS.items():
                logging.info(f"  ... searching in '{key}' ({root_dir})")
                try:
                    found_in_path = self._perform_search(root_dir, pattern, include_hidden)
                    all_found_files.extend(found_in_path)
                except Exception as e:
                    logging.warning(f"Failed to search {key}: {e}")

        response.found_files.extend(all_found_files)
        print(f"--- DEBUG (gRPC): Search complete. Found {len(all_found_files)} files. Sending response. ---")
        return response

    def ListAllowedDirs(self, request, context):
        print("\n--- DEBUG (gRPC): Received request to list allowed directories. ---")

        if not ALLOWED_PATHS:
            response = filesearch_pb2.ListDirsResponse()
            response.error_message = NO_CONFIG_ERROR
            print("--- DEBUG (gRPC): No allowed paths configured. Sending error response. ---")
            return response

        response = filesearch_pb2.ListDirsResponse()
        for key, path in ALLOWED_PATHS.items():
            response.allowed_dirs[key] = path
        print(f"--- DEBUG (gRPC): Sending {len(ALLOWED_PATHS)} allowed directories. ---")
        return response

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    filesearch_pb2_grpc.add_FileSearcherServicer_to_server(
        FileSearcherServicer(), server
    )
    server.add_insecure_port('[::]:50051')
    print("DEBUG Server (v5) started on port 50051...")
    print("Found and allowed search paths:")
    if not ALLOWED_PATHS:
        print("  - WARNING: No known folders were found.")
    for key, path in ALLOWED_PATHS.items():
        print(f"  - '{key}' -> '{path}'")
    
    server.start()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        print("Stopping server...")
        server.stop(0)
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        serve()
    except KeyboardInterrupt:
        print("\nServer stopped.")