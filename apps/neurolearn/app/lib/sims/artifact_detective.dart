import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Artifact detective — the learner identifies what is contaminating a trace.
///
/// Built natively rather than as a bundled web view: no extra dependency, it
/// works offline, and the traces stay crisp at any device pixel ratio.
///
/// Every artifact is modelled on its real mechanism, not just "make it look
/// odd". Amplitudes and timings sit in physiological range, because a learner
/// who trains on wrong-looking data learns the wrong thing.
class ArtifactDetective extends StatefulWidget {
  const ArtifactDetective({super.key, this.onComplete});

  final VoidCallback? onComplete;

  @override
  State<ArtifactDetective> createState() => _ArtifactDetectiveState();
}

// ---------------------------------------------------------------- synthesis

const _fs = 250;
const _durationSeconds = 6;
const _sampleCount = _fs * _durationSeconds;

const _channels = <String>[
  'Fp1', 'Fp2', 'F7', 'F8', 'C3', 'C4',
  'T7', 'T8', 'P3', 'P4', 'O1', 'O2',
];

/// Seeded so every learner sees the same traces and answers stay comparable.
class _Rng {
  int _s = 7;
  double next() {
    _s ^= _s << 13;
    _s ^= _s >> 17;
    _s ^= _s << 5;
    _s &= 0xFFFFFFFF;
    return (_s / 0xFFFFFFFF) - 0.5;
  }
}

/// 1/f background plus posterior-weighted alpha — the substrate every round
/// starts from.
List<Float32List> _baseline(_Rng rng, {double alphaGain = 1}) {
  final out = <Float32List>[];
  for (final name in _channels) {
    final posterior = RegExp(r'^[OP]').hasMatch(name) ? 1.0 : 0.22;
    final trace = Float32List(_sampleCount);
    var pink = 0.0;
    final phase = rng.next() * 6.28;
    for (var i = 0; i < _sampleCount; i++) {
      final t = i / _fs;
      pink = pink * 0.965 + rng.next() * 6.5;
      final envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 0.35 * t + phase);
      trace[i] = pink +
          math.sin(2 * math.pi * 10.3 * t + phase) *
              13 *
              posterior *
              envelope *
              alphaGain;
    }
    out.add(trace);
  }
  return out;
}

class _Round {
  const _Round({
    required this.answer,
    required this.caption,
    required this.hint,
    required this.why,
    required this.tell,
    required this.build,
  });

  final String answer;
  final String caption;
  final String hint;
  final String why;
  final String tell;
  final List<Float32List> Function(_Rng rng) build;
}

const _options = <String>[
  'Eye blinks',
  'Jaw muscle tension',
  'Mains electrical interference',
  'A loose electrode',
  'Heartbeat',
  'Nothing — this is clean brain activity',
];

