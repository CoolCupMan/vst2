#include "PluginProcessor.h"
#include "PluginEditor.h"

// Cached raw parameter pointers (no string lookups on the audio thread).
#define ALGOREMIX_PARAMS(X) \
    X(mix) X(outGain) X(freeRun) \
    X(dcOn) X(gateOn) X(gateThresh) X(gateReduce) \
    X(vcOn) X(vcAmount) X(vcBassHz) X(vcBassReturn) \
    X(slOn) X(slMix) X(slMinMs) X(slMaxMs) X(slReverse) X(slStutter) X(slStutterMs) \
    X(slStutterReps) X(slXfadeMs) X(slLookback) X(slGain) \
    X(thOn) X(thLevel) X(thLevelMode) X(thRelDb) X(thLow) X(thHigh) X(thSweepMin) X(thSweepMax) \
    X(thVibHz) X(thVibDepth) X(thFm) X(thAmHz) X(thWidth) X(thMidi) X(thGlideMs) \
    X(btOn) X(btLevel) X(btTempo) X(btSwing) X(btStructure) X(btFills) X(btKickHz) X(btKickDropHz) \
    X(btKickMs) X(btSnareHz) X(btSnareMs) X(btSnareBodyMs) X(btHatClosedMs) X(btHatOpenMs) \
    X(pfOn) X(pfStutterSec) X(pfGlitchSec) X(pfStutterMs) X(pfStutterReps) X(pfGlitchMs) X(pfCrush) \
    X(pfXfadeMs) \
    X(clipOn) X(clipDrive) X(clipCeiling)

struct AlgoRemixProcessor::Params
{
#define X(name) std::atomic<float>* name = nullptr;
    ALGOREMIX_PARAMS (X)
#undef X

    explicit Params (juce::AudioProcessorValueTreeState& s)
    {
#define X(name) name = s.getRawParameterValue (ParamID::name); jassert (name != nullptr);
        ALGOREMIX_PARAMS (X)
#undef X
    }
};

namespace
{
    inline float val (const std::atomic<float>* p) noexcept { return p->load (std::memory_order_relaxed); }
    inline bool on (const std::atomic<float>* p) noexcept { return val (p) >= 0.5f; }

    constexpr int smoothSlice = 32;
}

//==============================================================================
AlgoRemixProcessor::AlgoRemixProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "AlgoRemix", createParameterLayout()),
      params (std::make_unique<Params> (apvts))
{
}

AlgoRemixProcessor::~AlgoRemixProcessor() = default;

bool AlgoRemixProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;

    const auto in = layouts.getMainInputChannelSet();
    return in == juce::AudioChannelSet::stereo() || in == juce::AudioChannelSet::mono()
        || in == juce::AudioChannelSet::disabled();
}

void AlgoRemixProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    sampleRateHz = sampleRate;
    maxChunk = juce::jmax (64, samplesPerBlock);

    dryBuffer.setSize (2, maxChunk, false, true, false);
    slicerBuffer.setSize (2, maxChunk, false, true, false);

    cleaner.prepare (sampleRate);
    centerCut.prepare (sampleRate);
    slicer.prepare (sampleRate);
    theremin.prepare (sampleRate);
    beats.prepare (sampleRate);
    periodic.prepare (sampleRate);

    for (auto* s : { &mixSmoothed, &outGainSmoothed, &slMixSmoothed, &thGainSmoothed, &btGainSmoothed })
        s->reset (sampleRate, 0.03);

    mixSmoothed.setCurrentAndTargetValue (val (params->mix));
    outGainSmoothed.setCurrentAndTargetValue (ar::dbToGain (val (params->outGain)));
    slMixSmoothed.setCurrentAndTargetValue (on (params->slOn) ? val (params->slMix) : 0.0f);
    thGainSmoothed.setCurrentAndTargetValue (0.0f);
    btGainSmoothed.setCurrentAndTargetValue (0.0f);

    inputRmsCoef = ar::onePoleCoef (sampleRate, 0.3);
    inputRmsSq = 0.0f;
    internalSeconds = 0.0;
    wasPlaying = false;

    updateDspSettings();
}

