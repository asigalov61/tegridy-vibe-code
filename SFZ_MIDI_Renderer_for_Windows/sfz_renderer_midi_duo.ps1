param(
    [string]$Midi = "duo.mid",
    [string]$PianoSFZ = "piano.sfz",
    [string]$ViolinSFZ = "violin.sfz",
    [string]$Out = "duo_mix.wav",
    [int]$DefaultSampleRate = 48000,
    [int]$Quality = 4,
    [int]$Polyphony = 256,
    [int]$PolyphonyMin = 16,
    [int]$TargetBPM = 120,
    [int]$MaxBPM = 300,
    [int]$MinBPM = 20,
    [string]$SfizzRenderPath = "sfizz_render.exe",
    [switch]$KeepTempLogs,

    # New configurable violin reverb/echo parameters
    [double]$ViolinEchoIn = 0.8,
    [double]$ViolinEchoOut = 0.8,
    [int]$ViolinEchoDelayMs = 250,
    [double]$ViolinEchoDecay = 0.20,

    # New configurable piano reverb/echo parameters
    [double]$PianoEchoIn = 0.8,
    [double]$PianoEchoOut = 0.8,
    [int]$PianoEchoDelayMs = 250,
    [double]$PianoEchoDecay = 0.20
)

function Fail([string]$msg) {
    Write-Error $msg
    exit 1
}

# Basic checks
if (-not (Test-Path $Midi)) { Fail "MIDI file not found: $Midi" }
if (-not (Test-Path $PianoSFZ)) { Fail "Piano SFZ not found: $PianoSFZ" }
if (-not (Test-Path $ViolinSFZ)) { Fail "Violin SFZ not found: $ViolinSFZ" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "python not found in PATH." }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Fail "ffmpeg not found in PATH." }
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) { Fail "ffprobe not found in PATH." }
if (-not (Test-Path $SfizzRenderPath) -and -not (Get-Command $SfizzRenderPath -ErrorAction SilentlyContinue)) {
    Write-Warning "sfizz_render not found at $SfizzRenderPath. Set -SfizzRenderPath to the full path of sfizz_render.exe."
}

# Create temp folder
 $tempDir = Join-Path $PWD "render_temp"
if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
New-Item -ItemType Directory -Path $tempDir | Out-Null

# -----------------------------
# tempo_check_and_scale.py
# -----------------------------
 $tempoPy = @'
import sys, json
from mido import MidiFile, MidiTrack, MetaMessage

in_midi = sys.argv[1]
target_bpm = int(sys.argv[2])
max_bpm = int(sys.argv[3])
min_bpm = int(sys.argv[4])

def bpm_from_tempo(tempo):
    return 60000000.0 / tempo

def tempo_from_bpm(bpm):
    return int(60000000.0 / bpm)

m = MidiFile(in_midi)
first_tempo = None
for track in m.tracks:
    for msg in track:
        if msg.is_meta and getattr(msg, "type", "") == 'set_tempo':
            first_tempo = msg.tempo
            break
    if first_tempo is not None:
        break

if first_tempo is None:
    bpm = 120.0
    tempo = tempo_from_bpm(bpm)
else:
    bpm = bpm_from_tempo(first_tempo)
    tempo = first_tempo

result = {"bpm": bpm, "scaled": False, "out_midi": in_midi}

if bpm > max_bpm or bpm < min_bpm:
    factor = bpm / target_bpm
    out = MidiFile()
    out.ticks_per_beat = m.ticks_per_beat
    for track in m.tracks:
        newt = MidiTrack()
        for msg in track:
            if msg.is_meta and getattr(msg, "type", "") == 'set_tempo':
                newt.append(MetaMessage('set_tempo', tempo=int(msg.tempo * factor), time=int(msg.time)))
            else:
                newt.append(msg.copy(time=int(msg.time)))
        out.tracks.append(newt)
    out_path = in_midi.replace(".mid", "_scaled.mid")
    out.save(out_path)
    result["scaled"] = True
    result["out_midi"] = out_path
    new_m = MidiFile(out_path)
    new_first = None
    for track in new_m.tracks:
        for msg in track:
            if msg.is_meta and getattr(msg, "type", "") == 'set_tempo':
                new_first = msg.tempo
                break
        if new_first is not None:
            break
    if new_first is not None:
        result["bpm"] = bpm_from_tempo(new_first)
    else:
        result["bpm"] = target_bpm

