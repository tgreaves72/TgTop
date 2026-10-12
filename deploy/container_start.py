"""Initialize only the mounted data directory, then drop container privileges."""
import os
import sys
from pathlib import Path

if os.geteuid() == 0:
    import pwd
    account = pwd.getpwnam('tgtop')
    root = Path('/data')
    if root.is_symlink() or root.resolve() != root:
        raise RuntimeError('Unexpected data mount')
    root.mkdir(exist_ok=True)
    os.chown(root, account.pw_uid, account.pw_gid)
    os.chmod(root, 0o700)
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
if len(sys.argv) < 2:
    raise RuntimeError('Container command required')
os.execvp(sys.argv[1], sys.argv[1:])