void AlgoRemixProcessor::reset()
{
    cleaner.reset();
    centerCut.reset();
    slicer.reset();
    theremin.reset();
    beats.reset();
    periodic.reset();
    inputRmsSq = 0.0f;
}

void AlgoRemixProcessor::updateDspSettings()
{
    auto& p = *params;

    cleaner.setSettings ({ on (p.dcOn), on (p.gateOn), val (p.gateThresh), val (p.gateReduce) });
    centerCut.setSettings (val (p.vcAmount), val (p.vcBassHz), val (p.vcBassReturn));

    ar::Slicer::Settings sl;
    sl.minMs = val (p.slMinMs);
    sl.maxMs = val (p.slMaxMs);
    sl.reverseProb = val (p.slReverse);
    sl.stutterProb = val (p.slStutter);
    sl.stutterMs = val (p.slStutterMs);
    sl.stutterRepsMax = (int) std::lround (val (p.slStutterReps));
    sl.xfadeMs = val (p.slXfadeMs);
    sl.lookbackSec = juce::jlimit (1.0f, (float) ar::Slicer::maxLookbackSec, val (p.slLookback));
    sl.gain = val (p.slGain);
    slicer.setSettings (sl);

    ar::Theremin::Settings th;
    th.lowHz = val (p.thLow);
    th.highHz = val (p.thHigh);
    th.sweepMinSec = val (p.thSweepMin);
    th.sweepMaxSec = val (p.thSweepMax);
    th.vibHz = val (p.thVibHz);
    th.vibDepth = val (p.thVibDepth);
    th.fmDepth = val (p.thFm);
    th.amHz = val (p.thAmHz);
    th.width = val (p.thWidth);
    th.followMidi = on (p.thMidi);
    th.glideMs = val (p.thGlideMs);
    theremin.setSettings (th);

    ar::BeatMachine::Settings bt;
    bt.tempo = (int) val (p.btTempo) == 1 ? ar::BeatMachine::TempoMode::rotate : ar::BeatMachine::TempoMode::hostSync;
    bt.swing = val (p.btSwing);
    bt.structure = on (p.btStructure);
    bt.fills = on (p.btFills);
    bt.kickHz = val (p.btKickHz);
    bt.kickDropHz = val (p.btKickDropHz);
    bt.kickMs = val (p.btKickMs);
    bt.snareHz = val (p.btSnareHz);
    bt.snareNoiseMs = val (p.btSnareMs);
    bt.snareBodyMs = val (p.btSnareBodyMs);
    bt.hatClosedMs = val (p.btHatClosedMs);
    bt.hatOpenMs = val (p.btHatOpenMs);
    beats.setSettings (bt);

    ar::PeriodicFx::Settings pf;
    pf.stutterEverySec = val (p.pfStutterSec);
    pf.glitchEverySec = val (p.pfGlitchSec);
    pf.stutterMs = val (p.pfStutterMs);
    pf.stutterReps = (int) std::lround (val (p.pfStutterReps));
    pf.glitchMs = val (p.pfGlitchMs);
    pf.crush = (int) std::lround (val (p.pfCrush));
    pf.xfadeMs = val (p.pfXfadeMs);
    periodic.setSettings (pf);
}

