#! /usr/bin/python3

r'''###############################################################################
###################################################################################
#
#   MIDIToolkit
#
#	Based upon MIDI.py module v.6.7. by Peter Billam / pjb.com.au
#
#	Project Los Angeles
#
#	Tegridy Code 2026
#
#   https://github.com/Tegridy-Code/Project-Los-Angeles
#
###################################################################################
###################################################################################
#   Copyright 2026 Project Los Angeles / Tegridy Code
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
###################################################################################
###################################################################################
#
#	PARTIAL MIDI.py Module v.6.7. by Peter Billam
#   Please see TMIDI 2.3/tegridy-tools repo for full MIDI.py module code
# 
#   Or you can always download the latest full version from:
#
#   https://pjb.com.au/
#   https://peterbillam.gitlab.io/miditools/
#	
#	Copyright 2020 Peter Billam
#
###################################################################################
###################################################################################
'''

from __future__ import annotations

###################################################################################

__version__ = "26.3.2"

###################################################################################

"""
Enhanced MIDI toolkit built on top of MIDI.py

Provides:
- Event wrappers (MIDIEvent, NoteEvent, TempoEvent, etc.)
- Track abstraction
- TempoMap for tick/ms/beat conversions
- MIDIPlugin base and registry
- MIDIFile façade with immutable, chainable transformations
"""

import copy
import sys
import shutil
import subprocess
from pathlib import Path
from typing import (
    Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple, Union, Type
)

import MIDI  # classic MIDI.py module

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
DEFAULT_TEMPO = 500_000  # microseconds per quarter note (120 BPM)

# ----------------------------------------------------------------------
# Event wrappers with defensive validation
# ----------------------------------------------------------------------
class MIDIEvent:
    """Base wrapper for a MIDI event stored as a list."""

    __slots__ = ("_data",)

    def __init__(self, data: List):
        if not isinstance(data, list):
            raise TypeError(f"Expected list, got {type(data)}")
        self._data = data

    @property
    def type(self) -> str:
        return self._data[0]

    @property
    def time(self) -> int:
        return self._data[1]

    @time.setter
    def time(self, value: int) -> None:
        self._data[1] = int(value)

    def to_list(self) -> List:
        return self._data

    def clone(self) -> MIDIEvent:
        return type(self)(copy.deepcopy(self._data))

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, idx):
        return self._data[idx]

    def __setitem__(self, idx, val):
        self._data[idx] = val

    def __iter__(self):
        return iter(self._data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._data!r})"


class NoteEvent(MIDIEvent):
    def __init__(self, data: List):
        super().__init__(data)
        if len(data) < 6:
            raise ValueError(f"Note event expects at least 6 elements, got {len(data)}")
        if data[0] != "note":
            raise ValueError(f"Expected 'note' event, got {data[0]}")

    @property
    def duration(self) -> int:
        return self._data[2]

    @duration.setter
    def duration(self, value: int) -> None:
        self._data[2] = max(0, int(value))

    @property
    def channel(self) -> int:
        return self._data[3]

    @channel.setter
    def channel(self, value: int) -> None:
        v = int(value)
        if not (0 <= v <= 15):
            raise ValueError(f"Invalid channel: {v}")
        self._data[3] = v

    @property
    def pitch(self) -> int:
        return self._data[4]

    @pitch.setter
    def pitch(self, value: int) -> None:
        v = int(value)
        if v < 0:
            v = 0
        elif v > 127:
            v = 127
        self._data[4] = v

    @property
    def velocity(self) -> int:
        return self._data[5]

    @velocity.setter
    def velocity(self, value: int) -> None:
        v = int(value)
        if v < 0:
            v = 0
        elif v > 127:
            v = 127
        self._data[5] = v

    @property
    def end_time(self) -> int:
        return self.time + self.duration


class TempoEvent(MIDIEvent):
    def __init__(self, data: List):
        super().__init__(data)
        if len(data) < 3:
            raise ValueError(f"Tempo event expects at least 3 elements, got {len(data)}")
        if data[0] != "set_tempo":
            raise ValueError(f"Expected 'set_tempo' event, got {data[0]}")

    @property
    def tempo(self) -> int:
        return self._data[2]

    @tempo.setter
    def tempo(self, value: int) -> None:
        self._data[2] = max(1, int(value))

    @property
    def bpm(self) -> float:
        return 60_000_000.0 / self.tempo


