"""Verify the final Brave Portable artifact has expected assets and no real user data."""
from __future__ import annotations
import argparse
from pathlib import Path
import zipfile


def verify(path: Path):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        required = [
            'BravePortable/BravePortable.exe',
            'BravePortable/App/Brave/brave.exe',
            'BravePortable/App/AppInfo/appinfo.ini',
            'BravePortable/App/AppInfo/appicon.ico',
            'BravePortable/App/AppInfo/appicon_16.png',
            'BravePortable/App/AppInfo/appicon_32.png',
            'BravePortable/Data/README.txt',
            'BravePortable/Other/buildinfo.txt',
        ]
        missing = [x for x in required if x not in names]
        if missing:
            raise RuntimeError('Missing required package files: ' + ', '.join(missing))
        # The builder ZIP must be free of browsing history, cookies and passwords.
        dangerous = [x for x in names if x.startswith('BravePortable/Data/') and x != 'BravePortable/Data/README.txt'
                     and not x.endswith('/')]
        if dangerous:
            raise RuntimeError('Unexpected personal data in build artifact: ' + ', '.join(dangerous))
        appinfo = z.read('BravePortable/App/AppInfo/appinfo.ini').decode()
        for value in ['Name=Brave Portable', 'Start=BravePortable.exe', 'Category=Internet']:
            if value not in appinfo:
                raise RuntimeError('PortableApps metadata missing: ' + value)
        with z.open('BravePortable/App/AppInfo/appicon.ico') as icon:
            if icon.read(4) != b'\x00\x00\x01\x00':
                raise RuntimeError('Original Windows icon has invalid ICO header.')
    print(f'ZIP verification passed: {path.name}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('zip_file', type=Path)
    verify(ap.parse_args().zip_file)
