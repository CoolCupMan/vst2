// Offline render test: loads the built AlgoRemix.vst3 like a DAW would, feeds it a
// synthetic stereo signal (centre "vocal" + wide pads), renders it with a fake
// transport and writes a WAV. Prints level statistics and fails on NaN/Inf/silence.
//
// Usage: AlgoRemixRenderTest <path/to/AlgoRemix.vst3> <out.wav> [seconds] [preset index]

#include <juce_audio_formats/juce_audio_formats.h>
#include <juce_audio_processors/juce_audio_processors.h>

namespace
{
    struct FakePlayHead final : juce::AudioPlayHead
    {
        double sampleRate = 44100.0, bpm = 90.0;
        juce::int64 samplePos = 0;

        juce::Optional<PositionInfo> getPosition() const override
        {
            PositionInfo info;
            info.setIsPlaying (true);
            info.setBpm (bpm);
            info.setTimeInSamples (samplePos);
            info.setTimeInSeconds ((double) samplePos / sampleRate);
            info.setPpqPosition ((double) samplePos / sampleRate * bpm / 60.0);
            return info;
        }
    };

    void fillInput (juce::AudioBuffer<float>& b, juce::int64 start, double sr)
    {
        for (int i = 0; i < b.getNumSamples(); ++i)
        {
            const double t = (double) (start + i) / sr;
            const float vocal = 0.25f * (float) std::sin (2.0 * juce::MathConstants<double>::pi * 220.0 * t)
                                * (0.5f + 0.5f * (float) std::sin (2.0 * juce::MathConstants<double>::pi * 0.5 * t));
            const float padL = 0.15f * (float) std::sin (2.0 * juce::MathConstants<double>::pi * 330.0 * t);
            const float padR = 0.15f * (float) std::sin (2.0 * juce::MathConstants<double>::pi * 415.3 * t);
            b.setSample (0, i, vocal + padL);
            b.setSample (1, i, vocal + padR);
        }
    }
}

int main (int argc, char* argv[])
{
    juce::ScopedJuceInitialiser_GUI init;

    if (argc < 3)
    {
        std::cerr << "usage: AlgoRemixRenderTest <plugin.vst3> <out.wav> [seconds] [preset]\n";
        return 2;
    }

    const juce::File pluginFile (juce::File::getCurrentWorkingDirectory().getChildFile (argv[1]));
    const juce::File outFile (juce::File::getCurrentWorkingDirectory().getChildFile (argv[2]));
    const double seconds = argc > 3 ? juce::String (argv[3]).getDoubleValue() : 70.0;
    const int preset = argc > 4 ? juce::String (argv[4]).getIntValue() : 0;

    juce::AudioPluginFormatManager formats;
    formats.addFormat (std::make_unique<juce::VST3PluginFormat>());

    juce::OwnedArray<juce::PluginDescription> found;
    juce::VST3PluginFormat vst3;
    vst3.findAllTypesForFile (found, pluginFile.getFullPathName());
    if (found.isEmpty())
    {
        std::cerr << "No plugin found in " << pluginFile.getFullPathName() << "\n";
        return 1;
    }

    constexpr double sr = 44100.0;
    constexpr int block = 512;

    juce::String error;
    auto plugin = formats.createPluginInstance (*found[0], sr, block, error);
    if (plugin == nullptr)
    {
        std::cerr << "Failed to load: " << error << "\n";
        return 1;
    }

    std::cout << "Loaded " << plugin->getName() << " with " << plugin->getParameters().size()
              << " parameters, " << plugin->getNumPrograms() << " presets\n";

    plugin->setCurrentProgram (preset);
    std::cout << "Preset: " << plugin->getProgramName (preset) << "\n";

    FakePlayHead playHead;
    playHead.sampleRate = sr;
    plugin->setPlayHead (&playHead);
    plugin->setPlayConfigDetails (2, 2, sr, block);
    plugin->prepareToPlay (sr, block);

    juce::WavAudioFormat wav;
    outFile.deleteFile();
    std::unique_ptr<juce::OutputStream> stream = std::make_unique<juce::FileOutputStream> (outFile);
    auto writer = wav.createWriterFor (stream, juce::AudioFormatWriterOptions{}
                                                   .withSampleRate (sr)
                                                   .withNumChannels (2)
                                                   .withBitsPerSample (16));
    if (writer == nullptr)
    {
        std::cerr << "Cannot write " << outFile.getFullPathName() << "\n";
        return 1;
    }

    juce::AudioBuffer<float> buffer (2, block);
    juce::MidiBuffer midi;
    const auto total = (juce::int64) (seconds * sr);
    double sumSq = 0.0;
    float peak = 0.0f;
    bool bad = false;

    for (juce::int64 pos = 0; pos < total; pos += block)
    {
        const int n = (int) juce::jmin ((juce::int64) block, total - pos);
        buffer.setSize (2, n, false, false, true);
        fillInput (buffer, pos, sr);
        playHead.samplePos = pos;

        midi.clear();
        plugin->processBlock (buffer, midi);

        for (int ch = 0; ch < 2; ++ch)
            for (int i = 0; i < n; ++i)
            {
                const float v = buffer.getSample (ch, i);
                if (! std::isfinite (v)) bad = true;
                peak = juce::jmax (peak, std::abs (v));
                sumSq += (double) v * v;
            }

        writer->writeFromAudioSampleBuffer (buffer, 0, n);
    }

    plugin->releaseResources();
    writer.reset();

    const double rms = std::sqrt (sumSq / (double) (total * 2));
    std::cout << "Rendered " << seconds << " s -> " << outFile.getFullPathName() << "\n"
              << "peak " << peak << " (" << juce::Decibels::gainToDecibels (peak) << " dBFS), rms "
              << rms << " (" << juce::Decibels::gainToDecibels ((float) rms) << " dBFS)\n";

    if (bad)  { std::cerr << "FAIL: non-finite samples\n"; return 1; }
    if (rms < 1.0e-4) { std::cerr << "FAIL: output is silent\n"; return 1; }
    if (peak > 1.0f)  { std::cerr << "FAIL: output exceeds 0 dBFS\n"; return 1; }

    std::cout << "OK\n";
    return 0;
}
