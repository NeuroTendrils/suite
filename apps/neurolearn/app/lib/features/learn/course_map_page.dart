import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../data/progress_repository.dart';
import '../../models/content.dart';
import '../../theme/app_theme.dart';
import '../../widgets/content_image.dart';
import 'lesson_overview_page.dart';

/// Decorative, unlabeled nodes that continue the path below the real lessons.
const _blankSteps = 4;

class CourseMapPage extends StatelessWidget {
  const CourseMapPage({
    super.key,
    required this.content,
    required this.progress,
    required this.onProgressChanged,
  });

  final ContentRepository content;
  final ProgressRepository progress;
  final VoidCallback onProgressChanged;

  Future<void> _openLesson(BuildContext context, String lessonId) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => LessonOverviewPage(
          lessonId: lessonId,
          content: content,
          progress: progress,
        ),
      ),
    );
    // Opening a lesson, reading it, or a failed attempt all change progress,
    // not only a pass, so always refresh on return.
    onProgressChanged();
  }

  @override
  Widget build(BuildContext context) {
    final course = content.course;
    final lessons = <Lesson>[
      for (final unit in course.units)
        for (final id in unit.lessonIds) course.lessonById(id)!,
    ];
    final continueId = progress.continueLessonId(course);
    var complete = 0;
    for (final lesson in lessons) {
      if (progress.statusForLesson(course: course, lessonId: lesson.id) ==
          LessonStatus.complete) {
        complete += 1;
      }
    }
    final total = lessons.length;
    final pct = total == 0 ? 0.0 : complete / total;

    return ListView(
      key: const PageStorageKey('learn-scroll'),
      padding: const EdgeInsets.all(NeuroLayout.pagePadding),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Text(
                'Learn',
                style: Theme.of(context).textTheme.headlineLarge,
              ),
            ),
            Text(
              'NeuroLearn',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: NeuroColors.tide,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        _CourseCard(
          title: course.title,
          complete: complete,
          total: total,
          progress: pct,
        ),
        const SizedBox(height: 24),
        Text(
          'Your brain journey',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 16),
        if (lessons.isNotEmpty)
          LayoutBuilder(
            builder: (context, constraints) {
              final labelWidth = constraints.maxWidth * .64;
              // Measure real titles so future lessons and enlarged text keep their space.
              var titleHeight = 0.0;
              for (final lesson in lessons) {
                final painter = TextPainter(
                  text: TextSpan(
                    text: lesson.title,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  textDirection: Directionality.of(context),
                  textScaler: MediaQuery.textScalerOf(context),
                )..layout(maxWidth: labelWidth - 12);
                if (painter.height > titleHeight) titleHeight = painter.height;
                painter.dispose();
              }
              final scale = MediaQuery.textScalerOf(context).scale(16) / 16;
              final calloutHeight = 36 * scale;
              var statusHeight = 0.0;
              for (final label in ['Completed', 'In progress']) {
                final painter = TextPainter(
                  text: TextSpan(
                    text: label,
                    style: Theme.of(context).textTheme.labelMedium,
                  ),
                  textDirection: Directionality.of(context),
                  textScaler: MediaQuery.textScalerOf(context),
                )..layout(maxWidth: labelWidth);
                if (painter.height > statusHeight) {
                  statusHeight = painter.height;
                }
                painter.dispose();
              }
              final rowHeight =
                  calloutHeight + 118 + titleHeight + statusHeight;
              return CustomPaint(
                painter: _BrainPathPainter(
                  count: lessons.length + _blankSteps,
                  rowHeight: rowHeight,
                  nodeCenter: calloutHeight + 46,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 28),
                  child: Column(
                    children: [
                      for (var i = 0; i < lessons.length; i++)
                        Align(
                          alignment: i.isEven
                              ? Alignment.centerLeft
                              : Alignment.centerRight,
                          child: SizedBox(
                            width: labelWidth,
                            height: rowHeight,
                            child: _LessonStep(
                              key: ValueKey(lessons[i].id),
                              number: i + 1,
                              calloutHeight: calloutHeight,
                              title: lessons[i].title,
                              status: progress.statusForLesson(
                                course: course,
                                lessonId: lessons[i].id,
                              ),
                              recommended: lessons[i].id == continueId,
                              onTap: () => _openLesson(context, lessons[i].id),
                            ),
                          ),
                        ),
                      for (
                        var i = lessons.length;
                        i < lessons.length + _blankSteps;
                        i++
                      )
                        Align(
                          alignment: i.isEven
                              ? Alignment.centerLeft
                              : Alignment.centerRight,
                          child: SizedBox(
                            width: labelWidth,
                            height: rowHeight,
                            child: _BlankStep(calloutHeight: calloutHeight),
                          ),
                        ),
                    ],
                  ),
                ),
              );
            },
          ),
        const SizedBox(height: 16),
      ],
    );
  }
}

