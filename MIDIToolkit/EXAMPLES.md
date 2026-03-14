# MIDI Toolkit Examples

This document provides concise, fully cleaned, and consistently formatted examples covering all features of the enhanced **MIDI Toolkit**. All examples use standard GitHub‑compatible Markdown and proper `python` code fences.

**Note:** All examples assume you have the toolkit code available (e.g., `MIDIToolkit.py`) and the `MIDI` module installed. Replace `"example.mid"` with an actual MIDI file path.

---

## 1. Basic Usage — Loading and Inspecting a MIDI File

```python
from MIDIToolkit import MIDIFile

# Load a MIDI file (lazy loading by default)
midi = MIDIFile("example.mid")

# Access basic properties
print(midi.ticks_per_quarter)   # e.g., 480
print(midi.num_tracks)          # number of tracks

# Get all tracks as Track objects (deep copies)
tracks = midi.tracks
for i, track in enumerate(tracks):
    print(f"Track {i}: {len(track)} events")

# Iterate over all events with track index
for track_idx, event in midi.iter_events():
    print(f"Track {track_idx}: {event.type} at time {event.time}")

# Get statistics dictionary
stats = midi.stats()
print(stats)
```

---

## 2. Event Wrappers — Typed Access to MIDI Events

```python
from MIDIToolkit import NoteEvent, TempoEvent, wrap_event

# Raw event list (as stored internally)
raw = ["note", 100, 480, 0, 60, 100]

# Wrap manually
note = NoteEvent(raw)
print(note.pitch, note.velocity, note.duration)

# Automatic dispatch
ev = wrap_event(raw)
if ev.type == "note":
    print(f"Note on channel {ev.channel}")

# Access tempo events
for tempo in midi.tempo_changes:
    print(f"Tempo at {tempo.time}: {tempo.bpm:.2f} BPM")

# Patch change
patch_events = midi.get_events_by_type("patch_change")
for ev in patch_events:
    pce = PatchChangeEvent(ev)
    print(f"Channel {pce.channel} -> {pce.instrument}")

# Control change
cc_events = midi.get_events_by_type("control_change")
for ev in cc_events:
    cce = ControlChangeEvent(ev)
    print(f"CC {cce.controller} = {cce.value} on ch {cce.channel}")

# Key signature
ks_events = midi.get_events_by_type("key_signature")
for ev in ks_events:
    kse = KeySignatureEvent(ev)
    print(f"Key: {kse.key_name}")
```

---

## 3. Track Manipulation — Using the `Track` Class

```python
from MIDIToolkit import Track

# Create a new track
track = Track()
track.append(["note", 0, 240, 0, 60, 100])
track.append(["note", 240, 240, 0, 62, 100])
track.append(["patch_change", 0, 0, 0])

# Sort events
track.sort()

# Filter events
notes_only = track.filter(lambda ev: ev.type == "note")

# Map events
def double_time(ev):
    ev.time *= 2
    if ev.type == "note":
        ev.duration *= 2
    return ev.to_list()

doubled = track.map(double_time)

# Copy
track_copy = track.copy()

# Track properties
print(track.duration)
print(track.channels_used)
print(track.pitch_range)
```

---

## 4. TempoMap — Time Conversions

```python
tempo_map = midi.tempo_map

print(tempo_map.tempo_at(1000))
print(tempo_map.bpm_at(1000))

ms = tempo_map.tick_to_ms(1000)
print(f"1000 ticks = {ms:.2f} ms")

tick = tempo_map.ms_to_tick(ms)
print(f"{ms:.2f} ms = {tick} ticks")

beat = tempo_map.tick_to_beat(1000)
print(f"1000 ticks = {beat:.2f} beats")

tick2 = tempo_map.beat_to_tick(beat)
print(f"{beat:.2f} beats = {tick2} ticks")
```

---

## 5. Note Transformations — Transpose, Velocity, Quantize

