#include "PluginEditor.h"

namespace Colours
{
    const juce::Colour background { 0xff15171c };
    const juce::Colour panel      { 0xff1f232b };
    const juce::Colour accent     { 0xff4fd1c5 };
    const juce::Colour accent2    { 0xfff6ad55 };
    const juce::Colour text       { 0xffe2e8f0 };
    const juce::Colour dim        { 0xff8a94a6 };
}

//==============================================================================
class AlgoRemixEditor::LookAndFeel final : public juce::LookAndFeel_V4
{
public:
    LookAndFeel()
    {
        setColour (juce::ResizableWindow::backgroundColourId, Colours::background);
        setColour (juce::Slider::rotarySliderFillColourId, Colours::accent);
        setColour (juce::Slider::rotarySliderOutlineColourId, Colours::panel.brighter (0.15f));
        setColour (juce::Slider::thumbColourId, Colours::text);
        setColour (juce::Slider::textBoxTextColourId, Colours::text);
        setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
        setColour (juce::Label::textColourId, Colours::text);
        setColour (juce::ToggleButton::textColourId, Colours::text);
        setColour (juce::ToggleButton::tickColourId, Colours::accent);
        setColour (juce::ToggleButton::tickDisabledColourId, Colours::dim);
        setColour (juce::ComboBox::backgroundColourId, Colours::panel);
        setColour (juce::ComboBox::outlineColourId, Colours::panel.brighter (0.2f));
        setColour (juce::ComboBox::textColourId, Colours::text);
        setColour (juce::ComboBox::arrowColourId, Colours::accent);
        setColour (juce::PopupMenu::backgroundColourId, Colours::panel);
        setColour (juce::PopupMenu::highlightedBackgroundColourId, Colours::accent.withAlpha (0.3f));
        setColour (juce::TabbedComponent::backgroundColourId, Colours::panel);
        setColour (juce::TabbedComponent::outlineColourId, juce::Colours::transparentBlack);
        setColour (juce::TabbedButtonBar::tabOutlineColourId, juce::Colours::transparentBlack);
        setColour (juce::TabbedButtonBar::frontOutlineColourId, juce::Colours::transparentBlack);
    }

    void drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos,
                           float startAngle, float endAngle, juce::Slider& s) override
    {
        const auto bounds = juce::Rectangle<int> (x, y, w, h).toFloat().reduced (6.0f);
        const float radius = juce::jmin (bounds.getWidth(), bounds.getHeight()) * 0.5f;
        const auto centre = bounds.getCentre();
        const float lineW = juce::jmax (3.0f, radius * 0.16f);
        const float arcR = radius - lineW * 0.5f;
        const float angle = startAngle + pos * (endAngle - startAngle);

        juce::Path track;
        track.addCentredArc (centre.x, centre.y, arcR, arcR, 0.0f, startAngle, endAngle, true);
        g.setColour (s.findColour (juce::Slider::rotarySliderOutlineColourId));
        g.strokePath (track, { lineW, juce::PathStrokeType::curved, juce::PathStrokeType::rounded });

        juce::Path value;
        value.addCentredArc (centre.x, centre.y, arcR, arcR, 0.0f, startAngle, angle, true);
        g.setColour (s.isEnabled() ? s.findColour (juce::Slider::rotarySliderFillColourId) : Colours::dim);
        g.strokePath (value, { lineW, juce::PathStrokeType::curved, juce::PathStrokeType::rounded });

        const float dotR = lineW * 0.6f;
        const juce::Point<float> dot (centre.x + (arcR - lineW * 1.6f) * std::sin (angle),
                                      centre.y - (arcR - lineW * 1.6f) * std::cos (angle));
        g.setColour (Colours::text);
        g.fillEllipse (juce::Rectangle<float> (dotR * 2, dotR * 2).withCentre (dot));
    }

    void drawTabButton (juce::TabBarButton& b, juce::Graphics& g, bool isMouseOver, bool) override
    {
        auto area = b.getActiveArea().toFloat().reduced (2.0f, 4.0f);
        const bool front = b.isFrontTab();
        g.setColour (front ? Colours::accent.withAlpha (0.18f) : (isMouseOver ? Colours::panel.brighter (0.1f) : Colours::panel));
        g.fillRoundedRectangle (area, 6.0f);
        if (front)
        {
            g.setColour (Colours::accent);
            g.fillRoundedRectangle (area.removeFromBottom (3.0f), 1.5f);
        }
        g.setColour (front ? Colours::text : Colours::dim);
        g.setFont (juce::FontOptions (14.0f, juce::Font::bold));
        g.drawText (b.getButtonText(), b.getActiveArea(), juce::Justification::centred);
    }

    int getTabButtonBestWidth (juce::TabBarButton&, int) override { return 110; }
};

