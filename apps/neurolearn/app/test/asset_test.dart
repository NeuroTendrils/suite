import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/widgets/content_image.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('mascot PNG loads with explicit size', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ContentImage(
            assetPath: 'assets/brand/mascot.png',
            width: 48,
            height: 48,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(Image), findsOneWidget);
  });

  testWidgets('lesson SVG loads with flutter_svg', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 300,
            height: 180,
            child: ContentImage(
              assetPath: 'assets/packs/bci-foundations/assets/bci-loop.svg',
              height: 180,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(SvgPicture), findsOneWidget);
  });
}
