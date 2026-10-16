#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

// Parameter IDs. Each section mirrors a stage of the original Python remix
// scripts (see reference/), now running in real time.
namespace ParamID
{
    // Global
    inline constexpr auto mix          = "mix";
    inline constexpr auto outGain      = "outGain";
    inline constexpr auto freeRun      = "freeRun";

    // Clean-up (DC removal + soft noise gate)
    inline constexpr auto dcOn         = "dcOn";
    inline constexpr auto gateOn       = "gateOn";
    inline constexpr auto gateThresh   = "gateThresh";
    inline constexpr auto gateReduce   = "gateReduce";

    // Vocal center-cut
    inline constexpr auto vcOn         = "vcOn";
    inline constexpr auto vcAmount     = "vcAmount";
    inline constexpr auto vcBassHz     = "vcBassHz";
    inline constexpr auto vcBassReturn = "vcBassReturn";

    // Remix slicer
    inline constexpr auto slOn         = "slOn";
    inline constexpr auto slMix        = "slMix";
    inline constexpr auto slMinMs      = "slMinMs";
    inline constexpr auto slMaxMs      = "slMaxMs";
    inline constexpr auto slReverse    = "slReverse";
    inline constexpr auto slStutter    = "slStutter";
    inline constexpr auto slStutterMs  = "slStutterMs";
    inline constexpr auto slStutterReps= "slStutterReps";
    inline constexpr auto slXfadeMs    = "slXfadeMs";
    inline constexpr auto slLookback   = "slLookback";
    inline constexpr auto slGain       = "slGain";

    // Theremin pad
    inline constexpr auto thOn         = "thOn";
    inline constexpr auto thLevel      = "thLevel";
    inline constexpr auto thLevelMode  = "thLevelMode";
    inline constexpr auto thRelDb      = "thRelDb";
    inline constexpr auto thLow        = "thLow";
    inline constexpr auto thHigh       = "thHigh";
    inline constexpr auto thSweepMin   = "thSweepMin";
    inline constexpr auto thSweepMax   = "thSweepMax";
    inline constexpr auto thVibHz      = "thVibHz";
    inline constexpr auto thVibDepth   = "thVibDepth";
    inline constexpr auto thFm         = "thFm";
    inline constexpr auto thAmHz       = "thAmHz";
    inline constexpr auto thWidth      = "thWidth";
    inline constexpr auto thMidi       = "thMidi";
    inline constexpr auto thGlideMs    = "thGlideMs";

    // Rotating beats
    inline constexpr auto btOn         = "btOn";
    inline constexpr auto btLevel      = "btLevel";
    inline constexpr auto btTempo      = "btTempo";
    inline constexpr auto btSwing      = "btSwing";
    inline constexpr auto btStructure  = "btStructure";
    inline constexpr auto btFills      = "btFills";
    inline constexpr auto btKickHz     = "btKickHz";
    inline constexpr auto btKickDropHz = "btKickDropHz";
    inline constexpr auto btKickMs     = "btKickMs";
    inline constexpr auto btSnareHz    = "btSnareHz";
    inline constexpr auto btSnareMs    = "btSnareMs";
    inline constexpr auto btSnareBodyMs= "btSnareBodyMs";
    inline constexpr auto btHatClosedMs= "btHatClosedMs";
    inline constexpr auto btHatOpenMs  = "btHatOpenMs";

    // Periodic stutter / glitch overlays
    inline constexpr auto pfOn         = "pfOn";
    inline constexpr auto pfStutterSec = "pfStutterSec";
    inline constexpr auto pfGlitchSec  = "pfGlitchSec";
    inline constexpr auto pfStutterMs  = "pfStutterMs";
    inline constexpr auto pfStutterReps= "pfStutterReps";
    inline constexpr auto pfGlitchMs   = "pfGlitchMs";
    inline constexpr auto pfCrush      = "pfCrush";
    inline constexpr auto pfXfadeMs    = "pfXfadeMs";

    // Master soft clip
    inline constexpr auto clipOn       = "clipOn";
    inline constexpr auto clipDrive    = "clipDrive";
    inline constexpr auto clipCeiling  = "clipCeiling";
}

juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

// Factory presets: a name plus (paramID, plain value) overrides on top of defaults.
struct FactoryPreset
{
    const char* name;
    std::vector<std::pair<const char*, float>> values;
};

const std::vector<FactoryPreset>& getFactoryPresets();
