import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../data/progress_repository.dart';
import '../../models/content.dart';
import '../../theme/app_theme.dart';
import '../../widgets/content_image.dart';
import 'check_page.dart';
import 'lesson_page.dart';

class LessonOverviewPage extends StatefulWidget {
  const LessonOverviewPage({
    super.key,
    required this.lessonId,
    required this.content,
    required this.progress,
  });

  final String lessonId;
  final ContentRepository content;
  final ProgressRepository progress;

  @override
  State<LessonOverviewPage> createState() => _LessonOverviewPageState();
}

class _LessonOverviewPageState extends State<LessonOverviewPage> {
  String get lessonId => widget.lessonId;
  ContentRepository get content => widget.content;
  ProgressRepository get progress => widget.progress;

  Lesson get lesson => content.course.lessonById(lessonId)!;

  String? get _heroAsset {
    for (final block in lesson.blocks) {
      if (block is FigureBlock) {
        return content.assetPathForFigure(block.src);
      }
    }
    return null;
  }

  CheckBlock? get _check {
    for (final block in lesson.blocks) {
      if (block is CheckBlock) return block;
    }
    return null;
  }

  Future<void> _openTheory(BuildContext context) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => LessonPage(
          lessonId: lessonId,
          content: content,
          progress: progress,
        ),
      ),
    );
    if (!context.mounted) return;
    if (changed == true) {
      Navigator.of(context).pop(true);
    } else {
      // Reading or a failed attempt still changes what this page shows.
      setState(() {});
    }
  }

  Future<void> _openPractice(BuildContext context) async {
    final check = _check;
    if (check == null) return;
    await progress.markInProgress(lessonId);
    if (!context.mounted) return;
    final result = await Navigator.of(context).push<CheckResult>(
      MaterialPageRoute(
        builder: (_) => CheckPage(
          title: lesson.title,
          check: check,
          onFinished: (result) => progress.recordCheckResult(
            lessonId: lessonId,
            score: result.score,
            passed: result.passed,
          ),
        ),
      ),
    );
    if (!context.mounted) return;
    if (result?.passed ?? false) {
      Navigator.of(context).pop(true);
    } else {
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = progress.statusForLesson(
      course: content.course,
      lessonId: lessonId,
    );
    final lessonProgress = progress.progressFor(lessonId);
    final best = lessonProgress.bestScore;
    final theoryRead = lessonProgress.theoryCompleted;
    final hero = _heroAsset;

    // Lead with whichever step comes next: theory first, then practice.
    final practiceButton = theoryRead
        ? FilledButton(
            onPressed: () => _openPractice(context),
            child: const Text('Take Practice'),
          )
        : OutlinedButton(
            onPressed: () => _openPractice(context),
            child: const Text('Take Practice'),
          );
    final theoryButton = theoryRead
        ? OutlinedButton(
            onPressed: () => _openTheory(context),
            child: const Text('Learn Theory'),
          )
        : FilledButton(
            onPressed: () => _openTheory(context),
            child: const Text('Learn Theory'),
          );

    return Scaffold(
      backgroundColor: NeuroColors.mist,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 32),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: _RoundIconButton(
                icon: Icons.arrow_back_ios_new_rounded,
                onTap: () => Navigator.of(context).pop(),
              ),
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: ColoredBox(
                color: NeuroColors.blush.withValues(alpha: 0.18),
                child: SizedBox(
                  width: double.infinity,
                  height: 200,
                  child: hero == null
                      ? const Center(
                          child: ContentImage(
                            assetPath: 'assets/brand/mascot.png',
                            semanticLabel: 'NeuroLearn mascot',
                            width: 140,
                            height: 140,
                            fit: BoxFit.contain,
                          ),
                        )
                      : ContentImage(
                          assetPath: hero,
                          semanticLabel: lesson.title,
                          height: 200,
                          fit: BoxFit.contain,
                        ),
                ),
              ),
            ),
            const SizedBox(height: 22),
            Text(
              lesson.title,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 10),
            Text(
              lesson.objective,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: NeuroColors.muted,
                  ),
            ),
            const SizedBox(height: 22),
            theoryRead ? practiceButton : theoryButton,
            const SizedBox(height: 12),
            theoryRead ? theoryButton : practiceButton,
            const SizedBox(height: 28),
            Text(
              'Study summary',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 12),
            Container(
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(22),
                border: Border.all(color: NeuroColors.line),
              ),
              child: Column(
                children: [
                  _SummaryRow(
                    icon: Icons.menu_book_outlined,
                    title: theoryRead ? 'Read' : 'Not yet',
                    subtitle: 'Theory',
                  ),
                  const Divider(height: 1, indent: 56),
                  _SummaryRow(
                    icon: Icons.replay_rounded,
                    title: best == null
                        ? 'Not attempted'
                        : 'Best ${(best * 100).round()}%'
                            '${status == LessonStatus.complete ? ' · passed' : ''}',
                    subtitle: 'Practice score',
                  ),
                  const Divider(height: 1, indent: 56),
                  _SummaryRow(
                    icon: Icons.schedule_rounded,
                    title: '${lesson.estMinutes} min',
                    subtitle: 'Estimated time',
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

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Icon(icon, color: NeuroColors.ink),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleLarge),
                Text(
                  subtitle,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: NeuroColors.muted,
                      ),
                ),
              ],
            ),
          ),
        ],
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
