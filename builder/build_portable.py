"""Build BravePortable ZIP from an official GitHub Windows ZIP (not an installer).

Fail closed on unexpected GitHub asset metadata, incomplete browser releases,
missing original icons, invalid ZIP files, or unrecognized file layouts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

REPO = 'brave/brave-browser'
UA = 'BravePortableBuilder/1.0 (manual GitHub Actions packager)'
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
HASH_RE = re.compile(r'^[a-fA-F0-9]{64}$')
MAX_UNPACKED = 4 * 1024 * 1024 * 1024


def url_get(url: str, *, accept: str = 'application/vnd.github+json') -> bytes:
    headers = {'User-Agent': UA, 'Accept': accept, 'X-GitHub-Api-Version': '2022-11-28'}
    # Authenticate API reads on GitHub Actions to avoid shared-runner rate limits.
    # Never send the GitHub token to download/CDN or raw-content hosts.
    token = os.environ.get('GITHUB_TOKEN', '')
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def api_get(url: str):
    return json.loads(url_get(url).decode('utf-8'))


def validate_version(version: str):
    if not VERSION_RE.fullmatch(version):
        raise RuntimeError('Version must be a stable numeric release like 1.97.59. Do not include v, beta, or nightly.')


def fetch_release_and_assets(version: str):
    validate_version(version)
    release = api_get(f'https://api.github.com/repos/{REPO}/releases/tags/v{version}')
    if release.get('draft') or release.get('prerelease'):
        raise RuntimeError('This is not an official published stable release.')
    if release.get('tag_name') != f'v{version}':
        raise RuntimeError('GitHub release tag mismatch.')
    assets = []
    for page in range(1, 15):
        batch = api_get(f'https://api.github.com/repos/{REPO}/releases/{release["id"]}/assets?per_page=100&page={page}')
        if not isinstance(batch, list):
            raise RuntimeError('Unexpected GitHub asset response.')
        assets.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError('Release has too many asset pages; update builder.')
    if not assets:
        raise RuntimeError('No release assets returned from GitHub.')
    return release, assets


def exact_asset(assets, name: str):
    matches = [item for item in assets if item.get('name') == name]
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one official asset {name}; found {len(matches)}')
    item = matches[0]
    url = item.get('browser_download_url', '')
    if not url.startswith('https://github.com/brave/brave-browser/releases/download/'):
        raise RuntimeError(f'Unexpected download domain for {name}: {url}')
    return item


def published_hash(archive, checksum_asset, filename):
    digest = archive.get('digest') or ''
    if digest and not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise RuntimeError('Invalid GitHub digest format; refusing to continue.')
    api_hash = digest.split(':', 1)[1].lower() if digest else None
    text = None
    if checksum_asset:
        raw = url_get(checksum_asset['browser_download_url'], accept='application/octet-stream')
        if len(raw) > 8192:
            raise RuntimeError('Unexpectedly large checksum file.')
        text = raw.decode('utf-8-sig').strip()
    sha = None
    if text:
        for line in text.splitlines():
            # Accept <hash>  <filename> or just <hash> in exact-name .sha256.
            match = re.match(r'^([0-9a-fA-F]{64})(?:\s+\*?(.+))?\s*$', line.strip())
            if match and (not match.group(2) or Path(match.group(2).replace('\\', '/')).name == filename):
                sha = match.group(1).lower()
                break
        if not sha:
            raise RuntimeError('Official checksum file does not name the expected archive.')
    if api_hash and sha and api_hash != sha:
        raise RuntimeError('GitHub digest and checksum-file hash disagree.')
    if not (api_hash or sha):
        raise RuntimeError('No independently published SHA-256 found (GitHub digest or matching .sha256). Refusing unsafe build.')
    return api_hash or sha


def download_and_verify(url: str, destination: Path, expected_hash: str) -> None:
    if not HASH_RE.fullmatch(expected_hash):
        raise RuntimeError('Expected SHA-256 missing or malformed.')
    dest_temp = destination.with_suffix('.part')
    if dest_temp.exists():
        dest_temp.unlink()
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/octet-stream'})
    try:
        with urllib.request.urlopen(req, timeout=120) as stream, dest_temp.open('wb') as out:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                h.update(block)
                out.write(block)
        if h.hexdigest().lower() != expected_hash.lower():
            raise RuntimeError(f'Official Brave archive SHA-256 mismatch: expected {expected_hash}, got {h.hexdigest()}')
        dest_temp.replace(destination)
    finally:
        if dest_temp.exists():
            dest_temp.unlink()


def inspect_archive(z: zipfile.ZipFile):
    total = 0
    seen = set()
    for item in z.infolist():
        name = item.filename.replace('\\', '/')
        parts = name.split('/')
        if (name.startswith('/') or '\x00' in name or any(p in ('..', '') for p in parts if p != parts[-1])
            or ':' in name or any(p == '..' for p in parts)):
            raise RuntimeError(f'Unsafe ZIP member: {name}')
        norm = '/'.join(parts).lower().rstrip('/')
        if norm in seen:
            raise RuntimeError(f'Duplicate ZIP member: {name}')
        seen.add(norm)
        total += item.file_size
        if total > MAX_UNPACKED:
            raise RuntimeError('Unusually large official ZIP; manual review required.')
    executables = [p for p in z.namelist() if p.replace('\\','/').lower().endswith('/brave.exe') or p.lower() == 'brave.exe']
    if len(executables) != 1:
        raise RuntimeError(f'Expected exactly one brave.exe, found {len(executables)}')
    prefix = Path(executables[0]).parent.as_posix()
    return prefix


def extract_app(archive: Path, app: Path):
    with zipfile.ZipFile(archive) as z:
        prefix = inspect_archive(z)
        z.extractall(app.parent / '_brave_unpacked')
    unboxed = app.parent / '_brave_unpacked'
    source = unboxed / prefix if prefix != '.' else unboxed
    if not source.is_dir():
        raise RuntimeError('Brave ZIP was extracted but executable directory missing.')
    shutil.move(str(source), str(app))
    shutil.rmtree(unboxed, ignore_errors=True)
    validate_app(app)


def validate_app(app: Path):
    required = ['brave.exe', 'chrome.dll', 'icudtl.dat']
    # Some releases place versioned DLL/resource files under a version directory.
    found_names = {p.name.lower() for p in app.rglob('*') if p.is_file()}
    missing = [item for item in required if item.lower() not in found_names]
    if missing or not (app / 'brave.exe').is_file():
        raise RuntimeError('Incomplete Brave Windows ZIP (missing essential browser files: ' + ', '.join(missing) + ').')
    if not any(p.name.lower() == 'locales' and p.is_dir() for p in app.rglob('locales')):
        raise RuntimeError('Incomplete Brave Windows ZIP: locales directory missing.')


def compile_icon_pngs(ico: Path, appinfo: Path):
    from PIL import Image
    with Image.open(ico) as img:
        # Preserve original full-res ICO unchanged. Produce copies for the menu.
        for px in [16, 32, 48, 128, 256]:
            sizes = img.ico.sizes()
            bigger = [sz for sz in sizes if min(sz) >= px]
            chosen = min(bigger, key=lambda t: t[0] * t[1]) if bigger else max(sizes, key=lambda t: t[0]*t[1])
            scaled = img.ico.getimage(chosen).convert('RGBA')
            if scaled.size != (px, px):
                scaled = scaled.resize((px, px), Image.Resampling.LANCZOS)
            scaled.save(appinfo / f'appicon_{px}.png')


def write_appinfo(target: Path, version: str):
    segments = version.split('.')
    package_ver = '.'.join(segments + ['0'])
    target.write_text(f'''[Format]
Type=PortableApps.comFormat
Version=3.9

[Details]
Name=Brave Portable
AppID=BravePortable
Publisher=Brave Software, Inc. / Community portability packaging
Homepage=https://github.com/brave/brave-browser
Category=Internet
Description=Community-packaged official Brave Browser stable build.
Language=Multilingual

[License]
Shareable=true
OpenSource=true
Freeware=true
CommercialUse=true

[Version]
PackageVersion={package_ver}
DisplayVersion={version}

[Control]
Icons=1
Start=BravePortable.exe
''', encoding='utf-8')


def verify_signature(app_exe: Path):
    if os.name != 'nt':
        raise RuntimeError('Authenticode verification requires Windows.')
    path = str(app_exe).replace("'", "''")
    ps = (
        "$s=Get-AuthenticodeSignature -LiteralPath '" + path + "'; "
        "if ($s.Status -ne 'Valid') {throw \"Invalid Brave executable signature: $($s.Status)\"}; "
        "if ($s.SignerCertificate.Subject -notmatch 'Brave Software') {throw \"Unexpected Brave executable publisher: $($s.SignerCertificate.Subject)\"}; "
        "Write-Host $s.SignerCertificate.Subject"
    )
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps], check=True)


def build(root: Path, version: str):
    validate_version(version)
    release, assets = fetch_release_and_assets(version)
    basename = f'brave-v{version}-win32-x64.zip'
    release_asset = exact_asset(assets, basename)
    match = [x for x in assets if x.get('name') == basename + '.sha256']
    checksum_asset = exact_asset(assets, basename + '.sha256') if match else None
    sha = published_hash(release_asset, checksum_asset, basename)

    temp = root / '_downloads'
    temp.mkdir(parents=True, exist_ok=True)
    archive = temp / basename
    print('Downloading Brave stable', version, 'and verifying SHA-256: ', sha, flush=True)
    download_and_verify(release_asset['browser_download_url'], archive, sha)

    stage = root / 'stage' / 'BravePortable'
    if stage.exists():
        shutil.rmtree(stage)
    app = stage / 'App' / 'Brave'
    app.parent.mkdir(parents=True, exist_ok=True)
    extract_app(archive, app)
    verify_signature(app / 'brave.exe')

    appinfo = stage / 'App' / 'AppInfo'
    appinfo.mkdir(parents=True, exist_ok=True)
    ico_url = f'https://raw.githubusercontent.com/brave/brave-core/v{version}/app/theme/brave/win/brave.ico'
    icon_data = url_get(ico_url, accept='application/octet-stream')
    if not icon_data.startswith(b'\x00\x00\x01\x00') or len(icon_data) < 1024:
        raise RuntimeError('Cannot retrieve official full-resolution Brave ICO at selected release tag.')
    ico = appinfo / 'appicon.ico'
    ico.write_bytes(icon_data)
    compile_icon_pngs(ico, appinfo)
    write_appinfo(appinfo / 'appinfo.ini', version)

    for folder in ['Profile', 'Cache', 'Temp', 'Downloads']:
        (stage / 'Data' / folder).mkdir(parents=True, exist_ok=True)
    (stage / 'Data' / 'README.txt').write_text(
        'PRESERVE THIS FOLDER ON UPGRADES.\nYour Brave profile, bookmarks, extension data, browsing history and caches are stored here.\n'
        'Never commit this folder to a public GitHub repository.\n'
        'Web passwords/cookies are encrypted using Windows; they may not survive a Windows reinstall.\n'
        'Default download location must be changed manually in brave://settings/downloads if wanted.\n',
        encoding='utf-8')
    other = stage / 'Other'
    other.mkdir(parents=True, exist_ok=True)
    (other / 'buildinfo.txt').write_text(
        f'Unofficial Brave Portable wrapper\nOfficial Brave release: https://github.com/brave/brave-browser/releases/tag/v{version}\n'
        f'Archive: {basename}\nVerified SHA256: {sha}\nIcon: https://github.com/brave/brave-core/blob/v{version}/app/theme/brave/win/brave.ico\n'
        'Launcher and package are community-provided, not an official Brave portable distribution.\n', encoding='utf-8')

    print('Staged:', stage)
    return stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='1.97.59')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args()
    stage = build(args.root.resolve(), args.version)
    print(f'BRAVE_STAGE={stage}', flush=True)


if __name__ == '__main__':
    main()