//==============================================================================
void AlgoRemixProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;

    const int numSamples = buffer.getNumSamples();
    const int numIn = getTotalNumInputChannels();

    if (buffer.getNumChannels() < 2 || numSamples == 0)
        return;

    if (numIn == 0)
        buffer.clear();
    else if (numIn == 1)
        buffer.copyFrom (1, 0, buffer, 0, 0, numSamples);

    for (int ch = 2; ch < buffer.getNumChannels(); ++ch)
        buffer.clear (ch, 0, numSamples);

    updateDspSettings();

    // ---- transport ----
    bool hostHasInfo = false, hostPlaying = false, hasPpq = false;
    double bpm = 120.0, ppq = 0.0, hostSeconds = 0.0;

    if (auto* ph = getPlayHead())
    {
        if (auto pos = ph->getPosition())
        {
            hostHasInfo = true;
            hostPlaying = pos->getIsPlaying();
            if (auto b = pos->getBpm()) bpm = *b;
            if (auto q = pos->getPpqPosition()) { ppq = *q; hasPpq = true; }
            if (auto t = pos->getTimeInSeconds()) hostSeconds = *t;
            else if (hasPpq) hostSeconds = ppq * 60.0 / juce::jmax (1.0, bpm);
        }
    }

    // No transport info (e.g. standalone): behave as if always playing.
    const bool running = ! hostHasInfo || hostPlaying || on (params->freeRun);
    const bool useHostTime = hostHasInfo && hostPlaying;

    if (running && ! wasPlaying)
    {
        beats.resetClock();
        if (! useHostTime)
            internalSeconds = 0.0;
    }
    wasPlaying = running;

    const double songStart = useHostTime ? hostSeconds : internalSeconds;
    internalSeconds = songStart + (running ? numSamples / sampleRateHz : 0.0);

    // ---- process in chunks that fit the preallocated scratch buffers ----
    auto* L = buffer.getWritePointer (0);
    auto* R = buffer.getWritePointer (1);

    for (int offset = 0; offset < numSamples; offset += maxChunk)
    {
        const int n = juce::jmin (maxChunk, numSamples - offset);
        const double dt = offset / sampleRateHz;

        ar::BeatMachine::Clock clock;
        clock.songSeconds = songStart + dt;
        clock.hasHostPpq = useHostTime && hasPpq;
        clock.hostPpq = ppq + dt * bpm / 60.0;
        clock.hostBpm = bpm;

        processChunk (L + offset, R + offset, n, offset, midi, songStart + dt, clock, running);
    }
}

