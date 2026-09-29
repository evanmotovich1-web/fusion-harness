# Sound and Picture Palette

FICTIONAL SIMULATION. Redhawk Forge and Bayline Kings are invented teams.
No real league, club, broadcaster, or player names, marks, logos, uniforms,
or likenesses. This file does not order scenes. Beat windows below are
copied from `shot-list.json`. If a window and that file disagree, the shot
list wins. Scores and clock strings stay in `canon.md`.

Cue ids are frozen. Do not rename, merge, or add ids.

```
crowd.bed
crowd.rise
crowd.roar_peak
pa.horn
ref.whistle
hit.snap
hit.helmet
ball.hiss
ball.tip
hit.catch
call.radio
sting.final
```

## Loudness contract

Loud means mastered, not clipped.

| measure | pass window | target |
|---|---|---|
| integrated loudness | -16 to -12 LUFS | -14 LUFS |
| true peak, PCM stems and `audio/mix.wav` | <= -2.0 dBTP | -2.0 dBTP |
| true peak, final AAC in `final-38-35.mp4` | <= -1.0 dBTP | -1.5 dBTP |

AAC can raise true peak by about 1 dB. Keep the PCM mix at or under -2.0 dBTP so the encoded file still passes <= -1.0 dBTP. If the mp4 measurement fails the peak gate, lower the PCM ceiling and re-encode. Do not raise gains until the meter clips.

Measure the final file with:

```
ffmpeg -i self-compact/hail-mary/final-38-35.mp4 -af ebur128=peak=true -f null -
```

Pass only if integrated `I` is inside [-16, -12] and true peak is <= -1.0 dBTP.

Two-pass `loudnorm` on the mix, then store the printed JSON at `audio/loudnorm.json` so a rerun can replay the same measured gains:

```
loudnorm=I=-14:TP=-2.0:LRA=11:print_format=json
```

Limiter before that pass, so the meter never sees a clip:

```
alimiter=limit=0.794:level=false:attack=1:release=80:latency=true
```

`0.794` is -2.0 dBFS. `amix` must use `normalize=0`. Default amix normalization will bury the roar.

## Stem contract for 2.c

Synthesize locally. Sources are ffmpeg lavfi (`anoisesrc`, `sine`, `aevalsrc`) and `/usr/bin/say`. No downloaded samples. Pins from `capabilities.json`: ffmpeg 9.0.1, voice `Daniel` (probed), `afconvert` to 48 kHz stereo PCM.

Every cue wav:

- path: `self-compact/hail-mary/audio/<cue-id>.wav` (keep the dot: `audio/crowd.bed.wav`)
- pcm_s16le, 48000 Hz, stereo
- exactly 40.000 s (1,920,000 samples per channel)
- silence outside the active window
- isolated-file peak <= -6.0 dBFS before the mix bus
- `anoisesrc` seed pinned (table below). Seed `-1` is forbidden.

Mixed bed, pre-encode: `self-compact/hail-mary/audio/mix.wav`, same format, 40.000 s, peak <= -2.0 dBTP, integrated about -14 LUFS after two-pass loudnorm.

`call.radio` words are not authored here. 2.c speaks the broadcast lines from `screenplay.md`. If a beat has no screenplay line yet, use that beat's `captions` in `shot-list.json`. Do not invent a second call.

## Cue registry

Active windows are the union of beats that already list the cue. Offset is seconds after that beat's `t_in_s`, except where a window is given in absolute seconds.

| cue id | class | active window (s) | mix gain | seed / voice |
|---|---|---|---|---|
| `crowd.bed` | bed | 0.0-40.0 | -18 dB, see envelope | 3801 |
| `crowd.rise` | bed | 4.0-18.0 | -18 dB to -8 dB | 3802 |
| `crowd.roar_peak` | bed | 18.0-33.5 | -6 dB | 3803 |
| `pa.horn` | one-shot | 0.35-1.55 | -8 dB | n/a |
| `ref.whistle` | one-shot | 7.15-7.70 | -10 dB | n/a |
| `hit.helmet` | one-shot | 4.60 and 5.40, 0.12 each | -8 dB | 3811 |
| `hit.snap` | one-shot | 8.05-8.11 | -7 dB | 3812 |
| `ball.hiss` | bed | 8.55-18.00 | -16 dB | 3813 |
| `ball.tip` | one-shot | 18.20-18.26 | -9 dB | 3814 |
| `hit.catch` | one-shot | 18.55-18.71 | -6 dB | 3815 |
| `call.radio` | voice | inside s01, s03, s04, s05 | -10 dB | Daniel |
| `sting.final` | one-shot | 26.40-39.20 | -7 dB | n/a |

