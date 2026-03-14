# MIDIToolkit

## **Enhanced MIDI manipulation library with immutable, chainable operations built on the classic MIDI.py module by Peter Billam**

<img width="1024" height="1024" alt="Copilot_20260302_161630" src="https://github.com/user-attachments/assets/8b4c7d4d-7da3-47d9-adc0-a14dd581a90d" />

---

MIDIToolkit provides a high‑level, Pythonic interface for reading, transforming, and writing MIDI files. It wraps the classic `MIDI.py` parser with a modern layer of immutable objects, event wrappers, track abstractions, tempo mapping utilities, and a plugin system designed for expressive, safe, and reusable MIDI processing workflows.

---

## Key Features

- **Immutable, chainable operations** — Every transformation returns a new `MIDIFile` instance.
- **Typed event wrappers** — `NoteEvent`, `TempoEvent`, `PatchChangeEvent`, `ControlChangeEvent`, `KeySignatureEvent`, and more.
- **Track abstraction** — Filter, map, sort, copy, and inspect metadata such as duration, pitch range, and channels used.
- **TempoMap utilities** — Convert between ticks, milliseconds, and beats with full support for tempo changes.
- **Plugin system** — Extend functionality with custom plugins; includes a registry for discovery and invocation.
- **Comprehensive transformations** — Transpose, scale velocities, quantize, segment, time‑shift, merge, mix, concatenate, and grep channels.
- **Analysis & reporting** — Statistics, instrument lookup, key signature lookup, text events, validation, and human‑readable summaries.
- **Flexible I/O** — Load from file, bytes, opus list, or score list; save to disk or memory.
- **Lazy loading** — Delay file parsing until data is accessed.
- **Playback** — Cross‑platform MIDI playback using available system tools.

---

## Installation

MIDIToolkit requires only Python 3

Install via pip:

```python
!pip install midipytoolkit
```

Or download the two core files and place them in your project directory or Python path:

- [`MIDI.py`](https://github.com/asigalov61/MIDIToolkit/blob/main/MIDI.py) — classic MIDI parser  
- [`MIDIToolkit.py`](https://github.com/asigalov61/MIDIToolkit/blob/main/MIDIToolkit.py) — enhanced toolkit

Or clone the repository:

```bash
git clone https://github.com/asigalov61/tegridy-vibe-code
cd tegridy-vibe-code/MIDIToolkit
```

Import the toolkit:

```python
from MIDIToolkit import MIDIFile
```

---

## Quick Start

```python
from MIDIToolkit import MIDIFile

# Load a MIDI file (lazy loading by default)
midi = MIDIFile("example.mid")

# Inspect basic properties
print(midi.ticks_per_quarter)   # e.g. 480
print(midi.num_tracks)          # number of tracks

# Get all notes
notes = midi.get_notes()
print(f"Total notes: {len(notes)}")

# Transpose all notes up by 2 semitones
transposed = midi.transpose(2)

# Save the result
transposed.save("transposed.mid")
```

---

## Documentation & Examples

A complete reference with runnable examples is available in  
**[EXAMPLES.md](https://github.com/asigalov61/MIDIToolkit/blob/main/EXAMPLES.md)**.

Topics include:

- Loading and inspecting MIDI files  
- Event wrappers  
- Track manipulation  
- Tempo map conversions  
- Note transformations  
- Track‑level operations  
- Merging, mixing, concatenation  
- Segmentation and time shifting  
- Analysis and metadata  
- Plugin system  
- Validation and reporting  
- Playback and saving  
- Working from memory  
- Context manager and lazy loading  

---

## Project Structure

```
MIDIToolkit/
├── MIDI.py           # Classic low-level MIDI parser
├── MIDIToolkit.py    # Enhanced toolkit (main library)
├── EXAMPLES.md       # Comprehensive usage examples
└── README.md         # This file
```

---

## Attribution and acknowledgements

* MIDIToolkit class was passinatelly vibe-coded together with [Microsoft Copilot](https://copilot.microsoft.com/) and [DeepSeek AI](https://chat.deepseek.com/)
* README.md and EXAMPLES.md were co-written using Microsoft Copilot and DeepSeek AI
* Artwork was created with Microsoft Copilot
* Original MIDI.py module is a courtesy of [Peter Billam](https://peterbillam.gitlab.io/miditools/)

---

## License

This project is open source. The original `MIDI.py` module is by Peter Billam and contributors; enhancements are provided under the same spirit of free use. See source files for individual notices.

---

### Project Los Angeles  

### Tegridy Code 2026


