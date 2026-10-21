import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/data/content_repository.dart';
import 'package:neurolearn/data/progress_repository.dart';
import 'package:neurolearn/features/learn/check_page.dart';
import 'package:neurolearn/features/learn/lesson_overview_page.dart';
import 'package:neurolearn/sims/artifact_detective.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const lessonId = 'intro-03-artifacts';

  testWidgets('artifacts lesson: theory pages lead to the sim, then practice', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(430, 932);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    SharedPreferences.setMockInitialValues({});
    final content = ContentRepository();
    await content.load();
    final progress = ProgressRepository(await SharedPreferences.getInstance());
    await progress.load();

    await tester.pumpWidget(
      MaterialApp(
        home: LessonOverviewPage(
          lessonId: lessonId,
          content: content,
          progress: progress,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Not yet'), findsOneWidget);

    await tester.tap(find.text('Learn Theory'));
    await tester.pumpAndSettle();

    // Page forward until the simulation appears, without skipping past it.
    var guard = 0;
    while (find.byType(ArtifactDetective).evaluate().isEmpty) {
      expect(find.text('Start practice'), findsNothing,
          reason: 'reached the last page without seeing the sim');
      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
      expect(++guard, lessThan(10));
    }
    expect(progress.progressFor(lessonId).theoryCompleted, isFalse);

    await tester.tap(find.text('Start practice'));
    await tester.pumpAndSettle();
    expect(find.byType(CheckPage), findsOneWidget);
    expect(progress.progressFor(lessonId).theoryCompleted, isTrue);

    // Leaving practice early returns to an overview that shows the new state.
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.close_rounded));
    await tester.pumpAndSettle();
    expect(find.byType(LessonOverviewPage), findsOneWidget);
    expect(find.text('Read'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