void AlgoRemixProcessor::processChunk (float* L, float* R, int n, int midiOffset, const juce::MidiBuffer& midi,
                                       double songSeconds, const ar::BeatMachine::Clock& clockAtChunk, bool running)
{
    auto& p = *params;
    auto* dryL = dryBuffer.getWritePointer (0);
    auto* dryR = dryBuffer.getWritePointer (1);
    std::copy (L, L + n, dryL);
    std::copy (R, R + n, dryR);

    // 1. Clean-up: DC + soft gate
    cleaner.process (L, R, n);

    // 2. Vocal center-cut
    if (on (p.vcOn))
        centerCut.process (L, R, n);

    // Level follower for the theremin's "Follow Input" mode.
    for (int i = 0; i < n; ++i)
    {
        const float m = 0.5f * (L[i] + R[i]);
        inputRmsSq += inputRmsCoef * (m * m - inputRmsSq);
    }

    // 3. Remix slicer
    slMixSmoothed.setTargetValue (on (p.slOn) ? val (p.slMix) : 0.0f);
    if (on (p.slOn) || slMixSmoothed.isSmoothing())
    {
        if (! slicerActive)
        {
            slicer.reset();
            slicerActive = true;
        }

        auto* sL = slicerBuffer.getWritePointer (0);
        auto* sR = slicerBuffer.getWritePointer (1);
        std::copy (L, L + n, sL);
        std::copy (R, R + n, sR);
        slicer.process (sL, sR, n);

        for (int i = 0; i < n; ++i)
        {
            const float m = slMixSmoothed.getNextValue();
            L[i] += (sL[i] - L[i]) * m;
            R[i] += (sR[i] - R[i]) * m;
        }
    }
    else
    {
        slicerActive = false;
    }

    // 4. Theremin pad (MIDI events split the render so notes land sample-accurately)
    const bool followMidi = on (p.thMidi);
    float thTarget = 0.0f;
    if (on (p.thOn) && (running || followMidi))
    {
        if ((int) val (p.thLevelMode) == 1)
            thTarget = juce::jmin (1.0f, std::sqrt (inputRmsSq) * ar::dbToGain (val (p.thRelDb)) / ar::Theremin::nominalRms);
        else
            thTarget = val (p.thLevel);
    }
    thGainSmoothed.setTargetValue (thTarget);

    auto renderTheremin = [&] (int from, int to)
    {
        for (int s = from; s < to; s += smoothSlice)
        {
            const int len = juce::jmin (smoothSlice, to - s);
            const float g = thGainSmoothed.getNextValue();
            thGainSmoothed.skip (len - 1);
            if (g > 0.0f || thGainSmoothed.isSmoothing())
                theremin.render (L + s, R + s, len, g);
        }
    };

    int pos = 0;
    for (const auto meta : midi)
    {
        const int when = meta.samplePosition - midiOffset;
        if (when < 0 || when >= n)
            continue;

        renderTheremin (pos, when);
        pos = when;

        const auto msg = meta.getMessage();
        if (followMidi)
        {
            if (msg.isNoteOn())
                theremin.noteOn (msg.getNoteNumber());
            else if (msg.isNoteOff())
                theremin.noteOff (msg.getNoteNumber());
            else if (msg.isAllNotesOff() || msg.isAllSoundOff())
                theremin.allNotesOff();
        }
    }
    renderTheremin (pos, n);

    // 5. Rotating beats
    btGainSmoothed.setTargetValue (on (p.btOn) && running ? val (p.btLevel) : 0.0f);
    if (on (p.btOn) || btGainSmoothed.isSmoothing())
    {
        for (int s = 0; s < n; s += smoothSlice)
        {
            const int len = juce::jmin (smoothSlice, n - s);
            const double dt = s / sampleRateHz;
            ar::BeatMachine::Clock c = clockAtChunk;
            c.songSeconds += dt;
            c.hostPpq += dt * c.hostBpm / 60.0;

            const float g = btGainSmoothed.getNextValue();
            btGainSmoothed.skip (len - 1);
            if (running)
                beats.render (L + s, R + s, len, c, g);
        }
    }

    // 6. Periodic stutter / glitch overlays
    if (on (p.pfOn) && running)
        periodic.process (L, R, n, songSeconds);

    // 7. Soft clip (MASTER_TARGET_PEAK * tanh)
    if (on (p.clipOn))
    {
        const float drive = val (p.clipDrive);
        const float ceiling = val (p.clipCeiling);
        for (int i = 0; i < n; ++i)
        {
            L[i] = ceiling * std::tanh (drive * L[i]);
            R[i] = ceiling * std::tanh (drive * R[i]);
        }
    }

    // 8. Dry/wet and output gain
    mixSmoothed.setTargetValue (val (p.mix));
    outGainSmoothed.setTargetValue (ar::dbToGain (val (p.outGain)));
    for (int i = 0; i < n; ++i)
    {
        const float m = mixSmoothed.getNextValue();
        const float g = outGainSmoothed.getNextValue();
        L[i] = (dryL[i] + (L[i] - dryL[i]) * m) * g;
        R[i] = (dryR[i] + (R[i] - dryR[i]) * m) * g;
    }
}

//==============================================================================
int AlgoRemixProcessor::getNumPrograms()
{
    return (int) getFactoryPresets().size();
}

const juce::String AlgoRemixProcessor::getProgramName (int index)
{
    const auto& presets = getFactoryPresets();
    if (juce::isPositiveAndBelow (index, (int) presets.size()))
        return presets[(size_t) index].name;
    return {};
}

void AlgoRemixProcessor::setCurrentProgram (int index)
{
    const auto& presets = getFactoryPresets();
    if (! juce::isPositiveAndBelow (index, (int) presets.size()))
        return;

    currentProgram = index;

    for (auto* param : getParameters())
        if (auto* ranged = dynamic_cast<juce::RangedAudioParameter*> (param))
            ranged->setValueNotifyingHost (ranged->getDefaultValue());

    for (const auto& [id, value] : presets[(size_t) index].values)
        if (auto* ranged = apvts.getParameter (id))
            ranged->setValueNotifyingHost (ranged->convertTo0to1 (value));
}

void AlgoRemixProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    state.setProperty ("program", currentProgram, nullptr);
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void AlgoRemixProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
    {
        if (xml->hasTagName (apvts.state.getType()))
        {
            auto tree = juce::ValueTree::fromXml (*xml);
            currentProgram = tree.getProperty ("program", 0);
            apvts.replaceState (tree);
        }
    }
}

juce::AudioProcessorEditor* AlgoRemixProcessor::createEditor()
{
    return new AlgoRemixEditor (*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AlgoRemixProcessor();
}
