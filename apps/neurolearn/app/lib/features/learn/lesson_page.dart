import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../data/progress_repository.dart';
import '../../models/content.dart';
import '../../theme/app_theme.dart';
import '../../widgets/content_image.dart';
import '../../widgets/lesson_blocks.dart';
import 'check_page.dart';
import 'lesson_pagination.dart';

class LessonPage extends StatefulWidget {
  const LessonPage({
    super.key,
    required this.lessonId,
    required this.content,
    required this.progress,
  });

  final String lessonId;
  final ContentRepository content;
  final ProgressRepository progress;

  @override
  State<LessonPage> createState() => _LessonPageState();
}

class _LessonPageState extends State<LessonPage> {
  late final Lesson lesson;
  late final List<List<LessonBlock>> pages;
  var _index = 0;

  @override
  void initState() {
    super.initState();
    lesson = widget.content.course.lessonById(widget.lessonId)!;
    pages = paginateLesson(lesson.blocks);
    widget.progress.markInProgress(widget.lessonId);
  }

  CheckBlock? get _check {
    for (final block in lesson.blocks) {
      if (block is CheckBlock) return block;
    }
    return null;
  }

  Future<void> _startPractice() async {
    await widget.progress.markTheoryCompleted(lesson.id);
    if (!mounted) return;
    final check = _check;
    if (check == null) {
      Navigator.of(context).pop(true);
      return;
    }
    final result = await Navigator.of(context).push<CheckResult>(
      MaterialPageRoute(
        builder: (_) => CheckPage(
          title: lesson.title,
          check: check,
          onFinished: (result) => widget.progress.recordCheckResult(
            lessonId: lesson.id,
            score: result.score,
            passed: result.passed,
          ),
        ),
      ),
    );
    if (!mounted) return;
    if (result?.passed ?? false) Navigator.of(context).pop(true);
  }

  void _next() {
    if (_index < pages.length - 1) {
      setState(() => _index += 1);
      return;
    }
    _startPractice();
  }

  void _backPage() {
    if (_index > 0) {
      setState(() => _index -= 1);
      return;
    }
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final progressValue = pages.isEmpty ? 1.0 : (_index + 1) / pages.length;
    final pageBlocks = pages.isEmpty ? const <LessonBlock>[] : pages[_index];

    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 16, 4),
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded),
                  ),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(99),
                      child: LinearProgressIndicator(
                        value: progressValue,
                        minHeight: 8,
                        color: NeuroColors.tide,
                        backgroundColor: NeuroColors.sand,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    pages.isEmpty ? '0/0' : '${_index + 1}/${pages.length}',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: NeuroColors.muted,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(width: 8),
                  const ContentImage(
                    assetPath: 'assets/brand/mascot.png',
                    semanticLabel: 'NeuroLearn mascot',
                    width: 36,
                    height: 36,
                    fit: BoxFit.contain,
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                // A new key per page starts every page at the top.
                key: ValueKey(_index),
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                children: [
                  if (_index == 0) ...[
                    Text(
                      lesson.title,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      lesson.objective,
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: NeuroColors.muted,
                          ),
                    ),
                    const SizedBox(height: 22),
                  ],
                  for (final block in pageBlocks) ...[
                    LessonBlockView(
                      block: block,
                      content: widget.content,
                      compactTheory: true,
                      onSimComplete: () {
                        widget.progress.markSimCompleted(lesson.id);
                      },
                    ),
                    const SizedBox(height: 18),
                  ],
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              child: Row(
                children: [
                  if (_index > 0) ...[
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _backPage,
                        child: const Text('Back'),
                      ),
                    ),
                    const SizedBox(width: 12),
                  ],
                  Expanded(
                    flex: 2,
                    child: FilledButton(
                      onPressed: _next,
                      child: Text(
                        _index >= pages.length - 1 ? 'Start practice' : 'Next',
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
