# Build on Windows with the hash-locked dependencies from the build toolchain.
# The user runs the finished portable EXE; this file is for developers only.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

project = Path(SPECPATH).resolve().parent
ffmpeg = Path(os.environ['MAYCOM_FFMPEG_DIR']).resolve()
if not (ffmpeg / 'ffmpeg.exe').is_file() or not (ffmpeg / 'ffprobe.exe').is_file():
    raise RuntimeError('MAYCOM_FFMPEG_DIR must contain verified Windows FFmpeg/FFprobe binaries and their adjacent DLLs.')

datas = [(str(project / 'frontend' / 'dist'), 'frontend/dist'), (str(ffmpeg / '*'), 'bin')]
license_path = ffmpeg.parent / 'LICENSE.txt'
if license_path.is_file():
    datas.append((str(license_path), 'licenses/ffmpeg'))
datas += copy_metadata('fastapi') + copy_metadata('fal-client', recursive=True)

a = Analysis([str(project / 'desktop' / 'launcher.py')], pathex=[str(project / 'backend')], binaries=[], datas=datas,
             hiddenimports=collect_submodules('uvicorn'), hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
# External FFmpeg programs find their DLLs beside themselves in bin/.
# Avoid also carrying PyInstaller's duplicate copies at the collection root.
dlls = {item.name.lower() for item in ffmpeg.glob('*.dll')}
a.binaries = [entry for entry in a.binaries if not (entry[0].lower() in dlls and Path(entry[1]).parent.resolve() == ffmpeg)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MaycomBackend', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=True, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MaycomBackend')
