#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "Parameters.h"
#include "dsp/BeatMachine.h"
#include "dsp/CenterCut.h"
#include "dsp/InputCleaner.h"
#include "dsp/PeriodicFx.h"
#include "dsp/Slicer.h"
#include "dsp/Theremin.h"

class AlgoRemixProcessor final : public juce::AudioProcessor
{
public:
    AlgoRemixProcessor();
    ~AlgoRemixProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    void reset() override;

    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.5; }

    int getNumPrograms() override;
    int getCurrentProgram() override { return currentProgram; }
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;

private:
    struct Params;
    void updateDspSettings();
    void processChunk (float* L, float* R, int n, int midiOffset, const juce::MidiBuffer& midi,
                       double songSeconds, const ar::BeatMachine::Clock& clockAtChunk, bool running);

    ar::InputCleaner cleaner;
    ar::CenterCut centerCut;
    ar::Slicer slicer;
    ar::Theremin theremin;
    ar::BeatMachine beats;
    ar::PeriodicFx periodic;

    juce::AudioBuffer<float> dryBuffer, slicerBuffer;
    juce::SmoothedValue<float> mixSmoothed, outGainSmoothed, slMixSmoothed, thGainSmoothed, btGainSmoothed;
    float inputRmsSq = 0.0f, inputRmsCoef = 0.001f;

    double sampleRateHz = 44100.0;
    int maxChunk = 512;

    // Internal song clock, used when the host gives no transport information.
    double internalSeconds = 0.0;
    bool wasPlaying = false;
    bool slicerActive = false;

    int currentProgram = 0;

    std::unique_ptr<Params> params;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (AlgoRemixProcessor)
};
