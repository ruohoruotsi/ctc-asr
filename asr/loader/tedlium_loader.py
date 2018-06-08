"""Load the Tedlium v2 dataset."""

# TODO incomplete

import sys
import os
import re
import math
import subprocess

from multiprocessing import Pool, Lock, cpu_count
from tqdm import tqdm
from scipy.io import wavfile

from asr.params import BASE_PATH, FLAGS
from asr.util.storage import delete_file_if_exists


# Path to the Tedlium v2 dataset.
__DATASETS_PATH = os.path.join(BASE_PATH, '../datasets/speech_data')
__TEDLIUM_PATH = os.path.realpath(os.path.join(__DATASETS_PATH, 'tedlium'))
print('__TEDLIUM_PATH:', __TEDLIUM_PATH)   # TODO


def tedlium_loader(target):
    """Build the output string that can be written to the desired *.txt file.

     Note:
         Since TEDLIUM data is one large .wav file per speaker. Therefore this method creates
         several smaller partial .wav files. This takes some time.

        The large .wav files are being converted into parts, even if `dry_run=True` has been
        selected.

    Args:
        target (str): 'train', 'test', or 'dev'

    Returns:
        [str]: List containing the output string that can be written to *.txt file.
    """

    target_folders = {
        'dev': 'dev',
        'test': 'test',
        'train': 'train'
    }

    target_folder = os.path.join(__TEDLIUM_PATH, 'TEDLIUM_release2', target_folders[target], 'stm')

    # Flag that marks time segments that should be skipped.
    ignore_flag = 'ignore_time_segment_in_scoring'

    # RegEx pattern to extract TEDLIUM's .stm information's.
    format_pattern = re.compile(
        r"[.\w]+ [0-9] [.\w]+ ([0-9]+(?:\.[0-9]+)?) ([0-9]+(?:\.[0-9]+)?) <[\w,]+> ([\w ']+)")

    files = os.listdir(target_folder)

    lock = Lock()
    output = []
    with Pool(processes=cpu_count()) as pool:
        for result in tqdm(pool.imap_unordered(_tedlium_loader_helper, files),
                           desc='Reading audio files', total=len(files), file=sys.stdout,
                           unit='files', dynamic_ncols=True):
            if result is not None:
                lock.acquire()
                output.append(result)
                lock.release()

    return output


def _tedlium_loader_helper(stm_file):
    if os.path.splitext(stm_file)[1] != '.stm':
        # This check is required, since there are swap files, etc. in the TEDLIUM dataset.
        print('WARN: Invalid .stm file found:', stm_file)
        return None

    stm_file_path = os.path.join(target_folder, stm_file)
    with open(stm_file_path, 'r') as f:
        lines = f.readlines()

        wav_path = os.path.join(__TEDLIUM_PATH, 'TEDLIUM_release2', target_folders[target],
                                'sph', '{}.wav'.format(os.path.splitext(stm_file)[0]))
        assert os.path.isfile(wav_path), '{} not found.'.format(wav_path)

        # Load the audio data, to later split it into a part per audio segment.
        (sampling_rate, wav_data) = wavfile.read(wav_path)
        assert sampling_rate == FLAGS.sampling_rate

        for i, line in enumerate(lines):
            if ignore_flag in line:
                continue

            res = re.search(format_pattern, line)
            if res is None:
                raise RuntimeError('TEDLIUM loader error in file {}\nLine: {}'
                                   .format(stm_file_path, line))

            start_time = float(res.group(1))
            end_time = float(res.group(2))
            text = res.group(3)

            # Create new partial .wav file.
            part_path = '{}_{}.wav'.format(wav_path[: -4], i)
            _write_part_to_wav(wav_data, part_path, start_time, end_time)

            # Relative path to DATASET_PATH.
            part_path = os.path.relpath(part_path, __TEDLIUM_PATH)

            # Sanitize lines.
            text = text.lower().replace(" '", '').replace('  ', ' ').strip()

            # Skip labels with less than 5 words.
            if len(text.split(' ')) > 4:
                output.append('{} {}\n'.format(part_path, text))

                return ASDF


def _write_part_to_wav(wav_data, path, start, end, sr=16000):
    assert 0. <= start < (len(wav_data) / sr)
    assert start < end <= (len(wav_data) / sr)

    # print('Saving {:12,d}({:6.2f}s) to {:12,d}({:6.2f}s) at: {}'
    #       .format(seconds_to_sample(start), start, seconds_to_sample(end), end, path))

    delete_file_if_exists(path)
    # TODO Verify that the created WAV files are okay!
    wavfile.write(path, sr, wav_data[_seconds_to_sample(start, True):
                                     _seconds_to_sample(end, False)])


def _seconds_to_sample(seconds, start=True, sr=16000):
    if start:
        return int(math.floor(seconds * sr))
    else:
        return int(math.ceil(seconds * sr))
