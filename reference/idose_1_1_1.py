#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, wave, struct, io, traceback, random, re, math

# Try numpy (faster). If unavailable, we use pure-Python paths everywhere.
try:
    import numpy as np
    HAVE_NUMPY = True
except Exception:
    HAVE_NUMPY = False

# --- stdout flush for Pydroid ---
try:
    sys.stdout.reconfigure(write_through=True, line_buffering=True)
except Exception:
    pass

# ====== Config ======

REMIX_OUTPUT_BASENAME = "remix_output"  # remix_output_part01.wav, etc.
SUPPORTED_EXTS = (".wav",)

# Silence/Noise handling for source-cleanup
SILENCE_TRIM_DB = -45
MIN_SILENCE_MS = 30
REMOVE_INTERNAL_SILENCE_MS = 150
NOISE_GATE_DB = -50
NOISE_GATE_REDUCTION = 0.25

# Target format
TARGET_SR = 44100
TARGET_CHANNELS = 2
TARGET_SAMPWIDTH = 2          # 16-bit PCM

# Remix engine settings
SEG_MIN_MS = 800
SEG_MAX_MS = 4000
SEG_REVERSE_PROB = 0.15
SEG_STUTTER_PROB = 0.10
STUTTER_MS = 120
STUTTER_REPEATS = (2, 4)

CROSSFADE_MS = 80
LAYER_DRUMS_PROB = 0.40
LAYER_DRUM_GAIN = 0.6
MAIN_SEG_GAIN = 0.95

# Mastering
MASTER_TARGET_PEAK = 0.98
SOFT_CLIP = True

# Split huge outputs safely below RIFF ~4 GB
PART_ROLLOVER_BYTES = 1_800_000_000

# === NEW: consolidated output settings ===
CONSOLIDATED_NAME = "consolidatedartificalalgorithmic.wav"
HIDDEN_CONSOLIDATED_NAME = ".consolidatedartificalalgorithmic.wav"
CONSOLIDATED_PROGRESS_PRINT_STEP = 5  # print progress each N percent

# === SECOND VERSION (clean, structured) ===
CLEAN_CONSOLIDATED_NAME = "consolidatedartificalalgorithmic_v2.wav"
CLEAN_HIDDEN_CONSOLIDATED_NAME = ".consolidatedartificalalgorithmic_v2.wav"

# === NEW: Flowing theremin-like pad layer ===
THEREMIN_ENABLE = True
THEREMIN_MIX_IN_BOTH_BUILDS = True     # add to both 'creative' and 'clean' versions
THEREMIN_GAIN = 0.22                   # base gain (we also apply relative +dB later)
THEREMIN_VIBRATO_HZ = 5.0              # subtle vibrato
THEREMIN_SWEEP_SEC_RANGE = (5.0, 12.0) # glides between targets over this many seconds
THEREMIN_FREQ_RANGE = (160.0, 880.0)   # musical range
THEREMIN_STEREO_WIDTH = 0.35           # small L/R detune for width

# === NEW: 63/27 structure + periodic FX ===
STRUCT_63_27_ENABLE = True
STRUCT_LONG_BLOCK_S = 63
STRUCT_SHORT_BLOCK_S = 27
STRUCT_LONG_SUBLOOPS_S = [0, 21, 42]   # 3 × 21s inside the 63s block
STRUCT_LONG_SUBLOOP_LEN_S = 21

# Theremin prominence & motion
THEREMIN_RELATIVE_DB = 1.5    # ~+1.5 dB vs. base
THEREMIN_AM_HZ = 0.7          # slow tremolo
THEREMIN_FM_DEPTH = 0.015     # extra slow FM wobble

# Periodic overlays (keep rest clean): stutters/glitches in rotation
PERIODIC_STUTTER_SEC = 33     # "at least 33s" loop time
PERIODIC_GLITCH_SEC = 67      # "at least 67s" loop time
STUTTER_OVERLAY_MS = 140      # short, audible but not destructive
STUTTER_OVERLAY_REPEATS = 2
GLITCH_OVERLAY_MS = 90        # tiny bursts
GLITCH_BITCRUSH_FACTOR = 6    # crude downsample/hold to “glitch”
CLEAN_FX_CROSSFADE_MS = 40

# === NEW: rotating generative beats per 63/27 block ===
ROTATING_BEATS_ENABLE = True
BEAT_GAIN = 0.70                 # drum bus mix-in level
BEAT_BPM_CHOICES = [86, 88, 90, 92, 96, 72]  # Relapse/Refill-ish pockets (incl. halftime)
BEAT_SWING = 0.56                # 0.50=straight, >0.5 = swung 16ths
BEAT_FILL_GAIN = 0.85            # fills at 0/21/42s inside 63s block (used internally)
BEAT_RANDOM_SEED_PER_BLOCK = True

# Synthesis envelopes for beat synth
KICK_BASE_HZ = 56.0
KICK_DROP_TO_HZ = 38.0
KICK_MS = 120

SNARE_TONE_HZ = 180.0
SNARE_NOISE_MS = 130
SNARE_BODY_MS  = 70

HAT_CLOSED_MS = 40
HAT_OPEN_MS   = 120

# Keep human-interest phrase lengths (avoid overlong stitched loops)
MAX_MOTIF_SECONDS = 14

# === NEW: Exclude percussive single-shot sources from user input ===
EXCLUDE_PERCUSSIVE = True
EXCLUDE_CLASSES = {"drums", "perc"}
EXCLUDE_KEYWORDS = (
    "kick", "snare", "rim", "tom", "808", "909", "drum", "cymbal", "hihat",
    "hh", "hat", "perc", "shaker", "timbale", "conga", "bongo", "cowbell", "clap"
)
EXCLUDE_MAX_DURATION_SEC = 1.8  # skip very short hits (under ~2 seconds)

# ---- Instrument lexicon (trim/extend as you like) ----
INSTRUMENT_LEXICON = {
    "grand piano": ["grand piano","acoustic piano","apiano","steinway"],
    "electric piano": ["electric piano","e-piano","rhodes","wurli","mk1","mk2"],
    "real honky tonk piano": ["real honky tonk piano","honky tonk","honky-tonk"],
    "upright piano": ["upright piano"],
    "octave piano": ["octave piano"],
    "clavinet": ["clavinet","clav"],
    "harpsichord": ["harpsichord","cembalo"],
    "celesta": ["celesta"],
    "concert strings": ["concert strings","ensemble strings","string ensemble","strings ens","real strings"],
    "real strings": ["real strings","orch strings","orchestral strings"],
    "sweet violin": ["sweet violin","violin","vln"],
    "viola": ["viola","vla"],
    "cello": ["cello","vc"],
    "contrabass": ["contrabass","double bass","upright bass"],
    "flute": ["flute","concert flute","pan flute","shakuhachi"],
    "piccolo": ["piccolo"],
    "clarinet": ["clarinet","cl"],
    "oboe": ["oboe"],
    "english horn": ["english horn","cor anglais"],
    "bassoon": ["bassoon","bn"],
    "sweet tenor sax": ["sweet tenor sax","tenor sax","tenor saxophone","tsax"],
    "sweet alto sax": ["sweet alto sax","alto sax","alto saxophone","asax"],
    "sweet soprano sax": ["sweet soprano sax","soprano sax","ssax"],
    "baritone sax": ["baritone sax","bari sax","bsax"],
    "trumpet": ["trumpet","tpt"],
    "flugelhorn": ["flugelhorn"],
    "trombone": ["trombone","tbn"],
    "french horn": ["french horn","horn","hn"],
    "tuba": ["tuba"],
    "acoustic guitar": ["acoustic guitar","steel guitar","nylon guitar","classical guitar"],
    "electric guitar": ["electric guitar","eguitar","strat","tele","les paul","lp"],
    "jazz guitar": ["jazz guitar"],
    "muted guitar": ["muted guitar","palm mute guitar"],
    "electric bass": ["electric bass","e-bass","bass guitar","precision","j-bass","fretless bass"],
    "synth bass": ["synth bass","sub bass"],
    "upright bass": ["upright bass","double bass"],
    "synth lead": ["synth lead","lead synth","ld"],
    "synth pad": ["synth pad","pad","warm pad","string pad","air pad"],
    "synth pluck": ["synth pluck","pluck"],
    "synth brass": ["synth brass"],
    "synth keys": ["synth keys","poly synth","polysynth"],
    "fm piano": ["fm piano","dx7 piano"],
    "supersaw": ["supersaw"],
    "square lead": ["square lead"],
    "saw lead": ["saw lead"],
    "drum kit": ["drum kit","acoustic kit","studio kit"],
    "electronic kit": ["electronic kit","edm kit"],
    "909 kit": ["909","tr-909"],
    "808 kit": ["808","tr-808","808s"],
    "snare": ["snare"],
    "kick": ["kick","bd"],
    "hihat": ["hihat","hi-hat","hh"],
    "tom": ["tom"],
    "cymbal": ["cymbal","ride","crash","splash","china"],
    "timpani": ["timpani","kettle drum"],
    "percussion": ["percussion","perc","shaker","tambourine","cowbell","guiro","conga","bongo","timbale"],
    "rim": ["rim","rimshot","rim shot"],
    "bell": ["bell","bell synth","glockenspiel","tubular bells"],
    "synth": ["synth","synths"],
}
_ALIAS_TO_CANON = {a.lower(): canon for canon, aliases in INSTRUMENT_LEXICON.items() for a in aliases}

