import 'package:flutter/material.dart';

import '../../models/content.dart';
import '../../theme/app_theme.dart';
import '../../widgets/content_image.dart';

class CheckResult {
  CheckResult({required this.score, required this.passed});
  final double score;
  final bool passed;
}

class CheckPage extends StatefulWidget {
  const CheckPage({
    super.key,
    required this.title,
    required this.check,
    this.onFinished,
  });

  final String title;
  final CheckBlock check;

  /// Called once per completed attempt, as soon as results are shown, so a
  /// score is saved even if the learner retries or leaves with the back
  /// button instead of Continue.
  final Future<void> Function(CheckResult result)? onFinished;

  @override
  State<CheckPage> createState() => _CheckPageState();
}

class _CheckPageState extends State<CheckPage> {
  late List<int?> _selected;
  late List<bool?> _correct;
  var _index = 0;
  var _revealed = false;
  var _finished = false;
  CheckResult? _lastResult;

  @override
  void initState() {
    super.initState();
    _reset();
  }

  void _reset() {
    _selected = List<int?>.filled(widget.check.items.length, null);
    _correct = List<bool?>.filled(widget.check.items.length, null);
    _index = 0;
    _revealed = false;
    _finished = false;
  }

  void _retry() => setState(_reset);

  CheckItem get _item => widget.check.items[_index];

  double get _score =>
      _correct.where((e) => e == true).length / widget.check.items.length;

  void _submitChoice(int choiceIndex) {
    if (_revealed) return;
    setState(() {
      _selected[_index] = choiceIndex;
      _correct[_index] = _item.choices[choiceIndex].correct;
      _revealed = true;
    });
  }

  void _next() {
    if (_index < widget.check.items.length - 1) {
      setState(() {
        _index += 1;
        _revealed = _correct[_index] != null;
      });
      return;
    }
    final result = CheckResult(
      score: _score,
      passed: _score >= widget.check.passScore,
    );
    setState(() {
      _finished = true;
      _lastResult = result;
    });
    widget.onFinished?.call(result);
  }

  void _leave() => Navigator.of(context).pop(_finished ? _lastResult : null);

  @override
  Widget build(BuildContext context) {
    final passed = _score >= widget.check.passScore;
    final progress = (_index + (_revealed ? 1 : 0)) / widget.check.items.length;

    return Scaffold(
      backgroundColor: NeuroColors.mist,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Row(
                children: [
                  _RoundIconButton(
                    icon: Icons.arrow_back_ios_new_rounded,
                    onTap: _leave,
                  ),
                  Expanded(
                    child: Text(
                      widget.title,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  const SizedBox(width: 42),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(
                  value: _finished ? 1 : progress.clamp(0.05, 1),
                  minHeight: 8,
                  color: NeuroColors.tide,
                  backgroundColor: NeuroColors.sand,
                ),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
                children: [
                  if (_finished) ...[
                    const SizedBox(height: 24),
                    const ContentImage(
                      assetPath: 'assets/brand/mascot.png',
                      semanticLabel: 'NeuroLearn mascot',
                      width: 110,
                      height: 110,
                      fit: BoxFit.contain,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      '${(_score * 100).round()}%',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.displayMedium?.copyWith(
                            color: passed ? NeuroColors.moss : NeuroColors.clay,
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      passed
                          ? 'Nice work — practice passed.'
                          : 'Not yet — review theory and try again. No penalty.',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 28),
                    if (passed)
                      FilledButton(
                        onPressed: _leave,
                        child: const Text('Continue'),
                      )
                    else ...[
                      FilledButton(
                        onPressed: _retry,
                        child: const Text('Try again'),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton(
                        onPressed: _leave,
                        child: const Text('Back to lesson'),
                      ),
                    ],
                  ] else ...[
                    Text(
                      'Question ${_index + 1} of ${widget.check.items.length}',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: NeuroColors.muted,
                            fontWeight: FontWeight.w700,
                          ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _item.prompt,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 18),
                    ...List.generate(_item.choices.length, (i) {
                      final choice = _item.choices[i];
                      final selected = _selected[_index] == i;
                      Color border = NeuroColors.line;
                      Color fill = Colors.white;
                      if (_revealed && selected) {
                        border = choice.correct
                            ? NeuroColors.moss
                            : NeuroColors.danger;
                        fill = choice.correct
                            ? NeuroColors.moss.withValues(alpha: 0.08)
                            : NeuroColors.danger.withValues(alpha: 0.08);
                      } else if (_revealed && choice.correct) {
                        border = NeuroColors.moss;
                        fill = NeuroColors.moss.withValues(alpha: 0.06);
                      } else if (selected) {
                        border = NeuroColors.tide;
                      }

                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Material(
                          color: fill,
                          borderRadius: BorderRadius.circular(18),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(18),
                            onTap: _revealed ? null : () => _submitChoice(i),
                            child: Container(
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(18),
                                border: Border.all(color: border, width: 1.4),
                              ),
                              child: Row(
                                children: [
                                  Container(
                                    width: 22,
                                    height: 22,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      border: Border.all(
                                        color: selected
                                            ? NeuroColors.tide
                                            : NeuroColors.locked,
                                        width: 2,
                                      ),
                                      color: selected && !_revealed
                                          ? NeuroColors.tide
                                          : Colors.transparent,
                                    ),
                                  ),
                                  const SizedBox(width: 14),
                                  Expanded(
                                    child: Text(
                                      choice.text,
                                      style:
                                          Theme.of(context).textTheme.bodyLarge,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      );
                    }),
                    if (_revealed) ...[
                      const SizedBox(height: 8),
                      Text(
                        (_correct[_index] ?? false) ? 'Correct' : 'Not quite',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                              color: (_correct[_index] ?? false)
                                  ? NeuroColors.moss
                                  : NeuroColors.danger,
                            ),
                      ),
                      if (_item.explain != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          _item.explain!,
                          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                                color: NeuroColors.muted,
                              ),
                        ),
                      ],
                      const SizedBox(height: 20),
                      FilledButton(
                        onPressed: _next,
                        child: Text(
                          _index == widget.check.items.length - 1
                              ? 'See results'
                              : 'Next',
                        ),
                      ),
                    ],
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoundIconButton extends StatelessWidget {
  const _RoundIconButton({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      shape: const CircleBorder(),
      elevation: 1.5,
      shadowColor: NeuroColors.ink.withValues(alpha: 0.12),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: SizedBox(
          width: 42,
          height: 42,
          child: Icon(icon, size: 18, color: NeuroColors.ink),
        ),
      ),
    );
  }
}