Beat cross-reference, copied, not reordered:

| cue id | shot-list beats |
|---|---|
| `crowd.bed` | s01, s06 |
| `crowd.rise` | s02, s03 |
| `crowd.roar_peak` | s04, s05 |
| `pa.horn` | s01 |
| `ref.whistle` | s02 |
| `hit.helmet` | s02 |
| `hit.snap` | s03 |
| `ball.hiss` | s03 |
| `ball.tip` | s04 |
| `hit.catch` | s04 |
| `call.radio` | s01, s03, s04, s05 |
| `sting.final` | s05, s06 |

## Cue recipes

Gains below are the isolated synth level. The mix-gain column is applied on the bus. Do not also bake the mix gain into the stem, or the roar will be applied twice.

### `crowd.bed`

Floor of the stadium. A murmur, not a roar. Pink noise, narrowed, plus a quieter brown layer for the bowl.

```
anoisesrc=color=pink:r=48000:a=0.20:d=40:s=3801,highpass=f=180,lowpass=f=2400,aformat=channel_layouts=stereo
```

Second layer, mix at 0.35 relative to the pink layer, then the bus gain:

```
anoisesrc=color=brown:r=48000:a=0.12:d=40:s=3801,lowpass=f=400,aformat=channel_layouts=stereo
```

Envelope on the summed bed, before bus gain: hold 0.55 from 0.0-8.0, rise to 0.80 by 18.0, hold through 33.0, fall to 0.40 by 36.0, hold to 40.0. The rise and the roar are separate cues. This envelope only keeps the floor from vanishing or fighting them.

Stereo: split, `adelay=17|0` on one copy, amix. That is width, not a new cue.

### `crowd.rise`

Same pink recipe as the bed, seed 3802, bus silent outside 4.0-18.0. Volume expression from 0.15 at 4.0 to 1.0 at 18.0. No brown layer. This is the swell under the throw, not a second stadium.

### `crowd.roar_peak`

The loud cue. Pink plus white, less lowpass, plus a sub sine so the bowl shakes.

```
anoisesrc=color=pink:r=48000:a=0.45:d=40:s=3803,highpass=f=120,lowpass=f=5000
anoisesrc=color=white:r=48000:a=0.12:d=40:s=3803,highpass=f=2000,lowpass=f=8000
sine=frequency=70:sample_rate=48000:duration=40,volume=0.18
```

Active 18.0-33.5 only. Attack 80 ms at 18.0 (the catch, not a fade-in from the snap). Hold to 31.5. Linear fall to silence at 33.5 so s06 is bed plus sting, not a second roar. Peak of this stem at -6 dBFS. It should be the loudest element in the mix besides the catch thump.

### `pa.horn`

One stadium horn. Dissonant, not a melody. Probed on ffmpeg 9.0.1.

```
aevalsrc=0.35*sin(2*PI*466*t)+0.22*sin(2*PI*587*t)+0.12*sin(2*PI*740*t)|0.35*sin(2*PI*466*t+0.2)+0.22*sin(2*PI*587*t)+0.12*sin(2*PI*740*t):s=48000:d=1.2:c=stereo,afade=t=in:st=0:d=0.015,afade=t=out:st=0.85:d=0.35
```

Place the 1.2 s render at absolute 0.35. Do not loop it.

### `ref.whistle`

Pea whistle. High sine, tremolo, short. Probed.

```
sine=frequency=3480:sample_rate=48000:duration=0.55,tremolo=f=15:d=0.8,highpass=f=2000,afade=t=in:st=0:d=0.01,afade=t=out:st=0.40:d=0.15,aformat=channel_layouts=stereo
```

Place at absolute 7.15 so it ends before the snap at 8.05. One blast. Not a touchdown whistle. The touchdown is the roar and the sting.

