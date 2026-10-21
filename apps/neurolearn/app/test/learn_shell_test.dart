import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/data/content_repository.dart';
import 'package:neurolearn/data/progress_repository.dart';
import 'package:neurolearn/features/learn/lesson_overview_page.dart';
import 'package:neurolearn/features/learn/course_map_page.dart';
import 'package:neurolearn/main.dart';
import 'package:neurolearn/models/content.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ContentRepository content;
  late ProgressRepository progress;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    content = ContentRepository();
    await content.load();
    progress = ProgressRepository(await SharedPreferences.getInstance());
    await progress.load();
    final icons = FontLoader('MaterialIcons')
      ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
    await icons.load();
    for (final font in ['Fraunces', 'SourceSans3']) {
      final loader = FontLoader(font == 'Fraunces' ? font : 'Source Sans 3');
      loader.addFont(rootBundle.load('assets/fonts/$font.ttf'));
      await loader.load();
    }
  });

  Future<void> show(WidgetTester tester, Size size, {double scale = 1}) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = size;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(
            size: size,
            textScaler: TextScaler.linear(scale),
          ),
          child: NeuroLearnApp(content: content, progress: progress),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('later and completed lessons open through the existing route', (
    tester,
  ) async {
    await show(tester, const Size(390, 844));
    final later = find.byKey(const ValueKey('intro-02-eeg-basics'));
    await tester.drag(find.byType(ListView).first, const Offset(0, -400));
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(of: later, matching: find.byType(InkWell)),
    );
    await tester.pumpAndSettle();
    expect(find.byType(LessonOverviewPage), findsOneWidget);
    expect(find.text('Introduction to EEGs'), findsWidgets);
    Navigator.of(tester.element(find.byType(LessonOverviewPage))).pop();
    await tester.pumpAndSettle();
    await progress.recordCheckResult(
      lessonId: 'intro-01-brain-electricity',
      score: 1,
      passed: true,
    );
    await tester.pumpWidget(const SizedBox());
    await show(tester, const Size(390, 844));
    expect(find.text('1 of ${content.course.lessons.length} lessons completed'), findsOneWidget);
    expect(find.text('Completed'), findsOneWidget);
    final first = find.byKey(const ValueKey('intro-01-brain-electricity'));
    await tester.ensureVisible(first);
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(of: first, matching: find.byType(InkWell)),
    );
    await tester.pumpAndSettle();
    expect(find.byType(LessonOverviewPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('selection survives viewport changes and all destinations work', (
    tester,
  ) async {
    await show(tester, const Size(390, 844));
    await tester.tap(find.text('Practice').last);
    await tester.pumpAndSettle();
    tester.view.physicalSize = const Size(1280, 900);
    await tester.pumpAndSettle();
    expect(
      tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
      1,
    );
    await tester.tap(find.text('You').first);
    await tester.pumpAndSettle();
    expect(find.text('About'), findsOneWidget);
    await tester.tap(find.text('Learn').first);
    await tester.pumpAndSettle();
    expect(find.text('0 of ${content.course.lessons.length} lessons completed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  for (final size in [
    const Size(390, 844),
    const Size(1280, 900),
    const Size(320, 844),
  ]) {
    testWidgets('Learn fits $size with enlarged text', (tester) async {
      await show(tester, size, scale: 2);
      expect(
        MediaQuery.textScalerOf(
          tester.element(find.byType(CourseMapPage)),
        ).scale(16),
        32,
      );
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('intro-02-eeg-basics')),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('in-progress action and keyboard lesson access', (tester) async {
    await progress.markInProgress('intro-01-brain-electricity');
    await show(tester, const Size(1280, 900));
    expect(find.text('Resume'), findsOneWidget);
    Focus.of(
      tester.element(find.text("The brain's electrical currents")),
    ).requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(LessonOverviewPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('additional long-titled lessons stay ordered and reachable', (
    tester,
  ) async {
    final original = content.course;
    final lessons = [
      ...original.lessons.values,
      for (var i = 3; i <= 5; i++)
        Lesson(
          id: 'test-$i',
          title:
              'A longer lesson title for checking the brain journey layout $i',
          unit: 'test',
          objective: '',
          estMinutes: 0,
          blocks: [],
        ),
    ];
    content = _CourseFixture(
      Course(
        id: original.id,
        title: original.title,
        version: original.version,
        units: [
          Unit(
            id: 'test',
            title: '',
            section: '',
            lessonIds: lessons.map((lesson) => lesson.id).toList(),
          ),
        ],
        lessons: {for (final lesson in lessons) lesson.id: lesson},
      ),
    );
    await show(tester, const Size(360, 800), scale: 2);
    final last = find.byKey(const ValueKey('test-5'));
    await tester.scrollUntilVisible(
      last,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.descendant(of: last, matching: find.byType(InkWell)));
    await tester.pumpAndSettle();
    expect(find.byType(LessonOverviewPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('persisted completion renders accurate progress and semantics', (
    tester,
  ) async {
    for (final id in content.course.lessons.keys) {
      await progress.recordCheckResult(lessonId: id, score: 1, passed: true);
    }
    progress = ProgressRepository(await SharedPreferences.getInstance());
    await progress.load();
    final semantics = tester.ensureSemantics();
    await show(tester, const Size(390, 844));
    expect(find.text('${content.course.lessons.length} of ${content.course.lessons.length} lessons completed'), findsOneWidget);
    expect(
      find.text('Completed'),
      findsNWidgets(content.course.lessons.length),
    );
    expect(find.text('Start lesson'), findsNothing);
    expect(
      tester
          .widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator))
          .value,
      1,
    );
    expect(
      find.bySemanticsLabel(RegExp(r'Lesson 1:.*Completed. Open lesson')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
    semantics.dispose();
  });

  // Opt-in rendered previews; normal test runs do not create artifacts.
  if (const bool.fromEnvironment('PREVIEWS')) {
    testWidgets('shared screen previews', (tester) async {
      await show(tester, const Size(390, 844));
      for (final tab in ['Practice', 'You']) {
        await tester.tap(find.text(tab).last);
        await tester.pumpAndSettle();
        await expectLater(
          find.byType(NeuroLearnApp),
          matchesGoldenFile('/tmp/neurolearn-$tab.png'),
        );
      }
    });
    for (final size in [const Size(390, 844), const Size(1280, 900)]) {
      testWidgets('preview $size', (tester) async {
        await show(tester, size);
        await expectLater(
          find.byType(NeuroLearnApp),
          matchesGoldenFile('/tmp/neurolearn-${size.width.toInt()}.png'),
        );
      });
    }
  }
}

class _CourseFixture extends ContentRepository {
  _CourseFixture(this.course);
  @override
  final Course course;
}
