# Third-party notices

The installer-ready toolchain is downloaded from the projects below. The exact
versions, source URLs and SHA-256 checksums are recorded in `tools-manifest.json`.

## Deno 2.8.1

- Project: https://github.com/denoland/deno
- License: MIT
- License text: `THIRD_PARTY_LICENSES/deno-MIT.txt`

## FFmpeg 8.1 LGPL build

- Project: https://ffmpeg.org/
- Windows build provider: https://github.com/BtbN/FFmpeg-Builds
- Selected variant: Windows x64 LGPL
- License text bundled by the selected build: `bin/windows-x64/licenses/ffmpeg-LICENSE.txt`
- License information: https://ffmpeg.org/legal.html

FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.

## Python 3.14

- Project: https://www.python.org/
- License: Python Software Foundation License
- License text: `THIRD_PARTY_LICENSES/Python-PSF-LICENSE.txt`

## Qt for Python / PySide6 / Shiboken6 6.11.1

- Project: https://doc.qt.io/qtforpython-6/
- Community license expression: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
- LGPLv3 text: `THIRD_PARTY_LICENSES/LGPL-3.0.txt`
- GPLv3 text: `LICENSE`

The Windows distribution keeps Qt and PySide6 shared libraries as separate DLL
files in the onedir package. Recipients may replace compatible shared libraries.
Nothing in Apson YTDownloader restricts reverse engineering for debugging changes
to LGPL-covered components.

## Python runtime packages

The distribution also contains yt-dlp, yt-dlp-ejs, requests, certifi, urllib3,
websockets, mutagen, brotli and pycryptodomex. Their exact versions are recorded
in the artifact manifest. License texts are included under
`THIRD_PARTY_LICENSES/python-packages/`.

## Inno Setup 7.0.2

The Windows Setup executable is generated with Inno Setup. The compiler itself
is not redistributed with Apson YTDownloader. Commercial users should review
the current licensing information at https://jrsoftware.org/isorder.php.
