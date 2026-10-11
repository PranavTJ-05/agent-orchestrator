from __future__ import annotations

import os
from typing import Any

from ..core.tool import Tool


class ReadFileTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="read_file",
            description="Read the contents of a file. Use this to read text files, code, logs, etc.",
        )

    async def execute(self, file_path: str) -> str:
        """Read a file and return its contents."""
        try:
            # Security: only allow reading files within current directory or subdirectories
            # Prevent directory traversal attacks
            abs_path = os.path.abspath(file_path)
            if not abs_path.startswith(os.getcwd()):
                return f"Error: Access denied. File must be within current working directory."
            
            with open(abs_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"Error: File not found: {file_path}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="write_file",
            description="Write content to a file. Use this to create or overwrite text files.",
        )

    async def execute(self, file_path: str, content: str) -> str:
        """Write content to a file."""
        try:
            # Security: only allow writing files within current directory or subdirectories
            abs_path = os.path.abspath(file_path)
            if not abs_path.startswith(os.getcwd()):
                return f"Error: Access denied. File must be within current working directory."
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else '.', exist_ok=True)
            
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="edit_file",
            description="Edit a file by replacing specific text. Use this to modify existing files.",
        )

    async def execute(self, file_path: str, old_string: str, new_string: str) -> str:
        """Replace old_string with new_string in a file."""
        try:
            # Security: only allow editing files within current directory or subdirectories
            abs_path = os.path.abspath(file_path)
            if not abs_path.startswith(os.getcwd()):
                return f"Error: Access denied. File must be within current working directory."
            
            if not os.path.exists(abs_path):
                return f"Error: File not found: {file_path}"
            
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_string not in content:
                return f"Error: String not found in file: {repr(old_string)}"
            
            new_content = content.replace(old_string, new_string)
            
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"Successfully edited {file_path}"
        except Exception as e:
            return f"Error editing file: {str(e)}"


class ListDirectoryTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="list_directory",
            description="List contents of a directory. Use this to see what files and folders exist.",
        )

    async def execute(self, directory_path: str = ".") -> str:
        """List contents of a directory."""
        try:
            # Security: only allow listing directories within current directory or subdirectories
            abs_path = os.path.abspath(directory_path)
            if not abs_path.startswith(os.getcwd()):
                return f"Error: Access denied. Directory must be within current working directory."
            
            if not os.path.isdir(abs_path):
                return f"Error: Not a directory: {directory_path}"
            
            items = []
            for item in sorted(os.listdir(abs_path)):
                item_path = os.path.join(abs_path, item)
                if os.path.isdir(item_path):
                    items.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(item_path)
                    items.append(f"📄 {item} ({size} bytes)")
            
            if not items:
                return f"Directory is empty: {directory_path}"
            
            return f"Contents of {directory_path}:\n" + "\n".join(items)
        except Exception as e:
            return f"Error listing directory: {str(e)}"