class PatchChangeEvent(MIDIEvent):
    def __init__(self, data: List):
        super().__init__(data)
        if len(data) < 4:
            raise ValueError(f"PatchChange event expects at least 4 elements, got {len(data)}")
        if data[0] != "patch_change":
            raise ValueError(f"Expected 'patch_change' event, got {data[0]}")

    @property
    def channel(self) -> int:
        return self._data[2]

    @property
    def patch(self) -> int:
        return self._data[3]

    @property
    def instrument(self) -> str:
        return MIDI.Number2patch.get(self.patch, f"Unknown({self.patch})")


class ControlChangeEvent(MIDIEvent):
    def __init__(self, data: List):
        super().__init__(data)
        if len(data) < 5:
            raise ValueError(f"ControlChange event expects at least 5 elements, got {len(data)}")
        if data[0] != "control_change":
            raise ValueError(f"Expected 'control_change' event, got {data[0]}")

    @property
    def channel(self) -> int:
        return self._data[2]

    @property
    def controller(self) -> int:
        return self._data[3]

    @property
    def value(self) -> int:
        return self._data[4]


class KeySignatureEvent(MIDIEvent):
    def __init__(self, data: List):
        super().__init__(data)
        if len(data) < 4:
            raise ValueError(f"KeySignature event expects at least 4 elements, got {len(data)}")
        if data[0] != "key_signature":
            raise ValueError(f"Expected 'key_signature' event, got {data[0]}")

    @property
    def sf(self) -> int:
        return self._data[2]

    @property
    def mi(self) -> int:
        return self._data[3]

    @property
    def key_name(self) -> str:
        sharps = ["C", "G", "D", "A", "E", "B", "F#", "C#"]
        flats  = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
        if self.mi == 0:
            if self.sf >= 0:
                return sharps[self.sf] + " major"
            else:
                return flats[-self.sf] + " major"
        else:
            if self.sf >= 0:
                return sharps[self.sf] + " minor"
            else:
                return flats[-self.sf] + " minor"


def wrap_event(ev: List) -> MIDIEvent:
    """Convert a raw event list into the appropriate wrapper class."""
    t = ev[0]
    if t == "note":
        return NoteEvent(ev)
    if t == "set_tempo":
        return TempoEvent(ev)
    if t == "patch_change":
        return PatchChangeEvent(ev)
    if t == "control_change":
        return ControlChangeEvent(ev)
    if t == "key_signature":
        return KeySignatureEvent(ev)
    return MIDIEvent(ev)


# ----------------------------------------------------------------------
# Track abstraction
# ----------------------------------------------------------------------
class Track:
    """A single MIDI track, stored as a list of event lists."""

    def __init__(self, events: Optional[List[List]] = None):
        self._events: List[List] = events if events is not None else []

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[MIDIEvent]:
        for ev in self._events:
            yield wrap_event(ev)

    def __getitem__(self, idx) -> MIDIEvent:
        return wrap_event(self._events[idx])

    def __setitem__(self, idx, ev: Union[List, MIDIEvent]) -> None:
        if isinstance(ev, MIDIEvent):
            ev = ev.to_list()
        self._events[idx] = ev

    def append(self, ev: Union[List, MIDIEvent]) -> None:
        if isinstance(ev, MIDIEvent):
            ev = ev.to_list()
        self._events.append(ev)

    def extend(self, events: Iterable[Union[List, MIDIEvent]]) -> None:
        for ev in events:
            self.append(ev)

    def sort(self) -> None:
        self._events.sort(key=lambda e: (e[1], _event_priority(e[0])))

    def filter(self, pred: Callable[[MIDIEvent], bool]) -> Track:
        return Track([ev.to_list() for ev in self if pred(ev)])

    def map(self, func: Callable[[MIDIEvent], Optional[List]]) -> Track:
        new_events: List[List] = []
        for ev in self:
            res = func(ev)
            if res is not None:
                new_events.append(res)
        return Track(new_events)

    def copy(self) -> Track:
        return Track(copy.deepcopy(self._events))

    @property
    def duration(self) -> int:
        end = 0
        for ev in self:
            if ev.type == "note":
                end = max(end, ev.end_time)
            else:
                end = max(end, ev.time)
        return end

    @property
    def channels_used(self) -> Set[int]:
        chs: Set[int] = set()
        for ev in self:
            if ev.type == "note":
                chs.add(ev.channel)
            elif ev.type in ("patch_change", "control_change"):
                chs.add(ev[2])
        return chs

    @property
    def pitch_range(self) -> Optional[Tuple[int, int]]:
        low, high = None, None
        for ev in self:
            if ev.type == "note":
                p = ev.pitch
                low = p if low is None else min(low, p)
                high = p if high is None else max(high, p)
        if low is None:
            return None
        return low, high

    def to_list(self) -> List[List]:
        return self._events

    def __repr__(self) -> str:
        return f"Track(len={len(self._events)})"


