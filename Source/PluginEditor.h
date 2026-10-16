#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include "PluginProcessor.h"

class AlgoRemixEditor final : public juce::AudioProcessorEditor
{
public:
    explicit AlgoRemixEditor (AlgoRemixProcessor&);
    ~AlgoRemixEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    class LookAndFeel;
    class ParamPage;

    AlgoRemixProcessor& processor;
    std::unique_ptr<LookAndFeel> lnf;

    juce::Label title;
    juce::ComboBox presetBox;
    juce::TabbedComponent tabs { juce::TabbedButtonBar::TabsAtTop };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (AlgoRemixEditor)
};
