__config_version__ = 1

GLOBALS = {
    "serializer": "{{major}}.{{minor}}.{{patch}}",
}

FILES = ["README.md", "setup.py", "src/codelog/__init__.py"]

VERSION = ["major", "minor", "patch"]

VCS = {
    "name": "git",
    "commit_message": (
        "Version updated from {{ current_version }}" " to {{ new_version }}"
    ),
}