FAMILY_MAP = {
    # melodic/harmonic
    "grand piano":"melodic","upright piano":"melodic","electric piano":"melodic",
    "real honky tonk piano":"melodic","octave piano":"melodic","clavinet":"melodic","harpsichord":"melodic","celesta":"melodic",
    "concert strings":"melodic","real strings":"melodic","sweet violin":"melodic","viola":"melodic","cello":"melodic","contrabass":"melodic",
    "flute":"melodic","piccolo":"melodic","clarinet":"melodic","oboe":"melodic","english horn":"melodic","bassoon":"melodic",
    "sweet tenor sax":"melodic","sweet alto sax":"melodic","sweet soprano sax":"melodic","baritone sax":"melodic",
    "trumpet":"melodic","flugelhorn":"melodic","trombone":"melodic","french horn":"melodic","tuba":"melodic",
    "acoustic guitar":"melodic","electric guitar":"melodic","jazz guitar":"melodic","muted guitar":"melodic",
    "electric bass":"melodic","synth bass":"melodic","upright bass":"melodic",
    "synth lead":"melodic","synth pad":"melodic","synth pluck":"melodic","synth brass":"melodic","synth keys":"melodic","fm piano":"melodic","supersaw":"melodic","square lead":"melodic","saw lead":"melodic",
    "bell":"melodic","synth":"melodic",
    # drums
    "drum kit":"drums","electronic kit":"drums","909 kit":"drums","snare":"drums","kick":"drums","hihat":"drums","tom":"drums","cymbal":"drums","timpani":"drums",
    # perc bottom
    "percussion":"perc","808 kit":"perc","rim":"perc",
}
FAMILY_ORDER = ["melodic", "drums", "perc"]

# ------- Prompting -------