class _CourseCard extends StatelessWidget {
  const _CourseCard({
    required this.title,
    required this.complete,
    required this.total,
    required this.progress,
  });
  final String title;
  final int complete;
  final int total;
  final double progress;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: NeuroColors.tide,
        borderRadius: BorderRadius.circular(NeuroLayout.surfaceRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: text.displayMedium?.copyWith(
                    color: Colors.white,
                    fontSize: 26,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              const ExcludeSemantics(
                child: SizedBox(
                  width: 90,
                  height: 80,
                  child: ContentImage(assetPath: 'assets/brand/mascot.png'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            '$complete of $total lessons completed',
            style: text.labelLarge?.copyWith(color: Colors.white),
          ),
          const SizedBox(height: 10),
          ExcludeSemantics(
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              borderRadius: BorderRadius.circular(8),
              color: NeuroColors.brainPink,
              backgroundColor: NeuroColors.deepBlue,
            ),
          ),
        ],
      ),
    );
  }
}

/// Friendly contours only: no anatomical meaning or extra curriculum nodes.
/// Route endpoints share the same row geometry as the lesson buttons.
class _BrainPathPainter extends CustomPainter {
  const _BrainPathPainter({
    required this.count,
    required this.rowHeight,
    required this.nodeCenter,
  });
  final int count;
  final double rowHeight;
  final double nodeCenter;

