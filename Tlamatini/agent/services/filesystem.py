import os
import sys
from datetime import datetime, timezone
from asgiref.sync import sync_to_async
from ..models import LLMProgram

def get_time_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

def generate_tree_view_content(directory_name):
    """
    Generate a tree view of the directory structure and save it as a .txt file.
    Args:
        directory_name (str): Relative path from application_path to the directory to parse
    Returns:
        str: Message indicating the file was generated successfully or error message
    """
    try:
        # Get the application path
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
            application_path = os.path.dirname(application_path) # Go up to agent

        # Build the target directory path from application_path + directory_name
        target_directory = os.path.join(application_path, directory_name)

        # Verify the directory exists
        if not os.path.exists(target_directory):
            return f"Error: Directory '{directory_name}' does not exist."

        if not os.path.isdir(target_directory):
            return f"Error: '{directory_name}' is not a directory."

        # Generate the tree structure
        tree_lines = []
        tree_lines.append(f"Directory Tree for: {target_directory}")
        tree_lines.append("=" * 80)
        tree_lines.append("")

        def build_tree(path, prefix="", is_last=True):
            """Recursively build the tree structure."""
            try:
                # Get all entries including hidden files
                entries = []
                for entry in os.listdir(path):
                    entry_path = os.path.join(path, entry)
                    entries.append((entry, entry_path, os.path.isdir(entry_path)))

                # Sort: directories first, then files, both alphabetically
                entries.sort(key=lambda x: (not x[2], x[0].lower()))

                for i, (name, entry_path, is_dir) in enumerate(entries):
                    is_last_entry = (i == len(entries) - 1)

                    # Build the tree characters
                    connector = "└── " if is_last_entry else "├── "
                    tree_lines.append(f"{prefix}{connector}{name}{'/' if is_dir else ''}")

                    # Recursively process subdirectories
                    if is_dir:
                        extension = "    " if is_last_entry else "│   "
                        build_tree(entry_path, prefix + extension, is_last_entry)

            except PermissionError:
                tree_lines.append(f"{prefix}[Permission Denied]")
            except Exception as e:
                tree_lines.append(f"{prefix}[Error: {str(e)}]")

        # Start building the tree from the target directory
        tree_lines.append(f"{os.path.basename(target_directory)}/")
        build_tree(target_directory)

        # Add summary statistics
        tree_lines.append("")
        tree_lines.append("=" * 80)

        # Count files and directories
        total_files = 0
        total_dirs = 0
        for root, dirs, files in os.walk(target_directory):
            total_dirs += len(dirs)
            total_files += len(files)

        tree_lines.append(f"Total directories: {total_dirs}")
        tree_lines.append(f"Total files: {total_files}")
        tree_lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Join all lines
        tree_content = "\n".join(tree_lines)

        # Save to content_generated directory under application_path
        content_generated_path = os.path.join(application_path, 'content_generated')

        # Create the directory if it doesn't exist
        if not os.path.exists(content_generated_path):
            os.makedirs(content_generated_path)
        return tree_content
    except Exception as e:
        return f"Error generating tree view: {str(e)}"

async def save_files_from_db(message, channel_layer, room_group_name):
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        application_path = os.path.dirname(application_path) # Go up to agent
        
    content_generated_path = os.path.join(application_path, 'content_generated')
    files = message.split('|')
    
    # Helper to get program (sync wrapped)
    @sync_to_async
    def get_program(name):
        return LLMProgram.objects.get(programName=name)

    for file in files:
        print("Saving file: "+file+"...")
        try:
            program = await get_program(file)
            #Open a file for writing and write the content of program on it in the path 'content_generated_path'...
            with open(os.path.join(content_generated_path, program.programName), 'w', encoding='utf-8') as f:
                f.write(program.programContent)
                f.flush()
                os.fsync(f.fileno())
                f.close()
                print("File: "+file+" saved!")
                if channel_layer:
                    await channel_layer.group_send(
                        room_group_name,
                        {'type': 'agent_message', 'message': 'File: <code>'+content_generated_path+'/'+file+'</code> saved!', 'username': 'LLM_Bot'}
                    )
                print("--- Bot message of file saving broadcasted to room.")
        except Exception as e:
            print(f"!!! ERROR while saving file: {e}")
