import 'package:flutter/material.dart';

import '../../data/content_repository.dart';
import '../../data/progress_repository.dart';
import '../../models/content.dart';
import '../../theme/app_theme.dart';
import '../learn/course_map_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.content, required this.progress});

  final ContentRepository content;
  final ProgressRepository progress;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  var _index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      CourseMapPage(
        content: widget.content,
        progress: widget.progress,
        onProgressChanged: () => setState(() {}),
      ),
      const _SimplePage(
        title: 'Practice',
        body:
            'A light review queue from missed check items will live here. Coming next.',
      ),
      _ProfilePage(content: widget.content, progress: widget.progress),
    ];

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: NeuroLayout.contentWidth,
            ),
            child: IndexedStack(index: _index, children: pages),
          ),
        ),
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: NeuroColors.line)),
        ),
        child: SafeArea(
          top: false,
          child: Center(
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: NeuroLayout.contentWidth,
              ),
              child: NavigationBar(
                selectedIndex: _index,
                onDestinationSelected: (value) =>
                    setState(() => _index = value),
                animationDuration: MediaQuery.disableAnimationsOf(context)
                    ? Duration.zero
                    : NeuroLayout.motion,
                destinations: const [
                  NavigationDestination(
                    icon: Icon(Icons.route_outlined),
                    selectedIcon: Icon(Icons.route_rounded),
                    label: 'Learn',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.fact_check_outlined),
                    selectedIcon: Icon(Icons.fact_check_rounded),
                    label: 'Practice',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    selectedIcon: Icon(Icons.person_rounded),
                    label: 'You',
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SimplePage extends StatelessWidget {
  const _SimplePage({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(title, style: Theme.of(context).textTheme.headlineLarge),
        const SizedBox(height: 12),
        Text(
          body,
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: NeuroColors.muted),
        ),
      ],
    );
  }
}

class _ProfilePage extends StatelessWidget {
  const _ProfilePage({required this.content, required this.progress});

  final ContentRepository content;
  final ProgressRepository progress;

  @override
  Widget build(BuildContext context) {
    final course = content.course;
    var complete = 0;
    var total = 0;
    for (final unit in course.units) {
      for (final id in unit.lessonIds) {
        total += 1;
        if (progress.statusForLesson(course: course, lessonId: id) ==
            LessonStatus.complete) {
          complete += 1;
        }
      }
    }

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text('You', style: Theme.of(context).textTheme.headlineLarge),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: NeuroColors.line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Progress', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(
                '$complete of $total lessons complete',
                style: Theme.of(
                  context,
                ).textTheme.bodyLarge?.copyWith(color: NeuroColors.muted),
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(99),
                child: LinearProgressIndicator(
                  value: total == 0 ? 0 : complete / total,
                  color: NeuroColors.moss,
                  backgroundColor: NeuroColors.sand,
                  minHeight: 8,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Text('About', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(
          'NeuroLearn is education software for BCI literacy. '
          'It is not a medical device and does not provide clinical training or advice. '
          'Lessons work offline from a bundled content pack.',
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: NeuroColors.muted),
        ),
        const SizedBox(height: 18),
        Text(
          'Course pack ${course.version}',
          style: Theme.of(
            context,
          ).textTheme.bodyMedium?.copyWith(color: NeuroColors.muted),
        ),
      ],
    );
  }
}
