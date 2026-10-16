#include "Parameters.h"

namespace
{
    using APF = juce::AudioParameterFloat;
    using APB = juce::AudioParameterBool;
    using APC = juce::AudioParameterChoice;
    using API = juce::AudioParameterInt;

    constexpr int paramVersion = 1;

    juce::NormalisableRange<float> range (float lo, float hi, float centre = 0.0f)
    {
        juce::NormalisableRange<float> r (lo, hi);
        if (centre > lo && centre < hi)
            r.setSkewForCentre (centre);
        return r;
    }

    std::unique_ptr<APF> flt (const char* id, const char* name, juce::NormalisableRange<float> r,
                              float def, const char* label = "")
    {
        auto toText = [] (float v, int)
        {
            const float a = std::abs (v);
            return juce::String (v, a >= 100.0f ? 0 : (a >= 10.0f ? 1 : (a >= 0.1f || a < 1.0e-6f ? 2 : 3)));
        };

        return std::make_unique<APF> (juce::ParameterID { id, paramVersion }, name, r, def,
                                      juce::AudioParameterFloatAttributes()
                                          .withLabel (label)
                                          .withStringFromValueFunction (toText));
    }

    std::unique_ptr<APB> boo (const char* id, const char* name, bool def)
    {
        return std::make_unique<APB> (juce::ParameterID { id, paramVersion }, name, def);
    }

    std::unique_ptr<API> integer (const char* id, const char* name, int lo, int hi, int def)
    {
        return std::make_unique<API> (juce::ParameterID { id, paramVersion }, name, lo, hi, def);
    }

    std::unique_ptr<APC> choice (const char* id, const char* name, juce::StringArray items, int def)
    {
        return std::make_unique<APC> (juce::ParameterID { id, paramVersion }, name, items, def);
    }
}

juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout()
{
    using namespace ParamID;
    using Group = juce::AudioProcessorParameterGroup;

    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    layout.add (std::make_unique<Group> ("master", "Master", "|",
        flt (mix,         "Dry/Wet",        range (0.0f, 1.0f), 1.0f),
        flt (outGain,     "Output",         range (-24.0f, 12.0f), 0.0f, "dB"),
        boo (clipOn,      "Soft Clip",      true),
        flt (clipDrive,   "Clip Drive",     range (0.5f, 4.0f, 1.4f), 1.0f, "x"),
        flt (clipCeiling, "Clip Ceiling",   range (0.5f, 1.0f), 0.98f),
        boo (freeRun,     "Run When Stopped", false)));

    layout.add (std::make_unique<Group> ("clean", "Clean", "|",
        boo (dcOn,        "DC Removal",     true),
        boo (gateOn,      "Noise Gate",     true),
        flt (gateThresh,  "Gate Threshold", range (-90.0f, 0.0f), -50.0f, "dB"),
        flt (gateReduce,  "Gate Floor",     range (0.0f, 1.0f), 0.25f)));

    layout.add (std::make_unique<Group> ("vocal", "Vocal Cut", "|",
        boo (vcOn,        "Vocal Cut",      false),
        flt (vcAmount,    "Center Cut",     range (0.0f, 1.0f), 0.90f),
        flt (vcBassHz,    "Bass Keep Freq", range (40.0f, 500.0f, 160.0f), 160.0f, "Hz"),
        flt (vcBassReturn,"Bass Return",    range (0.0f, 1.0f), 0.35f)));

    layout.add (std::make_unique<Group> ("slicer", "Remix Slicer", "|",
        boo (slOn,          "Slicer",         true),
        flt (slMix,         "Slicer Mix",     range (0.0f, 1.0f), 1.0f),
        flt (slMinMs,       "Seg Min",        range (50.0f, 6000.0f, 800.0f), 800.0f, "ms"),
        flt (slMaxMs,       "Seg Max",        range (50.0f, 6000.0f, 2000.0f), 4000.0f, "ms"),
        flt (slReverse,     "Reverse Prob",   range (0.0f, 1.0f), 0.15f),
        flt (slStutter,     "Stutter Prob",   range (0.0f, 1.0f), 0.10f),
        flt (slStutterMs,   "Stutter Len",    range (20.0f, 500.0f, 120.0f), 120.0f, "ms"),
        integer (slStutterReps, "Stutter Reps Max", 2, 8, 4),
        flt (slXfadeMs,     "Crossfade",      range (1.0f, 250.0f, 80.0f), 80.0f, "ms"),
        flt (slLookback,    "Lookback",       range (1.0f, 8.0f), 8.0f, "s"),
        flt (slGain,        "Segment Gain",   range (0.0f, 1.5f), 0.95f)));

    layout.add (std::make_unique<Group> ("theremin", "Theremin", "|",
        boo (thOn,        "Theremin",       true),
        flt (thLevel,     "Level",          range (0.0f, 1.0f), 0.22f),
        choice (thLevelMode, "Level Mode",  { "Fixed", "Follow Input" }, 0),
        flt (thRelDb,     "Rel. to Input",  range (-24.0f, 12.0f), 1.5f, "dB"),
        flt (thLow,       "Freq Low",       range (40.0f, 2000.0f, 300.0f), 160.0f, "Hz"),
        flt (thHigh,      "Freq High",      range (80.0f, 4000.0f, 800.0f), 880.0f, "Hz"),
        flt (thSweepMin,  "Glide Min",      range (0.1f, 30.0f, 5.0f), 5.0f, "s"),
        flt (thSweepMax,  "Glide Max",      range (0.1f, 30.0f, 8.0f), 12.0f, "s"),
        flt (thVibHz,     "Vibrato Rate",   range (0.0f, 12.0f), 5.0f, "Hz"),
        flt (thVibDepth,  "Vibrato Depth",  range (0.0f, 0.1f, 0.02f), 0.02f),
        flt (thFm,        "FM Wobble",      range (0.0f, 0.1f, 0.015f), 0.015f),
        flt (thAmHz,      "Tremolo Rate",   range (0.0f, 5.0f, 0.7f), 0.7f, "Hz"),
        flt (thWidth,     "Stereo Width",   range (0.0f, 1.0f), 0.35f),
        boo (thMidi,      "Follow MIDI",    false),
        flt (thGlideMs,   "MIDI Glide",     range (0.0f, 2000.0f, 150.0f), 150.0f, "ms")));

    layout.add (std::make_unique<Group> ("beats", "Beats", "|",
        boo (btOn,          "Beats",          true),
        flt (btLevel,       "Level",          range (0.0f, 1.0f), 0.70f),
        choice (btTempo,    "Tempo",          { "Host Sync", "Rotate 72-96" }, 0),
        flt (btSwing,       "Swing",          range (0.5f, 0.75f), 0.56f),
        boo (btStructure,   "63/27 Rotation", true),
        boo (btFills,       "Fills",          true),
        flt (btKickHz,      "Kick Freq",      range (30.0f, 120.0f), 56.0f, "Hz"),
        flt (btKickDropHz,  "Kick Drop To",   range (20.0f, 100.0f), 38.0f, "Hz"),
        flt (btKickMs,      "Kick Decay",     range (20.0f, 500.0f, 120.0f), 120.0f, "ms"),
        flt (btSnareHz,     "Snare Tone",     range (80.0f, 400.0f), 180.0f, "Hz"),
        flt (btSnareMs,     "Snare Noise",    range (20.0f, 400.0f, 130.0f), 130.0f, "ms"),
        flt (btSnareBodyMs, "Snare Body",     range (10.0f, 300.0f, 70.0f), 70.0f, "ms"),
        flt (btHatClosedMs, "Hat Closed",     range (5.0f, 200.0f, 40.0f), 40.0f, "ms"),
        flt (btHatOpenMs,   "Hat Open",       range (20.0f, 600.0f, 120.0f), 120.0f, "ms")));

    layout.add (std::make_unique<Group> ("periodic", "Stutter/Glitch", "|",
        boo (pfOn,          "Periodic FX",    true),
        flt (pfStutterSec,  "Stutter Every",  range (1.0f, 120.0f, 33.0f), 33.0f, "s"),
        flt (pfGlitchSec,   "Glitch Every",   range (1.0f, 120.0f, 67.0f), 67.0f, "s"),
        flt (pfStutterMs,   "Stutter Len",    range (20.0f, 500.0f, 140.0f), 140.0f, "ms"),
        integer (pfStutterReps, "Stutter Reps", 1, 8, 2),
        flt (pfGlitchMs,    "Glitch Len",     range (10.0f, 500.0f, 90.0f), 90.0f, "ms"),
        integer (pfCrush,   "Crush Factor",   1, 32, 6),
        flt (pfXfadeMs,     "Crossfade",      range (1.0f, 100.0f, 40.0f), 40.0f, "ms")));

    return layout;
}

const std::vector<FactoryPreset>& getFactoryPresets()
{
    using namespace ParamID;

    static const std::vector<FactoryPreset> presets {
        // Defaults == the creative build of the scripts.
        { "Algorithmic Remix", {} },

        // build_remix_clean_structured: no random reverse/stutter, structure + overlays.
        { "Clean Structured", { { slReverse, 0.0f }, { slStutter, 0.0f }, { slMinMs, 2000.0f },
                                { slMaxMs, 4000.0f } } },

        // "voiceinstrument"/"wedance" variants: center-cut vocals out.
        { "Instrumental (Vocal Cut)", { { vcOn, 1.0f } } },

        { "Beat Machine", { { slOn, 0.0f }, { thOn, 0.0f }, { pfOn, 0.0f }, { gateOn, 0.0f } } },

        { "Theremin Pad", { { slOn, 0.0f }, { btOn, 0.0f }, { pfOn, 0.0f }, { thLevel, 0.35f } } },

        // trusttheprocess.py: clean-up only (DC + gate), everything else off.
        { "Clean-Up Only", { { slOn, 0.0f }, { thOn, 0.0f }, { btOn, 0.0f }, { pfOn, 0.0f },
                             { clipOn, 0.0f } } },

        { "Glitch Machine", { { slReverse, 0.4f }, { slStutter, 0.4f }, { slMinMs, 200.0f },
                              { slMaxMs, 900.0f }, { pfStutterSec, 4.0f }, { pfGlitchSec, 7.0f },
                              { thOn, 0.0f } } },
    };

    return presets;
}
