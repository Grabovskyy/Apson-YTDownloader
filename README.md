<p align="center">
  <img src="assets/branding/piratecat.png" alt="Apson YTDownloader" width="144">
</p>

# Apson YTDownloader 0.5.2

Desktopowa aplikacja PySide6 do analizy materiałów YouTube i sekwencyjnego
pobierania audio MP3 przez yt-dlp oraz FFmpeg. Obsługuje pojedyncze filmy,
ograniczone playlisty, anulowanie, historię, ustawienia i szybkie przekazywanie
bieżącej strony z przeglądarki.

> **Windows 10/11, 64-bit.** Gotowy installer i wersja portable znajdują się
> w sekcji [Releases](https://github.com/Grabovskyy/Apson-YTDownloader/releases/latest).

## Najważniejsze funkcje

- pobieranie audio MP3 w jakości 128, 192, 256 lub 320 kbps,
- analiza pojedynczych filmów i ograniczonych playlist,
- sekwencyjna kolejka, postęp, anulowanie i obsługa częściowych błędów,
- historia pobrań oraz konfigurowalne katalogi danych,
- szybkie przekazywanie linku z przeglądarki przez protokół aplikacji,
- dołączony i przypięty wersjami toolchain FFmpeg, ffprobe oraz Deno,
- installer i wersja portable niewymagające globalnej instalacji Pythona.

## Instalacja i pierwsze użycie

1. Pobierz `Apson-YTDownloader-Setup-0.5.2.exe` z najnowszego wydania.
2. Uruchom instalator i wybierz katalog aplikacji oraz katalog danych.
3. Wklej adres filmu lub playlisty YouTube i kliknij **Analizuj**.
4. Zaznacz materiały, wybierz jakość MP3 i rozpocznij pobieranie.

Alternatywnie rozpakuj `Apson-YTDownloader-Portable-0.5.2.zip` na zapisywalnym
dysku i uruchom `ApsonYTDownloader.exe`. Wersja portable przechowuje dane obok
aplikacji i nie rejestruje protokołu przeglądarki.

Installer nie jest podpisany cyfrowo, dlatego Windows SmartScreen może
wyświetlić ostrzeżenie. Publikowane wydanie zawiera manifest SHA-256 pozwalający
zweryfikować pobrane pliki.

Używaj aplikacji wyłącznie do pobierania treści, do których masz odpowiednie
prawa lub zgodę. Użytkownik odpowiada za sposób wykorzystania programu.

## Uruchomienie developerskie na dysku D:

Projekt nie instaluje zależności globalnie. Przykładowe środowisko utrzymujące
venv, cache pip i pliki tymczasowe na `D:`:

```powershell
New-Item -ItemType Directory -Force D:\Dev\pip-cache\YTDownloader | Out-Null
New-Item -ItemType Directory -Force D:\Dev\tmp\YTDownloader | Out-Null
$env:PIP_CACHE_DIR = "D:\Dev\pip-cache\YTDownloader"
$env:TEMP = "D:\Dev\tmp\YTDownloader"
$env:TMP = "D:\Dev\tmp\YTDownloader"
py -m venv D:\Dev\YTDownloader-venv
Set-Location D:\Apson-YTdownloader
D:\Dev\YTDownloader-venv\Scripts\python.exe -m pip install -r requirements.txt
D:\Dev\YTDownloader-venv\Scripts\python.exe scripts\fetch_tools.py
D:\Dev\YTDownloader-venv\Scripts\python.exe main.py
```

Aplikacja nie szuka FFmpeg ani Deno w systemowym `PATH`. Używa wyłącznie
zweryfikowanych plików `ffmpeg.exe`, `ffprobe.exe` i `deno.exe` z
`bin/windows-x64/`. Wersje, źródła i SHA-256 opisuje `tools-manifest.json`.

## Szybki link z przeglądarki

Installer rejestruje dla bieżącego użytkownika protokół:

```text
apson-ytdownloader://add?url=<zakodowany-adres-http-lub-https>
```

W Ustawieniach znajduje się przycisk otwierający lokalną instrukcję oraz
kopiujący kod przeciąganej zakładki. Kolejne wywołanie protokołu przekazuje link
do już działającej instancji. Jeśli trwa analiza, deduplikowany URL czeka na jej
zakończenie. Wersja portable nie modyfikuje rejestru Windows.

## Lokalizacje danych

Kod aplikacji nie zawiera zakodowanej litery dysku. Installer pozwala osobno
wybrać katalog programu oraz katalog danych i zapisuje obok EXE plik
`app-config.json`. Ustawienia, cache, historia, miniatury, temp i logi trafiają
pod wybrany katalog danych. Portable ZIP zawiera znacznik `.portable` i zapisuje
dane w podkatalogu `data` obok aplikacji.

Rozwój lokalny domyślnie korzysta z `data/` w repozytorium. Dostępne są też
zmienne `YTDOWNLOADER_DATA_DIR`, `YTDOWNLOADER_PORTABLE` oraz osobne nadpisania
`YTDOWNLOADER_SETTINGS_DIR`, `YTDOWNLOADER_CACHE_DIR`,
`YTDOWNLOADER_HISTORY_DIR`, `YTDOWNLOADER_THUMBNAILS_DIR`,
`YTDOWNLOADER_TEMP_DIR`, `YTDOWNLOADER_LOGS_DIR` i
`YTDOWNLOADER_DOWNLOADS_DIR`.

## Testy i build Windows

```powershell
D:\Dev\YTDownloader-venv\Scripts\python.exe -m unittest discover -s tests -v
D:\Dev\YTDownloader-venv\Scripts\python.exe -m compileall app main.py scripts tests

.\scripts\build_windows.ps1 `
  -PythonExecutable D:\Dev\YTDownloader-venv\Scripts\python.exe `
  -BuildRoot D:\Dev\ApsonYTDownloader-build `
  -ArtifactsRoot D:\Dev\ApsonYTDownloader-artifacts\0.5.2 `
  -InnoCompiler D:\Dev\InnoSetup-7\ISCC.exe
```

Build używa PyInstaller `onedir`, uruchamia zamrożony `--self-test`, tworzy
portable ZIP, opcjonalnie kompiluje per-user installer Inno Setup i generuje
manifest SHA-256. Katalogi robocze muszą znajdować się poza repozytorium.

Installer i ZIP są niepodpisane cyfrowo, dlatego Windows SmartScreen może
wyświetlić ostrzeżenie. Podpisywanie wymaga osobnego certyfikatu.

Podczas zwykłej dezinstalacji installer pyta, czy usunąć również zarządzane
dane aplikacji. Domyślnie zachowuje ustawienia, historię i pobrania. Wybranie
usunięcia danych kasuje również MP3 z katalogu `data\downloads`, ale nie dotyka
pobrań zapisanych w innym folderze. Cicha dezinstalacja zachowuje dane, chyba że
zostanie jawnie uruchomiona z parametrem `/PURGEDATA=1`.

Installer jest generowany przez Inno Setup 7.0.2. Przy wykorzystaniu projektu
komercyjnie należy sprawdzić aktualne zasady licencji komercyjnej Inno Setup:
https://jrsoftware.org/isorder.php.

Licencje dystrybuowanych składników znajdują się w
`THIRD_PARTY_NOTICES.md` i `THIRD_PARTY_LICENSES/`.

## Licencja i branding

Kod źródłowy Apson YTDownloader jest udostępniany na warunkach
[GNU General Public License v3.0](LICENSE). Licencja wymaga, aby
rozpowszechniane modyfikacje pozostały otwarte na tych samych warunkach.

Nazwa produktu, logo oraz sposób oznaczania oficjalnych wydań podlegają zasadom
opisanym w [BRANDING.md](BRANDING.md). Licencja kodu nie pozwala sugerować, że
zmodyfikowany fork jest oficjalnym wydaniem projektu.
