# Brave Browser — True Portable ZIP Builder (Windows x64)

**Community builder — not an official Brave portable edition.**

This repository builds a **portable ZIP only**, using Brave's **official Windows x64 ZIP release**, its unmodified browser executable, and the exact full-resolution Windows icon from the matching `brave-core` release tag. GitHub Actions runs **only when you click Run workflow**. It does not install Brave on the GitHub runner or build Chromium from source.

**Initial target:** Brave stable **1.97.59**. Choose a newer **stable numeric** version only after it exists on the [official release page](https://github.com/brave/brave-browser/releases).

## First-time setup — simplest GitHub Desktop method

1. Open https://github.com/new and create an **empty public repository** named `Brave-Portable-Builder`. Do not create a README, `.gitignore`, or license at this stage.
2. Download/extract the builder kit ZIP. It contains `.github`, `builder`, `tests`, `README.md`, `START-HERE.txt`, and `.gitignore`.
3. Open **GitHub Desktop → File → Clone repository**. Select `Brave-Portable-Builder` and choose a convenient folder.
4. Click **Repository → Show in Explorer**. Copy **all of the extracted contents**, including the `.github` folder, into the cloned repository. Do not copy the ZIP itself. Windows Explorer may hide dot folders; show hidden files or use GitHub Desktop.
5. In GitHub Desktop, review Changes; type `Add manual Brave portable builder`, click **Commit to main**, then **Push origin**.
6. On your GitHub repository website, click **Actions → Build Brave True Portable ZIP (Manual) → Run workflow**. Keep `release_version` as `1.97.59` for the first run.
7. If GitHub shows a **green check**, open the finished run and download the artifact named `Brave-TruePortable-1.97.59-x64`. Extract the GitHub-generated ZIP, then extract the `Brave-v1.97.59-TRUE-Portable.zip` inside it.
8. Open `BravePortable/` and double-click **`BravePortable.exe`**. Never launch `App/Brave/brave.exe` directly; that bypasses the portable profile setting.

If GitHub shows a **red X**, download the failed run's **Logs** and provide those to diagnose the exact failed step. The workflow refuses missing checksums, incomplete Windows archives, missing icons, and unsigned or incorrectly signed browser binaries rather than silently generating a bad package.

## Resulting application layout

```text
BravePortable/
  BravePortable.exe                  <-- ALWAYS launch this
  App/
    Brave/
      brave.exe                      <-- original, unmodified executable
      chrome.dll                     <-- original browser dependencies
      ...
    AppInfo/
      appinfo.ini                    <-- PortableApps Menu title/category
      appicon.ico                    <-- ORIGINAL full-resolution Brave icon
      appicon_16.png, appicon_32.png, ...
  Data/                              <-- KEEP during upgrades
    Profile/                         <-- bookmarks, history, extensions, preferences
    Cache/
    Temp/
    Downloads/                       <-- manually choose this in browser settings
    README.txt
  Other/
    buildinfo.txt
```

The browser launcher passes `--user-data-dir` and `--disk-cache-dir` with **absolute paths calculated from its current folder**, and uses child-process-only `TEMP`/`TMP` variables. It does not rewrite the machine/user registry, install system services, disable encryption, or register the browser as Windows' default. The launcher intentionally blocks profile/cache override arguments so you do not accidentally open the host's Chrome/Brave profile.

The PortableApps Menu metadata is a **community PortableApps-style layout**, not a PortableApps.com `.paf.exe` installer or official certification.

## How future updates work

1. Open the official [Brave releases](https://github.com/brave/brave-browser/releases) page and find the latest **stable** version.
2. Click your repository's **Actions → Build Brave True Portable ZIP (Manual) → Run workflow**. Enter the numeric version, without `v` (e.g. `1.97.59`).
3. After a successful build, download and extract the new artifact.
4. **Exit every Brave Portable window and process.** Back up your existing **`Data`** folder to a safe, private location.
5. **Replace only** the existing `App` folder and `BravePortable.exe` with those from the new ZIP. **Do not overwrite `Data`**, ever.
6. Run `BravePortable.exe`. Open `brave://version` and confirm `Profile Path` points inside **`BravePortable\Data\Profile`**. Check your bookmarks/extensions.

**Do not copy your `Data` directory into the public builder repository**. It can contain passwords, cookies, history and access tokens. `.gitignore` is a secondary safeguard, not a substitute for keeping private profile files out of GitHub entirely.

## Windows security & limitations

- **Passwords and cookies:** Brave encrypts sensitive browser data using Windows. Copying the portable profile to a reinstalled Windows system or different Windows user can render stored passwords and cookies unreadable. Do not disable Windows protection to try to fix this. Export bookmarks and use a separately managed password vault when migrating Windows.
- **OS-level encryption updates:** Chromium/Brave may use protection mechanisms tied to the installed application or its path. These may impose further limits on profile use when moving directories. Profile portability does **not** guarantee that encrypted logins work after Windows reinstall or relocation.
- **Brave Wallet / Rewards:** These are sensitive data areas. Test their own official backup/recovery methods separately before formatting Windows or updating major versions.
- **Default browser / external links:** Keep this portable Brave as a **secondary browser** initially. If Windows launches the inner `brave.exe` to open an external link, that bypasses the launcher. Do not set it as Windows' default browser during initial portability testing.
- **Downloads:** In `brave://settings/downloads`, select the `BravePortable\Data\Downloads` directory manually if you want downloaded files inside the portable folder. Our launcher does not silently change browser settings.
- **Other traces:** Chromium/Brave and Windows can still create operating-system records, crash logs, integration files and temporary data. These are **not proven to be remnant-free**. Test with Windows Process Monitor if strict cleanliness is required.
- **Updates:** GitHub Actions builds are **manual only**. Do not rely on the browser's About/Update page to replace portable binaries. Keep Brave patched promptly, since browsers are security-sensitive.

## Security and build checks

This builder:

- Retrieves official release asset details from GitHub's API, **paginating** through large asset lists.
- Selects the **exact** `brave-v<version>-win32-x64.zip` asset and verifies its SHA-256 against the published GitHub digest and/or matching official `.sha256` asset. It refuses an unverified download.
- Checks the official `brave.exe` Windows Authenticode signature and publisher on the GitHub Windows runner.
- Rejects a ZIP missing `brave.exe`, `chrome.dll`, `icudtl.dat`, or `locales`.
- Fetches the actual multi-resolution icon at `brave/brave-core` **the same version tag**. It uses that original ICO for both the root Windows launcher and PortableApps metadata; PNG menu icons are derived from it.
- Uses an **offline test suite** and checks final artifact structure; **never packages an existing user profile**.

No custom PAF builder is added because the proven ZIP-only GitHub Actions approach is simpler.

### First Windows test checklist

1. Before launching: note whether `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data` already exists. Don't delete any existing installed Brave data.
2. Launch **`BravePortable.exe`** and visit `brave://version`. The `Profile Path` must point into `Data\Profile`.
3. Bookmark a page, change Brave Shields preferences, install a small extension, close all Brave Portable windows and reopen. Verify persistence.
4. Recheck host AppData and process history for unexpected new BraveSoftware folders. A new folder means additional investigation is needed before claiming complete portability.
5. Verify PortableApps Menu shows **Brave Portable**, official logo, and **Internet** category.
6. Before a later upgrade, back up `Data`, replace `App` and launcher only, then ensure profile stays intact.

## References

- [Official Brave stable releases](https://github.com/brave/brave-browser/releases)
- [Official Brave icon source (same tag as selected release)](https://github.com/brave/brave-core/blob/v1.97.59/app/theme/brave/win/brave.ico)
- [Brave sensitive data encryption](https://support.brave.com/hc/en-us/articles/29808985123085-Sensitive-data-storage)
- [Brave Windows ZIP archive history](https://github.com/brave/brave-browser/issues/19344)
- [PortableApps.com application structure reference](https://portableapps.com/development/portableapps.com_format)

This community builder is not endorsed or maintained by Brave Software or PortableApps.com. Respect Brave's third-party licenses and branding when redistributing binaries.
