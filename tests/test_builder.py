"""Offline tests: no user data, downloads or Windows runtime needed."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from unittest.mock import patch
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('brave_build', root / 'builder' / 'build_portable.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
spec2 = importlib.util.spec_from_file_location('brave_verify', root / 'builder' / 'verify_zip.py')
verify = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(verify)


class BraveBuilderTests(unittest.TestCase):
    def test_stable_version_is_accepted(self):
        build.validate_version('1.97.59')

    def test_malformed_versions_rejected(self):
        for value in ['v1.97.59', '1.97.59-beta.1', 'latest', '', '../evil', '1.97.59;rm']:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                build.validate_version(value)

    def test_asset_selection_is_exact(self):
        item = {'name': 'brave-v1.97.59-win32-x64.zip', 'browser_download_url': 'https://github.com/brave/brave-browser/releases/download/v1.97.59/brave-v1.97.59-win32-x64.zip'}
        self.assertEqual(build.exact_asset([item], item['name']), item)
        with self.assertRaises(RuntimeError):
            build.exact_asset([], item['name'])
        with self.assertRaises(RuntimeError):
            build.exact_asset([item, item], item['name'])

    def test_untrusted_asset_host_is_blocked(self):
        with self.assertRaises(RuntimeError):
            build.exact_asset([{'name': 'x', 'browser_download_url': 'https://example.com/x'}], 'x')

    def test_checksum_from_api_digest(self):
        h = 'a' * 64
        self.assertEqual(build.published_hash({'digest': 'sha256:' + h}, None, 'example.zip'), h)

    def test_checksum_unavailable_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build.published_hash({}, None, 'example.zip')

    def test_checksum_format_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build.published_hash({'digest': 'sha1:aabb'}, None, 'example.zip')

    def test_zip_file_layout_single_brave_exe(self):
        with TemporaryDirectory() as t:
            p = Path(t) / 'test.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('Chrome-bin/brave.exe', b'brave')
                z.writestr('Chrome-bin/chrome.dll', b'dll')
                z.writestr('Chrome-bin/icudtl.dat', b'dat')
                z.writestr('Chrome-bin/locales/en-US.pak', b'lang')
            with zipfile.ZipFile(p) as z:
                self.assertEqual(build.inspect_archive(z), 'Chrome-bin')

    def test_zip_member_path_traversal_blocked(self):
        with TemporaryDirectory() as t:
            p = Path(t) / 'bad.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('../outside.exe', b'exe')
                z.writestr('Chrome-bin/brave.exe', b'exe')
            with zipfile.ZipFile(p) as z, self.assertRaises(RuntimeError):
                build.inspect_archive(z)

    def test_missing_browser_library_is_rejected(self):
        with TemporaryDirectory() as t:
            p = Path(t)
            (p / 'brave.exe').write_bytes(b'x')
            with self.assertRaises(RuntimeError):
                build.validate_app(p)

    def test_appinfo_has_required_menu_entries(self):
        with TemporaryDirectory() as t:
            path = Path(t) / 'appinfo.ini'
            build.write_appinfo(path, '1.97.59')
            content = path.read_text()
            self.assertIn('Name=Brave Portable', content)
            self.assertIn('Start=BravePortable.exe', content)
            self.assertIn('PackageVersion=1.97.59.0', content)

    def test_verify_zip_rejects_personal_data(self):
        with TemporaryDirectory() as t:
            p = Path(t) / 'bad.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('BravePortable/Data/Profile/Default/Login Data', 'sensitive')
            with self.assertRaises(RuntimeError):
                verify.verify(p)

    def test_launcher_always_scopes_profile(self):
        code = (root / 'builder' / 'BravePortable.cs').read_text()
        self.assertIn('--user-data-dir=', code)
        self.assertIn(r'Data\User Data', code)
        self.assertIn(r'Data\Profile', code)  # migration guard only
        self.assertIn('legacyHasData && !newHasData', code)
        self.assertIn('--disk-cache-dir=', code)
        self.assertIn('Directory.CreateDirectory(profile)', code)
        self.assertNotIn('CryptUnprotectData', code)

    def test_packager_stages_user_data_directory(self):
        code = (root / 'builder' / 'build_portable.py').read_text()
        self.assertIn("for folder in ['User Data', 'Cache', 'Temp', 'Downloads']:", code)
        self.assertNotIn("for folder in ['Profile', 'Cache', 'Temp', 'Downloads']:", code)

    def test_reject_legacy_profile_in_new_zip(self):
        with TemporaryDirectory() as t:
            p = Path(t) / 'legacy.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr('BravePortable/Data/Profile/', '')
            with self.assertRaisesRegex(RuntimeError, 'Old Data/Profile layout'):
                verify.verify(p)

    def test_correct_zip_verification(self):
        with TemporaryDirectory() as t:
            p = Path(t) / 'correct.zip'
            prefix = 'BravePortable/'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr(prefix + 'BravePortable.exe', b'launcher')
                z.writestr(prefix + 'App/Brave/brave.exe', b'official browser')
                z.writestr(prefix + 'App/AppInfo/appinfo.ini',
                           'Name=Brave Portable\nStart=BravePortable.exe\nCategory=Internet\n')
                z.writestr(prefix + 'App/AppInfo/appicon.ico', b'\x00\x00\x01\x00original ico')
                z.writestr(prefix + 'App/AppInfo/appicon_16.png', b'png')
                z.writestr(prefix + 'App/AppInfo/appicon_32.png', b'png')
                z.writestr(prefix + 'Data/README.txt', 'Keep Data!')
                z.writestr(prefix + 'Other/buildinfo.txt', 'Brave stable release')
            verify.verify(p)

    def test_signature_success_uses_windows_sdk_and_checks_publisher(self):
        fake = SimpleNamespace(returncode=0, stdout="""Signing Certificate Chain:
   Issued to: Brave Software, Inc.
   Issued by: Trusted Code Signing CA