final _rounds = <_Round>[
  _Round(
    answer: 'Eye blinks',
    caption: 'Rest, eyes open',
    hint: 'Frontal channels at top, occipital at bottom',
    why: 'Eye blinks. The eyeball is an electrical dipole — cornea positive, '
        'retina negative. Each blink swings that dipole and the nearest '
        'electrodes see a large, slow deflection.',
    tell: 'Tell: smooth humps 200–400 ms wide, over 100 µV, biggest at Fp1 and '
        'Fp2 and fading toward the back of the head.',
    build: (rng) {
      final data = _baseline(rng);
      for (final onset in [1.1, 2.7, 4.4, 5.3]) {
        final start = (onset * _fs).round();
        for (var c = 0; c < _channels.length; c++) {
          final name = _channels[c];
          final weight = name.startsWith('Fp')
              ? 1.0
              : name.startsWith('F')
                  ? 0.55
                  : RegExp(r'^[CT]').hasMatch(name)
                      ? 0.12
                      : 0.03;
          for (var k = -45; k < 110; k++) {
            final i = start + k;
            if (i < 0 || i >= _sampleCount) continue;
            final d = k - 22;
            data[c][i] += math.exp(-(d * d) / 1400) * 130 * weight;
          }
        }
      }
      return data;
    },
  ),
  _Round(
    answer: 'Jaw muscle tension',
    caption: 'Participant clenched their teeth',
    hint: 'T7 and T8 sit over the jaw muscles',
    why: 'Muscle activity (EMG) from the jaw. Muscle fibres fire far faster '
        'than cortex, so the contamination is fast, dense fuzz rather than a '
        'smooth wave.',
    tell: 'Tell: a burst of high-frequency noise that starts and stops '
        'abruptly, worst at T7/T8 because the temporalis muscle sits right '
        'under those electrodes.',
    build: (rng) {
      final data = _baseline(rng);
      final a = (1.9 * _fs).round();
      final b = (3.8 * _fs).round();
      for (var c = 0; c < _channels.length; c++) {
        final name = _channels[c];
        final weight = name.startsWith('T')
            ? 1.0
            : name.startsWith('F')
                ? 0.42
                : name.startsWith('C')
                    ? 0.3
                    : 0.1;
        for (var i = a; i < b; i++) {
          final ramp = math.min(1.0, math.min((i - a) / 25, (b - i) / 25));
          data[c][i] += rng.next() * 95 * weight * ramp;
        }
      }
      return data;
    },
  ),
  _Round(
    answer: 'Mains electrical interference',
    caption: 'Recorded next to a fridge',
    hint: 'Look at every channel at once',
    why: 'Mains interference at 60 Hz. Building wiring radiates a field that '
        'every electrode picks up, so the contamination is identical '
        'everywhere — no brain signal behaves like that.',
    tell: 'Tell: a perfectly regular oscillation, same amplitude on every '
        'channel, that never starts or stops. A notch filter removes it.',
    build: (rng) {
      final data = _baseline(rng);
      for (var c = 0; c < _channels.length; c++) {
        for (var i = 0; i < _sampleCount; i++) {
          data[c][i] += math.sin(2 * math.pi * 60 * i / _fs + c * 0.2) * 22;
        }
      }
      return data;
    },
  ),
  _Round(
    answer: 'A loose electrode',
    caption: 'Impedance check was skipped',
    hint: 'Compare each channel against its neighbours',
    why: 'An electrode pop. When contact breaks, the charge at that one '
        'contact suddenly rebalances and the trace steps to a new baseline. '
        'It is a hardware fault, not biology.',
    tell: 'Tell: a sharp jump confined to a single channel. Brain activity is '
        'spatially smeared, so no real signal appears on exactly one '
        'electrode and none of its neighbours.',
    build: (rng) {
      final data = _baseline(rng);
      final c = _channels.indexOf('C4');
      final start = (2.4 * _fs).round();
      for (var i = start; i < _sampleCount; i++) {
        final k = i - start;
        data[c][i] += 165 * math.exp(-k / (_fs * 2.2)) + 40;
      }
      for (var k = 0; k < 12; k++) {
        if (start + k < _sampleCount) data[c][start + k] += 90;
      }
      return data;
    },
  ),
  _Round(
    answer: 'Heartbeat',
    caption: 'Electrodes referenced near the neck',
    hint: 'Time the spacing between the spikes',
    why: 'Cardiac activity. The heart is the strongest electrical generator '
        'in the body, and its field reaches the scalp — especially with a '
        'reference placed low, near a large vessel.',
    tell: 'Tell: sharp identical spikes at a steady rhythm, roughly one per '
        'second. If the spacing matches a plausible pulse rate, suspect the '
        'heart.',
    build: (rng) {
      final data = _baseline(rng);
      const rr = 0.86; // ≈70 bpm
      for (var t = 0.35; t < _durationSeconds; t += rr) {
        final start = (t * _fs).round();
        for (var c = 0; c < _channels.length; c++) {
          final weight =
              0.35 + (RegExp(r'^[TP]').hasMatch(_channels[c]) ? 0.5 : 0.1);
          for (var k = -6; k < 14; k++) {
            final i = start + k;
            if (i < 0 || i >= _sampleCount) continue;
            final d = k - 3;
            final v = k < 0 ? -14.0 : math.exp(-(d * d) / 9) * 52;
            data[c][i] += v * weight;
          }
        }
      }
      return data;
    },
  ),
  _Round(
    answer: 'Nothing — this is clean brain activity',
    caption: 'Rest, eyes closed',
    hint: 'O1 and O2 sit over visual cortex',
    why: 'Nothing is wrong. This is the alpha rhythm — 8–12 Hz activity that '
        'appears over visual cortex when the eyes close. It is the healthiest '
        'thing EEG can show you.',
    tell: 'Tell: a smooth rhythmic wave that waxes and wanes, strongest at '
        'O1/O2 and weak at the front. Learning to leave real signal alone '
        'matters as much as spotting artifacts.',
    build: (rng) => _baseline(rng, alphaGain: 2.6),
  ),
];

