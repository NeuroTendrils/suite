import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/content_repository.dart';
import 'data/progress_repository.dart';
import 'features/shell/home_shell.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    final content = ContentRepository();
    await content.load();
    final prefs = await SharedPreferences.getInstance();
    final progress = ProgressRepository(prefs);
    await progress.load();
    runApp(NeuroLearnApp(content: content, progress: progress));
  } catch (error, stack) {
    // A broken content pack would otherwise leave a blank white screen.
    debugPrint('NeuroLearn failed to start: $error\n$stack');
    runApp(StartupErrorApp(error: error, onRetry: main));
  }
}

/// Shown when lessons cannot be loaded, instead of a blank screen.
class StartupErrorApp extends StatelessWidget {
  const StartupErrorApp({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NeuroLearn',
      debugShowCheckedModeBanner: false,
      theme: buildNeuroTheme(),
      home: Builder(
        builder: (context) {
          final text = Theme.of(context).textTheme;
          return Scaffold(
            body: SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: NeuroLayout.contentWidth,
                  ),
                  child: ListView(
                    shrinkWrap: true,
                    padding: const EdgeInsets.all(24),
                    children: [
                      Text("Lessons couldn't load", style: text.headlineMedium),
                      const SizedBox(height: 12),
                      Text(
                        'Something is wrong with the lesson files bundled '
                        'with the app. Your progress has not been changed.',
                        style: text.bodyLarge,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        '$error',
                        style: text.bodySmall?.copyWith(
                          color: NeuroColors.muted,
                        ),
                      ),
                      const SizedBox(height: 20),
                      if (onRetry != null)
                        FilledButton(
                          onPressed: onRetry,
                          child: const Text('Try again'),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class NeuroLearnApp extends StatelessWidget {
  const NeuroLearnApp({
    super.key,
    required this.content,
    required this.progress,
  });

  final ContentRepository content;
  final ProgressRepository progress;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NeuroLearn',
      debugShowCheckedModeBanner: false,
      theme: buildNeuroTheme(),
      home: HomeShell(content: content, progress: progress),
    );
  }
}