def _event_priority(t: str) -> int:
    if t in ("set_tempo", "time_signature", "key_signature"):
        return 0
    if t in ("patch_change", "control_change"):
        return 1
    if t == "note":
        return 2
    if t == "end_track":
        return 99
    return 50


# ----------------------------------------------------------------------
# Tempo map (rewritten with clear interval logic)
# ----------------------------------------------------------------------
class TempoMap:
    """Tempo map for converting between ticks, ms, and beats."""

    def __init__(self, tpq: int, tempo_events: List[TempoEvent]):
        self.tpq = tpq
        # Start with default tempo at tick 0
        changes: List[Tuple[int, int]] = [(0, DEFAULT_TEMPO)]
        changes.extend((ev.time, ev.tempo) for ev in tempo_events)
        changes.sort(key=lambda x: x[0])

        # Remove duplicates: keep the last tempo for each tick
        dedup: Dict[int, int] = {}
        for t, tmp in changes:
            dedup[t] = tmp
        self._changes = sorted(dedup.items())   # list of (tick, tempo)

    def tempo_at(self, tick: int) -> int:
        tempo = self._changes[0][1]
        for t, tmp in self._changes:
            if t <= tick:
                tempo = tmp
            else:
                break
        return tempo

    def bpm_at(self, tick: int) -> float:
        return 60_000_000.0 / self.tempo_at(tick)

    def tick_to_ms(self, tick: int) -> float:
        """Convert absolute ticks to milliseconds."""
        if tick < 0:
            return 0.0
        ms = 0.0
        prev_tick = 0
        prev_tempo = self._changes[0][1]

        for change_tick, tempo in self._changes[1:]:
            if change_tick >= tick:
                # Last segment ends at tick
                delta = tick - prev_tick
                ms += delta * prev_tempo / (self.tpq * 1000.0)
                return ms
            # Full segment from prev_tick to change_tick
            delta = change_tick - prev_tick
            ms += delta * prev_tempo / (self.tpq * 1000.0)
            prev_tick = change_tick
            prev_tempo = tempo

        # After the last tempo change (or if there were none)
        delta = tick - prev_tick
        ms += delta * prev_tempo / (self.tpq * 1000.0)
        return ms

    def ms_to_tick(self, ms: float) -> int:
        """Convert milliseconds to the nearest absolute tick."""
        if ms < 0:
            return 0
        remaining_ms = ms
        prev_tick = 0
        prev_tempo = self._changes[0][1]

        for change_tick, tempo in self._changes[1:]:
            delta_ticks = change_tick - prev_tick
            block_ms = delta_ticks * prev_tempo / (self.tpq * 1000.0)
            if remaining_ms <= block_ms:
                # Inside this block
                ticks_inside = remaining_ms * self.tpq * 1000.0 / prev_tempo
                return prev_tick + int(round(ticks_inside))
            remaining_ms -= block_ms
            prev_tick = change_tick
            prev_tempo = tempo

        # After last tempo change (or if there were none)
        ticks_inside = remaining_ms * self.tpq * 1000.0 / prev_tempo
        return prev_tick + int(round(ticks_inside))

    def tick_to_beat(self, tick: int) -> float:
        return tick / float(self.tpq)

    def beat_to_tick(self, beat: float) -> int:
        return int(round(beat * self.tpq))


