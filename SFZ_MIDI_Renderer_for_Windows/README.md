# SFZ MIDI Renderer for Windows
## Violin-Piano duo SFZ MIDI renderer for Windows

***

## Installation

### 1) Install [Chocolatey](https://chocolatey.org/install)

### 2) Install latest Python via Chocolatey

```sh
# From Windows PowerShell
choco install python
```

### 3) Install mido

```sh
# From Windows PowerShell
pip install mido
```

### 4) Download and unzip latest [sfizz](https://github.com/sfztools/sfizz) binaries for Windows

```sh
# Download from https://github.com/sfztools/sfizz/releases
# I.e https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-win64.zip

# You will need only two files from release archive:
* \bin\Release\sfizz.dll
* \bin\Release\sfizz_render.exe
```

### 5) Download and unzip [HQ SFZ instruments](https://sfzinstruments.github.io/)

### 6) Download and save [sfz_renderer_midi_duo.ps1](https://github.com/asigalov61/tegridy-vibe-code/raw/refs/heads/main/SFZ_MIDI_Renderer_for_Windows/sfz_renderer_midi_duo.ps1)

***

## Basic usage

```sh
# Run the PowerShell sfz_renderer_midi_duo.ps1 script to render Violin-Piano MIDIs
# From Windows PowerShell execute the following command

# NOTE: Make sure that you change all example paths in the command below to your actual ones

powershell -ExecutionPolicy Bypass `
    -File "C:/Users/your_user_name/Desktop/SFZ/script/sfz_renderer_midi_duo.ps1" `
    -Midi "C:/Users/your_user_name/Desktop/SFZ/script/duo.mid" `
    -PianoSFZ "C:/Users/your_user_name/Desktop/SFZ/SalamanderGrandPianoV3_48khz24bit/SalamanderGrandPianoV3.sfz" `
    -ViolinSFZ "C:/Users/your_user_name/Desktop/SFZ/VPO/Virtual-Playing-Orchestra3/Strings/1st-violin-SEC-accent.sfz" `
    -Out "C:/Users/your_user_name/Desktop/SFZ/script/duo_mix.wav" `
    -SfizzRenderPath "C:/Users/your_user_name/Desktop/SFZ/script/sfizz_render.exe"
```

***

### Project Los Angeles
### Tegrity Code 2026
