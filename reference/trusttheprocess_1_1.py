import os, sys, wave, struct, io, traceback

# Optional speed boost:
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
OUTPUT_BASENAME = "merged_output"       # merged_output_part01.wav, etc.
SUPPORTED_EXTS = (".wav",)

# Silence/Noise handling
SILENCE_TRIM_DB = -45        # trim leading/trailing below this RMS level
MIN_SILENCE_MS = 30          # need this much continuous silence to count as silence
REMOVE_INTERNAL_SILENCE_MS = 150  # remove internal silent blocks >= this length (0 to disable)
NOISE_GATE_DB = -50          # attenuate frames below this RMS (light gate, not hard mute)
NOISE_GATE_REDUCTION = 0.25  # multiply amplitude when gated (0=hard mute, 0.25=soft)

# Target format (we'll avoid conversion if already matching)
TARGET_SR = 44100
TARGET_CHANNELS = 2
TARGET_SAMPWIDTH = 2          # 16-bit

# Split huge outputs safely below RIFF 4 GB
PART_ROLLOVER_BYTES = 1_800_000_000
# =====================


def prompt_directory():
    while True:
        try:
            inp = input("Enter the directory containing WAVs (e.g. /storage/emulated/0/Music/needahitman/): ").strip()
        except EOFError:
            print("\nNo input received. Exiting.")
            sys.exit(1)
        inp = inp.strip('"').strip("'")
        if not inp:
            print("No path entered. Exiting.")
            sys.exit(1)
        path = os.path.abspath(os.path.expanduser(inp))
        if os.path.isdir(path):
            return path
        print(f"Path not found or not a directory: {path}\nPlease try again.\n")


def prompt_output_directory(default_dir):
    """Prompt for an output directory. Press Enter to use the input directory."""
    while True:
        try:
            inp = input(f"Enter the OUTPUT directory (Press Enter to use input dir: {default_dir}): ").strip()
        except EOFError:
            print("\nNo input received. Exiting.")
            sys.exit(1)
        inp = inp.strip('"').strip("'")
        # Default to input directory if blank
        if not inp:
            path = default_dir
        else:
            path = os.path.abspath(os.path.expanduser(inp))
        if os.path.isdir(path):
            return path
        print(f"Path not found or not a directory: {path}\nPlease try again.\n")


# --- NEW: ask only which merged part to start at (e.g., 4). Size is auto-simulated.
def prompt_start_part():
    while True:
        try:
            raw = input("Start writing at which PART number? (Press Enter for 1): ").strip()
        except EOFError:
            print("\nNo input received. Exiting.")
            sys.exit(1)
        if not raw:
            return 1
        try:
            part = int(raw)
            if 1 <= part <= 99:
                return part
            print("Please enter a number between 1 and 99.")
        except ValueError:
            print("Please enter a valid integer (e.g., 1, 2, 3, ...).")


def is_our_temp_or_output(path: str) -> bool:
    name = os.path.basename(path)
    return name.startswith(OUTPUT_BASENAME + "_part") or name.startswith(".merge_tmp_part")


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


def gather_candidates(root):
    files = []
    for p in fast_walk(root):
        if p.lower().endswith(SUPPORTED_EXTS) and not is_our_temp_or_output(p):
            files.append(p)
    files.sort()
    return files


# ----- Quick header read -----
def _read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError("Unexpected EOF")
    return b


def quick_wav_header(path):
    with open(path, "rb") as f:
        if _read_exact(f, 4) != b"RIFF":
            raise ValueError("Not RIFF")
        _ = _read_exact(f, 4)
        if _read_exact(f, 4) != b"WAVE":
            raise ValueError("Not WAVE")

        fmt = None
        data_off = None
        data_size = None

        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            chunk_id, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if chunk_id == b"fmt ":
                raw = _read_exact(f, size)
                if size < 16:
                    raise ValueError("fmt chunk too small")
                (wFormatTag, nChannels, nSamplesPerSec, _nAvgBytesPerSec,
                 nBlockAlign, wBitsPerSample) = struct.unpack("<HHIIHH", raw[:16])
                fmt = (wFormatTag, nChannels, nSamplesPerSec, wBitsPerSample, nBlockAlign)
            elif chunk_id == b"data":
                data_off = f.tell()
                data_size = size
                f.seek(size, io.SEEK_CUR)
            else:
                f.seek(size, io.SEEK_CUR)

        if not fmt or data_off is None:
            raise ValueError("Missing fmt or data chunk")

        format_tag, channels, sr, bps, blockalign = fmt
        if blockalign == 0:
            raise ValueError("Invalid blockalign=0")
        nframes = data_size // blockalign
        return {
            "format_tag": format_tag,  # 1=PCM, 3=float
            "channels": channels,
            "sr": sr,
            "bits_per_sample": bps,
            "blockalign": blockalign,
            "data_offset": data_off,
            "data_size": data_size,
            "nframes": nframes,
        }


