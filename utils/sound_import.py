"""
Import Source 1 sound files to Source 2 / s&box.

- Copies .wav / .mp3 from src1 sound/ → s2 sounds/
- Generates .sound asset files referencing the audio
"""

import shutil
from pathlib import Path
import shared.base_utils2 as sh

OVERWRITE = False

# s&box .sound asset template
_SOUND_TEMPLATE = '''<!-- kv3 encoding:text:version{{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d}} format:generic:version{{7412167c-06e9-4698-aff2-e63eb59037e7}} -->
{{
	data =
	{{
		volume = 1.0
		sounds =
		[
			"{rel_path}",
		]
		VolumeRandom = 0.0
		Pitch = 1.0
		PitchRandom = 0.0
		DistanceMax = 3000.0
		ui = false
		selectionmode = "0"
	}}
}}'''

AUDIO_EXTS = {'.wav', '.mp3', '.ogg'}


def main():
    print('Source 2 Sound Importer!')

    sound_dir = Path('sound')
    sounds_dir = Path('sounds')

    if OVERWRITE:
        print(' - Overwrite mode ON')

    # 1. Copy audio files from src1 sound/ → s2 sounds/
    audio_files = list(sh.src(sound_dir).rglob('*'))
    audio_files = [f for f in audio_files if f.suffix.lower() in AUDIO_EXTS]

    if not audio_files:
        print(' - No audio files found in source sound/ directory')
        return

    print(f' - Found {len(audio_files)} audio files')

    copied = 0
    for src_file in audio_files:
        rel = src_file.relative_to(sh.src(sound_dir))
        dst_file = sh.output(sounds_dir / rel)

        if dst_file.exists() and not OVERWRITE:
            continue

        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        copied += 1

    if copied:
        print(f' - Copied {copied} audio files')
    else:
        print(' - All audio files already exist (use Overwrite to replace)')

    # 2. Generate .sound asset files
    generated = 0
    for src_file in audio_files:
        rel = src_file.relative_to(sh.src(sound_dir))
        dst_audio = sounds_dir / rel

        # .sound file goes alongside the audio file
        sound_rel = (sounds_dir / rel).as_posix()
        sound_file = sh.output(sounds_dir / rel).with_suffix('.sound')

        if sound_file.exists() and not OVERWRITE:
            continue

        sound_file.parent.mkdir(parents=True, exist_ok=True)
        content = _SOUND_TEMPLATE.format(rel_path=sound_rel)
        sound_file.write_text(content, encoding='utf-8')
        generated += 1

    if generated:
        print(f' - Generated {generated} .sound asset files')
    else:
        print(' - All .sound files already exist (use Overwrite to replace)')

    print("Looks like we are done with sounds!")
