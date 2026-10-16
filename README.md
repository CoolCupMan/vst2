# AlgoRemix — VST3 plugin

AlgoRemix turns the audio code in the Python scripts in [`reference/`](reference/) into a
real-time VST3 effect. It runs inside your DAW (FL Studio, Ableton, Reaper, Bitwig, Cubase, …)
with no webserver, no Python and no extra runtime.

Signal chain (each stage can be switched on and off on its own tab):

```
input → Clean → Vocal Cut → Remix Slicer → + Theremin → + Beats → Stutter/Glitch → Soft Clip → Dry/Wet → output
```

| Tab | What it does | Comes from (Python) |
|---|---|---|
| **Clean** | DC offset removal and a soft noise gate (-50 dB threshold, x0.25 floor) | `trim_and_gate_int16_stereo` |
| **Vocal Cut** | Removes center-panned vocals: `L - a·M + b·lowpass(M)` (same for R), so the bass stays | `_center_cut_np` |
| **Remix Slicer** | Records the input and plays it back as random 0.8–4 s segments with 80 ms crossfades. Each segment can be reversed (15%) or end in a stuttered tail (10%, 120 ms × 2–4) | `build_remix`, `_np_stutter_tail` |
| **Theremin** | Sine pad that glides between random notes (160–880 Hz over 5–12 s), with vibrato, FM wobble, tremolo and stereo detune. It can follow MIDI notes or the input level (+1.5 dB) | `_generate_theremin_np`, `_mix_with_relative_gain` |
| **Beats** | Synthesized kick, snare and hats (kick on 1, 1-and, 3, 4-and; snare on 2 and 4 with ghost notes; open hats) with swing. The pattern changes on every alternating 63 s / 27 s block, with fills at 0/21/42 s. Tempo follows the host or rotates through 72–96 BPM | `_generate_beat_block_np`, `_apply_rotating_beats_63_27` |
| **Stutter/Glitch** | Every 33 s, repeats the last 140 ms. Every 67 s, plays a 90 ms bit-crushed, sometimes reversed glitch | `_apply_periodic_stutter_glitch_np` |
| **Master** | `ceiling · tanh(drive · x)` soft clip, dry/wet, output gain | `_np_normalize` |

The defaults match the constants in the scripts. Seven factory presets are included
(Algorithmic Remix, Clean Structured, Instrumental (Vocal Cut), Beat Machine, Theremin Pad,
Clean-Up Only, Glitch Machine).

The file-batch parts of the scripts are not in the plugin, because a DAW does those jobs:
folder scanning, WAV reading and resampling, instrument-name sorting, merging files and
splitting output into parts. To render a whole song, use your DAW's export.

## Get the plugin

### Option A: download a build (no compiler needed)
Each push to this repository runs **GitHub Actions → Build plugin**, which builds and tests
the plugin on Windows, macOS and Linux. To get it, open the latest run under the repository's
**Actions** tab and download the **AlgoRemix-Windows** artifact (or the macOS or Linux one).
It contains `AlgoRemix.vst3`.

### Option B: build it yourself
You need CMake 3.22+ and a C++17 compiler (Visual Studio 2022 on Windows, Xcode on macOS).
JUCE is downloaded automatically.

```bash
cmake -S . -B build                 # add -G "Visual Studio 17 2022" -A x64 on Windows
cmake --build build --config Release
```

The output is `build/AlgoRemix_artefacts/Release/VST3/AlgoRemix.vst3`. A Standalone app is
built too, plus an AU on macOS.

## Install in FL Studio (Windows)

1. Copy the whole `AlgoRemix.vst3` folder to `C:\Program Files\Common Files\VST3\`.
2. In FL Studio, go to **Options → Manage plugins** and click **Find installed plugins**
   (or **Start scan**). Then star **AlgoRemix** so it shows up in your plugin list.
3. Put it on a **Mixer** track insert slot like any effect. Audio routed to that track gets
   cleaned, sliced and remixed. The theremin and beats are generators, so they also play on
   an empty mixer track.
4. Press **Play**. By default the generators and timed effects follow the song position, and
   the beats sync to the project tempo. To hear them with the transport stopped, turn on
   **Master → Run When Stopped**.
5. Optional: to play the theremin from the piano roll, turn on **Theremin → Follow MIDI**.
   Then route MIDI to the effect: add a *MIDI Out* channel on the same port as the plugin's
   MIDI input, which you set in the wrapper's settings.

On macOS, copy `AlgoRemix.vst3` to `~/Library/Audio/Plug-Ins/VST3/` (and `AlgoRemix.component`
to `~/Library/Audio/Plug-Ins/Components/` for Logic and GarageBand).

## Tests

- `pluginval` strictness 5 (the standard level) passes. It covers audio processing at several
  sample rates and block sizes, state save/load, parameter fuzzing, thread safety and bus
  layouts. At strictness 7+, only the *state restoration* test fails, on on/off switches. That
  test runs in pluginval's own host, which doesn't call `setComponentState`; real DAWs call it
  after loading a project, and that resyncs every value.
- `tools/RenderTest.cpp` loads the built `.vst3` the way a DAW does and renders a test signal
  through each preset. It fails on NaN/Inf, silence or clipping. Build it with
  `-DALGOREMIX_BUILD_TOOLS=ON`:
  ```bash
  AlgoRemixRenderTest build/AlgoRemix_artefacts/Release/VST3/AlgoRemix.vst3 out.wav 100 0
  ```
- Performance: with every stage on, 300 s of stereo audio renders in about 2.5 s on one CPU
  core, roughly 120× faster than real time.

## Notes

- Zero latency. Every buffer is allocated in `prepareToPlay`, so the audio thread never
  allocates memory or takes locks.
- Mono and stereo inputs are supported. The output is always stereo.
- Licensing: JUCE is used under its AGPLv3 / commercial license terms. If you distribute
  closed-source binaries, you need a JUCE license. Personal use and open-source use are fine.

## Project layout

```
Source/PluginProcessor.*   audio processing, transport, presets, state
Source/PluginEditor.*      tabbed UI (generated from the parameter groups)
Source/Parameters.*        all parameters and factory presets
Source/dsp/                DSP modules: InputCleaner, CenterCut, Slicer, Theremin, BeatMachine, PeriodicFx
tools/RenderTest.cpp       offline render test host
reference/                 the original Python scripts
```