# ----- Byte conversions -----
def pcm24_to_int16le_bytes(raw_bytes):
    out = bytearray(len(raw_bytes) // 3 * 2)
    o = 0
    for i in range(0, len(raw_bytes), 3):
        b0, b1, b2 = raw_bytes[i], raw_bytes[i+1], raw_bytes[i+2]
        val = b0 | (b1 << 8) | (b2 << 16)
        if val & 0x800000:
            val -= 0x1000000
        s16 = max(-32768, min(32767, val // 256))
        out[o:o+2] = struct.pack("<h", s16); o += 2
    return bytes(out)


def float32_to_int16le_bytes(raw_bytes):
    out = bytearray(len(raw_bytes) // 2)
    o = 0
    for (x,) in struct.iter_unpack("<f", raw_bytes):
        if x > 1.0: x = 1.0
        elif x < -1.0: x = -1.0
        s16 = int(x * 32767.0)
        if s16 < -32768: s16 = -32768
        elif s16 > 32767: s16 = 32767
        out[o:o+2] = struct.pack("<h", s16); o += 2
    return bytes(out)


def mono_to_stereo(raw16, channels):
    if channels == 2:
        return raw16
    out = bytearray(len(raw16) * 2); o = 0
    for i in range(0, len(raw16), 2):
        s = raw16[i:i+2]
        out[o:o+2] = s; out[o+2:o+4] = s; o += 4
    return bytes(out)


def nch_to_stereo_take_first_two(raw16, channels):
    if channels == 2:
        return raw16
    if channels == 1:
        return mono_to_stereo(raw16, 1)
    frame_count = len(raw16) // (2 * channels)
    out = bytearray(frame_count * 4); o = 0; step = 2 * channels
    for i in range(0, len(raw16), step):
        out[o:o+2] = raw16[i:i+2]
        out[o+2:o+4] = raw16[i+2:i+4]
        o += 4
    return bytes(out)


def resample_linear_int16(raw16_stereo, src_sr, dst_sr):
    if src_sr == dst_sr:
        return raw16_stereo
    if len(raw16_stereo) < 4:
        return raw16_stereo

    if HAVE_NUMPY:
        s = np.frombuffer(raw16_stereo, dtype='<i2')
        s = s.astype(np.int16)
        L = s[0::2].astype(np.float32)
        R = s[1::2].astype(np.float32)
        ratio = dst_sr / float(src_sr)
        frames_src = L.shape[0]
        frames_dst = int(round(frames_src * ratio))
        if frames_src <= 1 or frames_dst <= 1:
            return raw16_stereo
        src_pos = np.linspace(0, frames_src - 1, frames_dst, dtype=np.float32)
        i0 = np.floor(src_pos).astype(np.int32)
        i1 = np.minimum(i0 + 1, frames_src - 1)
        frac = src_pos - i0
        L_out = (L[i0] + (L[i1] - L[i0]) * frac).clip(-32768, 32767).astype('<i2')
        R_out = (R[i0] + (R[i1] - R[i0]) * frac).clip(-32768, 32767).astype('<i2')
        out = np.empty(frames_dst * 2, dtype='<i2')
        out[0::2] = L_out
        out[1::2] = R_out
        return out.tobytes()

    # Fallback pure-Python resampler
    total_samples = len(raw16_stereo) // 2
    frames_src = total_samples // 2
    samples = list(struct.unpack("<{}h".format(total_samples), raw16_stereo))
    L_src = samples[0::2]; R_src = samples[1::2]
    ratio = dst_sr / float(src_sr)
    frames_dst = int(round(frames_src * ratio))
    if frames_src <= 1 or frames_dst <= 1:
        return raw16_stereo
    outL = [0]*frames_dst; outR = [0]*frames_dst
    step = src_sr / float(dst_sr); pos = 0.0; last = frames_src - 1
    for i in range(frames_dst):
        i0 = int(pos); i1 = i0 + 1
        if i1 > last: i1 = last
        frac = pos - i0
        l = int(L_src[i0] + (L_src[i1] - L_src[i0]) * frac)
        r = int(R_src[i0] + (R_src[i1] - R_src[i0]) * frac)
        outL[i] = max(-32768, min(32767, l))
        outR[i] = max(-32768, min(32767, r))
        pos += step
    out = bytearray(frames_dst*4); o = 0
    for l, r in zip(outL, outR):
        out[o:o+2] = struct.pack("<h", l); out[o+2:o+4] = struct.pack("<h", r); o += 4
    return bytes(out)


# ----- Audio utilities -----
def _db_to_lin(db):
    return 10.0 ** (db / 20.0)

def trim_and_gate_int16_stereo(raw16_stereo, sr, silence_db=SILENCE_TRIM_DB,
                               min_sil_ms=MIN_SILENCE_MS,
                               gate_db=NOISE_GATE_DB, gate_mult=NOISE_GATE_REDUCTION,
                               remove_internal_sil_ms=REMOVE_INTERNAL_SILENCE_MS):
    """Trim leading/trailing silence and optionally remove long internal silences. Light noise gate."""
    if len(raw16_stereo) < 4:
        return raw16_stereo, 0, 0

    if HAVE_NUMPY:
        s = np.frombuffer(raw16_stereo, dtype='<i2').astype(np.int16)
        # shape [frames, 2]
        if s.size % 2 != 0:
            s = s[:-1]
        s = s.reshape(-1, 2)

        # --- DC offset removal ---
        s = s.astype(np.int32)
        s[:,0] -= int(np.mean(s[:,0]))
        s[:,1] -= int(np.mean(s[:,1]))
        s = np.clip(s, -32768, 32767).astype(np.int16)

        # Frame-based RMS (mono energy of stereo)
        win = max(1, int(sr * 0.02))  # 20 ms
        # Pad for simple moving RMS
        pad = win // 2
        mono = (s[:,0].astype(np.int32) + s[:,1].astype(np.int32)) / 2.0
        mono = mono.astype(np.float32)

        # moving RMS without scipy
        sq = mono * mono
        csum = np.cumsum(np.pad(sq, (1,0)))
        # windowed sum
        wsum = csum[win:] - csum[:-win]
        rms = np.sqrt(wsum / float(win))
        # align to frame count
        rms = np.pad(rms, (pad, s.shape[0]-len(rms)-pad), mode='edge') if len(rms) < s.shape[0] else rms[:s.shape[0]]

        # thresholds
        sil_th = 32767.0 * _db_to_lin(silence_db)
        gate_th = 32767.0 * _db_to_lin(gate_db)

        # --- Trim leading ---
        min_sil_frames = int(sr * (min_sil_ms/1000.0))
        start = 0
        i = 0
        while i < len(rms):
            block_end = min(len(rms), i + min_sil_frames)
            if np.max(rms[i:block_end]) > sil_th:
                start = max(0, i - int(0.005*sr))
                break
            i = block_end
        else:
            return b"", 0, len(s)

        # --- Trim trailing ---
        end = len(rms)
        j = len(rms)
        while j > 0:
            block_start = max(0, j - min_sil_frames)
            if np.max(rms[block_start:j]) > sil_th:
                end = min(len(rms), j + int(0.005*sr))
                break
            j = block_start

        s = s[start:end]

        # --- Noise gate (soft) ---
        if gate_mult < 1.0:
            mask = rms[start:end] < gate_th
            if np.any(mask):
                s = s.astype(np.float32)
                s[mask] *= gate_mult
                s = np.clip(s, -32768, 32767).astype(np.int16)

        # --- Remove internal long silences ---
        if remove_internal_sil_ms and remove_internal_sil_ms > 0:
            thr = sil_th
            min_block = int(sr * (remove_internal_sil_ms/1000.0))
            low = rms[start:end] < thr
            if np.any(low):
                idx = np.where(np.diff(np.concatenate(([0], low.view(np.int8), [0]))))[0]
                cuts = []
                for a, b in zip(idx[0::2], idx[1::2]):
                    if (b - a) >= min_block:
                        cuts.append((a, b))
                if cuts:
                    keep_chunks = []
                    last = 0
                    for a, b in cuts:
                        if a > last:
                            keep_chunks.append(s[last:a])
                        last = b
                    if last < s.shape[0]:
                        keep_chunks.append(s[last:])
                    if keep_chunks:
                        s = np.concatenate(keep_chunks, axis=0)
                    else:
                        s = np.zeros((0,2), dtype=np.int16)

        if s.size == 0:
            return b"", start, end
        inter = np.empty(s.shape[0]*2, dtype='<i2')
        inter[0::2] = s[:,0]
        inter[1::2] = s[:,1]
        return inter.tobytes(), start, end

    # Fallback (no NumPy): simpler
    samples = list(struct.iter_unpack("<hh", raw16_stereo))
    frames = len(samples)
    if frames == 0:
        return raw16_stereo, 0, 0
    def frame_abs(i):
        l, r = samples[i]
        return (abs(l) + abs(r)) // 2
    sil_th = int(32767 * _db_to_lin(silence_db))
    gate_th = int(32767 * _db_to_lin(gate_db))
    min_sil_frames = max(1, int(sr * (min_sil_ms/1000.0)))

    # trim leading
    start = 0; i = 0
    while i < frames:
        block_end = min(frames, i + min_sil_frames)
        if max(frame_abs(k) for k in range(i, block_end)) > sil_th:
            start = max(0, i - int(0.005*sr))
            break
        i = block_end
    else:
        return b"", 0, frames

    # trim trailing
    end = frames; j = frames
    while j > 0:
        block_start = max(0, j - min_sil_frames)
        if max(frame_abs(k) for k in range(block_start, j)) > sil_th:
            end = min(frames, j + int(0.005*sr))
            break
        j = block_start

    work = samples[start:end]

    if gate_mult < 1.0:
        scaled = []
        for (l, r) in work:
            if (abs(l)+abs(r))//2 < gate_th:
                l = int(l*gate_mult); r = int(r*gate_mult)
            l = max(-32768, min(32767, l))
            r = max(-32768, min(32767, r))
            scaled.append((l, r))
        work = scaled

    out = bytearray(len(work)*4); o=0
    for (l,r) in work:
        out[o:o+2] = struct.pack("<h", l); out[o+2:o+4] = struct.pack("<h", r); o+=4
    return bytes(out), start, end


def read_convert_to_target(path, hdr=None):
    if hdr is None:
        hdr = quick_wav_header(path)
    fmt = hdr["format_tag"]; sr = hdr["sr"]; ch = hdr["channels"]; bps = hdr["bits_per_sample"]
    nframes = hdr["nframes"]

    if fmt == 1:
        with wave.open(path, "rb") as r:
            r.setpos(0)
            raw = r.readframes(nframes)
            sampwidth = bps // 8
            if sampwidth == 3:
                raw16 = pcm24_to_int16le_bytes(raw)
            elif sampwidth == 2:
                raw16 = raw
            elif sampwidth == 1:
                out = bytearray(nframes * ch * 2); o=0
                for (u,) in struct.iter_unpack("<B", raw):
                    s = (u - 128) << 8
                    out[o:o+2] = struct.pack("<h", s); o+=2
                raw16 = bytes(out)
            else:
                raise wave.Error(f"Unsupported PCM bit depth: {bps} bit")
    elif fmt == 3 and bps == 32:
        bytes_per_frame = ch * 4
        to_read = nframes * bytes_per_frame
        with open(path, "rb") as f:
            f.seek(hdr["data_offset"], io.SEEK_SET)
            buf = f.read(to_read)
        raw16 = float32_to_int16le_bytes(buf)
    else:
        raise wave.Error(f"Unsupported WAV format (format_tag={fmt}, bits={bps}).")

    if ch == 1:
        raw16 = mono_to_stereo(raw16, 1); ch = 2
    elif ch != 2:
        raw16 = nch_to_stereo_take_first_two(raw16, ch); ch = 2

    if sr != TARGET_SR:
        raw16 = resample_linear_int16(raw16, sr, TARGET_SR)
        sr = TARGET_SR

    return raw16, sr, 2, 16


# --- NEW: estimate output bytes per file (post-conversion, pre-trim) ---
def estimate_output_bytes_after_convert(hdr):
    # frames at destination SR (linear resample length)
    frames_src = hdr["nframes"]
    sr_src = hdr["sr"]
    if sr_src <= 0:
        return 0
    frames_dst = frames_src if sr_src == TARGET_SR else int(round(frames_src * (TARGET_SR / float(sr_src))))
    # 16-bit stereo -> 4 bytes per frame
    return frames_dst * TARGET_CHANNELS * TARGET_SAMPWIDTH


# --- NEW: simulate packing to find where part N starts; returns start index and prints map ---
def simulate_find_start_index(files, start_part):
    current_part = 1
    part_bytes = 0
    start_index = 0
    total_est = 0

    print("\n🧩 Pre-scan & simulation (estimates, pre-trim):", flush=True)

    for idx, path in enumerate(files):
        try:
            hdr = quick_wav_header(path)
            est = estimate_output_bytes_after_convert(hdr)
        except Exception as e:
            print(f"   ⚠️  Estimation failed for {os.path.basename(path)}: {e}. Assuming 0 bytes.", flush=True)
            est = 0

        # If adding this file would exceed rollover, it begins the NEXT part
        if part_bytes + est > PART_ROLLOVER_BYTES:
            # boundary reached; next part starts here
            current_part += 1
            part_bytes = 0
            if current_part == start_part:
                start_index = idx
                print(f"   ➤ Part {start_part:02d} engages at position {idx+1}/{len(files)}: {os.path.basename(path)}", flush=True)
        part_bytes += est
        total_est += est

    if start_part == 1:
        print(f"   ➤ Part 01 engages at position 1/{len(files)}: {os.path.basename(files[0]) if files else '(none)'}", flush=True)
        start_index = 0
    elif start_index == 0 and current_part < start_part:
        # Not enough data to reach that many parts
        print(f"   ⚠️  Not enough estimated data to reach part {start_part}. Starting at end.", flush=True)
        start_index = len(files)

    print(f"   Σ Estimated total after convert: {total_est/1_000_000:.1f} MB", flush=True)
    return start_index


def main(root_dir, output_dir):
    print(f"🔎 Scanning: {root_dir}", flush=True)
    files = gather_candidates(root_dir)
    print(f"📂 Found {len(files)} WAV candidates.", flush=True)
    if not files:
        print("❌ No audio files found.", flush=True)
        return

    files.sort(key=lambda p: os.path.basename(p))

    # --- NEW: ask which part and simulate where that part begins; then skip earlier files
    start_part = prompt_start_part()
    start_index = simulate_find_start_index(files, start_part)
    files = files[start_index:]

    part_idx = start_part
    out_path = os.path.join(output_dir, f"{OUTPUT_BASENAME}_part{part_idx:02d}.wav")
    wf = wave.open(out_path, "wb")
    wf.setnchannels(TARGET_CHANNELS)
    wf.setsampwidth(TARGET_SAMPWIDTH)
    wf.setframerate(TARGET_SR)
    bytes_written = 0

    if start_index > 0:
        print(f"⏭️  Skipping first {start_index} file(s); starting merge at directory position {start_index+1}.", flush=True)
    print(f"🧱 Writing → {os.path.basename(out_path)}", flush=True)

    try:
        for i, path in enumerate(files, 1):
            name = os.path.basename(path)
            try:
                hdr = quick_wav_header(path)
                raw16, sr, ch, bps = read_convert_to_target(path, hdr)

                processed, _cut_start, _cut_end = trim_and_gate_int16_stereo(
                    raw16, sr,
                    silence_db=SILENCE_TRIM_DB,
                    min_sil_ms=MIN_SILENCE_MS,
                    gate_db=NOISE_GATE_DB,
                    gate_mult=NOISE_GATE_REDUCTION,
                    remove_internal_sil_ms=REMOVE_INTERNAL_SILENCE_MS
                )

                if not processed:
                    print(f"⚠️  Skipped (silent after trim/gate): {name}", flush=True)
                    continue

                nbytes = len(processed)

                if bytes_written + nbytes > PART_ROLLOVER_BYTES:
                    wf.close()
                    print(f"📦 Finalized part {part_idx:02d}: {out_path}  (~{bytes_written/1_000_000:.1f} MB)", flush=True)
                    part_idx += 1
                    out_path = os.path.join(output_dir, f"{OUTPUT_BASENAME}_part{part_idx:02d}.wav")
                    wf = wave.open(out_path, "wb")
                    wf.setnchannels(TARGET_CHANNELS)
                    wf.setsampwidth(TARGET_SAMPWIDTH)
                    wf.setframerate(TARGET_SR)
                    bytes_written = 0
                    print(f"🧱 Writing → {os.path.basename(out_path)}", flush=True)

                wf.writeframes(processed)
                bytes_written += nbytes
                print(f"✅ Added: {name} | wrote {nbytes/1_000_000:.2f} MB | part_size≈{bytes_written/1_000_000:.2f} MB", flush=True)

            except KeyboardInterrupt:
                print("\n🛑 Interrupted by user.", flush=True)
                raise
            except Exception as e:
                print(f"\n⚠️  Skip on error: {name} | {e}", flush=True)
                traceback.print_exc(limit=1)

        print(f"📦 Finalized part {part_idx:02d}: {out_path}  (~{bytes_written/1_000_000:.1f} MB)", flush=True)
        print("💾 Export complete.", flush=True)
        print(f"✅ WAV parts written in: {output_dir}", flush=True)
    finally:
        try: wf.close()
        except Exception: pass


if __name__ == "__main__":
    root = prompt_directory()
    outdir = prompt_output_directory(default_dir=root)
    main(root, outdir)
