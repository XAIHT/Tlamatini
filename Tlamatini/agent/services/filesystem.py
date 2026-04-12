import html
import os
from datetime import datetime, timezone

from asgiref.sync import sync_to_async

from ..models import LLMProgram
from ..path_guard import get_runtime_agent_root, resolve_runtime_agent_path


def get_time_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def generate_tree_view_content(directory_name):
    """
    Generate a tree view of the directory structure.

    ``directory_name`` may be an absolute validated path restored from session state
    or a relative path under the runtime agent root.
    """
    try:
        application_path = get_runtime_agent_root()
        target_directory = resolve_runtime_agent_path(directory_name)

        if target_directory is None:
            return f"Error: Directory '{directory_name}' is outside the allowed paths."

        if not os.path.exists(target_directory):
            return f"Error: Directory '{directory_name}' does not exist."

        if not os.path.isdir(target_directory):
            return f"Error: '{directory_name}' is not a directory."

        tree_lines = []
        tree_lines.append(f"Directory Tree for: {target_directory}")
        tree_lines.append("=" * 80)
        tree_lines.append("")

        def build_tree(path, prefix=""):
            try:
                entries = []
                for entry in os.listdir(path):
                    entry_path = os.path.join(path, entry)
                    entries.append((entry, entry_path, os.path.isdir(entry_path)))

                entries.sort(key=lambda x: (not x[2], x[0].lower()))

                for index, (name, entry_path, is_dir) in enumerate(entries):
                    is_last_entry = index == len(entries) - 1
                    connector = "└── " if is_last_entry else "├── "
                    tree_lines.append(f"{prefix}{connector}{name}{'/' if is_dir else ''}")

                    if is_dir:
                        extension = "    " if is_last_entry else "│   "
                        build_tree(entry_path, prefix + extension)

            except PermissionError:
                tree_lines.append(f"{prefix}[Permission Denied]")
            except Exception as exc:
                tree_lines.append(f"{prefix}[Error: {exc}]")

        tree_lines.append(f"{os.path.basename(target_directory)}/")
        build_tree(target_directory)

        tree_lines.append("")
        tree_lines.append("=" * 80)

        total_files = 0
        total_dirs = 0
        for _root, dirs, files in os.walk(target_directory):
            total_dirs += len(dirs)
            total_files += len(files)

        tree_lines.append(f"Total directories: {total_dirs}")
        tree_lines.append(f"Total files: {total_files}")
        tree_lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        tree_content = "\n".join(tree_lines)

        content_generated_path = os.path.join(application_path, 'content_generated')
        os.makedirs(content_generated_path, exist_ok=True)
        return tree_content
    except Exception as exc:
        return f"Error generating tree view: {exc}"


async def save_files_from_db(message, channel_layer, room_group_name):
    application_path = get_runtime_agent_root()
    content_generated_path = os.path.join(application_path, 'content_generated')
    os.makedirs(content_generated_path, exist_ok=True)
    files = message.split('|')

    @sync_to_async
    def get_program(name):
        return LLMProgram.objects.get(programName=name)

    for file in files:
        print("Saving file: " + file + "...")
        try:
            program = await get_program(file)
            destination = os.path.join(content_generated_path, program.programName)
            with open(destination, 'w', encoding='utf-8') as f:
                f.write(program.programContent)
                f.flush()
                os.fsync(f.fileno())
            print("File: " + file + " saved!")
            if channel_layer:
                await channel_layer.group_send(
                    room_group_name,
                    {
                        'type': 'agent_message',
                        'message': 'File: <code>' + html.escape(destination) + '</code> saved!',
                        'username': 'Tlamatini'
                    }
                )
            print("--- Bot message of file saving broadcasted to room.")
        except Exception as exc:
            print(f"!!! ERROR while saving file: {exc}")
