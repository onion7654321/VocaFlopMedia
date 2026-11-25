"""Output format and quality rules."""

VIDEO_FORMATS = ("mp4", "mkv", "webm", "mov", "avi")
AUDIO_FORMATS = ("mp3", "m4a", "aac", "opus", "ogg", "wav", "flac")
LOSSLESS_FORMATS = ("wav", "flac")


def available_formats(audio_only=False):
    return AUDIO_FORMATS if audio_only else VIDEO_FORMATS + AUDIO_FORMATS


def quality_choices(kind, resolutions=(), audio_rates=(320, 256, 192, 128)):
    if kind in LOSSLESS_FORMATS:
        return [0]
    if kind in AUDIO_FORMATS:
        return [q for q in audio_rates if kind != "opus" or q <= 256]
    return list(resolutions)[:4] or [0]


def quality_label(kind, quality):
    if kind in LOSSLESS_FORMATS:
        return "Lossless"
    if kind in AUDIO_FORMATS:
        return f"{quality} kbps"
    return f"{quality}p" if quality else "Best available"


def output_extension(kind):
    return kind