def prompt_directories():
    print("Enter one or more directories containing WAVs.")
    print("• Type a path and press Enter to add it.")
    print("• Press Enter on a blank line OR type 'done' to finish.\n")
    dirs, seen, idx = [], set(), 1
    while True:
        try:
            inp = input(f"[{idx}] Path (Enter or 'done' to finish): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        inp = inp.strip('"').strip("'")
        if not inp or inp.lower() == "done":
            if dirs:
                return dirs
            print("You haven't entered any directories yet. Please add at least one.\n")
            continue
        path = os.path.abspath(os.path.expanduser(inp))
        if os.path.isdir(path):
            if path in seen:
                print("Already added. Enter a different path or finish.\n"); continue
            dirs.append(path); seen.add(path); idx += 1
        else:
            print(f"Path not found or not a directory: {path}\nPlease try again.\n")

def prompt_output_directory(default_dir):
    while True:
        try:
            inp = input(f"Enter the OUTPUT directory (Press Enter to use input dir: {default_dir}): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        inp = inp.strip('"').strip("'")
        path = default_dir if not inp else os.path.abspath(os.path.expanduser(inp))
        if os.path.isdir(path):
            return path
        print(f"Path not found or not a directory: {path}\nPlease try again.\n")

def _yn(prompt, default="n"):
    d = default.lower()
    opt = "Y/n" if d == "y" else "y/N"
    while True:
        try:
            raw = input(f"{prompt} ({opt}): ").strip().lower()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if raw == "":
            return d == "y"
        if raw in ("y","yes"):
            return True
        if raw in ("n","no"):
            return False
        print("Please enter y or n.")

def prompt_sort_scope():
    print("\nSorting scope:")
    print("  1) BOTH: Primary (instrument/grouping) + Secondary (alpha/size/random/MIX)")
    print("  2) PRIMARY only: instrument/grouping only")
    print("  3) SECONDARY only: ignore instruments")
    while True:
        try:
            raw = input("Select 1/2/3 (Enter = 1): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw:
            return 1
        if raw in ("1","2","3"):
            return int(raw)
        print("Please enter 1, 2, or 3.\n")

def _normalize_label_for_match(s: str) -> str:
    s = s.lower()
    s = s.replace("*", " ").replace("-", " ").replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _strip_digits_for_alpha(s: str) -> str:
    return re.sub(r"\d", "", s)

def prompt_primary_mode():
    print("\nPrimary (instrument) mode:")
    print("  1) Custom instrument sequence (you type instrument names in order)")
    print("  2) Music-type priority (melodic/harmonic → drums → perc/808/rims)")
    while True:
        try:
            raw = input("Select 1/2 (Enter = 1): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw:
            return 1
        if raw in ("1","2"):
            return int(raw)
        print("Please enter 1 or 2.\n")

def prompt_instrument_sequence():
    print("\nEnter instrument names in the EXACT order you want grouped (top→bottom).")
    print("Type instrument names (alias or canonical). Type 'done' to finish.\n")
    ordered, used, idx = [], set(), 1
    while True:
        try:
            raw = input(f"Instrument #{idx} (or 'done'): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw or raw.lower() == "done":
            if ordered:
                return ordered
            print("Please enter at least one instrument or type 'done' after adding some.")
            continue
        key = raw.lower().strip()
        canon = _ALIAS_TO_CANON.get(key) or (key if key in INSTRUMENT_LEXICON else key)
        if canon in used:
            print("Already added. Choose another or type 'done'."); continue
        ordered.append(canon); used.add(canon); idx += 1

def auto_instrument_sequence_by_family():
    fam_to_list = {f: [] for f in FAMILY_ORDER}
    for canon in INSTRUMENT_LEXICON.keys():
        fam = FAMILY_MAP.get(canon, "melodic")
        if fam in fam_to_list:
            fam_to_list[fam].append(canon)
    seq = []
    for fam in FAMILY_ORDER:
        seq.extend(sorted(fam_to_list[fam]))
    return seq

def prompt_order_mode():
    print("\nSecondary ordering (applies globally or inside groups):")
    print("  1) numeric/alphabetical (0..Z)")
    print("  2) most big from top to bottom (by estimated WAV size)")
    print("  3) random")
    print("  4) random-by-size (weighted randomness by estimated size)")
    print("  5) MIX: blend A/B/C/D with percentages")
    while True:
        try:
            raw = input("Select 1/2/3/4/5 (Enter = 1): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw:
            return 1
        if raw in ("1","2","3","4","5"):
            return int(raw)
        print("Please enter 1, 2, 3, 4, or 5.\n")

def _read_pct(label, default="0"):
    while True:
        try:
            raw = input(f"{label} percentage 0-100 (Enter = {default}): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw:
            raw = default
        try:
            v = int(raw)
            v = 0 if v<0 else (100 if v>100 else v)
            return v
        except ValueError:
            print("Please enter an integer 0..100.")

def prompt_mix_percentages():
    print("\nMIX mode: set how much each function influences the order.")
    print("A = numeric/alphabetical (0..Z)")
    print("B = sort by .wav size (largest first)")
    print("C = randomize by alphabetical (biased random)")
    print("D = randomize by .wav size (biased random)\n")
    A = _read_pct("A (alpha 0..Z)","100")
    B = _read_pct("B (size desc)","0")
    C = _read_pct("C (random-by-alpha)","0")
    D = _read_pct("D (random-by-size)","0")
    total = A+B+C+D
    if total == 0:
        return (1.0,0.0,0.0,0.0)
    return (A/total, B/total, C/total, D/total)

# === NEW: per-instrument percentages (tied to custom instrument sequence) ===
def prompt_per_instrument_percentages(instr_sequence):
    """Immediately after user types custom instrument order, ask for a number (0..100) for each instrument."""
    print("\nSet percentages for each instrument (0–100). Type just the number (e.g., 25).")
    weights = {}
    total = 0
    for canon in instr_sequence:
        key = canon
        try:
            raw = input(f'  {canon}: ').strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        try:
            v = int(raw)
        except Exception:
            v = 0
        if v < 0: v = 0
        if v > 100: v = 100
        weights[key] = v
        total += v
    if total <= 0:
        return {}
    return {k: (v/float(total)) for k, v in weights.items()}

def prompt_start_part():
    while True:
        try:
            raw = input("Start writing at which PART number? (Press Enter for 1): ").strip()
        except EOFError:
            print("\nNo input received. Exiting."); sys.exit(1)
        if not raw:
            return 1
        try:
            part = int(raw)
            if 1 <= part <= 99:
                return part
            print("Please enter a number between 1 and 99.")
        except ValueError:
            print("Please enter a valid integer (e.g., 1, 2, 3, ...).")

# ------- FS walk / gather --------

def is_our_temp_or_output(path: str) -> bool:
    name = os.path.basename(path)
    return name.startswith(REMIX_OUTPUT_BASENAME + "_part") or name.startswith(".remix_tmp_part")

def fast_walk(root):
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        yield e.path
        except PermissionError:
            pass

# ---- Quick header read -----

def _read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError("Unexpected EOF")
    return b

def quick_wav_header(path):
    with open(path, "rb") as f:
        if _read_exact(f, 4) != b"RIFF": raise ValueError("Not RIFF")
        _ = _read_exact(f, 4)
        if _read_exact(f, 4) != b"WAVE": raise ValueError("Not WAVE")
        fmt = None; data_off = None; data_size = None
        while True:
            hdr = f.read(8)
            if len(hdr) < 8: break
            chunk_id, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if chunk_id == b"fmt ":
                raw = _read_exact(f, size)
                if size < 16: raise ValueError("fmt chunk too small")
                (wFormatTag, nChannels, nSamplesPerSec, _avg, nBlockAlign, wBitsPerSample) = struct.unpack("<HHIIHH", raw[:16])
                fmt = (wFormatTag, nChannels, nSamplesPerSec, wBitsPerSample, nBlockAlign)
            elif chunk_id == b"data":
                data_off = f.tell(); data_size = size; f.seek(size, io.SEEK_CUR)
            else:
                f.seek(size, io.SEEK_CUR)
        if not fmt or data_off is None:
            raise ValueError("Missing fmt or data chunk")
        format_tag, channels, sr, bps, blockalign = fmt
        if blockalign == 0:
            raise ValueError("Invalid blockalign=0")
        nframes = data_size // blockalign
        return {
            "format_tag": format_tag,
            "channels": channels,
            "sr": sr,
            "bits_per_sample": bps,
            "blockalign": blockalign,
            "data_offset": data_off,
            "data_size": data_size,
            "nframes": nframes,
        }

# ----- Candidate filtering -----

def _class_of_canon(canon): 
    return FAMILY_MAP.get(canon, "melodic")

def _instrument_of_path(path):
    name = os.path.basename(path)
    norm = _normalize_label_for_match(name)
    norm_nodigits = _strip_digits_for_alpha(norm)
    return detect_canonical_instrument(norm) or detect_canonical_instrument(norm_nodigits)

def _should_exclude_percussive(path, hdr=None):
    """Return True if file should be ignored (single-shot percussive)."""
    if not EXCLUDE_PERCUSSIVE:
        return False
    name = os.path.basename(path).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return True
    canon = _instrument_of_path(path)
    fam = _class_of_canon(canon)
    if fam in EXCLUDE_CLASSES:
        return True
    try:
        if hdr is None:
            hdr = quick_wav_header(path)
        dur = hdr["nframes"] / float(max(1, hdr["sr"]))
        if dur <= EXCLUDE_MAX_DURATION_SEC:
            return True
    except Exception:
        pass
    return False

def gather_candidates(root):
    files = []
    for p in fast_walk(root):
        if not p.lower().endswith(SUPPORTED_EXTS):
            continue
        if is_our_temp_or_output(p):
            continue
        try:
            hdr = quick_wav_header(p)
        except Exception:
            hdr = None
        if _should_exclude_percussive(p, hdr):
            continue  # skip percussive hits and short one-shots
        files.append(p)
    files.sort()
    return files

# ----- Byte conversions -----

def pcm24_to_int16le_bytes(raw_bytes):
    out = bytearray(len(raw_bytes) // 3 * 2); o = 0
    for i in range(0, len(raw_bytes), 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        val = b0 | (b1 << 8) | (b2 << 16)
        if val & 0x800000: val -= 0x1000000
        s16 = max(-32768, min(32767, val // 256))
        out[o:o+2] = struct.pack("<h", s16); o += 2
    return bytes(out)

def float32_to_int16le_bytes(raw_bytes):
    out = bytearray(len(raw_bytes) // 2); o = 0
    for (x,) in struct.iter_unpack("<f", raw_bytes):
        x = 1.0 if x > 1.0 else (-1.0 if x < -1.0 else x)
        s16 = int(x * 32767.0)
        s16 = -32768 if s16 < -32768 else (32767 if s16 > 32767 else s16)
        out[o:o+2] = struct.pack("<h", s16); o += 2
    return bytes(out)

def mono_to_stereo(raw16, channels):
    if channels == 2: return raw16
    out = bytearray(len(raw16) * 2); o = 0
    for i in range(0, len(raw16), 2):
        s = raw16[i:i+2]
        out[o:o+2] = s; out[o+2:o+4] = s; o += 4
    return bytes(out)

def nch_to_stereo_take_first_two(raw16, channels):
    if channels == 2: return raw16
    if channels == 1: return mono_to_stereo(raw16, 1)
    frame_count = len(raw16) // (2 * channels)
    out = bytearray(frame_count * 4); o = 0; step = 2 * channels
    for i in range(0, len(raw16), step):
        out[o:o+2] = raw16[i:i+2]
        out[o+2:o+4] = raw16[i+2:i+4]; o += 4
    return bytes(out)

def resample_linear_int16(raw16_stereo, src_sr, dst_sr):
    if src_sr == dst_sr or len(raw16_stereo) < 4:
        return raw16_stereo
    if HAVE_NUMPY:
        s = np.frombuffer(raw16_stereo, dtype='<i2').astype(np.int16)
        L = s[0::2].astype(np.float32); R = s[1::2].astype(np.float32)
        ratio = dst_sr / float(src_sr)
        frames_src = L.shape[0]; frames_dst = int(round(frames_src * ratio))
        if frames_src <= 1 or frames_dst <= 1: return raw16_stereo
        src_pos = np.linspace(0, frames_src - 1, frames_dst, dtype=np.float32)
        i0 = np.floor(src_pos).astype(np.int32); i1 = np.minimum(i0 + 1, frames_src - 1)
        frac = src_pos - i0
        L_out = (L[i0] + (L[i1] - L[i0]) * frac).clip(-32768, 32767).astype('<i2')
        R_out = (R[i0] + (R[i1] - R[i0]) * frac).clip(-32768, 32767).astype('<i2')
        out = np.empty(frames_dst * 2, dtype='<i2'); out[0::2] = L_out; out[1::2] = R_out
        return out.tobytes()
    # pure-Python fallback
    total_samples = len(raw16_stereo) // 2
    frames_src = total_samples // 2
    samples = list(struct.iter_unpack("<{}h".format(total_samples), raw16_stereo))
    L_src = list(samples[0::2]); R_src = list(samples[1::2])
    ratio = dst_sr / float(src_sr)
    frames_dst = int(round(frames_src * ratio))
    if frames_src <= 1 or frames_dst <= 1: return raw16_stereo
    out = bytearray(frames_dst*4); o = 0
    step = src_sr / float(dst_sr); pos = 0.0; last = frames_src - 1
    for _ in range(frames_dst):
        i0 = int(pos); i1 = i0 + 1
        if i1 > last: i1 = last
        frac = pos - i0
        l = int(L_src[i0] + (L_src[i1] - L_src[i0]) * frac)
        r = int(R_src[i0] + (R_src[i1] - R_src[i0]) * frac)
        l = -32768 if l < -32768 else (32767 if l > 32767 else l)
        r = -32768 if r < -32768 else (32767 if r > 32767 else r)
        out[o:o+2] = struct.pack("<h", l); out[o+2:o+4] = struct.pack("<h", r); o += 4
        pos += step
    return bytes(out)

def _db_to_lin(db): return 10.0 ** (db / 20.0)

# ---- Ordering helpers (alpha ignoring digits, size/random, MIX) ----
def _normalized_ranks(items, key_vals, reverse=False):
    idxs = list(range(len(items)))
    idxs.sort(key=lambda i: key_vals[i], reverse=reverse)
    ranks = [0]*len(items)
    for r,i in enumerate(idxs):
        ranks[i]=r
    if len(items) <= 1: return [0.0]*len(items)
    return [r/(len(items)-1) for r in ranks]

def _safe_norm(vals):
    if not vals: return []
    m = max(vals)
    if m <= 0: return [0.0]*len(vals)
    return [v/m for v in vals]

def alpha_key(name: str):
    return _strip_digits_for_alpha(name.lower())

def order_files(files, mode, mix_weights=None):
    if mode == 1:
        return sorted(files, key=lambda p: alpha_key(os.path.basename(p)))
    need_est = mode in (2,4,5)
    est = None
    if need_est:
        est = []
        for p in files:
            try:
                hdr = quick_wav_header(p); e = estimate_output_bytes_after_convert(hdr); e = 1 if e<=0 else e
            except Exception:
                e = 1
            est.append(e)
    if mode == 2:
        return [fp for _, fp in sorted(zip(est, files), key=lambda t: t[0], reverse=True)]
    if mode == 3:
        shuffled = list(files); random.shuffle(shuffled); return shuffled
    if mode == 4:
        pool = list(files); weights = list(est); ordered = []
        while pool:
            total = sum(weights)
            if total <= 0:
                idx = random.randrange(len(pool))
            else:
                r = random.uniform(0, total); acc = 0.0; idx = 0
                for i,w in enumerate(weights):
                    acc += w
                    if r <= acc:
                        idx = i; break
            ordered.append(pool.pop(idx)); weights.pop(idx)
        return ordered
    if mode == 5:
        alpha_sorted = sorted(range(len(files)), key=lambda i: alpha_key(os.path.basename(files[i])))
        alpha_rank = [0]*len(files)
        for r,i in enumerate(alpha_sorted):
            alpha_rank[i]=r
        alpha_rank = [r/(len(files)-1) if len(files)>1 else 0.0 for r in alpha_rank]
        if est is None: est = [1]*len(files)
        size_rank = _normalized_ranks(files, est, reverse=True)
        eps = 1e-9
        rand_alpha = []
        for ar in alpha_rank:
            denom = max(eps, 1.0 - ar); rand_alpha.append(random.random()/denom)
        norm_size = _safe_norm(est)
        rand_size = []
        for ns in norm_size:
            denom = max(1e-9, ns); rand_size.append(random.random()/denom)
        wA,wB,wC,wD = mix_weights if mix_weights else (1.0,0.0,0.0,0.0)
        scores = []
        for i in range(len(files)):
            s = (wA*alpha_rank[i]) + (wB*size_rank[i]) + (wC*rand_alpha[i]) + (wD*rand_size[i])
            scores.append((s,i))
        scores.sort(key=lambda t: t[0])
        return [files[i] for _,i in scores]
    return files

# ---- Instrument detection & grouping ----
def detect_canonical_instrument(filename_lower_norm: str):
    for alias, canon in _ALIAS_TO_CANON.items():
        if alias in filename_lower_norm:
            return canon
    for canon in INSTRUMENT_LEXICON.keys():
        if canon in filename_lower_norm:
            return canon
    return None

def build_presence_report(files):
    counts = {}
    for p in files:
        name = os.path.basename(p)
        norm = _normalize_label_for_match(name)
        norm_nodigits = _strip_digits_for_alpha(norm)
        found = detect_canonical_instrument(norm) or detect_canonical_instrument(norm_nodigits)
        if found:
            counts[found] = counts.get(found, 0) + 1
    if counts:
        print("\n📈 Instrument hits (filename matches):")
        for k in sorted(counts.keys()):
            print(f"  • {k}: {counts[k]}")

def group_files_by_instruments(files, user_order):
    buckets = {g: [] for g in user_order}
    others = []
    for p in files:
        name = os.path.basename(p)
        norm = _normalize_label_for_match(name)
        norm_nodigits = _strip_digits_for_alpha(norm)
        found = detect_canonical_instrument(norm) or detect_canonical_instrument(norm_nodigits)
        if found and found in buckets:
            buckets[found].append(p)
        else:
            others.append(p)
    ordered_groups = []
    for g in user_order:
        ordered_groups.append((g, buckets[g]))
    if others:
        ordered_groups.append(("(other)", others))
    return ordered_groups

# ==== Remix engine helpers ====
def _bytes_to_frames(raw_bytes):  # -> list[(l,r)]
    return [xy for xy in struct.iter_unpack("<hh", raw_bytes)]

def _frames_to_bytes(frames):
    out = bytearray(len(frames)*4); o = 0
    for (l, r) in frames:
        out[o:o+2] = struct.pack("<h", l)
        out[o+2:o+4] = struct.pack("<h", r)
        o += 4
    return bytes(out)

def _pp_clip(v):  # clip int to 16-bit
    return -32768 if v < -32768 else (32767 if v > 32767 else v)

def _pp_apply_gain(frames, gain):
    if gain == 1.0: return frames
    out = []
    for (l, r) in frames:
        out.append((_pp_clip(int(l*gain)), _pp_clip(int(r*gain))))
    return out

def _pp_reverse(frames): return list(reversed(frames))

def _pp_lin_ramp(n): return [i/(n-1) if n>1 else 1.0 for i in range(n)]

def _pp_crossfade(a, b, cross_frames):
    if cross_frames <= 0 or not a:
        return a + b
    cross_frames = min(cross_frames, len(a), len(b))
    fade_out = _pp_lin_ramp(cross_frames)[::-1]
    fade_in  = _pp_lin_ramp(cross_frames)
    out = a[:-cross_frames]
    for i in range(cross_frames):
        l = _pp_clip(int(a[-cross_frames+i][0]*fade_out[i] + b[i][0]*fade_in[i]))
        r = _pp_clip(int(a[-cross_frames+i][1]*fade_out[i] + b[i][1]*fade_in[i]))
        out.append((l, r))
    out.extend(b[cross_frames:])
    return out

def _pp_stutter_tail(frames, sr):
    tail = max(1, int(sr*(STUTTER_MS/1000.0)))
    if len(frames) <= tail: return frames
    chunk = frames[-tail:]
    reps = random.randint(STUTTER_REPEATS[0], STUTTER_REPEATS[1])
    out = frames[:]
    for _ in range(reps):
        out.extend(chunk)
    return out

def _pp_normalize(frames, target_peak=MASTER_TARGET_PEAK, soft_clip=SOFT_CLIP):
    peak = 1
    for (l, r) in frames:
        a = abs(l); b = abs(r)
        if a > peak: peak = a
        if b > peak: peak = b
    if peak == 0: return frames
    scale = (target_peak * 32767.0) / float(peak)
    out = []
    if soft_clip:
        def sc(x):
            y = math.tanh(1.4 * (x/32768.0))
            return _pp_clip(int(y * 32767.0))
        for (l, r) in frames:
            l2 = sc(int(l*scale)); r2 = sc(int(r*scale))
            out.append((l2, r2))
    else:
        for (l, r) in frames:
            out.append((_pp_clip(int(l*scale)), _pp_clip(int(r*scale))))
    return out

def _pick_segments_from_clip_bytes(cleaned_bytes, sr):
    frames = _bytes_to_frames(cleaned_bytes)
    min_len = int(sr*(SEG_MIN_MS/1000.0))
    max_len = int(sr*(SEG_MAX_MS/1000.0))
    if len(frames) < min_len: return []
    segs = []
    aim = max(1, int(len(frames) / ((min_len+max_len)/2)))
    for _ in range(aim):
        seg_len = random.randint(min_len, max_len)
        if seg_len >= len(frames):
            start = 0
        else:
            start = random.randint(0, len(frames)-seg_len)
        segs.append(frames[start:start+seg_len])
    return segs

# NumPy helpers
def _to_np_int16(stereo_bytes):
    arr = np.frombuffer(stereo_bytes, dtype='<i2').astype(np.int16)
    if arr.size % 2 != 0: arr = arr[:-1]
    return arr.reshape(-1, 2)

def _from_np_int16(arr): return arr.astype('<i2').tobytes()

def _np_linear_fade(arr, fade_in=True):
    n = arr.shape[0]
    if n <= 1: return arr
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if not fade_in: ramp = 1.0 - ramp
    return (arr.astype(np.float32) * ramp[:, None]).round().astype(np.int16)

def _np_crossfade(a, b, cross_frames):
    if cross_frames <= 0:
        return np.vstack([a, b])
    cross_frames = min(cross_frames, a.shape[0], b.shape[0])
    fade_out = _np_linear_fade(a[-cross_frames:].copy(), fade_in=False)
    fade_in  = _np_linear_fade(b[:cross_frames].copy(),  fade_in=True)
    blend = (fade_out.astype(np.int32) + fade_in.astype(np.int32))
    np.clip(blend, -32768, 32767, out=blend)
    return np.vstack([a[:-cross_frames], blend.astype(np.int16), b[cross_frames:]])

def _np_apply_gain(arr, g):
    out = (arr.astype(np.float32)*g).round().astype(np.int32)
    np.clip(out, -32768, 32767, out=out)
    return out.astype(np.int16)

def _np_stutter_tail(arr, sr):
    n = max(1, int(sr*(STUTTER_MS/1000.0)))
    if arr.shape[0] <= n: return arr
    tail = arr[-n:].copy()
    reps = random.randint(STUTTER_REPEATS[0], STUTTER_REPEATS[1])
    return np.vstack([arr] + [tail.copy() for _ in range(reps)])

def _np_normalize(arr, target_peak=MASTER_TARGET_PEAK, soft_clip=SOFT_CLIP):
    peak = np.max(np.abs(arr.astype(np.int32)))
    if peak == 0: return arr
    scale = (target_peak*32767.0)/float(peak)
    out = (arr.astype(np.float32)*scale).astype(np.int32)
    if soft_clip:
        f = out.astype(np.float32)/32768.0
        f = np.tanh(1.4*f)
        out = (f*32767.0).round().astype(np.int32)
    np.clip(out, -32768, 32767, out=out)
    return out.astype(np.int16)

# === NEW: Theremin generator (enhanced)
def _generate_theremin_np(total_frames, sr=TARGET_SR,
                          freq_low=THEREMIN_FREQ_RANGE[0], freq_high=THEREMIN_FREQ_RANGE[1],
                          sweep_range=THEREMIN_SWEEP_SEC_RANGE, vib_hz=THEREMIN_VIBRATO_HZ,
                          stereo_width=THEREMIN_STEREO_WIDTH, gain=THEREMIN_GAIN):
    """Sine-ish theremin with glides, vibrato, added slow AM + subtle FM wobble for periodic complexity."""
    if not HAVE_NUMPY:
        # Simple pure-Python sine fallback (no AM/FM), still returns bytes later via writer
        total_frames = max(1, int(total_frames))
        out = []
        phase = 0.0
        freq = (freq_low + freq_high)/2.0
        dphi = 2.0*math.pi*freq/float(sr)
        for _ in range(total_frames):
            s = math.sin(phase)
            v = int(max(-32768, min(32767, int(s*gain*32767.0))))
            out.append((v, v))
            phase += dphi
        return np.array(out, dtype=np.int16) if HAVE_NUMPY else out

    if total_frames <= 0:
        return np.zeros((1,2), dtype=np.int16)
    t = np.arange(total_frames, dtype=np.float32) / float(sr)

    # random target points -> linear freq glides
    points = [0.0]
    while points[-1] < (total_frames / float(sr)):
        points.append(points[-1] + random.uniform(*sweep_range))
    if points[-1] < (total_frames / float(sr)):
        points.append(total_frames / float(sr))

    freqs = [random.uniform(freq_low, freq_high) for _ in range(len(points))]
    freq_track = np.zeros_like(t, dtype=np.float32)
    for i in range(len(points)-1):
        t0 = points[i]; t1 = points[i+1]
        idx0 = int(round(t0*sr)); idx1 = int(round(t1*sr))
        if idx1 <= idx0: continue
        seg = idx1 - idx0
        f0 = freqs[i]; f1 = freqs[i+1]
        ramp = np.linspace(0.0, 1.0, seg, dtype=np.float32)
        freq_track[idx0:idx1] = f0 + (f1 - f0)*ramp
    if freq_track[-1] == 0.0:
        freq_track[-1] = freq_track[-2] if total_frames > 1 else (freq_low+freq_high)/2.0

    # vibrato + subtle FM wobble (complex periodic)
    vib = 0.02 * np.sin(2*np.pi*vib_hz*t).astype(np.float32)              # ±2%
    wob = THEREMIN_FM_DEPTH * np.sin(2*np.pi*(vib_hz*0.33)*t).astype(np.float32)
    freq_track = freq_track * (1.0 + vib + wob)

    # integrate to phase
    phaseL = 2*np.pi*np.cumsum(freq_track)/float(sr)
    detune = 0.003
    phaseR = 2*np.pi*np.cumsum(freq_track*(1.0+detune))/float(sr)

    left  = np.sin(phaseL).astype(np.float32)
    right = np.sin(phaseR).astype(np.float32)

    # slow amplitude modulation (AM) as tremolo
    am = (0.85 + 0.15*np.sin(2*np.pi*THEREMIN_AM_HZ*t)).astype(np.float32)

    mid = 0.5*(left+right)
    side = 0.5*(left-right)
    L = (mid + stereo_width*side) * am * gain
    R = (mid - stereo_width*side) * am * gain

    # gentle fades
    fadeN = int(sr*1.5)
    if total_frames > 2*fadeN:
        fade_in = np.linspace(0.0, 1.0, fadeN, dtype=np.float32)
        fade_out = fade_in[::-1]
        L[:fadeN] *= fade_in; R[:fadeN] *= fade_in
        L[-fadeN:] *= fade_out; R[-fadeN:] *= fade_out

    out = np.stack([L, R], axis=1)
    out_i16 = np.clip((out*32767.0).round(), -32768, 32767).astype(np.int16)
    return out_i16

def _mix_np(a, b):
    """Mix b into a (same length) with clipping."""
    if HAVE_NUMPY:
        if a.shape[0] < b.shape[0]:
            a = np.vstack([a, np.zeros((b.shape[0]-a.shape[0], 2), dtype=np.int16)])
        if b.shape[0] < a.shape[0]:
            b = np.vstack([b, np.zeros((a.shape[0]-b.shape[0], 2), dtype=np.int16)])
        mix = (a.astype(np.int32) + b.astype(np.int32))
        np.clip(mix, -32768, 32767, out=mix)
        return mix.astype(np.int16)
    # pure Python fallback (convert tuples)
    out = []
    for i in range(max(len(a), len(b))):
        L1,R1 = a[i] if i < len(a) else (0,0)
        L2,R2 = b[i] if i < len(b) else (0,0)
        out.append((_pp_clip(L1+L2), _pp_clip(R1+R2)))
    return out

def _mix_with_relative_gain(a, b, rel_db=THEREMIN_RELATIVE_DB):
    """Mix b into a, auto-scaling b so its RMS sits ~rel_db above a."""
    if not HAVE_NUMPY:
        # Simple fallback: just apply a fixed gain boost to b and mix
        gain = 10.0**(rel_db/20.0)
        b_boost = []
        for (l,r) in b:
            l2 = _pp_clip(int(l*gain)); r2 = _pp_clip(int(r*gain))
            b_boost.append((l2,r2))
        return _mix_np(a, b_boost)

    if a.shape[0] != b.shape[0]:
        # tile/trim b to match a
        if b.shape[0] < a.shape[0]:
            reps = int(np.ceil(a.shape[0]/b.shape[0]))
            b = np.tile(b, (reps,1))[:a.shape[0]]
        else:
            b = b[:a.shape[0]]
    eps = 1e-9
    a_rms = float(np.sqrt(np.mean((a.astype(np.float32))**2))) + eps
    b_rms = float(np.sqrt(np.mean((b.astype(np.float32))**2))) + eps
    target = a_rms * (10.0**(rel_db/20.0))
    scale = target / b_rms
    b_scaled = (b.astype(np.float32)*scale).astype(np.int32)
    mix = a.astype(np.int32) + b_scaled
    np.clip(mix, -32768, 32767, out=mix)
    return mix.astype(np.int16)

# === Minute-grid helpers (existing)
def _sec_to_frames(sec, sr=TARGET_SR): return int(round(sec * sr))

def _np_insert_with_crossfade(base, seg, start_frame, cross_frames):
    """Insert seg into base at start_frame using crossfade. Extends with zeros as needed."""
    if base is None or (HAVE_NUMPY and base.shape[0] == 0) or (not HAVE_NUMPY and len(base)==0):
        if HAVE_NUMPY:
            pad = np.zeros((start_frame, 2), dtype=np.int16)
            return _np_crossfade(pad, seg, cross_frames)
        else:
            # pure Python: just append silence then seg
            pre = [(0,0)] * start_frame
            return pre + seg
    if HAVE_NUMPY:
        if start_frame <= 0:
            return _np_crossfade(seg, base, cross_frames)
        if start_frame > base.shape[0]:
            pad = np.zeros((start_frame - base.shape[0], 2), dtype=np.int16)
            base = np.vstack([base, pad])
        pre = base[:start_frame]
        post = base[start_frame:]
        mixed = _np_crossfade(seg, post, cross_frames)
        return np.vstack([pre, mixed])
    else:
        # simple insertion without crossfade for fallback
        pre = base[:start_frame] if start_frame < len(base) else base[:]
        post = base[start_frame:] if start_frame < len(base) else []
        return pre + seg + post

def _np_tile_to_length(arr, frames_needed):
    # hard cap to avoid “exceeding human interest”
    max_frames = _sec_to_frames(MAX_MOTIF_SECONDS)
    frames_needed = min(frames_needed, max_frames)
    if arr.shape[0] >= frames_needed:
        return arr[:frames_needed]
    reps = int(np.ceil(frames_needed / float(arr.shape[0])))
    return np.tile(arr, (reps, 1))[:frames_needed]

# === NEW: Minute grid (existing feature kept)
def _minute_grid_inserts_np(base, motif_pool, cross_frames, sr=TARGET_SR,
                            loop20_gain=1.0, recurring_gain=1.0,
                            recur_len_min=15, recur_len_max=25):
    """
    For each 60s window:
      • place 3 subloops of exactly 20s at +0s, +20s, +40s (3 × 20s = 60s)
      • also place one recurring motif of length 15–25s aligned to the minute (start at +0s by default)
    """
    if base is None: return None
    if not HAVE_NUMPY: return base  # minute grid overlay only implemented in NumPy path
    total_s = base.shape[0] / float(sr)
    total_minutes = int(math.ceil(total_s / 60.0))
    twenty_sec = _sec_to_frames(20, sr)

    def _pick_from_pool_exact(frames_needed):
        if not motif_pool:
            return None
        src = random.choice(motif_pool).copy()
        if src.shape[0] <= 1:
            return None
        seg = _np_tile_to_length(src, frames_needed)
        if loop20_gain != 1.0:
            seg = _np_apply_gain(seg, loop20_gain)
        return seg

    def _pick_from_pool_range(min_s, max_s):
        if not motif_pool:
            return None
        src = random.choice(motif_pool).copy()
        if src.shape[0] <= 1:
            return None
        length_s = random.uniform(min_s, max_s)
        frames_needed = _sec_to_frames(length_s, sr)
        seg = _np_tile_to_length(src, frames_needed)
        if recurring_gain != 1.0:
            seg = _np_apply_gain(seg, recurring_gain)
        return seg

    out = base
    for m in range(total_minutes):
        minute_start_f = _sec_to_frames(60*m, sr)

        # 3×20s subloops locked to the minute grid
        for offset_s in (0, 20, 40):
            start_f = minute_start_f + _sec_to_frames(offset_s, sr)
            loop20 = _pick_from_pool_exact(twenty_sec)
            if loop20 is not None:
                out = _np_insert_with_crossfade(out, loop20, start_f, cross_frames)

        # One additional recurring motif per minute of length 15–25s
        recur = _pick_from_pool_range(recur_len_min, recur_len_max)
        if recur is not None:
            out = _np_insert_with_crossfade(out, recur, minute_start_f, cross_frames)

    return out

# === NEW: Enforce 63/27 alternation with 3×21s inside 63s blocks
def _enforce_63_27_np(base, motif_pool, cross_frames, sr=TARGET_SR):
    """
    Alternating 63s + 27s blocks.
    For each 63s block, insert 3 × 21s subloops at +0s, +21s, +42s.
    """
    if base is None:
        return base
    if not HAVE_NUMPY:
        return base  # only implemented for NumPy flow

    total_s = base.shape[0] / float(sr)
    idx_s = 0.0
    out = base
    sub_len_f = _sec_to_frames(STRUCT_LONG_SUBLOOP_LEN_S, sr)

    def pick_seg(frames_needed):
        if not motif_pool:
            return None
        src = random.choice(motif_pool).copy()
        if src.shape[0] <= 1:
            return None
        return _np_tile_to_length(src, frames_needed)

    long_turn = True
    while idx_s < total_s:
        start_f = _sec_to_frames(idx_s, sr)
        if long_turn:
            for off in STRUCT_LONG_SUBLOOPS_S:
                seg = pick_seg(sub_len_f)
                if seg is not None:
                    out = _np_insert_with_crossfade(out, seg, start_f + _sec_to_frames(off, sr), cross_frames)
            idx_s += STRUCT_LONG_BLOCK_S
        else:
            idx_s += STRUCT_SHORT_BLOCK_S
        long_turn = not long_turn
    return out

# === NEW: Clean periodic stutter/glitch overlays ===
def _apply_periodic_stutter_glitch_np(base, pool, sr=TARGET_SR):
    """
    Adds short stutter overlays every 33s and glitch bursts every 67s, interleaved.
    Keeps most of the WAV clean thanks to short overlays and small crossfades.
    """
    if base is None or not HAVE_NUMPY or not pool:
        return base

    cross_frames = int(sr * (CLEAN_FX_CROSSFADE_MS/1000.0))
    total_s = base.shape[0] / float(sr)

    stutter_period = PERIODIC_STUTTER_SEC
    glitch_period  = PERIODIC_GLITCH_SEC
    stutter_len_f  = _sec_to_frames(STUTTER_OVERLAY_MS/1000.0, sr)
    glitch_len_f   = _sec_to_frames(GLITCH_OVERLAY_MS/1000.0, sr)

    def pick_seg(frames_needed):
        s = random.choice(pool).copy()
        return _np_tile_to_length(s, frames_needed)

    def bitcrush(arr, factor):
        if factor <= 1: return arr
        n = arr.shape[0]
        out = arr.copy()
        for ch in (0,1):
            chan = out[:, ch]
            idx = np.arange(0, n, factor)
            vals = chan[idx]
            rep = np.repeat(vals, np.diff(np.append(idx, n)))
            out[:, ch] = rep
        return out

    out = base

    stutter_times = np.arange(stutter_period, int(total_s)+stutter_period, stutter_period, dtype=int)
    glitch_times  = np.arange(glitch_period,  int(total_s)+glitch_period,  glitch_period,  dtype=int)
    events = [(int(t), 'stutter') for t in stutter_times] + [(int(t), 'glitch') for t in glitch_times]
    events.sort(key=lambda x: x[0])

    last_type = None
    for t_sec, typ in events:
        if typ == last_type:
            continue  # rotate types if they collide
        start_f = _sec_to_frames(t_sec, sr)
        if start_f >= out.shape[0]-1:
            break
        if typ == 'stutter':
            seg = pick_seg(stutter_len_f)
            seg = np.vstack([seg] + [seg.copy() for _ in range(STUTTER_OVERLAY_REPEATS)])
            out = _np_insert_with_crossfade(out, seg, start_f, cross_frames)
        else:
            seg = pick_seg(glitch_len_f)
            seg = bitcrush(seg, GLITCH_BITCRUSH_FACTOR)
            if random.random() < 0.5:
                seg = seg[::-1].copy()
            out = _np_insert_with_crossfade(out, seg, start_f, cross_frames)
        last_type = typ

    return out

# === NEW: Rotating beat generator (NumPy only). Pure-Python fallback disabled.
def _env_exp(frames, sr, ms):
    n = max(1, int(sr*(ms/1000.0)))
    env =     np.exp(-np.linspace(0, 6, n)).astype(np.float32)
    if frames <= n:
        return env[:frames]
    tail = np.zeros(frames-n, dtype=np.float32)
    return np.concatenate([env, tail])

def _sine_tone(freq, frames, sr):
    t = np.arange(frames, dtype=np.float32)/sr
    return np.sin(2*np.pi*freq*t)

def _kick(frames, sr):
    # pitch-drop sine + decay
    t = np.arange(frames, dtype=np.float32)/sr
    f0, f1 = KICK_BASE_HZ, KICK_DROP_TO_HZ
    k = (f1/f0)**(1.0/max(1, frames))
    freq_track = f0 * (k**np.arange(frames, dtype=np.float32))
    phase = 2*np.pi*np.cumsum(freq_track)/sr
    tone = np.sin(phase).astype(np.float32)
    env = _env_exp(frames, sr, KICK_MS)
    return (tone*env)

def _snare(frames, sr):
    noise = (np.random.uniform(-1,1,frames)).astype(np.float32)
    noise *= _env_exp(frames, sr, SNARE_NOISE_MS)
    tone  = _sine_tone(SNARE_TONE_HZ, frames, sr)*_env_exp(frames, sr, SNARE_BODY_MS)*0.6
    return (noise*0.8 + tone*0.6)

def _hat(frames, sr, open_hat=False):
    noise = (np.random.uniform(-1,1,frames)).astype(np.float32)
    env = _env_exp(frames, sr, HAT_OPEN_MS if open_hat else HAT_CLOSED_MS)
    return noise*env*0.6

def _place(buf, start, sig):
    end = min(buf.shape[0], start + sig.shape[0])
    if end <= start: return
    seg = sig[:end-start]
    tmp = np.zeros((seg.shape[0], 2), dtype=np.float32)
    tmp[:,0] = seg; tmp[:,1] = seg
    buf[start:end] += tmp

def _grid_times(bpm, total_frames, sr, swing=0.5):
    sec_per_beat = 60.0/float(bpm)
    f_per_16th = int(round(sr * (sec_per_beat/4.0)))
    times = []
    pos = 0
    step_even = f_per_16th
    step_swing = int(round(f_per_16th * (2*swing)))  # longer off 16ths
    while pos < total_frames:
        times.append(pos)
        if len(times) % 2 == 1:
            pos += step_swing
        else:
            pos += (2*f_per_16th - step_swing)
    return times, f_per_16th

def _generate_beat_block_np(length_sec, sr, bpm, swing, seed=None, loud=BEAT_GAIN, with_fills=False):
    if seed is not None:
        rng_state = np.random.get_state()
        np.random.seed(seed)
    frames = int(round(length_sec*sr))
    out = np.zeros((frames,2), dtype=np.float32)
    _t16, f16 = _grid_times(bpm, frames, sr, swing)

    beats_per_bar = 4
    sixteenth_per_bar = 16
    bar_frames = sixteenth_per_bar * f16
    n_bars = max(1, frames // bar_frames)

    for b in range(n_bars):
        bar_start = b*bar_frames

        # Kicks: 1, 1e&, sometimes 2&, 4&
        k_slots = [0, 2, 8, 14]
        if np.random.rand() < 0.35: k_slots.append(6)
        for s in k_slots:
            when = bar_start + s*f16
            _place(out, when, _kick(int(f16*3.2), sr))

        # Snares: 2 and 4 (+ ghosts)
        for s in (4, 12):
            when = bar_start + s*f16
            _place(out, when, _snare(int(f16*3.0), sr))
        if np.random.rand() < 0.4:
            ghost = bar_start + 11*f16
            _place(out, ghost, _snare(int(f16*1.2), sr)*0.35)

        # Hats: 16ths with occasional open
        for idx in range(16):
            when = bar_start + idx*f16
            open_hat = (idx in (15,) and np.random.rand() < 0.5)
            _place(out, when, _hat(int(f16*(2.0 if open_hat else 1.0)), sr, open_hat=open_hat))

    # Accents/fills inside a 63s block
    if with_fills:
        for fill_sec in (0, 21, 42):
            fs = int(round(fill_sec*sr))
            if fs < frames:
                rush = _snare(int(f16*6), sr)*1.1 + _hat(int(f16*8), sr, open_hat=True)*0.8
                _place(out, fs, rush.astype(np.float32))

    peak = np.max(np.abs(out)) if out.size else 1.0
    if peak < 1e-6: peak = 1.0
    out = (out/peak) * loud
    mix = np.clip((out*32767.0).round(), -32768, 32767).astype(np.int16)

    if seed is not None:
        np.random.set_state(rng_state)
    return mix

def _apply_rotating_beats_63_27(base, sr=TARGET_SR):
    """
    For each 63s or 27s block, generate a brand-new beat (new BPM/seed),
    overlay it, and rotate next block to a different beat.
    Inside 63s blocks, add fills at 0/21/42s.
    """
    if base is None or not HAVE_NUMPY:
        return base

    total_s = base.shape[0] / float(sr)
    out = base
    t = 0.0
    long_turn = True
    prev_choice = None
    block_idx = 0

    while t < total_s:
        length_sec = STRUCT_LONG_BLOCK_S if long_turn else STRUCT_SHORT_BLOCK_S
        start_f = _sec_to_frames(t, sr)
        end_f = min(out.shape[0], start_f + _sec_to_frames(length_sec, sr))

        choices = [b for b in BEAT_BPM_CHOICES if b != prev_choice] or BEAT_BPM_CHOICES
        bpm = random.choice(choices)
        prev_choice = bpm

        seed = (block_idx*7919 + bpm*97) if BEAT_RANDOM_SEED_PER_BLOCK else None
        beat = _generate_beat_block_np(
            length_sec=length_sec,
            sr=sr,
            bpm=bpm,
            swing=BEAT_SWING,
            seed=seed,
            loud=BEAT_GAIN,
            with_fills=long_turn
        )

        seg = beat[:(end_f-start_f)]
        pre = out[:start_f]
        post = out[end_f:]

        body = out[start_f:end_f].astype(np.int32) + seg.astype(np.int32)
        np.clip(body, -32768, 32767, out=body)
        out = np.vstack([pre, body.astype(np.int16), post])

        t += length_sec
        long_turn = not long_turn
        block_idx += 1

    return out

# --- Estimate output bytes (after convert, pre-trim) ---
def estimate_output_bytes_after_convert(hdr):
    frames_src = hdr["nframes"]; sr_src = hdr["sr"]
    if sr_src <= 0: return 0
    frames_dst = frames_src if sr_src == TARGET_SR else int(round(frames_src * (TARGET_SR / float(sr_src))))
    return frames_dst * TARGET_CHANNELS * TARGET_SAMPWIDTH

# ----- Trim/gate and conversion (ported from original) -----
def trim_and_gate_int16_stereo(raw16_stereo, sr, silence_db=SILENCE_TRIM_DB, min_sil_ms=MIN_SILENCE_MS,
                               gate_db=NOISE_GATE_DB, gate_mult=NOISE_GATE_REDUCTION,
                               remove_internal_sil_ms=REMOVE_INTERNAL_SILENCE_MS):
    if len(raw16_stereo) < 4: return raw16_stereo, 0, 0
    samples = list(struct.iter_unpack("<hh", raw16_stereo))
    frames = len(samples)
    if frames == 0: return raw16_stereo, 0, 0

    def frame_abs(i):
        l,r = samples[i]; return (abs(l)+abs(r))//2

    sil_th = int(32767 * _db_to_lin(silence_db))
    gate_th = int(32767 * _db_to_lin(gate_db))
    min_sil_frames = max(1, int(sr * (min_sil_ms/1000.0)))

    # leading trim
    start = 0; i = 0
    while i < frames:
        block_end = min(frames, i + min_sil_frames)
        if max(frame_abs(k) for k in range(i, block_end)) > sil_th:
            start = max(0, i - int(0.005*sr)); break
        i = block_end
    else:
        return b"", 0, frames

    # trailing trim
    end = frames; j = frames
    while j > 0:
        block_start = max(0, j - min_sil_frames)
        if max(frame_abs(k) for k in range(block_start, j)) > sil_th:
            end = min(frames, j + int(0.005*sr)); break
        j = block_start

    work = samples[start:end]

    # light gate
    if gate_mult < 1.0:
        scaled=[]
        for (l, r) in work:
            if (abs(l)+abs(r))//2 < gate_th:
                l = int(l*gate_mult); r = int(r*gate_mult)
            l = -32768 if l < -32768 else (32767 if l > 32767 else l)
            r = -32768 if r < -32768 else (32767 if r > 32767 else r)
            scaled.append((l, r))
        work = scaled

    # remove internal long silences
    if remove_internal_sil_ms and remove_internal_sil_ms > 0:
        min_block = int(sr * (remove_internal_sil_ms/1000.0))
        out_frames = []
        acc_sil = 0
        for (l, r) in work:
            if (abs(l)+abs(r))//2 < sil_th:
                acc_sil += 1
                if acc_sil >= min_block:
                    acc_sil = 0
                    continue
            else:
                out_frames.append((l, r))
                acc_sil = 0
        if out_frames:
            work = out_frames

    out = bytearray(len(work)*4); o=0
    for (l,r) in work:
        out[o:o+2]=struct.pack("<h", l); out[o+2:o+4]=struct.pack("<h", r); o+=4
    return bytes(out), start, end

def read_convert_to_target(path, hdr=None):
    if hdr is None: hdr = quick_wav_header(path)
    fmt = hdr["format_tag"]; sr = hdr["sr"]; ch = hdr["channels"]; bps = hdr["bits_per_sample"]; nframes = hdr["nframes"]
    if fmt == 1:
        with wave.open(path, "rb") as r:
            r.setpos(0); raw = r.readframes(nframes); sampwidth = bps // 8
            if sampwidth == 3:
                raw16 = pcm24_to_int16le_bytes(raw)
            elif sampwidth == 2:
                raw16 = raw
            elif sampwidth == 1:
                out = bytearray(nframes * ch * 2); o=0
                for (u,) in struct.iter_unpack("<B", raw):
                    s = (u - 128) << 8; out[o:o+2] = struct.pack("<h", s); o+=2
                raw16 = bytes(out)
            else:
                raise wave.Error(f"Unsupported PCM bit depth: {bps} bit")
    elif fmt == 3 and bps == 32:
        bytes_per_frame = ch * 4; to_read = nframes * bytes_per_frame
        with open(path, "rb") as f:
            f.seek(hdr["data_offset"], io.SEEK_SET); buf = f.read(to_read)
            raw16 = float32_to_int16le_bytes(buf)
    else:
        raise wave.Error(f"Unsupported WAV format (format_tag={fmt}, bits={bps}).")

    if ch == 1:
        raw16 = mono_to_stereo(raw16, 1); ch = 2
    elif ch != 2:
        raw16 = nch_to_stereo_take_first_two(raw16, ch); ch = 2
    if sr != TARGET_SR:
        raw16 = resample_linear_int16(raw16, sr, TARGET_SR); sr = TARGET_SR
    return raw16, sr, 2, 16

# === BUILDERS ===
def build_remix(files, inst_weight_map=None, out_frames_target=None):
    """Creative build (with optional 63/27 structure and rotating beats)."""
    sr = TARGET_SR
    cross_frames = int(sr * (CROSSFADE_MS/1000.0))
    drum_segs = []; perc_segs = []; melodic_segs = []
    file_segments = []
    frames_per_instrument = {}

    def weight_for(canon):
        if not inst_weight_map or not canon: return 0.0
        return inst_weight_map.get(canon, 0.0)

    for path in files:
        try:
            hdr = quick_wav_header(path)
            raw16, sr_, ch, bps = read_convert_to_target(path, hdr)
            cleaned, _, _ = trim_and_gate_int16_stereo(raw16, sr_)
            if not cleaned: continue
            canon = _instrument_of_path(path)
            cls = _class_of_canon(canon) if canon else "melodic"

            if HAVE_NUMPY:
                arr = _to_np_int16(cleaned)
                min_len = int(sr*(SEG_MIN_MS/1000.0))
                max_len = int(sr*(SEG_MAX_MS/1000.0))
                segs = []
                if arr.shape[0] >= min_len:
                    aim = max(1, int(arr.shape[0]/((min_len+max_len)/2)))
                    mult = 1.0 + 2.0*weight_for(canon)
                    aim = max(1, int(round(aim * mult)))
                    max_aim = 64
                    if aim > max_aim: aim = max_aim
                    for _ in range(aim):
                        seg_len = random.randint(min_len, max_len)
                        start = 0 if seg_len >= arr.shape[0] else random.randint(0, arr.shape[0]-seg_len)
                        segs.append(arr[start:start+seg_len].copy())
            else:
                allsegs = _pick_segments_from_clip_bytes(cleaned, sr)
                mult = 1.0 + 2.0*weight_for(canon)
                keep = max(1, int(round(len(allsegs) * mult)))
                max_keep = 64
                if keep > max_keep: keep = max_keep
                segs = allsegs[:keep]

            if not segs: continue
            if cls == "drums": drum_segs.extend(segs)
            elif cls == "perc": perc_segs.extend(segs)
            else: melodic_segs.extend(segs)

            file_segments.append((cls, canon, segs, weight_for(canon)))
        except Exception as e:
            print(f"   ⚠️  Skipping {os.path.basename(path)}: {e}", flush=True)

    if HAVE_NUMPY:
        assembled = None
        for cls, canon, segs, _w in file_segments:
            for seg in segs:
                if random.random() < SEG_REVERSE_PROB:
                    seg = seg[::-1].copy()
                if random.random() < SEG_STUTTER_PROB:
                    seg = _np_stutter_tail(seg, sr)
                seg = _np_apply_gain(seg, MAIN_SEG_GAIN)

                # no layering with user drums/perc (we filtered inputs), keep melodic
                tag = canon if canon else "(unknown)"
                frames_per_instrument[tag] = frames_per_instrument.get(tag, 0) + int(seg.shape[0])

                if assembled is None:
                    assembled = seg.copy()
                else:
                    assembled = _np_crossfade(assembled, seg, cross_frames)

                if out_frames_target and assembled.shape[0] >= out_frames_target:
                    assembled = assembled[:out_frames_target]
                    break

        if assembled is None:
            assembled = np.zeros((sr,2), dtype=np.int16)

        # Theremin bed slightly above base
        if THEREMIN_ENABLE and THEREMIN_MIX_IN_BOTH_BUILDS:
            th = _generate_theremin_np(assembled.shape[0], sr=sr)
            assembled = _mix_with_relative_gain(assembled, th, rel_db=THEREMIN_RELATIVE_DB)

        # Apply rotating beats across 63/27 blocks
        if ROTATING_BEATS_ENABLE:
            assembled = _apply_rotating_beats_63_27(assembled, sr=sr)

        # Optional: enforce extra 63/27 inserts from motif pool (melodic)
        if STRUCT_63_27_ENABLE:
            motif_pool = (melodic_segs or [])
            assembled = _enforce_63_27_np(assembled, motif_pool, cross_frames, sr=sr)

        # Subtle periodic overlays
        assembled = _apply_periodic_stutter_glitch_np(assembled, (melodic_segs or []), sr=sr)

        assembled = _np_normalize(assembled, MASTER_TARGET_PEAK, SOFT_CLIP)
        total_frames = int(assembled.shape[0])
        return assembled, {"frames_per_instrument": frames_per_instrument, "total_frames": total_frames}

    # Pure-Python fallback (no rotating beats/minute-grid due to NumPy dependency)
    assembled = []
    for cls, canon, segs, _w in file_segments:
        for seg in segs:
            if random.random() < SEG_REVERSE_PROB:
                seg = _pp_reverse(seg)
            if random.random() < SEG_STUTTER_PROB:
                seg = _pp_stutter_tail(seg, sr)
            seg = _pp_apply_gain(seg, MAIN_SEG_GAIN)
            tag = canon if canon else "(unknown)"
            frames_per_instrument[tag] = frames_per_instrument.get(tag, 0) + len(seg)
            if not assembled:
                assembled = seg[:]
            else:
                assembled = _pp_crossfade(assembled, seg, cross_frames)
    if not assembled:
        assembled = [(0,0)]
    assembled = _pp_normalize(assembled, MASTER_TARGET_PEAK, SOFT_CLIP)
    total_frames = len(assembled)
    return assembled, {"frames_per_instrument": frames_per_instrument, "total_frames": total_frames}

def build_remix_clean_structured(files, inst_weight_map=None, out_frames_target=None):
    """Clean & flowing, with structure and rotating beats replacing recurring loops."""
    sr = TARGET_SR
    cross_frames = int(sr * (CROSSFADE_MS/1000.0))
    melodic_segs = []; base_pool = []

    def weight_for(canon):
        if not inst_weight_map or not canon: return 0.0
        return inst_weight_map.get(canon, 0.0)

    for path in files:
        try:
            hdr = quick_wav_header(path)
            raw16, sr_, ch, bps = read_convert_to_target(path, hdr)
            cleaned, _, _ = trim_and_gate_int16_stereo(raw16, sr_)
            if not cleaned: continue
            canon = _instrument_of_path(path)
            cls = _class_of_canon(canon) if canon else "melodic"

            if HAVE_NUMPY:
                arr = _to_np_int16(cleaned)
                min_len = int(sr*(SEG_MIN_MS/1000.0))
                max_len = int(sr*(SEG_MAX_MS/1000.0))
                segs = []
                if arr.shape[0] >= min_len:
                    aim = max(1, int(arr.shape[0]/((min_len+max_len)/2)))
                    mult = 1.0 + 2.0*weight_for(canon)
                    aim = max(1, int(round(aim * mult)))
                    if aim > 64: aim = 64
                    for _ in range(aim):
                        seg_len = random.randint(min_len, max_len)
                        start = 0 if seg_len >= arr.shape[0] else random.randint(0, arr.shape[0]-seg_len)
                        s = arr[start:start+seg_len].copy()
                        edge = min(int(0.02*sr), max(8, int(0.005*sr)))
                        if s.shape[0] > 2*edge:
                            s[:edge]  = _np_linear_fade(s[:edge].copy(),  fade_in=True)
                            s[-edge:] = _np_linear_fade(s[-edge:].copy(), fade_in=False)
                        segs.append(_np_apply_gain(s, MAIN_SEG_GAIN))
            else:
                segs = []
                for fr in _pick_segments_from_clip_bytes(cleaned, sr)[:64]:
                    segs.append(_pp_apply_gain(fr, MAIN_SEG_GAIN))

            if cls == "melodic":
                melodic_segs.extend(segs)
            base_pool.extend(segs)
        except Exception as e:
            print(f"   ⚠️  Clean build skip {os.path.basename(path)}: {e}", flush=True)

    if not HAVE_NUMPY:
        # Fallback simple crossfade assembly
        base = []
        target_frames = out_frames_target if out_frames_target else _sec_to_frames(15*60)
        pool = base_pool[:]
        while len(base) < target_frames and pool:
            seg = pool.pop(0)
            if not base:
                base = seg[:]
            else:
                base = _pp_crossfade(base, seg, cross_frames)
        if not base:
            base = [(0,0)] * sr
        base = _pp_normalize(base, MASTER_TARGET_PEAK, SOFT_CLIP)
        return base, {"frames_per_instrument": {}, "total_frames": len(base), "structured": True}

    # NumPy path
    target_frames = out_frames_target if out_frames_target else _sec_to_frames(15*60)
    base = None
    random.shuffle(base_pool)
    while (base.shape[0] if base is not None else 0) < target_frames and base_pool:
        seg = base_pool.pop(0)
        base = seg.copy() if base is None else _np_crossfade(base, seg, cross_frames)

    if base is None:
        base = np.zeros((sr,2), dtype=np.int16)

    # Theremin pad underlay (+dB relative)
    if THEREMIN_ENABLE and THEREMIN_MIX_IN_BOTH_BUILDS:
        th = _generate_theremin_np(base.shape[0], sr=sr)
        base = _mix_with_relative_gain(base, th, rel_db=THEREMIN_RELATIVE_DB)

    # Micro-motifs for glue in early section
    micro_len_min = 7; micro_len_max = 12
    micro_offsets = [ _sec_to_frames(10), _sec_to_frames(35) ]
    micro_repeats = 2
    motif_pool = (melodic_segs or base_pool)
    for moff in micro_offsets:
        if motif_pool:
            m = random.choice(motif_pool).copy()
            mlen_s = random.uniform(micro_len_min, micro_len_max)
            m = _np_tile_to_length(m, _sec_to_frames(mlen_s))
            for r in range(micro_repeats):
                start = moff + r * _sec_to_frames(12)
                base = _np_insert_with_crossfade(base, m, start, cross_frames)

    # Replace recurring loops with rotating beats per 63/27 block
    if ROTATING_BEATS_ENABLE:
        base = _apply_rotating_beats_63_27(base, sr=sr)
    else:
        base = _minute_grid_inserts_np(base, motif_pool=motif_pool, cross_frames=cross_frames, sr=sr)

    # Enforce 63/27 structural subloops (melodic fills) if desired
    if STRUCT_63_27_ENABLE:
        base = _enforce_63_27_np(base, motif_pool=motif_pool, cross_frames=cross_frames, sr=sr)

    # Subtle overlays so the rest stays clean
    base = _apply_periodic_stutter_glitch_np(base, pool=motif_pool, sr=sr)

    out = _np_normalize(base, MASTER_TARGET_PEAK, SOFT_CLIP)
    stats = {"frames_per_instrument": {}, "total_frames": int(out.shape[0]), "structured": True}
    return out, stats

# --- Writers ---
def _iter_consolidated_chunks(arr_or_frames, chunk_frames=44100*5):
    if HAVE_NUMPY:
        total = arr_or_frames.shape[0]
        for start in range(0, total, chunk_frames):
            end = min(total, start + chunk_frames)
            yield _from_np_int16(arr_or_frames[start:end]), end
    else:
        total = len(arr_or_frames)
        for start in range(0, total, chunk_frames):
            end = min(total, start + chunk_frames)
            yield _frames_to_bytes(arr_or_frames[start:end]), end

def write_consolidated_wav_with_progress(arr_or_frames, outdir, filename):
    bytes_per_frame = TARGET_CHANNELS * TARGET_SAMPWIDTH
    total_frames = arr_or_frames.shape[0] if HAVE_NUMPY else len(arr_or_frames)
    total_bytes = total_frames * bytes_per_frame
    RIFF_MAX_BYTES = (0xFFFFFFFF - 44)
    if total_bytes >= RIFF_MAX_BYTES:
        print(f"⚠️  Consolidated WAV (~{total_bytes/1_000_000:.1f} MB) exceeds RIFF limit; skipping single-file render.", flush=True)
        return None

    out_path = os.path.join(outdir, filename)
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(TARGET_CHANNELS)
        wf.setsampwidth(TARGET_SAMPWIDTH)
        wf.setframerate(TARGET_SR)

        last_reported = -1
        for chunk_bytes, frames_done in _iter_consolidated_chunks(arr_or_frames):
            wf.writeframes(chunk_bytes)
            pct = int((frames_done * 100) / max(1, total_frames))
            if pct // CONSOLIDATED_PROGRESS_PRINT_STEP != last_reported or pct == 100:
                last_reported = pct // CONSOLIDATED_PROGRESS_PRINT_STEP
                print(f"🧵 artificalalgorithmicconconcatenation: {pct}% ({frames_done}/{total_frames} frames)", flush=True)

    print(f"🎯 {filename} generation: 100% ({total_frames}/{total_frames} frames)", flush=True)
    est_mb = total_bytes / 1_000_000.0
    print(f"✅ Wrote {os.path.basename(out_path)} (~{est_mb:.1f} MB)", flush=True)
    try:
        real_size = os.path.getsize(out_path)
        print(f"   • Actual file size: {real_size/1_000_000:.3f} MB ({real_size} bytes)", flush=True)
    except Exception:
        pass
    return out_path
def write_wav_parts(arr_or_frames, outdir, basename=REMIX_OUTPUT_BASENAME):
    if HAVE_NUMPY:
        bytes_per_frame = TARGET_CHANNELS * TARGET_SAMPWIDTH
        total_frames = arr_or_frames.shape[0]
        start = 0; part_idx = 1
        while start < total_frames:
            max_frames = PART_ROLLOVER_BYTES // bytes_per_frame
            end = min(total_frames, start + int(max_frames))
            chunk = arr_or_frames[start:end]
            out_path = os.path.join(outdir, f"{basename}_part{part_idx:02d}.wav")
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(TARGET_CHANNELS)
                wf.setsampwidth(TARGET_SAMPWIDTH)
                wf.setframerate(TARGET_SR)
                wf.writeframes(_from_np_int16(chunk))
            mb = ((end-start) * bytes_per_frame) / 1_000_000.0
            print(f"💾 Wrote {os.path.basename(out_path)}  ({mb:.1f} MB)", flush=True)
            start = end; part_idx += 1
    else:
        bytes_per_frame = TARGET_CHANNELS * TARGET_SAMPWIDTH
        total_frames = len(arr_or_frames)
        start = 0; part_idx = 1
        while start < total_frames:
            max_frames = PART_ROLLOVER_BYTES // bytes_per_frame
            end = min(total_frames, start + int(max_frames))
            chunk = arr_or_frames[start:end]
            out_path = os.path.join(outdir, f"{basename}_part{part_idx:02d}.wav")
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(TARGET_CHANNELS)
                wf.setsampwidth(TARGET_SAMPWIDTH)
                wf.setframerate(TARGET_SR)
                wf.writeframes(_frames_to_bytes(chunk))
            mb = ((end-start) * bytes_per_frame) / 1_000_000.0
            print(f"💾 Wrote {os.path.basename(out_path)}  ({mb:.1f} MB)", flush=True)
            start = end; part_idx += 1

# === Main pipeline ===
def main(root_dirs, output_dir, sort_scope, primary_mode, instr_sequence, order_mode, mix_weights):
    if isinstance(root_dirs, (str, bytes, os.PathLike)):
        root_dirs = [str(root_dirs)]

    print("🔎 Scanning:", flush=True)
    all_files, seen_paths = [], set()
    for rd in root_dirs:
        print(f"   • {rd}", flush=True)
        files = gather_candidates(rd)
        for p in files:
            if p not in seen_paths:
                seen_paths.add(p); all_files.append(p)

    print(f"📂 Found {len(all_files)} WAV candidates across {len(root_dirs)} input path(s).", flush=True)
    if not all_files:
        print("❌ No audio files found.", flush=True); return

    build_presence_report(all_files)

    # Primary / Secondary sorting
    if sort_scope in (1, 2):
        if primary_mode == 2:
            instr_sequence = auto_instrument_sequence_by_family()
            print("\n🎼 Music-type priority engaged: melodic/harmonic → drums → perc/808/rims (bottom).")

        print("\n🪄 Instrument-aware grouping prepared.")
        groups = group_files_by_instruments(all_files, instr_sequence)

        if not _yn("Accept primary sorting by detected instrument groups?", default="y"):
            if sort_scope == 2:
                print("↪️  Primary declined; using alphabetical (digits ignored).")
                all_files = sorted(all_files, key=lambda p: alpha_key(os.path.basename(p)))
            else:
                print("↪️  Primary declined; proceeding with Secondary only.")
                sort_scope = 3
        else:
            ordered = []
            for _, gfiles in groups:
                if not gfiles: continue
                if sort_scope == 1:
                    gf_sorted = order_files(gfiles, order_mode, mix_weights=mix_weights)
                else:
                    gf_sorted = sorted(gfiles, key=lambda p: alpha_key(os.path.basename(p)))
                ordered.extend(gf_sorted)
            all_files = ordered

    if sort_scope == 3:
        all_files = order_files(all_files, order_mode, mix_weights=mix_weights)

    inst_weight_map = None
    if sort_scope in (1, 2) and primary_mode == 1 and instr_sequence:
        print("\n🎚️  Per-instrument percentages (influences the remix itself):")
        inst_weight_map = prompt_per_instrument_percentages(instr_sequence)
        if inst_weight_map:
            print("\n🎯 Target emphasis:")
            for k in instr_sequence:
                if k in inst_weight_map:
                    print(f"  • {k}: {inst_weight_map[k]*100:.1f}%")
        else:
            print("No emphasis set (all instruments equal).")

    print("\n🎛️  Building artificial remix ...", flush=True)
    remix_data, stats = build_remix(all_files, inst_weight_map=inst_weight_map)

    frames_map = stats.get("frames_per_instrument", {})
    total_frames = max(1, int(stats.get("total_frames", 1)))
    if frames_map:
        print("\n📊 Remix contribution by instrument (actual):")
        for k in sorted(frames_map.keys()):
            pct = 100.0 * (frames_map[k] / float(total_frames))
            print(f"  • {k}: {pct:.1f}%")
    else:
        print("\n📊 Remix contribution by instrument: (no tags detected)")

    print("\n📦 Writing consolidated WAV(s) ...", flush=True)
    path_visible = write_consolidated_wav_with_progress(
        remix_data, output_dir, filename=CONSOLIDATED_NAME
    )
    path_hidden = write_consolidated_wav_with_progress(
        remix_data, output_dir, filename=HIDDEN_CONSOLIDATED_NAME
    )

    print("\n🌊 Building CLEAN, structured second version ...", flush=True)
    clean_data, clean_stats = build_remix_clean_structured(all_files, inst_weight_map=inst_weight_map)
    print("📦 Writing CLEAN consolidated WAV(s) ...", flush=True)
    clean_visible = write_consolidated_wav_with_progress(
        clean_data, output_dir, filename=CLEAN_CONSOLIDATED_NAME
    )
    clean_hidden = write_consolidated_wav_with_progress(
        clean_data, output_dir, filename=CLEAN_HIDDEN_CONSOLIDATED_NAME
    )

    print("\n📦 Writing output parts ...", flush=True)
    write_wav_parts(remix_data, output_dir, basename=REMIX_OUTPUT_BASENAME)

    for p in (path_visible, path_hidden, clean_visible, clean_hidden):
        if p and os.path.isfile(p):
            try:
                sz = os.path.getsize(p)
                print(f"ℹ️  {os.path.basename(p)} size: {sz/1_000_000:.3f} MB ({sz} bytes)", flush=True)
            except Exception:
                pass

    print("✅ Remix complete.", flush=True)

# ====== Entrypoint ======
if __name__ == "__main__":
    try:
        roots = prompt_directories()
        outdir = prompt_output_directory(default_dir=roots[0])

        sort_scope = prompt_sort_scope()

        primary_mode = 1
        instr_seq = []
        if sort_scope in (1, 2):
            primary_mode = prompt_primary_mode()
            if primary_mode == 1:
                instr_seq = prompt_instrument_sequence()
                print("\nYour instrument group order:")
                for i, it in enumerate(instr_seq, 1):
                    print(f"  {i:02d}. {it}")
            else:
                instr_seq = []  # auto-built later

        order_mode = 1
        mix_weights = None
        if sort_scope in (1, 3):
            order_mode = prompt_order_mode()
            if order_mode == 5:
                mix_weights = prompt_mix_percentages()

        main(roots, outdir, sort_scope, primary_mode, instr_seq, order_mode, mix_weights)

    except KeyboardInterrupt:
        print("\n🛑 Aborted by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc(limit=2)