### `hit.helmet`

Composite crack. Two transients, not a fight soundtrack. Each is 0.12 s.

```
anoisesrc=color=white:r=48000:a=0.8:d=0.12:s=3811,highpass=f=900,lowpass=f=4200,afade=t=out:st=0.02:d=0.10
sine=frequency=140:sample_rate=48000:duration=0.08,afade=t=out:st=0.01:d=0.07,volume=0.4
```

Amix those two layers per hit. Place hits at 4.60 and 5.40. Second hit uses seed 3816 so they are not a copy-paste echo.

### `hit.snap`

Drier and shorter than the helmet. Leather and hands. 0.06 s at absolute 8.05.

```
anoisesrc=color=white:r=48000:a=0.9:d=0.06:s=3812,highpass=f=1500,lowpass=f=7000,afade=t=out:st=0.008:d=0.05,aformat=channel_layouts=stereo
```

### `ball.hiss`

Thin spiral. Easy to mix too hot. Keep the bus gain at -16 dB.

```
anoisesrc=color=violet:r=48000:a=0.15:d=9.45:s=3813,highpass=f=6000,lowpass=f=12000
aevalsrc=0.08*sin(2*PI*(2200+180*t)*t):s=48000:d=9.45,aformat=channel_layouts=stereo
```

Amix noise and glide at equal weight. Place the 9.45 s render at absolute 8.55 so it dies as the tip starts at 18.20. Fade the last 0.30 s.

### `ball.tip`

Fingertip tick. Brighter and shorter than the catch. 0.06 s at absolute 18.20. This is not the score.

```
sine=frequency=2500:sample_rate=48000:duration=0.04,afade=t=out:st=0.008:d=0.03,volume=0.5
anoisesrc=color=white:r=48000:a=0.7:d=0.05:s=3814,highpass=f=3000,afade=t=out:st=0.01:d=0.04
```

### `hit.catch`

The thump. Lower and longer than the tip. 0.16 s at absolute 18.55, after the tip, not on top of it.

```
sine=frequency=95:sample_rate=48000:duration=0.14,afade=t=out:st=0.02:d=0.12,volume=0.7
anoisesrc=color=brown:r=48000:a=0.45:d=0.16:s=3815,lowpass=f=600,highpass=f=60,afade=t=out:st=0.03:d=0.13
```

Stem peak -6 dBFS. On the bus this may sit next to `crowd.roar_peak`. The limiter is there for that overlap. Do not drop the catch to make the limiter idle.

### `call.radio`

Booth texture, not a clean voiceover. Voice `Daniel`, rate 180:

```
say -v Daniel -r 180 -o call.aiff "<line>"
afconvert -f WAVE -d LEI16@48000 -c 2 call.aiff call.wav
```

Then:

```
highpass=f=280,lowpass=f=3400,equalizer=f=2500:t=q:w=1.2:g=3,aecho=0.8:0.88:20:0.08,alimiter=limit=0.5:level=false
```

Under the voice, a hiss bed at -28 dB relative to the dry voice:

```
anoisesrc=color=white:r=48000:a=0.02:d=<phrase>:s=3820,highpass=f=2000,lowpass=f=6000
```

Place each phrase 0.40 s after the `t_in_s` of s01, s03, s04, and s05. If a phrase would run into the next phrase, trim the tail. Do not time-stretch. Do not cover the tip (18.20) or the catch (18.55) with a loud syllable. Duck the voice 6 dB from 18.15 to 18.80.

No ASR in this environment. 4.a checks call text against `screenplay.md`, not against the waveform.

### `sting.final`

End sting. A major stab, not a song. A2 plus E3 plus C#4, short attack, long tail under the card.

```
aevalsrc=0.40*sin(2*PI*110*t)*exp(-0.35*t)+0.28*sin(2*PI*165*t)*exp(-0.45*t)+0.18*sin(2*PI*277*t)*exp(-0.70*t)|0.40*sin(2*PI*110*t+0.15)*exp(-0.35*t)+0.28*sin(2*PI*165*t)*exp(-0.45*t)+0.18*sin(2*PI*277*t+0.1)*exp(-0.70*t):s=48000:d=12.8:c=stereo
```