// ------------------------------------------------------------------- widget

class _ArtifactDetectiveState extends State<ArtifactDetective> {
  var _rng = _Rng();
  int _index = 0;
  int _correct = 0;
  String? _picked;
  bool _answered = false;
  late List<Float32List> _data;

  @override
  void initState() {
    super.initState();
    _data = _rounds[0].build(_rng);
  }

  /// Replay from round one with the same seeded traces.
  void _restart() {
    setState(() {
      _rng = _Rng();
      _index = 0;
      _correct = 0;
      _picked = null;
      _answered = false;
      _data = _rounds[0].build(_rng);
    });
  }

  void _check() {
    if (_picked == null || _answered) return;
    setState(() {
      _answered = true;
      if (_picked == _rounds[_index].answer) _correct++;
    });
  }

  void _next() {
    if (_index + 1 >= _rounds.length) {
      widget.onComplete?.call();
      setState(() => _index = _rounds.length);
      return;
    }
    setState(() {
      _index++;
      _picked = null;
      _answered = false;
      _data = _rounds[_index].build(_rng);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_index >= _rounds.length) return _summary(context);

    final round = _rounds[_index];
    final isRight = _picked == round.answer;
    final text = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Artifact detective', style: text.titleMedium),
            const Spacer(),
            Text('$_correct / ${_rounds.length}',
                style: text.labelLarge?.copyWith(color: NeuroColors.muted)),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(99),
          child: LinearProgressIndicator(
            value: _index / _rounds.length,
            minHeight: 10,
            backgroundColor: NeuroColors.sand,
            valueColor: const AlwaysStoppedAnimation(NeuroColors.moss),
          ),
        ),
        const SizedBox(height: 14),
        Text('What is contaminating this recording?', style: text.titleLarge),
        const SizedBox(height: 10),

        // trace panel
        Container(
          decoration: BoxDecoration(
            border: Border.all(color: NeuroColors.line, width: 2),
            borderRadius: BorderRadius.circular(16),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                color: NeuroColors.mist,
                child: Row(
                  children: [
                    Expanded(
                      child: Text(round.caption, style: text.labelLarge),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Simulated · 1 s grid',
                      style: text.labelSmall?.copyWith(
                        color: NeuroColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(
                height: 230,
                child: CustomPaint(
                  painter: _TracePainter(_data),
                  size: Size.infinite,
                ),
              ),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                decoration: const BoxDecoration(
                  border: Border(top: BorderSide(color: NeuroColors.line)),
                ),
                child: Text(round.hint,
                    style: text.bodySmall?.copyWith(color: NeuroColors.muted)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),

        for (final option in _options) _choice(option, round),

        const SizedBox(height: 12),
        if (!_answered)
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _picked == null ? null : _check,
              child: const Text('Check'),
            ),
          )
        else
          _verdict(context, round, isRight),
      ],
    );
  }

  Widget _choice(String option, _Round round) {
    final selected = _picked == option;
    Color border = NeuroColors.line;
    Color fill = Colors.transparent;

    if (_answered) {
      if (option == round.answer) {
        border = NeuroColors.moss;
        fill = NeuroColors.moss.withValues(alpha: 0.08);
      } else if (selected) {
        border = NeuroColors.danger;
        fill = NeuroColors.danger.withValues(alpha: 0.08);
      }
    } else if (selected) {
      border = NeuroColors.tide;
      fill = NeuroColors.tide.withValues(alpha: 0.08);
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: _answered ? null : () => setState(() => _picked = option),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
          decoration: BoxDecoration(
            color: fill,
            border: Border.all(color: border, width: 2),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(option, style: Theme.of(context).textTheme.bodyLarge),
        ),
      ),
    );
  }

  Widget _verdict(BuildContext context, _Round round, bool isRight) {
    final text = Theme.of(context).textTheme;
    final accent = isRight ? NeuroColors.moss : NeuroColors.danger;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.07),
        border: Border.all(color: accent.withValues(alpha: 0.35), width: 2),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(isRight ? "That's it" : 'Not this time',
              style: text.titleMedium?.copyWith(color: accent)),
          const SizedBox(height: 6),
          Text(round.why, style: text.bodyMedium),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.only(left: 11),
            decoration: const BoxDecoration(
              border: Border(
                left: BorderSide(color: NeuroColors.line, width: 3),
              ),
            ),
            child: Text(round.tell,
                style: text.bodySmall?.copyWith(color: NeuroColors.muted)),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _next,
              child: Text(
                _index + 1 >= _rounds.length ? 'Finish' : 'Continue',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _summary(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final pct = (_correct / _rounds.length * 100).round();
    final message = pct == 100
        ? 'You read every trace correctly, including the clean one.'
        : pct >= 67
            ? 'Solid. The ones you missed are the ones worth rereading.'
            : 'Artifacts take practice. Go back through the tells and retry.';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: NeuroColors.sand,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        children: [
          Text('Round complete', style: text.headlineSmall),
          const SizedBox(height: 8),
          Text('$pct%',
              style: text.displaySmall?.copyWith(color: NeuroColors.tide)),
          const SizedBox(height: 8),
          Text(message, textAlign: TextAlign.center, style: text.bodyMedium),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: _restart,
            child: const Text('Play again'),
          ),
        ],
      ),
    );
  }
}