Successfully verified: brave.exe""")
        with patch.object(build, 'os', SimpleNamespace(name='nt')), \
             patch.object(build, 'find_signtool', return_value=Path('C:/sdk/signtool.exe')), \
             patch.object(build.subprocess, 'run', return_value=fake) as run:
            build.verify_signature(Path('D:/stage/brave.exe'))
            self.assertEqual(run.call_args.args[0][1:4], ['verify', '/pa', '/v'])
            self.assertNotIn('powershell.exe', run.call_args.args[0])

    def test_signature_invalid_fails_closed(self):
        fake = SimpleNamespace(returncode=1, stdout='Error: not digitally signed')
        with patch.object(build, 'os', SimpleNamespace(name='nt')), \
             patch.object(build, 'find_signtool', return_value=Path('C:/sdk/signtool.exe')), \
             patch.object(build.subprocess, 'run', return_value=fake):
            with self.assertRaisesRegex(RuntimeError, 'not trusted'):
                build.verify_signature(Path('D:/stage/brave.exe'))

    def test_signature_wrong_publisher_fails_closed(self):
        fake = SimpleNamespace(returncode=0, stdout='Signing Certificate Chain:\n Issued to: Example Corp\nSuccessfully verified: brave.exe')
        with patch.object(build, 'os', SimpleNamespace(name='nt')), \
             patch.object(build, 'find_signtool', return_value=Path('C:/sdk/signtool.exe')), \
             patch.object(build.subprocess, 'run', return_value=fake):
            with self.assertRaisesRegex(RuntimeError, 'Brave Software'):
                build.verify_signature(Path('D:/stage/brave.exe'))

    def test_sign_tool_absent_fails_closed(self):
        with patch.dict(build.os.environ, {}, clear=True), \
             patch.object(build.shutil, 'which', return_value=None), \
             patch.object(build.Path, 'is_dir', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'SignTool not found'):
                build.find_signtool()

    def test_signature_uses_sdk_not_powershell(self):
        source = (root / 'builder' / 'build_portable.py').read_text()
        self.assertIn("'verify', '/pa', '/v'", source)
        self.assertNotIn("subprocess.run(['powershell.exe'", source)

    def test_workflow_is_manual_and_zip_only(self):
        workflow = (root / '.github/workflows/build-brave-portable.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertNotIn('.paf.exe', workflow)
        self.assertIn('upload-artifact', workflow)


if __name__ == '__main__':
    unittest.main()
