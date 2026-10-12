"""Stable private storage independent of launch directory or installation version."""
import os
from pathlib import Path


def data_root():
    configured = os.environ.get('TGTOP_DATA')
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == 'nt':
        # AppData is redirected by Windows app containers, including Store Python.
        # A user-profile directory gives native and source processes one physical store.
        return Path.home() / '.tgtop' / 'data'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'tgtop'
