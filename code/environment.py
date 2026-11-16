"""Record reproducible runtime metadata without credentials (paper Appendix I).

Usage: imported by runners; capture_environment([source_file, ...]) returns log fields.
Reads the repository's HEAD/ref files directly, never git configuration or commands.
An unborn repository or unsupported worktree layout leaves its commit unknown.
Package metadata reports the optional plotting dependency when installed; no package
is installed or imported to obtain its version. No machine hostname or user path is logged.
"""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import re

ROOT = Path(__file__).resolve().parents[1]


def git_commit(root=ROOT):
    git = Path(root)/'.git'
    if not git.is_dir():
        return None
    try:
        value = (git/'HEAD').read_text().strip()
        if re.fullmatch(r'[0-9a-fA-F]{40,64}',value):
            return value
        if not value.startswith('ref: refs/'):
            return None
        ref = value[5:]
        if '..' in Path(ref).parts:
            return None
        loose = git/ref
        if loose.is_file():
            value = loose.read_text().strip()
            return value if re.fullmatch(r'[0-9a-fA-F]{40,64}',value) else None
        packed = git/'packed-refs'
        if packed.exists():
            for line in packed.read_text().splitlines():
                parts = line.split()
                if len(parts)==2 and parts[1]==ref and re.fullmatch(r'[0-9a-fA-F]{40,64}',parts[0]):
                    return parts[0]
    except OSError:
        return None
    return None


def capture_environment(files=()):
    packages = {}
    try:
        packages['matplotlib'] = importlib.metadata.version('matplotlib')
    except importlib.metadata.PackageNotFoundError:
        pass
    hashes = {}
    for filename in files:
        path = Path(filename)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(python=platform.python_version(), platform=platform.platform(), packages=packages,
                git_commit=git_commit(), code_sha256=hashes)
