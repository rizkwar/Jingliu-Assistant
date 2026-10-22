"""Shared, dependency-free voice and playback validation."""

VOICES = ("alba", "anna", "azelma", "cosette", "eponine", "fantine", "jane", "vera")


def validate_rate(rate):
    if type(rate) is not int or not 80 <= rate <= 115:
        raise ValueError("Voice delivery rate must be a whole percentage from 80 to 115.")
    return rate


def playback_sample_rate(sample_rate, rate=100):
    """Varispeed playback: lower rates slow speech and lower pitch together."""
    return round(sample_rate * validate_rate(rate) / 100)