// ------------------------------------------------------------------ painter

class _TracePainter extends CustomPainter {
  _TracePainter(this.data);

  final List<Float32List> data;

  @override
  void paint(Canvas canvas, Size size) {
    const padLeft = 34.0;
    const padRight = 8.0;
    const padY = 6.0;

    final plotWidth = size.width - padLeft - padRight;
    final rowHeight = (size.height - padY * 2) / _channels.length;
    // 50 µV maps to a little under half a row, so a 130 µV blink spills into
    // the neighbouring row exactly as it does on real review software.
    final amp = (rowHeight * 0.46) / 50;
    // Clip at 1.5 rows either side of centre, MNE's default for raw plots:
    // large artifacts overlap neighbours but keep their true shape.
    final clip = rowHeight * 1.5;

    final grid = Paint()
      ..color = const Color(0xFFF1F3F6)
      ..strokeWidth = 1;
    for (var s = 1; s < _durationSeconds; s++) {
      final x = padLeft + (s / _durationSeconds) * plotWidth;
      canvas.drawLine(Offset(x, padY), Offset(x, size.height - padY), grid);
    }

    final stroke = Paint()
      ..color = const Color(0xFF2A3550)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.9
      ..isAntiAlias = true;

    // When there are more samples than pixels, draw each pixel column's
    // minimum and maximum. Keeping every nth sample instead would alias fast
    // signals: 60 Hz mains sampled at 125 Hz shows up as a slow 5 Hz wobble.
    final perColumn = _sampleCount / plotWidth;

    for (var c = 0; c < _channels.length; c++) {
      final centre = padY + rowHeight * c + rowHeight / 2;
      final low = centre - clip;
      final high = centre + clip;
      final path = Path();
      var started = false;

      void point(int i, double v) {
        final x = padLeft + (i / (_sampleCount - 1)) * plotWidth;
        final y = (centre - v * amp).clamp(low, high);
        if (started) {
          path.lineTo(x, y);
        } else {
          path.moveTo(x, y);
          started = true;
        }
      }

      if (perColumn <= 2) {
        for (var i = 0; i < _sampleCount; i++) {
          point(i, data[c][i]);
        }
      } else {
        final columns = plotWidth.floor();
        for (var col = 0; col < columns; col++) {
          final start = (col * perColumn).floor();
          final end = math.min(_sampleCount, ((col + 1) * perColumn).floor());
          if (start >= end) continue;
          var minI = start, maxI = start;
          for (var i = start + 1; i < end; i++) {
            if (data[c][i] < data[c][minI]) minI = i;
            if (data[c][i] > data[c][maxI]) maxI = i;
          }
          // Keep time order so the line does not zig-zag backwards.
          final first = math.min(minI, maxI), second = math.max(minI, maxI);
          point(first, data[c][first]);
          if (second != first) point(second, data[c][second]);
        }
      }
      canvas.drawPath(path, stroke);

      final label = TextPainter(
        text: TextSpan(
          text: _channels[c],
          style: const TextStyle(fontSize: 9, color: NeuroColors.muted),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, Offset(padLeft - label.width - 6, centre - 6));
    }
  }

  @override
  bool shouldRepaint(covariant _TracePainter oldDelegate) =>
      !identical(oldDelegate.data, data);
}