  @override
  void paint(Canvas canvas, Size size) {
    // Scale uniformly to the width; extra height becomes extra mid-brain
    // lobes (inserted at y=185 left / y=213 right) rather than a stretch.
    var scale = size.width / 320;
    final lobes = ((size.height / scale - 440) / 96).round().clamp(0, 99);
    final lobe = lobes == 0 ? 0.0 : (size.height / scale - 440) / lobes;
    final d = lobes * lobe;
    canvas.save();
    if (lobes == 0) {
      scale = math.min(scale, size.height / 440);
      canvas.translate((size.width - 320 * scale) / 2, 0);
    }
    canvas.scale(scale);
    final brain = Path()
      ..moveTo(160, 30)
      ..cubicTo(136, 2, 90, 6, 76, 36)
      ..cubicTo(34, 28, 12, 62, 22, 99)
      ..cubicTo(-2, 119, 0, 160, 13, 185);
    for (var k = 0; k < lobes; k++) {
      final y = 185 + k * lobe;
      final bulge = k.isEven ? -3.0 : -6.0;
      brain.cubicTo(
        bulge,
        y + lobe * .3,
        bulge + 2,
        y + lobe * .75,
        13,
        y + lobe,
      );
    }
    brain
      ..cubicTo(-5, 215 + d, 1, 259 + d, 16, 281 + d)
      ..cubicTo(0, 321 + d, 19, 356 + d, 47, 362 + d)
      ..cubicTo(44, 402 + d, 101, 429 + d, 137, 403 + d)
      ..quadraticBezierTo(155, 395 + d, 160, 380 + d)
      ..cubicTo(181, 428 + d, 243, 415 + d, 261, 386 + d)
      ..cubicTo(306, 383 + d, 327, 344 + d, 304, 306 + d)
      ..cubicTo(330, 278 + d, 321, 230 + d, 308, 213 + d);
    for (var k = lobes - 1; k >= 0; k--) {
      final y = 213 + (k + 1) * lobe;
      final bulge = k.isEven ? 327.0 : 324.0;
      brain.cubicTo(
        bulge,
        y - lobe * .3,
        bulge - 2,
        y - lobe * .75,
        308,
        y - lobe,
      );
    }
    brain
      ..cubicTo(329, 179, 321, 133, 302, 113)
      ..cubicTo(315, 76, 286, 41, 253, 43)
      ..cubicTo(232, 5, 185, 4, 160, 30)
      ..close();
    canvas.drawPath(brain, Paint()..color = NeuroColors.brainWash);
    canvas.drawPath(
      brain,
      Paint()
        ..color = NeuroColors.brainLine
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2,
    );
    final fold = Paint()
      ..color = NeuroColors.brainLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final folds = Path()
      ..moveTo(160, 30)
      ..cubicTo(145, 65, 175, 92, 158, 124)
      ..moveTo(160, 328 + d)
      ..cubicTo(147, 348 + d, 166, 365 + d, 160, 380 + d)
      ..moveTo(41, 111)
      ..cubicTo(80, 124, 52, 160, 76, 173)
      ..moveTo(252, 83)
      ..cubicTo(220, 90, 254, 132, 276, 133)
      ..moveTo(42, 298 + d)
      ..cubicTo(78, 277 + d, 62, 329 + d, 100, 337 + d)
      ..moveTo(268, 314 + d)
      ..cubicTo(238, 327 + d, 274, 352 + d, 242, 369 + d);
    // One fold per added lobe, alternating sides, echoing the top folds.
    for (var k = 0; k < lobes; k++) {
      final y = 185 + k * lobe + (lobe - 62) / 2;
      if (k.isEven) {
        folds
          ..moveTo(30, y)
          ..cubicTo(69, y + 13, 41, y + 49, 65, y + 62);
      } else {
        folds
          ..moveTo(290, y)
          ..cubicTo(251, y + 13, 279, y + 49, 255, y + 62);
      }
    }
    canvas.drawPath(folds, fold);
    canvas.restore();
    final route = Path();
    for (var i = 0; i < count; i++) {
      final x = size.width * (i.isEven ? .32 : .68);
      final y = 28 + i * rowHeight + nodeCenter;
      if (i == 0) {
        route.moveTo(x, y);
      } else {
        final previousX = size.width * (i.isEven ? .68 : .32);
        route.cubicTo(
          previousX,
          y - rowHeight * .45,
          x,
          y - rowHeight * .55,
          x,
          y,
        );
      }
    }
    canvas.drawPath(
      route,
      Paint()
        ..color = NeuroColors.brainRoute
        ..style = PaintingStyle.stroke
        ..strokeWidth = 7
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _BrainPathPainter oldDelegate) =>
      count != oldDelegate.count ||
      rowHeight != oldDelegate.rowHeight ||
      nodeCenter != oldDelegate.nodeCenter;
}

/// Matches an available [_LessonStep] button, without a label or any input.
class _BlankStep extends StatelessWidget {
  const _BlankStep({required this.calloutHeight});
  final double calloutHeight;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Column(
        children: [
          SizedBox(height: calloutHeight),
          const SizedBox(height: 8),
          Container(
            width: 80,
            height: 76,
            decoration: BoxDecoration(
              color: NeuroColors.softTide,
              borderRadius: BorderRadius.circular(30),
              border: Border.all(color: NeuroColors.tide, width: 3),
              boxShadow: const [
                BoxShadow(color: NeuroColors.deepBlue, offset: Offset(0, 7)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LessonStep extends StatefulWidget {
  const _LessonStep({
    super.key,
    required this.number,
    required this.calloutHeight,
    required this.title,
    required this.status,
    required this.recommended,
    required this.onTap,
  });
  final int number;
  final double calloutHeight;
  final String title;
  final LessonStatus status;
  final bool recommended;
  final VoidCallback onTap;
  @override
  State<_LessonStep> createState() => _LessonStepState();
}

class _LessonStepState extends State<_LessonStep> {
  bool focused = false;
  bool pressed = false;
  bool hovered = false;

  @override
  Widget build(BuildContext context) {
    final complete = widget.status == LessonStatus.complete;
    final active = widget.recommended && !complete;
    final inProgress = widget.status == LessonStatus.inProgress;
    final action = inProgress
        ? 'Resume'
        : widget.status == LessonStatus.available
        ? 'Start lesson'
        : 'Open lesson';
    final status = complete
        ? 'Completed'
        : active
        ? 'Recommended'
        : inProgress
        ? 'In progress'
        : 'Available';
    final visibleStatus = complete
        ? 'Completed'
        : inProgress
        ? 'In progress'
        : null;
    final text = Theme.of(context).textTheme;
    final surface = complete
        ? NeuroColors.moss
        : active
        ? NeuroColors.tide
        : NeuroColors.softTide;
    return Semantics(
      button: true,
      label: 'Lesson ${widget.number}: ${widget.title}. $status. $action',
      onTap: widget.onTap,
      excludeSemantics: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: widget.onTap,
          onFocusChange: (value) => setState(() => focused = value),
          onHighlightChanged: (value) => setState(() => pressed = value),
          onHover: (value) => setState(() => hovered = value),
          borderRadius: BorderRadius.circular(24),
          hoverColor: NeuroColors.tide.withValues(alpha: .04),
          focusColor: NeuroColors.tide.withValues(alpha: .06),
          child: Column(
            children: [
              SizedBox(
                height: widget.calloutHeight,
                child: active
                    ? Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: NeuroColors.tide,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            action,
                            style: text.labelLarge?.copyWith(
                              color: Colors.white,
                            ),
                          ),
                        ),
                      )
                    : null,
              ),
              const SizedBox(height: 8),
              AnimatedContainer(
                duration: MediaQuery.disableAnimationsOf(context)
                    ? Duration.zero
                    : NeuroLayout.motion,
                transform: Matrix4.translationValues(0, pressed ? 5 : 0, 0),
                width: 80,
                height: 76,
                decoration: BoxDecoration(
                  color: hovered
                      ? Color.alphaBlend(
                          Colors.white.withValues(alpha: .1),
                          surface,
                        )
                      : surface,
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(
                    color: focused
                        ? NeuroColors.ink
                        : active || complete
                        ? Colors.white
                        : NeuroColors.tide,
                    width: focused ? 4 : 3,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: complete ? NeuroColors.moss : NeuroColors.deepBlue,
                      offset: Offset(0, pressed ? 2 : 7),
                    ),
                    if (active)
                      BoxShadow(
                        color: NeuroColors.tide.withValues(alpha: .12),
                        spreadRadius: 7,
                      ),
                  ],
                ),
                alignment: Alignment.center,
                child: complete
                    ? const Icon(
                        Icons.check_rounded,
                        color: Colors.white,
                        size: 34,
                      )
                    : Text(
                        '${widget.number}',
                        style: text.headlineLarge?.copyWith(
                          color: active ? Colors.white : NeuroColors.tide,
                        ),
                      ),
              ),
              const SizedBox(height: 18),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Text(
                  widget.title,
                  textAlign: TextAlign.center,
                  style: text.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              if (visibleStatus != null) ...[
                const SizedBox(height: 4),
                Text(
                  visibleStatus,
                  style: text.labelMedium?.copyWith(
                    color: complete ? NeuroColors.moss : NeuroColors.muted,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
