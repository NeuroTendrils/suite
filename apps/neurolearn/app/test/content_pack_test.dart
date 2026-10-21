import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/data/content_repository.dart';
import 'package:neurolearn/features/learn/lesson_pagination.dart';
import 'package:neurolearn/models/content.dart';
import 'package:neurolearn/sims/sim_registry.dart';

/// Integrity checks on the lesson pack that actually ships in the app.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Course course;

  setUpAll(() async {
    final content = ContentRepository();
    await content.load();
    course = content.course;
  });

  test('every unit lesson exists and belongs to that unit', () {
    for (final unit in course.units) {
      for (final id in unit.lessonIds) {
        final lesson = course.lessonById(id);
        expect(lesson, isNotNull, reason: '$id is missing');
        expect(lesson!.unit, unit.id);
      }
    }
  });

  test('every lesson has exactly one check with one correct answer per item',
      () {
    for (final lesson in course.lessons.values) {
      final checks = lesson.blocks.whereType<CheckBlock>().toList();
      expect(checks, hasLength(1), reason: lesson.id);
      for (final item in checks.single.items) {
        expect(
          item.choices.where((c) => c.correct),
          hasLength(1),
          reason: '${lesson.id}/${item.id}',
        );
        expect(item.explain, isNotNull, reason: '${lesson.id}/${item.id}');
      }
    }
  });

  test('every simulation a lesson references is built', () {
    for (final lesson in course.lessons.values) {
      for (final sim in lesson.blocks.whereType<SimBlock>()) {
        expect(simRegistry.containsKey(sim.id), isTrue,
            reason: '${lesson.id} uses unbuilt sim ${sim.id}');
      }
    }
  });

  test('artifact detective is reachable from a lesson', () {
    final uses = course.lessons.values.where(
      (l) => l.blocks.any((b) => b is SimBlock && b.id == 'artifact-detective'),
    );
    expect(uses, isNotEmpty);
  });

  test('every lesson paginates and keeps all its theory blocks', () {
    for (final lesson in course.lessons.values) {
      final pages = paginateLesson(lesson.blocks);
      expect(pages, isNotEmpty, reason: lesson.id);
      final nonMarkdown = lesson.blocks
          .where((b) => b is! MarkdownBlock && b is! CheckBlock)
          .length;
      final paged = pages.expand((p) => p).where((b) => b is! MarkdownBlock);
      expect(paged, hasLength(nonMarkdown), reason: lesson.id);
    }
  });

  test('compiled markdown keeps bold emphasis', () {
    final markdown = course.lessons.values
        .expand((l) => l.blocks)
        .whereType<MarkdownBlock>()
        .map((b) => b.markdown)
        .join('\n');
    expect(markdown, contains('**'));
  });
}