//==============================================================================
// A page of controls built automatically from one parameter group.
class AlgoRemixEditor::ParamPage final : public juce::Component
{
public:
    ParamPage (AlgoRemixProcessor& p, const juce::AudioProcessorParameterGroup& group)
    {
        for (auto* param : group.getParameters (false))
        {
            auto* ranged = dynamic_cast<juce::RangedAudioParameter*> (param);
            if (ranged == nullptr)
                continue;

            const auto id = ranged->getParameterID();
            auto item = std::make_unique<Item>();
            item->label.setText (ranged->getName (32), juce::dontSendNotification);
            item->label.setJustificationType (juce::Justification::centred);
            item->label.setFont (juce::FontOptions (13.0f));
            item->label.setColour (juce::Label::textColourId, Colours::dim);

            if (dynamic_cast<juce::AudioParameterBool*> (ranged) != nullptr)
            {
                item->toggle = std::make_unique<juce::ToggleButton> (ranged->getName (32));
                item->buttonAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (p.apvts, id, *item->toggle);
                addAndMakeVisible (*item->toggle);
                toggles.push_back (std::move (item));
                continue;
            }

            if (auto* c = dynamic_cast<juce::AudioParameterChoice*> (ranged))
            {
                item->combo = std::make_unique<juce::ComboBox>();
                item->combo->addItemList (c->choices, 1);
                item->comboAttachment = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment> (p.apvts, id, *item->combo);
                addAndMakeVisible (*item->combo);
            }
            else
            {
                item->slider = std::make_unique<juce::Slider> (juce::Slider::RotaryHorizontalVerticalDrag, juce::Slider::TextBoxBelow);
                item->slider->setTextBoxStyle (juce::Slider::TextBoxBelow, false, 90, 18);
                item->sliderAttachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, id, *item->slider);
                const auto suffix = ranged->getLabel();
                if (suffix.isNotEmpty())
                    item->slider->setTextValueSuffix (" " + suffix);
                item->slider->setPopupDisplayEnabled (false, false, nullptr);
                item->slider->setDoubleClickReturnValue (true, ranged->convertFrom0to1 (ranged->getDefaultValue()));
                addAndMakeVisible (*item->slider);
            }

            addAndMakeVisible (item->label);
            knobs.push_back (std::move (item));
        }
    }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (Colours::panel);
    }

    void resized() override
    {
        auto area = getLocalBounds().reduced (14, 10);

        if (! toggles.empty())
        {
            auto row = area.removeFromTop (30);
            const int w = juce::jmin (190, row.getWidth() / (int) toggles.size());
            for (auto& t : toggles)
                t->toggle->setBounds (row.removeFromLeft (w).reduced (2));
            area.removeFromTop (8);
        }

        constexpr int cellW = 112, cellH = 128;
        const int cols = juce::jmax (1, area.getWidth() / cellW);
        const int xPad = (area.getWidth() - cols * cellW) / 2;

        for (size_t i = 0; i < knobs.size(); ++i)
        {
            const int c = (int) i % cols, r = (int) i / cols;
            juce::Rectangle<int> cell (area.getX() + xPad + c * cellW, area.getY() + r * cellH, cellW, cellH);
            auto& k = *knobs[i];
            k.label.setBounds (cell.removeFromTop (18));
            if (k.slider)
                k.slider->setBounds (cell.reduced (4, 0));
            else if (k.combo)
                k.combo->setBounds (cell.withSizeKeepingCentre (cellW - 10, 26));
        }
    }

private:
    struct Item
    {
        juce::Label label;
        std::unique_ptr<juce::Slider> slider;
        std::unique_ptr<juce::ToggleButton> toggle;
        std::unique_ptr<juce::ComboBox> combo;
        std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> sliderAttachment;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> buttonAttachment;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> comboAttachment;
    };

    std::vector<std::unique_ptr<Item>> knobs, toggles;
};

//==============================================================================
AlgoRemixEditor::AlgoRemixEditor (AlgoRemixProcessor& p)
    : AudioProcessorEditor (&p), processor (p), lnf (std::make_unique<LookAndFeel>())
{
    setLookAndFeel (lnf.get());

    title.setText ("ALGOREMIX", juce::dontSendNotification);
    title.setFont (juce::FontOptions (22.0f, juce::Font::bold));
    title.setColour (juce::Label::textColourId, Colours::accent);
    addAndMakeVisible (title);

    for (int i = 0; i < processor.getNumPrograms(); ++i)
        presetBox.addItem (processor.getProgramName (i), i + 1);
    presetBox.setSelectedId (processor.getCurrentProgram() + 1, juce::dontSendNotification);
    presetBox.onChange = [this]
    {
        if (const int id = presetBox.getSelectedId(); id > 0)
            processor.setCurrentProgram (id - 1);
    };
    addAndMakeVisible (presetBox);

    tabs.setTabBarDepth (38);
    tabs.setOutline (0);
    for (auto* group : processor.getParameterTree().getSubgroups (false))
        tabs.addTab (group->getName(), Colours::panel, new ParamPage (processor, *group), true);
    addAndMakeVisible (tabs);

    setResizable (true, true);
    setResizeLimits (620, 420, 1600, 1000);
    setSize (920, 470);
}

AlgoRemixEditor::~AlgoRemixEditor()
{
    setLookAndFeel (nullptr);
}

void AlgoRemixEditor::paint (juce::Graphics& g)
{
    g.fillAll (Colours::background);
    g.setColour (Colours::dim);
    g.setFont (juce::FontOptions (12.0f));
    g.drawText ("clean > vocal cut > slicer > theremin > beats > stutter/glitch > soft clip",
                getLocalBounds().removeFromTop (48).reduced (16, 0).withTrimmedLeft (170).withTrimmedRight (240),
                juce::Justification::centredLeft);
}

void AlgoRemixEditor::resized()
{
    auto area = getLocalBounds();
    auto header = area.removeFromTop (48).reduced (16, 8);
    title.setBounds (header.removeFromLeft (160));
    presetBox.setBounds (header.removeFromRight (230));
    tabs.setBounds (area.reduced (10, 0).withTrimmedBottom (10));
}