Place at absolute 26.40. Silence after 39.20 (fade the last 0.40 s). One stab. Do not add a second hit at the card cut.

## Mix bus order

1. Pad every cue to 40.000 s with silence outside its window.
2. Apply the mix-gain column.
3. `amix=inputs=12:normalize=0:duration=longest`.
4. `alimiter` at -2.0 dBFS, `level=false`.
5. Two-pass `loudnorm` to -14 LUFS, TP -2.0.
6. Write `audio/mix.wav` and `audio/loudnorm.json`.

If integrated loudness lands outside [-16, -12], change bus gains by the same delta and rerun. Do not fix a short mix by clipping the limiter ceiling upward.

## Picture grade

Grade name: `NIGHT_ELECTRIC_v1`. Paint this in the canvas. Do not regrade in ffmpeg. `drawtext` is absent, and a second grade pass would break byte-identical frames.

These hex values expand the canon colors (Forge crimson/charcoal, Kings navy/silver). They are not new team colors.

| token | hex | use |
|---|---|---|
| `bg_void` | `#07090D` | darkest paint. Never `#000000`. |
| `light_spill` | `#F4F7FF` | brightest paint. Never `#FFFFFF`. |
| `field_lit` | `#14915A` | lit grass |
| `field_shadow` | `#0B4A32` | grass out of the pool |
| `yard_line` | `#F4F7F2` | yard lines, 70% alpha |
| `forge_crimson` | `#E10600` | Forge, winner, catch accent |
| `forge_charcoal` | `#141418` | Forge secondary, card field |
| `kings_navy` | `#071833` | Kings |
| `kings_silver` | `#D5DCE3` | Kings secondary |
| `scoreboard_bg` | `#07080C` | insert plate, 92% alpha |
| `scoreboard_amber` | `#FFC857` | clock and down |
| `scoreboard_text` | `#F7F4EC` | team abbreviations and captions |
| `shadow_teal` | `#0E3A42` | shadow tint |
| `highlight_warm` | `#FFB08A` | highlight tint |

Grade stack, in this order, inside the renderer:

1. Black lift. Floor is `bg_void`.
2. Teal multiply. `shadow_teal` at 18% on pixels with luma below 0.35.
3. Warm add. `highlight_warm` at 10% on luma above 0.72.
4. Contrast. Midtones +12%. Compress highlights so no pixel exceeds `light_spill`.
5. Light bloom. `light_spill` at 35% alpha, large radius, never solid white.
6. Vignette. 0 at center, 55% black at corners.
7. Grain. Monochrome, alpha 0.04, seed `38 + frame_index`. Same index must redraw the same grain. Unseeded `Math.random` is a frame-identity failure.

Look deltas keyed by existing beat id. This is a lookup, not a new cut.

| beat | look id | delta from the stack |
|---|---|---|
| s01 | `WIDE_NIGHT` | vignette 0.62, teal +8%, bloom 0.35 |
| s02 | `LINE_HEAT` | grain 0.06, warm highlight +6% |
| s03 | `ARC_TRACK` | `LINE_HEAT`, bloom follows the ball |
| s04 | `CATCH_SLOMO` | contrast +15%, teal +8%, crimson saturation +20%, other saturation -8% |
| s05 | `ROAR_BLOOM` | bloom 0.50, grain 0.03, crimson practicals on the field |
| s06 | `CARD_FLAT` | no vignette, no grain, field `forge_charcoal`, type `scoreboard_text` |

s06 fiction label stays legible for the whole beat. Scoreboard strings are copied from `shot-list.json` `scoreboard.line`. This palette does not restate them.

## Handoff

- 2.a: stage sound by these cue ids in action lines. Do not rename them. Call copy lives in the screenplay. Numbers stay in `canon.md`.
- 2.b: use `NIGHT_ELECTRIC_v1` and the beat look table. Seed grain. Do not pull hex values from anywhere else.
- 2.c: one wav per cue id, plus `audio/mix.wav`, plus `audio/loudnorm.json`. Recipes above. Voice text from the screenplay.
- 3.a: mux `audio/mix.wav`. Do not run a second loudnorm unless the mp4 true peak fails. Do not burn text in ffmpeg.
- 4.a: ebur128 gate is the table at the top. Call text is a source check, not a transcript check.