# ----------------------------------------------------------------------
# Plugin system (improved registry)
# ----------------------------------------------------------------------
class MIDIPlugin:
    """Base class for MIDI transformation plugins."""

    name: str = "base"

    def process(self, midi: MIDIFile) -> MIDIFile:  # type: ignore[name-defined]
        raise NotImplementedError


class PluginRegistry:
    _registry: Dict[str, Type[MIDIPlugin]] = {}

    @classmethod
    def register(cls, plugin_cls: Type[MIDIPlugin]) -> None:
        name = plugin_cls.name
        if name in cls._registry:
            raise ValueError(f"Plugin '{name}' already registered")
        cls._registry[name] = plugin_cls

    @classmethod
    def create(cls, name: str, *args, **kwargs) -> MIDIPlugin:
        if name not in cls._registry:
            raise KeyError(f"Unknown plugin: {name}")
        return cls._registry[name](*args, **kwargs)

    @classmethod
    def list_plugins(cls) -> List[str]:
        return list(cls._registry.keys())


# ----------------------------------------------------------------------
# MIDIFile façade (with safe path handling)
# ----------------------------------------------------------------------
class MIDIFile:
    """
    High-level façade over MIDI.py with immutable, chainable operations.
    """

    def __init__(self, path: Union[str, Path], lazy: bool = True):
        self.path = Path(path) if path is not None else None
        self.lazy = lazy

        self._midi: Optional[bytes] = None
        self._opus: Optional[List] = None
        self._score: Optional[List] = None
        self._stats: Optional[Dict[str, Any]] = None
        self._tempo_map: Optional[TempoMap] = None

        if not lazy and self.path is not None:
            self._load_all()

    # --- context manager ------------------------------------------------
    def __enter__(self) -> MIDIFile:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    # --- internal loading -----------------------------------------------
    def _load_midi(self) -> bytes:
        if self._midi is None:
            if self.path is None:
                raise ValueError("No MIDI data and no path to load from")
            self._midi = self.path.read_bytes()
        return self._midi

    def _load_opus(self) -> List:
        if self._opus is None:
            self._opus = MIDI.midi2opus(self._load_midi())
        return self._opus

    def _load_score(self) -> List:
        if self._score is None:
            self._score = MIDI.opus2score(self._load_opus())
        return self._score

    def _load_all(self) -> None:
        self._load_midi()
        self._load_opus()
        self._load_score()

    # --- properties -----------------------------------------------------
    @property
    def midi(self) -> bytes:
        return self._load_midi()

    @property
    def opus(self) -> List:
        return self._load_opus()

    @property
    def score(self) -> List:
        return self._load_score()

    @property
    def ticks_per_quarter(self) -> int:
        return self.score[0]

    @property
    def num_tracks(self) -> int:
        return len(self.score) - 1

    @property
    def tracks(self) -> List[Track]:
        """Return a list of Track objects, each a deep copy of the original track data."""
        return [Track(copy.deepcopy(t)) for t in self.score[1:]]

    @property
    def tempo_map(self) -> TempoMap:
        if self._tempo_map is None:
            tempo_events = [TempoEvent(ev) for ev in self.get_events_by_type("set_tempo")]
            self._tempo_map = TempoMap(self.ticks_per_quarter, tempo_events)
        return self._tempo_map

    # --- conversions ----------------------------------------------------
    def to_midi(self) -> bytes:
        return self.midi

    def to_opus(self) -> List:
        return self.opus

    def to_score(self) -> List:
        return self.score

    def to_milliseconds(self) -> MIDIFile:
        opus_ms = MIDI.to_millisecs(self.opus)
        score_ms = MIDI.opus2score(opus_ms)
        midi_ms = MIDI.score2midi(score_ms)
        return MIDIFile.from_memory(midi_ms)

    # --- track operations -----------------------------------------------
    def get_track(self, index: int) -> Track:
        """Return a deep copy of the track at the given index."""
        if not (0 <= index < self.num_tracks):
            raise IndexError(f"Track index {index} out of range")
        return Track(copy.deepcopy(self.score[index + 1]))

    def with_track(self, index: int, track: Union[Track, List[List]]) -> MIDIFile:
        """Return a new MIDIFile with the track at `index` replaced by a deep copy of `track`."""
        if not (0 <= index < self.num_tracks):
            raise IndexError(f"Track index {index} out of range")
        new_score = copy.deepcopy(self.score)
        if isinstance(track, Track):
            track_data = copy.deepcopy(track.to_list())
        else:
            track_data = copy.deepcopy(track)
        new_score[index + 1] = track_data
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    def without_track(self, index: int) -> MIDIFile:
        """Return a new MIDIFile with the track at `index` removed."""
        if not (0 <= index < self.num_tracks):
            raise IndexError(f"Track index {index} out of range")
        new_score = copy.deepcopy(self.score)
        del new_score[index + 1]
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    def with_added_track(self, track: Union[Track, List[List]]) -> MIDIFile:
        """Return a new MIDIFile with a deep copy of `track` appended."""
        new_score = copy.deepcopy(self.score)
        if isinstance(track, Track):
            track_data = copy.deepcopy(track.to_list())
        else:
            track_data = copy.deepcopy(track)
        new_score.append(track_data)
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    def extract_track(self, index: int) -> MIDIFile:
        """Return a new MIDIFile containing only a deep copy of the track at `index`."""
        t = self.get_track(index)
        new_score = [self.ticks_per_quarter, t.to_list()]
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    # --- event accessors -----------------------------------------------
    def get_events_by_type(self, event_type: str) -> List[List]:
        out: List[List] = []
        for track in self.score[1:]:
            for ev in track:
                if ev[0] == event_type:
                    out.append(ev)
        return out

    def iter_events(self) -> Iterator[Tuple[int, MIDIEvent]]:
        for ti, track in enumerate(self.tracks):
            for ev in track:
                yield ti, ev

    def get_notes(self) -> List[NoteEvent]:
        return [NoteEvent(ev) for ev in self.get_events_by_type("note")]

    def get_text_events(
        self, encoding: str = "utf-8", errors: str = "replace"
    ) -> List[Dict[str, Any]]:
        text_types = {
            "text_event",
            "copyright_text_event",
            "track_name",
            "instrument_name",
            "lyric",
            "marker",
            "cue_point",
            "text_event_08",
            "text_event_09",
            "text_event_0a",
            "text_event_0b",
            "text_event_0c",
            "text_event_0d",
            "text_event_0e",
            "text_event_0f",
        }
        result: List[Dict[str, Any]] = []
        for track in self.score[1:]:
            for ev in track:
                if ev[0] in text_types:
                    # Safely decode text
                    raw = ev[2]
                    if isinstance(raw, (bytes, bytearray)):
                        text = raw.decode(encoding, errors)
                    else:
                        text = str(raw)
                    result.append({
                        "type": ev[0],
                        "time": ev[1],
                        "text": text,
                        "raw": raw,
                    })
        return result

    # --- note transformations ------------------------------------------
    def _from_tracks(self, tracks: List[Track]) -> MIDIFile:
        """Internal: build a new MIDIFile from a list of Tracks (deep copies are made)."""
        new_score = [self.ticks_per_quarter] + [copy.deepcopy(t.to_list()) for t in tracks]
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    def map_notes(self, func: Callable[[NoteEvent], Optional[List]]) -> MIDIFile:
        def mapper(ev: MIDIEvent) -> Optional[List]:
            if ev.type == "note":
                return func(NoteEvent(ev.to_list()))
            return ev.to_list()

        new_tracks: List[Track] = []
        for t in self.tracks:
            new_tracks.append(t.map(mapper))
        return self._from_tracks(new_tracks)

    def transpose(self, semitones: int) -> MIDIFile:
        def transposer(note: NoteEvent) -> List:
            note.pitch = note.pitch + semitones
            return note.to_list()

        return self.map_notes(transposer)

    def scale_velocities(self, factor: float) -> MIDIFile:
        def scaler(note: NoteEvent) -> List:
            note.velocity = int(note.velocity * factor)
            return note.to_list()

        return self.map_notes(scaler)

    def quantize(
        self, resolution: int, swing: float = 0.0, quantize_ends: bool = False
    ) -> MIDIFile:
        def quantizer(note: NoteEvent) -> List:
            start = note.time
            grid = int(round(start / resolution))
            new_start = grid * resolution
            if swing != 0.0 and grid % 2 == 1:
                new_start += int(swing * resolution)
            note.time = new_start
            if quantize_ends:
                end = note.end_time
                grid_e = int(round(end / resolution))
                new_end = grid_e * resolution
                if swing != 0.0 and grid_e % 2 == 1:
                    new_end += int(swing * resolution)
                if new_end > new_start:
                    note.duration = new_end - new_start
            return note.to_list()

        return self.map_notes(quantizer)

    # --- tempo and time -----------------------------------------------
    def set_tempo(self, new_tempo: int, time: int = 0) -> MIDIFile:
        new_score = copy.deepcopy(self.score)
        track0 = new_score[1]
        track0 = [
            ev for ev in track0 if not (ev[0] == "set_tempo" and ev[1] == time)
        ]
        track0.append(["set_tempo", time, new_tempo])
        track0.sort(key=lambda e: (e[1], _event_priority(e[0])))
        new_score[1] = track0
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    @property
    def tempo_changes(self) -> List[TempoEvent]:
        return [TempoEvent(ev) for ev in self.get_events_by_type("set_tempo")]

    def duration_ticks(self) -> int:
        stats = self.stats()
        return stats["nticks"]

    def duration_ms(self) -> float:
        return self.tempo_map.tick_to_ms(self.duration_ticks())

    def time_scale(self, factor: float) -> MIDIFile:
        def scaler(ev: MIDIEvent) -> List:
            ev.time = int(ev.time * factor)
            if ev.type == "note":
                ev.duration = int(ev.duration * factor)
            return ev.to_list()

        new_tracks: List[Track] = []
        for t in self.tracks:
            new_tracks.append(t.map(scaler))
        return self._from_tracks(new_tracks)

    # --- analysis ------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        if self._stats is None:
            self._stats = MIDI.score2stats(self.score)
        return self._stats

    def instrument_at(self, channel: int, time: int) -> str:
        patch = None
        for ev in self.get_events_by_type("patch_change"):
            if ev[2] == channel and ev[1] <= time:
                patch = ev[3]
        if patch is None:
            return "Undefined"
        return MIDI.Number2patch.get(patch, f"Unknown({patch})")

    def key_at(self, time: int) -> Optional[str]:
        key_ev = None
        for ev in self.get_events_by_type("key_signature"):
            if ev[1] <= time:
                key_ev = ev
        if key_ev is None:
            return None
        return KeySignatureEvent(key_ev).key_name

    # --- merging / mixing / concatenation ------------------------------
    def merge(self, other: MIDIFile) -> MIDIFile:
        merged_score = MIDI.merge_scores([self.score, other.score])
        return MIDIFile.from_memory(MIDI.score2midi(merged_score))

    def mix(self, other: MIDIFile) -> MIDIFile:
        mixed_score = MIDI.mix_scores([self.score, other.score])
        return MIDIFile.from_memory(MIDI.score2midi(mixed_score))

    def concatenate(self, other: MIDIFile) -> MIDIFile:
        concat_score = MIDI.concatenate_scores([self.score, other.score])
        return MIDIFile.from_memory(MIDI.score2midi(concat_score))

    # --- grep / segmentation / shifting -------------------------------
    def grep(self, channels: Set[int]) -> MIDIFile:
        new_score = MIDI.grep(self.score, channels)
        return MIDIFile.from_memory(MIDI.score2midi(new_score))

    def segment(
        self,
        start_time: int,
        end_time: int,
        tracks: Optional[Set[int]] = None,
    ) -> MIDIFile:
        if tracks is None:
            tracks = set(range(self.num_tracks))
        seg_score = MIDI.segment(
            self.score, start_time=start_time, end_time=end_time, tracks=tracks
        )
        return MIDIFile.from_memory(MIDI.score2midi(seg_score))

    def timeshift(
        self,
        shift: int,
        from_time: int = 0,
        tracks: Optional[Set[int]] = None,
    ) -> MIDIFile:
        if tracks is None:
            tracks = set(range(self.num_tracks))
        shifted_score = MIDI.timeshift(
            self.score, shift=shift, from_time=from_time, tracks=tracks
        )
        return MIDIFile.from_memory(MIDI.score2midi(shifted_score))

    # --- playback (hardened, cross‑platform) --------------------------
    def play(self) -> None:
        """Play the MIDI file using an available system MIDI player."""
        players: List[str] = []
        if sys.platform == "win32":
            # On Windows, common command-line MIDI players (if installed)
            players = ["timidity.exe", "fluidsynth.exe", "aplaymidi.exe"]
        else:
            players = ["aplaymidi", "timidity", "fluidsynth", "pmidi"]

        cmd = None
        for p in players:
            if shutil.which(p):
                cmd = [p, "-"]
                break

        if cmd is None:
            raise RuntimeError(
                f"No MIDI player found. Tried: {', '.join(players)}. "
                "Please install one (e.g. timidity, fluidsynth, aplaymidi)."
            )

        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            proc.stdin.write(self.midi)   # type: ignore
            proc.stdin.close()
            proc.wait(timeout=10)
        except Exception as e:
            raise RuntimeError(f"Failed to play MIDI: {e}") from e

    # --- plugins -------------------------------------------------------
    def apply_plugin(self, plugin: MIDIPlugin) -> MIDIFile:
        return plugin.process(self)

    def apply(self, plugin_name: str, *args, **kwargs) -> MIDIFile:
        plugin = PluginRegistry.create(plugin_name, *args, **kwargs)
        return plugin.process(self)

    # --- validation / reporting ---------------------------------------
    def validate(self) -> List[str]:
        warnings: List[str] = []
        if self.ticks_per_quarter <= 0:
            warnings.append(f"Invalid ticks_per_quarter: {self.ticks_per_quarter}")
        for i, track in enumerate(self.tracks):
            if not any(ev.type == "end_track" for ev in track):
                warnings.append(f"Track {i} missing end_track event")
            for ev in track:
                if ev.type == "note":
                    if not (0 <= ev.channel <= 15):
                        warnings.append(f"Track {i}: invalid channel {ev.channel}")
                    if not (0 <= ev.pitch <= 127):
                        warnings.append(f"Track {i}: invalid pitch {ev.pitch}")
                    if not (0 <= ev.velocity <= 127):
                        warnings.append(f"Track {i}: invalid velocity {ev.velocity}")
        return warnings

    def info(self) -> str:
        stats = self.stats()
        path_str = str(self.path) if self.path else "<memory>"
        lines = [
            f"MIDI File: {path_str}",
            f"Ticks per quarter: {self.ticks_per_quarter}",
            f"Number of tracks: {self.num_tracks}",
            f"Total duration (ticks): {self.duration_ticks()}",
            f"Total duration (ms): {self.duration_ms():.2f}",
            f"Channels used: {sorted(stats.get('channels_total', []))}",
            f"Patch changes: {sorted(stats.get('patch_changes_total', set()))}",
            f"Number of notes: {sum(stats.get('num_notes_by_channel', {}).values())}",
        ]
        return "\n".join(lines)

    def debug_report(self) -> str:
        return (
            "=== MIDIFile Debug Report ===\n"
            f"Path: {self.path}\n"
            f"Lazy: {self.lazy}\n"
            f"MIDI loaded: {self._midi is not None}\n"
            f"Opus loaded: {self._opus is not None}\n"
            f"Score loaded: {self._score is not None}\n"
            f"Stats cached: {self._stats is not None}\n"
            f"Ticks per quarter: {self.ticks_per_quarter}\n"
            f"Number of tracks: {self.num_tracks}\n"
        )

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_bytes(self.midi)

    # --- constructors --------------------------------------------------
    @classmethod
    def from_memory(cls, midi_bytes: bytes) -> MIDIFile:
        obj = cls.__new__(cls)
        obj.path = None
        obj.lazy = False
        obj._midi = midi_bytes
        obj._opus = None
        obj._score = None
        obj._stats = None
        obj._tempo_map = None
        return obj

    @classmethod
    def from_opus(cls, opus: List) -> MIDIFile:
        midi_bytes = MIDI.opus2midi(opus)
        return cls.from_memory(midi_bytes)

    @classmethod
    def from_score(cls, score: List) -> MIDIFile:
        midi_bytes = MIDI.score2midi(score)
        return cls.from_memory(midi_bytes)

    # --- dunder --------------------------------------------------------
    def __repr__(self) -> str:
        return f"MIDIFile(path={self.path!r}, lazy={self.lazy})"

    def __str__(self) -> str:

        return self.info()

