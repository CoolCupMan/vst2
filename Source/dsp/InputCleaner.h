#pragma once

#include "Common.h"

namespace ar
{
    // Real-time version of the scripts' clean-up pass:
    //  - DC offset removal (was: subtract the per-file mean) -> DC-blocking high-pass
    //  - soft noise gate: frames whose 20 ms RMS falls below NOISE_GATE_DB are
    //    multiplied by NOISE_GATE_REDUCTION, with smoothed gain to avoid clicks.
    class InputCleaner
    {
    public:
        struct Settings
        {
            bool dcOn = true;
            bool gateOn = true;
            float thresholdDb = -50.0f;
            float floorGain = 0.25f;
        };

        void prepare (double sr) noexcept
        {
            sampleRate = sr;
            dcR = 1.0f - (twoPi * 10.0f / (float) sr);
            rmsCoef = onePoleCoef (sr, 0.020);
            openCoef = onePoleCoef (sr, 0.001);
            closeCoef = onePoleCoef (sr, 0.060);
            reset();
        }

        void reset() noexcept
        {
            dcX1[0] = dcX1[1] = dcY1[0] = dcY1[1] = 0.0f;
            rmsSq = 0.0f;
            gain = 1.0f;
        }

        void setSettings (const Settings& s) noexcept
        {
            settings = s;
            threshold = dbToGain (s.thresholdDb);
        }

        void process (float* L, float* R, int n) noexcept
        {
            if (! settings.dcOn && ! settings.gateOn)
                return;

            for (int i = 0; i < n; ++i)
            {
                float l = L[i], r = R[i];

                if (settings.dcOn)
                {
                    const float yl = l - dcX1[0] + dcR * dcY1[0];
                    const float yr = r - dcX1[1] + dcR * dcY1[1];
                    dcX1[0] = l; dcY1[0] = yl; l = yl;
                    dcX1[1] = r; dcY1[1] = yr; r = yr;
                }

                if (settings.gateOn)
                {
                    const float mono = 0.5f * (l + r);
                    rmsSq += rmsCoef * (mono * mono - rmsSq);
                    const float target = std::sqrt (rmsSq) < threshold ? settings.floorGain : 1.0f;
                    gain += (target > gain ? openCoef : closeCoef) * (target - gain);
                    l *= gain;
                    r *= gain;
                }

                L[i] = l;
                R[i] = r;
            }
        }

    private:
        Settings settings;
        double sampleRate = 44100.0;
        float dcR = 0.999f;
        float dcX1[2] {}, dcY1[2] {};
        float rmsCoef = 0.001f, openCoef = 0.02f, closeCoef = 0.001f;
        float rmsSq = 0.0f, gain = 1.0f, threshold = 0.003f;
    };
}