```python
# Transpose
transposed = midi.transpose(2)

# Scale velocities
softer = midi.scale_velocities(0.8)

# Quantize
quantized = midi.quantize(resolution=120, swing=0.5, quantize_ends=True)

# Custom note mapping
def set_channel_one(note):
    note.channel = 1
    return note.to_list()

custom = midi.map_notes(set_channel_one)
```

---

## 6. Track-Level Operations — Extract, Replace, Add, Remove

```python
track0 = midi.get_track(0)

new_track = Track()
new_track.append(["note", 0, 480, 0, 60, 100])

midi2 = midi.with_track(1, new_track)
midi3 = midi.without_track(2)
midi4 = midi.with_added_track(new_track)

single_track_midi = midi.extract_track(0)
```

---

## 7. Merging, Mixing, Concatenation

```python
other = MIDIFile("other.mid")

merged = midi.merge(other)
mixed = midi.mix(other)
concatenated = midi.concatenate(other)
```

---

## 8. Segmentation and Time Shifting

```python
segment = midi.segment(start_time=1000, end_time=5000, tracks={0, 2})

shifted = midi.timeshift(shift=100, from_time=2000, tracks={1})

only_channel_0 = midi.grep(channels={0})
```

---

## 9. Analysis and Metadata

```python
notes = midi.get_notes()
print(f"Total notes: {len(notes)}")

text_events = midi.get_text_events(encoding="utf-8")
for te in text_events:
    print(f"{te['type']} at {te['time']}: {te['text']}")

instrument = midi.instrument_at(channel=0, time=1000)
print(f"Instrument: {instrument}")

key = midi.key_at(time=500)
print(f"Key: {key}")

stats = midi.stats()
print("Note counts per channel:", stats.get("num_notes_by_channel"))
```

---

## 10. Plugin System

```python
from MIDIToolkit import MIDIPlugin, PluginRegistry

class MuteChannelPlugin(MIDIPlugin):
    name = "mute_channel"

    def __init__(self, channel):
        self.channel = channel

    def process(self, midi):
        def mute_if_channel(ev):
            if ev.type == "note" and ev.channel == self.channel:
                ev.velocity = 0
            return ev.to_list()
        return midi.map_notes(mute_if_channel)

PluginRegistry.register(MuteChannelPlugin)

print(PluginRegistry.list_plugins())

muted = midi.apply("mute_channel", channel=1)

plugin = MuteChannelPlugin(channel=2)
muted2 = midi.apply_plugin(plugin)
```

---

## 11. Validation and Reporting

```python
warnings = midi.validate()
if warnings:
    print("Validation warnings:")
    for w in warnings:
        print("  ", w)

print(midi.info())
print(midi.debug_report())
```

---

## 12. Playback and Saving

```python
midi.play()

midi.save("output.mid")
midi.save(Path("new/path/example.mid"))
```

---

## 13. Working from Memory (No File on Disk)

```python
with open("example.mid", "rb") as f:
    data = f.read()

midi_from_bytes = MIDIFile.from_memory(data)

opus = midi_from_bytes.to_opus()
midi_from_opus = MIDIFile.from_opus(opus)

score = midi_from_opus.to_score()
midi_from_score = MIDIFile.from_score(score)

midi_ms = midi.to_milliseconds()
```

---

## 14. Context Manager and Lazy Loading

```python
with MIDIFile("example.mid") as midi:
    print(midi.num_tracks)

midi_lazy = MIDIFile("example.mid", lazy=True)
print(midi_lazy.num_tracks)  # triggers loading
```

---

## 15. Utility — Track Filtering and Mapping

```python
high_notes = midi.tracks[0].filter(
    lambda ev: ev.type == "note" and ev.pitch > 60
)

def to_c4(ev):
    if ev.type == "note":
        ev.pitch = 60
    return ev.to_list()

c4_track = midi.tracks[0].map(to_c4)

track.extend([
    ["note", 480, 240, 0, 64, 100],
    ["note", 720, 240, 0, 67, 100],
])
```

---

These examples cover every public method and feature of the MIDI Toolkit and are now formatted cleanly for GitHub README usage.

---

### Project Los Angeles
### Tegridy Code 2026