import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/sims/artifact_detective.dart';

void main() {
  const answers = [
    'Eye blinks',
    'Jaw muscle tension',
    'Mains electrical interference',
    'A loose electrode',
    'Heartbeat',
    'Nothing — this is clean brain activity',
  ];

  testWidgets('all six rounds complete once, then the sim can be replayed', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(800, 2000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    var completed = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: ArtifactDetective(onComplete: () => completed++),
          ),
        ),
      ),
    );
    expect(find.text('Simulated · 1 s grid'), findsOneWidget);

    for (var i = 0; i < answers.length; i++) {
      await tester.tap(find.text(answers[i]));
      await tester.pump();
      await tester.tap(find.text('Check'));
      await tester.pump();
      expect(find.text("That's it"), findsOneWidget, reason: answers[i]);
      await tester.tap(find.text(i == answers.length - 1 ? 'Finish' : 'Continue'));
      await tester.pump();
    }

    expect(completed, 1);
    expect(find.text('100%'), findsOneWidget);

    await tester.tap(find.text('Play again'));
    await tester.pump();
    expect(find.text('0 / 6'), findsOneWidget);
    expect(find.text('What is contaminating this recording?'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
