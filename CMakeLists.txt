cmake_minimum_required(VERSION 3.22)

project(AlgoRemix VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build universal binaries on macOS so the plugin runs on Intel and Apple Silicon.
if(APPLE)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "" FORCE)
endif()

# Static MSVC runtime: the .vst3 has no dependency on the VC++ redistributable,
# so FL Studio can load it on any Windows machine.
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

# --- JUCE -----------------------------------------------------------------
# Pass -DJUCE_DIR=/path/to/JUCE to use a local checkout, otherwise it is fetched.
set(JUCE_DIR "" CACHE PATH "Path to a local JUCE checkout (optional)")

if(JUCE_DIR)
    add_subdirectory(${JUCE_DIR} ${CMAKE_BINARY_DIR}/JUCE EXCLUDE_FROM_ALL)
else()
    include(FetchContent)
    FetchContent_Declare(
        JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG        8.0.12
        GIT_SHALLOW    TRUE)
    FetchContent_MakeAvailable(JUCE)
endif()

# --- Plugin ---------------------------------------------------------------
set(ALGOREMIX_FORMATS VST3 Standalone)
if(APPLE)
    list(APPEND ALGOREMIX_FORMATS AU)
endif()

juce_add_plugin(AlgoRemix
    COMPANY_NAME                "CoolCupMan"
    COMPANY_WEBSITE             "https://github.com/coolcupman/vst2"
    BUNDLE_ID                   "com.coolcupman.algoremix"
    PLUGIN_MANUFACTURER_CODE    Ccmn
    PLUGIN_CODE                 Algr
    PRODUCT_NAME                "AlgoRemix"
    FORMATS                     ${ALGOREMIX_FORMATS}
    IS_SYNTH                    FALSE
    NEEDS_MIDI_INPUT            TRUE      # MIDI notes can drive the theremin
    NEEDS_MIDI_OUTPUT           FALSE
    IS_MIDI_EFFECT              FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD     FALSE
    VST3_CATEGORIES             Fx Generator
    AU_MAIN_TYPE                kAudioUnitType_MusicEffect)

target_sources(AlgoRemix PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/Parameters.cpp)

target_include_directories(AlgoRemix PRIVATE Source)

target_compile_definitions(AlgoRemix PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

target_link_libraries(AlgoRemix
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)

# --- Optional offline render test (loads the built VST3 and renders a WAV) --
option(ALGOREMIX_BUILD_TOOLS "Build the offline render test host" OFF)
if(ALGOREMIX_BUILD_TOOLS)
    add_subdirectory(tools)
endif()