print(json.dumps(result))
'@

 $tempoPath = Join-Path $tempDir "tempo_check_and_scale.py"
Set-Content -Path $tempoPath -Value $tempoPy -Encoding UTF8

# -----------------------------
# split_midi.py - ROBUST SANITIZATION VERSION
# -----------------------------
 $splitPy = @'
#!/usr/bin/env python3
"""
split_midi.py - Splits MIDI and sanitizes to prevent stuck notes.
Handles:
1. Overlapping notes (same pitch on same channel).
2. Dangling notes at end of file.
3. Sustain pedal state.
4. Force resets at end of track.
"""
import json
import os
import sys
import traceback
from mido import MidiFile, MidiTrack, MetaMessage, Message

def main():
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"error": "Missing input MIDI file argument"}))
            sys.exit(1)

        in_midi = sys.argv[1]
        out_dir = sys.argv[2] if len(sys.argv) > 2 else "."

        if not os.path.exists(in_midi):
            print(json.dumps({"error": f"Input MIDI file not found: {in_midi}"}))
            sys.exit(1)

        os.makedirs(out_dir, exist_ok=True)

        mid = MidiFile(in_midi)
        ticks_per_beat = mid.ticks_per_beat

        # 1. Flatten all messages to absolute ticks
        all_msgs = []  # (abs_time, track_idx, msg)
        for track_idx, track in enumerate(mid.tracks):
            abs_time = 0
            for msg in track:
                abs_time += msg.time
                all_msgs.append((abs_time, track_idx, msg))

        # 2. Sort by absolute time, then track index
        all_msgs.sort(key=lambda x: (x[0], x[1]))

        # 3. SANITIZATION PASS
        # We process events in order to fix overlaps and convert note_offs.
        
        sanitized_events = [] # (abs_time, msg)
        
        # State tracking: (channel, note) -> start_time
        # We track active notes to detect overlaps.
        active_notes = {} 
        
        # Track program changes for file naming
        program_changes = {}
        
        # Global metas to propagate
        GLOBAL_META_TYPES = {'set_tempo', 'time_signature', 'key_signature'}

        for abs_time, track_idx, msg in all_msgs:
            if msg.is_meta:
                if msg.type in GLOBAL_META_TYPES:
                    # Add meta to output (will be duplicated per channel later)
                    sanitized_events.append((abs_time, msg))
            else:
                ch = msg.channel
                
                if msg.type == 'program_change':
                    program_changes[ch] = msg.program
                    sanitized_events.append((abs_time, msg.copy()))
                
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    # Standardize to note_on vel 0
                    key = (ch, msg.note)
                    if key in active_notes:
                        del active_notes[key]
                    # Emit note_on vel 0
                    new_msg = Message('note_on', channel=ch, note=msg.note, velocity=0, time=0)
                    sanitized_events.append((abs_time, new_msg))
                
                elif msg.type == 'note_on' and msg.velocity > 0:
                    key = (ch, msg.note)
                    
                    # FIX 1: Overlapping Note Check
                    # If this note is already active, we must force it off BEFORE turning it on again.
                    if key in active_notes:
                        # Insert a zero-velocity note_on at this exact time to kill the previous instance
                        kill_msg = Message('note_on', channel=ch, note=msg.note, velocity=0, time=0)
                        sanitized_events.append((abs_time, kill_msg))
                        # print(f"Warning: Fixed overlapping note {msg.note} ch {ch} at {abs_time}", file=sys.stderr)
                    
                    active_notes[key] = abs_time
                    sanitized_events.append((abs_time, msg.copy()))
                
                else:
                    # Other CCs, pitchbend, etc.
                    sanitized_events.append((abs_time, msg.copy()))

        # 4. END OF FILE CLEANUP
        # Determine the last event time
        max_time = 0
        if sanitized_events:
            max_time = max(e[0] for e in sanitized_events)
        
        # FIX 2: Flush any notes still active
        for (ch, note), start_time in list(active_notes.items()):
            # Append note_off at the very end
            kill_msg = Message('note_on', channel=ch, note=note, velocity=0, time=0)
            sanitized_events.append((max_time, kill_msg))
            # print(f"Warning: Flushed dangling note {note} ch {ch} at end", file=sys.stderr)

        # FIX 3: Add Global Reset CCs at the end for every channel used
        used_channels = set()
        for _, msg in sanitized_events:
            if hasattr(msg, 'channel'):
                used_channels.add(msg.channel)
        
        reset_msgs = []
        for ch in used_channels:
            # CC 64 Sustain Off
            reset_msgs.append((max_time, Message('control_change', channel=ch, control=64, value=0, time=0)))
            # CC 123 All Notes Off
            reset_msgs.append((max_time, Message('control_change', channel=ch, control=123, value=0, time=0)))
        
        sanitized_events.extend(reset_msgs)
        
        # 5. Sort again (just to be safe with injected events)
        sanitized_events.sort(key=lambda x: (x[0], 0 if x[1].is_meta else 1))

        # 6. Split into channels and convert to delta times
        channel_msgs = {ch: [] for ch in range(16)}
        last_time = {ch: 0 for ch in range(16)}
        
        # Propagate global metas to all channels
        current_global_metas = []
        
        for abs_time, msg in sanitized_events:
            if msg.is_meta:
                if msg.type in GLOBAL_META_TYPES:
                    current_global_metas.append((abs_time, msg))
                continue
            
            ch = msg.channel
            
            # Inject any global metas that happened since last time
            # (Simple approach: inject metas into the stream for every channel if time progressed)
            # For simplicity and to avoid duplicate metas confusing tempo maps, we put metas only in the FIRST used channel track?
            # Actually, for sfizz_render, it's safer if every file has the tempo map.
            
            # Check for pending metas to inject
            # We inject metas into every channel track to ensure tempo is preserved.
            # To avoid massive duplication lag, we just inject them as they come.
            # But we need to handle delta times correctly.
            
            # Let's do a simpler pass: separate per channel first, then insert metas.
            pass

        # Refined approach: Separate into channel buckets first
        channel_events_raw = {ch: [] for ch in range(16)}
        
        for abs_time, msg in sanitized_events:
            if msg.is_meta and msg.type in GLOBAL_META_TYPES:
                # Add to ALL channels
                for ch in range(16):
                    channel_events_raw[ch].append((abs_time, msg))
            elif hasattr(msg, 'channel'):
                channel_events_raw[msg.channel].append((abs_time, msg))

        # Now process each channel stream to calculate deltas and write files
        out_files = []
        
        for ch in range(16):
            events = channel_events_raw[ch]
            if not events:
                continue
            
            # Filter out channels that only have metas but no notes (empty tracks)
            has_substance = any(not m.is_meta for _, m in events)
            if not has_substance:
                continue

            # Sort channel events
            events.sort(key=lambda x: x[0])
            
            # Calculate deltas
            track = MidiTrack()
            last_t = 0
            
            # Insert program change at t=0 if known
            if ch in program_changes:
                # Time 0
                track.append(Message('program_change', program=program_changes[ch], channel=ch, time=0))
                last_t = 0
            
            for abs_time, msg in events:
                delta = abs_time - last_t
                # Ensure non-negative delta
                if delta < 0: delta = 0
                track.append(msg.copy(time=int(delta)))
                last_t = abs_time
            
            # Add End of Track
            track.append(MetaMessage('end_of_track', time=0))
            
            # Save
            out_mid = MidiFile(ticks_per_beat=ticks_per_beat)
            out_mid.tracks.append(track)
            
            if ch == 9:
                fname = f"ch{ch}_perc.mid"
            elif ch in program_changes:
                fname = f"ch{ch}_prog{program_changes[ch]}.mid"
            else:
                fname = f"ch{ch}.mid"
            
            out_path = os.path.join(out_dir, fname)
            try:
                out_mid.save(out_path)
                out_files.append(out_path)
            except Exception as e:
                print(f"Error saving {out_path}: {e}", file=sys.stderr)

        if out_files:
            print(json.dumps(out_files))
        else:
            print(json.dumps({"error": "No valid tracks created"}))

    except Exception as e:
        print(json.dumps({"error": f"{str(e)}\n{traceback.format_exc()}"}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'@

 $splitPath = Join-Path $tempDir "split_midi.py"
Set-Content -Path $splitPath -Value $splitPy -Encoding UTF8

# -----------------------------
# classify_tracks.py
# -----------------------------
 $classifyPy = @'
import json
from mido import MidiFile
import sys, os, traceback

VIOLIN_PROGS = {40, 41}
PIANO_PROGS = set(range(0, 8))

def detect_programs(path):
    progs = set()
    try:
        m = MidiFile(path)
    except:
        return progs
    for track in m.tracks:
        for msg in track:
            if getattr(msg, "type", "") == "program_change" and hasattr(msg, "program"):
                try:
                    progs.add(int(msg.program))
                except:
                    pass
    return progs

def classify(path):
    try:
        fname = os.path.basename(path).lower()
        if "violin" in fname or "vln" in fname:
            return "violin"
        if "piano" in fname or "pno" in fname or "grand" in fname:
            return "piano"

        progs = detect_programs(path)
        if progs:
            if any(p in VIOLIN_PROGS for p in progs):
                return "violin"
            if any(p in PIANO_PROGS for p in progs):
                return "piano"

        try:
            m = MidiFile(path)
        except:
            return "none"
        notes = []
        channels = set()
        for msg in m:
            if not msg.is_meta and getattr(msg, "type", "") == "note_on" and getattr(msg, "velocity", 0) > 0:
                notes.append(msg.note)
                if hasattr(msg, "channel"):
                    channels.add(getattr(msg, "channel", -1))
        if not notes:
            return "none"
        avg = sum(notes) / len(notes)

        if avg >= 70:
            return "violin"
        if avg <= 64:
            return "piano"

        if 0 in channels:
            return "piano"
        if 1 in channels:
            return "violin"

        return "piano"
    except Exception as e:
        return "none"

def main():
    try:
        out = {}
        for f in sorted(os.listdir(".")):
            if f.endswith(".mid"):
                try:
                    out[f] = classify(f)
                except:
                    out[f] = "none"
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
'@

 $classifyPath = Join-Path $tempDir "classify_tracks.py"
Set-Content -Path $classifyPath -Value $classifyPy -Encoding UTF8

# -----------------------------
# Helper: detect sample rate from SFZ
# -----------------------------
function Get-SFZSampleRate {
    param([string]$sfzPath)
    if (-not (Test-Path $sfzPath)) { return $null }
    $dir = Split-Path -Parent $sfzPath
    $content = Get-Content -Raw -Path $sfzPath -ErrorAction SilentlyContinue
    if (-not $content) { return $null }
    $m = Select-String -InputObject $content -Pattern 'sample\s*=\s*("?)([^"\s]+)\1' -AllMatches
    if (-not $m) { return $null }
    $first = $m.Matches[0].Groups[2].Value
    $samplePath = if ([System.IO.Path]::IsPathRooted($first)) { $first } else { Join-Path $dir $first }
    if (-not (Test-Path $samplePath)) {
        $try = Join-Path $dir (Split-Path $first -Leaf)
        if (Test-Path $try) { $samplePath = $try } else { return $null }
    }
    $probe = & ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=noprint_wrappers=1:nokey=1 $samplePath 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $probe) { return $null }
    $sr = [int]($probe.Trim())
    return $sr
}

# -----------------------------
# 0. MIDI tempo check
# -----------------------------
Write-Host "Checking MIDI tempo and scaling if extreme..."
 $tempoJson = & python $tempoPath $Midi $TargetBPM $MaxBPM $MinBPM 2>$null
if ($LASTEXITCODE -ne 0) { Fail "Tempo check failed. Ensure mido is installed." }

try {
    $tempoInfo = $tempoJson | ConvertFrom-Json
    if ($tempoInfo.error) {
        Fail "Tempo check error: $($tempoInfo.error)"
    }
} catch {
    Fail "Failed to parse tempo check output: `n$tempoJson"
}

Write-Host ("MIDI BPM detected: {0:N2}" -f $tempoInfo.bpm)
if ($tempoInfo.scaled -eq $true) {
    Write-Host "Tempo was extreme and has been scaled. Using scaled MIDI: $($tempoInfo.out_midi)"
    $MidiToRender = $tempoInfo.out_midi
} else {
    $MidiToRender = $Midi
}

# -----------------------------
# 1. Split MIDI
# -----------------------------
Write-Host "Splitting and sanitizing MIDI (fixing overlaps and stuck notes)..."
 $splitOut = & python $splitPath $MidiToRender $tempDir 2>&1
 $splitExitCode = $LASTEXITCODE

if ($splitOut -match '^{\s*"error"') {
    try {
        $errorObj = $splitOut | ConvertFrom-Json
        Fail "Split step error: $($errorObj.error)"
    } catch {
        Fail "Split step failed with error: $splitOut"
    }
}

if ($splitExitCode -ne 0) { 
    Write-Host "Split command output: $splitOut"
    Fail "Python split step failed with exit code $splitExitCode. Ensure 'mido' is installed." 
}

try {
    $created = $splitOut | ConvertFrom-Json
} catch {
    Write-Host "Raw split output: $splitOut"
    Fail "Failed to parse split output as JSON."
}

if ($created.Count -eq 0) { 
    Write-Host "Raw split output: $splitOut"
    Fail "No per-instrument MIDIs were created." 
}

Write-Host "Created $($created.Count) MIDI files"

Push-Location $tempDir

# -----------------------------
# 2. Classify
# -----------------------------
Write-Host "Classifying per-instrument MIDIs..."
 $classificationJson = & python $classifyPath 2>&1
if ($LASTEXITCODE -ne 0) { 
    Pop-Location
    Write-Host "Classification output: $classificationJson"
    Fail "Python classification step failed." 
}

try {
    $classification = $classificationJson | ConvertFrom-Json
    if ($classification.error) {
        Pop-Location
        Fail "Classification error: $($classification.error)"
    }
} catch {
    Pop-Location
    Write-Host "Raw classification output: $classificationJson"
    Fail "Failed to parse classification JSON."
}

 $pianoCount = 0
 $violinCount = 0
foreach ($prop in $classification.PSObject.Properties) {
    if ($prop.Value -eq "piano") { $pianoCount++ }
    if ($prop.Value -eq "violin") { $violinCount++ }
}
Write-Host "Classified: $pianoCount piano files, $violinCount violin files"

# -----------------------------
# 3. Determine Sample Rate
# -----------------------------
 $srP = Get-SFZSampleRate -sfzPath $PianoSFZ
 $srV = Get-SFZSampleRate -sfzPath $ViolinSFZ
if ($srP) { $RenderSampleRate = $srP }
elseif ($srV) { $RenderSampleRate = $srV }
else { $RenderSampleRate = $DefaultSampleRate }

Write-Host "Using render sample rate: $RenderSampleRate Hz"

# -----------------------------
# 4. Render stems
# -----------------------------
 $stems = @()
 $renderLogsDir = Join-Path $tempDir "sfizz_logs"
New-Item -ItemType Directory -Path $renderLogsDir | Out-Null

function Get-AudioDuration($path) {
    $out = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $path 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    try { return [double]$out.Trim() } catch { return $null }
}

function SFZ-SampleCheck {
    param([string]$sfzPath)
    $sfzDir = Split-Path -Parent $sfzPath
    $missing = @()
    $matches = Select-String -Path $sfzPath -Pattern 'sample\s*=\s*("?)([^"\s]+)\1' -AllMatches -ErrorAction SilentlyContinue
    if (-not $matches) { return @{ ok = $true; missing = $missing; samples = @() } }

    $audioExts = @(".wav", ".flac", ".ogg", ".aiff", ".aif", ".mp3", ".sf2")

    foreach ($m in $matches) {
        foreach ($mm in $m.Matches) {
            $rel = $mm.Groups[2].Value.Trim()
            if ([string]::IsNullOrWhiteSpace($rel)) { continue }

            $relNormalized = $rel -replace '/', '\'

            if ([IO.Path]::IsPathRooted($relNormalized)) {
                $candidate = $relNormalized
            } else {
                $candidate = Join-Path $sfzDir $relNormalized
            }

            $resolved = $null
            try {
                $rp = Resolve-Path -Path $candidate -ErrorAction SilentlyContinue
                if ($rp) { $resolved = $rp.Path }
            } catch {
                $resolved = $null
            }

            if ($resolved -and (Test-Path $resolved)) {
                continue
            }

            $foundPath = $null
            foreach ($ext in $audioExts) {
                $tryPath = $candidate
                if (-not $tryPath.EndsWith($ext, [System.StringComparison]::InvariantCultureIgnoreCase)) {
                    $tryPath = $candidate + $ext
                }
                try {
                    $rp = Resolve-Path -Path $tryPath -ErrorAction SilentlyContinue
                    if ($rp) { $foundPath = $rp.Path; break }
                } catch {}
            }
            if ($foundPath) { continue }

            $missing += [PSCustomObject]@{ sample = $rel; full = $candidate }
        }
    }

    if ($missing.Count -gt 0) { return @{ ok = $false; missing = $missing; samples = $matches } }
    return @{ ok = $true; missing = $missing; samples = $matches }
}

function Render-StemWithFallback {
    param(
        [string]$MidiFile,
        [string]$SFZ,
        [string]$OutWav,
        [int]$startPolyphony
    )

    try {
        if ([System.IO.Path]::IsPathRooted($MidiFile)) {
            $MidiFull = $MidiFile
        } else {
            $MidiFull = (Resolve-Path -Path $MidiFile -ErrorAction SilentlyContinue).Path
            if (-not $MidiFull) {
                $MidiFull = Join-Path (Get-Location) $MidiFile
            }
        }
    } catch {
        $MidiFull = Join-Path (Get-Location) $MidiFile
    }

    if ([System.IO.Path]::IsPathRooted($OutWav)) {
        $OutWavFull = $OutWav
    } else {
        $OutWavFull = Join-Path (Get-Location) $OutWav
    }

    $check = SFZ-SampleCheck -sfzPath $SFZ
    if (-not $check.ok) {
        Write-Warning "SFZ sample check found missing sample references for $SFZ. Attempting render anyway."
    }

    $poly = $startPolyphony
    $sfzDir = Split-Path -Parent $SFZ

    $exit = $null
    while ($poly -ge $PolyphonyMin) {
        $logBase = [System.IO.Path]::GetFileNameWithoutExtension($OutWav)
        $log = Join-Path $renderLogsDir ("{0}_poly{1}.log" -f $logBase, $poly)

        $renderArgs = @("--sfz", $SFZ, "--midi", $MidiFull, "--wav", $OutWavFull, "--samplerate", $RenderSampleRate, "--quality", $Quality, "--polyphony", $poly, "--use-eot")
        Write-Host ("Running sfizz_render for {0} with polyphony {1}" -f $MidiFile, $poly)

        $orig = Get-Location
        try {
            Push-Location $sfzDir

            $quotedArgs = $renderArgs | ForEach-Object {
                if ($_ -match '\s') { '"' + ($_ -replace '"','\"') + '"' } else { $_ }
            }
            $cmdLine = '"' + ($SfizzRenderPath -replace '"','\"') + '" ' + ($quotedArgs -join ' ')
            $redir = $cmdLine + " > `"$log`" 2>&1"

            & cmd.exe /c $redir
            $exit = $LASTEXITCODE
        } catch {
            Write-Warning ("Failed to start sfizz_render: {0}" -f $_.Exception.Message)
        } finally {
            Pop-Location
        }

        if (Test-Path $OutWavFull) {
            $fi = Get-Item $OutWavFull
            $size = $fi.Length
            $dur = Get-AudioDuration $OutWavFull
            if ($size -gt 2048 -and $dur -ne $null -and $dur -gt 0.1) {
                Write-Host ("sfizz_render succeeded for {0} (poly={1})" -f $MidiFile, $poly)
                return @{ success = $true; poly = $poly; log = $log; size = $size; duration = $dur; exit = $exit }
            } else {
                Write-Warning ("sfizz_render produced tiny or short file for {0} (poly={1}) - retrying." -f $MidiFile, $poly)
            }
        } else {
            Write-Warning ("sfizz_render did not produce {0} (poly={1})." -f $OutWavFull, $poly)
        }

        $newPoly = [int]([math]::Floor($poly / 2))
        if ($newPoly -lt $PolyphonyMin) { $newPoly = $PolyphonyMin }
        if ($newPoly -eq $poly) { break }
        $poly = $newPoly
    }

    return @{ success = $false; poly = $poly; log = $log; exit = $exit }
}

foreach ($prop in $classification.PSObject.Properties) {
    $track = $prop.Name
    $type = $prop.Value
    if ($type -eq "none") { continue }
    $sfz = if ($type -eq "piano") { $PianoSFZ } else { $ViolinSFZ }

    $baseTrackName = [System.IO.Path]::GetFileNameWithoutExtension($track)
    $outwav = "$baseTrackName.wav"

    Write-Host "Rendering $track as $type -> $outwav"
    $res = Render-StemWithFallback -MidiFile $track -SFZ $sfz -OutWav $outwav -startPolyphony $Polyphony
    if ($res.success) {
        $stems += [PSCustomObject]@{ name = $outwav; type = $type }
    } else {
        Write-Warning ("Failed to render {0}." -f $track)
    }
}

if ($stems.Count -eq 0) { Pop-Location; Fail "No stems were rendered successfully. Inspect logs in $renderLogsDir." }

# -----------------------------
# 5. Normalize stems
# -----------------------------
 $normalized = @()
foreach ($sobj in $stems) {
    $s = $sobj.name
    $norm = "${s}_norm.wav"
    Write-Host "Normalizing $s -> $norm"
    & ffmpeg -y -i $s -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11" -ar $RenderSampleRate -ac 2 -sample_fmt s16 $norm
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "ffmpeg normalization failed for $s" }
    if (-not (Test-Path $norm)) { Pop-Location; Fail "Normalization did not produce expected file: $norm" }
    $normalized += [PSCustomObject]@{ name = $norm; type = $sobj.type }
}

# -----------------------------
# 6. Apply reverb + EQ
# -----------------------------
 $processed = @()
foreach ($sobj in $normalized) {
    $s = $sobj.name
    $type = $sobj.type
    $proc = "${s}_proc.wav"
    Write-Host "Applying reverb + EQ to $s (type=$type) -> $proc"

    if ($type -eq "violin") {
        $delay = [int]$ViolinEchoDelayMs
        $inGain = [double]$ViolinEchoIn
        $outGain = [double]$ViolinEchoOut
        $decay = [double]$ViolinEchoDecay
        $aecho = "aecho={0}:{1}:{2}:{3}" -f $inGain, $outGain, $delay, $decay
        $eq = "equalizer=f=300:t=h:width=200:g=1, equalizer=f=3000:t=h:width=200:g=1.5"
        $filter = "$aecho, $eq"
    } elseif ($type -eq "piano") {
        $delay = [int]$PianoEchoDelayMs
        $inGain = [double]$PianoEchoIn
        $outGain = [double]$PianoEchoOut
        $decay = [double]$PianoEchoDecay
        $aecho = "aecho={0}:{1}:{2}:{3}" -f $inGain, $outGain, $delay, $decay
        $eq = "equalizer=f=300:t=h:width=200:g=2, equalizer=f=3000:t=h:width=200:g=3"
        $filter = "$aecho, $eq"
    } else {
        $filter = "aecho=0.8:0.9:1000:0.3, equalizer=f=300:t=h:width=200:g=2, equalizer=f=3000:t=h:width=200:g=3"
    }

    & ffmpeg -y -i $s -filter_complex $filter -ar $RenderSampleRate -ac 2 -sample_fmt s16 $proc
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "ffmpeg reverb/EQ failed for $s" }
    if (-not (Test-Path $proc)) { Pop-Location; Fail "Processing did not produce expected file: $proc" }
    $processed += [PSCustomObject]@{ name = $proc; type = $type }
}

if ($processed.Count -eq 0) { Pop-Location; Fail "No processed stems available for mixing." }

# -----------------------------
# 7. Mix stems
# -----------------------------
 $ffArgs = @("-y")
foreach ($pobj in $processed) { $ffArgs += "-i"; $ffArgs += $pobj.name }

 $mixFilter = "amix=inputs=$($processed.Count):normalize=0:duration=longest"
 $ffArgs += "-filter_complex"; $ffArgs += $mixFilter
 $ffArgs += "-ar"; $ffArgs += "$RenderSampleRate"
 $ffArgs += "-ac"; $ffArgs += "2"
 $ffArgs += "-sample_fmt"; $ffArgs += "s16"
 $ffArgs += $Out

Write-Host "Mixing final output -> $Out"
& ffmpeg @ffArgs
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "ffmpeg mixdown failed." }

Pop-Location

if (-not $KeepTempLogs) {
    try {
        Remove-Item -Recurse -Force $tempDir
    } catch {
        Write-Warning ("Failed to remove temporary directory {0}: {1}" -f $tempDir, $_.Exception.Message)
    }
} else {
    Write-Host "Keeping temporary logs and files in $tempDir"
}

Write-Host "Render completed successfully. Output: $Out"