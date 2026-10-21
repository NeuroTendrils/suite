import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/features/learn/check_page.dart';
import 'package:neurolearn/models/content.dart';

void main() {
  final check = CheckBlock(
    passScore: 0.7,
    items: [
      for (final id in ['q1', 'q2'])
        CheckItem(
          id: id,
          prompt: 'Prompt $id',
          explain: 'Because $id',
          choices: [
            Choice(text: 'Right $id', correct: true),
            Choice(text: 'Wrong $id', correct: false),
          ],
        ),
    ],
  );

  Future<List<CheckResult>> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final attempts = <CheckResult>[];
    await tester.pumpWidget(
      MaterialApp(
        home: CheckPage(
          title: 'Lesson',
          check: check,
          onFinished: (r) async => attempts.add(r),
        ),
      ),
    );
    return attempts;
  }

  Future<void> answer(WidgetTester tester, String text, String next) async {
    await tester.tap(find.text(text));
    await tester.pumpAndSettle();
    await tester.tap(find.text(next));
    await tester.pumpAndSettle();
  }

  testWidgets('a failed attempt is recorded and can be retried', (
    tester,
  ) async {
    final attempts = await open(tester);
    expect(find.text('Question 1 of 2'), findsOneWidget);

    await answer(tester, 'Wrong q1', 'Next');
    await answer(tester, 'Right q2', 'See results');
    expect(find.text('50%'), findsOneWidget);
    expect(attempts.single.passed, isFalse);
    expect(attempts.single.score, 0.5);

    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('Question 1 of 2'), findsOneWidget);
    expect(find.text('Correct'), findsNothing);

    await answer(tester, 'Right q1', 'Next');
    await answer(tester, 'Right q2', 'See results');
    expect(find.text('100%'), findsOneWidget);
    expect(attempts, hasLength(2));
    expect(attempts.last.passed, isTrue);
    expect(find.text('Continue'), findsOneWidget);
    expect(find.text('Try again'), findsNothing);
  });
}
