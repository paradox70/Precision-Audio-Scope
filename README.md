# Precision Audio Scope

A powerful, cross-platform real-time oscilloscope and digital frequency counter built with Python. This tool repurposes your computer's microphone input or AUX jack into a high-precision measurement instrument.

## Overview

Traditional software oscilloscopes often struggle with stability and precision at very low frequencies. This project was developed to provide a reliable, laboratory-grade tool for visualizing waveforms and measuring frequencies with professional accuracy using standard PC hardware.

## How it works:

You can connect an external signal source (like a **Signal Generator**) to your PC's **Microphone Input** using a standard AUX cable. The software captures the raw audio data and performs high-speed analysis to display the waveform and its exact frequency.

## Key Features

- **Laboratory-Grade Precision:** Uses a specialized state-machine algorithm with 5% hysteresis and sub-sample linear interpolation to provide frequency readings accurate to 3 decimal places.

- **Superior Stability:** Optimized to provide rock-solid frequency counts even at very low ranges (1Hz - 10Hz) where other tools often flicker or fail.

- **Raw Waveform Monitoring:** Displays the unprocessed signal exactly as captured by the hardware ADC, ensuring zero artificial smoothing or distortion.

- **Interactive Scaling:** On-the-fly adjustment of time windows and voltage scales using keyboard shortcuts.

- **Cross-Platform:** Built on PyAudio, making it compatible with both Linux and Windows systems.

## Technical Specifications

- **Frequency Range:** Best suited for **1 Hz to 5,000 Hz**.

- **Sample Rate:** 48,000 Hz (Standard Lab Rate).

- **Processing:** 2.0-second sliding math window for maximum frequency resolution.

## Installation

### Prerequisites

- Python 3.6 or higher

- System libraries for audio (ALSA on Linux)

## Setup
```
pip install numpy matplotlib pyaudio
```

## How to Use

1. Connect your signal.

2. Run the application:

3. python Precision_Audio_Scope.py


## Controls:

**Left/Right Arrows:** Zoom Time (Change horizontal scale).

**Up/Down Arrows:** Zoom Voltage (Change vertical sensitivity).

**'T' Key:** Toggle Visual Trigger (Stabilize the waveform).

## Safety Warning

Ensure your input signal does not exceed **1.0V to 1.5V peak-to-peak**. Never connect a power amplifier output directly to your microphone jack.

## License

Distributed under the MIT License. See LICENSE for more information.
