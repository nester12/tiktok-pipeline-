"""Regenerate subtitle timestamps after switching narration providers.

Run after generate_inworld_voice.py has produced narration.wav.
"""
from generate_audio import generate_word_timestamps

if __name__ == "__main__":
    generate_word_timestamps("narration.wav")
