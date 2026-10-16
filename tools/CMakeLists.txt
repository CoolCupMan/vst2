juce_add_console_app(AlgoRemixRenderTest PRODUCT_NAME "AlgoRemixRenderTest")

target_sources(AlgoRemixRenderTest PRIVATE RenderTest.cpp)

target_compile_definitions(AlgoRemixRenderTest PRIVATE
    JUCE_PLUGINHOST_VST3=1
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0)

target_link_libraries(AlgoRemixRenderTest PRIVATE
    juce::juce_audio_processors
    juce::juce_audio_formats
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)
