import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'artifact_detective.dart';

/// Maps a `<Sim id="...">` reference in lesson content to a real widget.
///
/// The registry is deliberately closed: content can only reference simulations
/// that exist in this map. That is the same contract the API enforces on the
/// server (`REGISTERED_SIMS` in content/validate.py), so an author can never
/// publish a lesson pointing at a simulation the app cannot run.
///
/// Keep both lists in step when adding one.
typedef SimBuilder = Widget Function({VoidCallback? onComplete});

final Map<String, SimBuilder> simRegistry = <String, SimBuilder>{
  'artifact-detective': ({onComplete}) =>
      ArtifactDetective(onComplete: onComplete),
};

/// Resolve a simulation, or render an honest placeholder if it is not built.
///
/// An unbuilt simulation says so rather than pretending — a silent blank space
/// would leave the learner unsure whether the app is broken.
Widget buildSim({
  required String id,
  required String goal,
  VoidCallback? onComplete,
}) {
  final builder = simRegistry[id];
  if (builder != null) return builder(onComplete: onComplete);
  return _NotBuiltYet(id: id, goal: goal, onComplete: onComplete);
}

class _NotBuiltYet extends StatelessWidget {
  const _NotBuiltYet({
    required this.id,
    required this.goal,
    this.onComplete,
  });

  final String id;
  final String goal;
  final VoidCallback? onComplete;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: NeuroColors.sand,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Simulation coming soon', style: text.titleLarge),
          const SizedBox(height: 4),
          Text(id, style: text.labelLarge?.copyWith(color: NeuroColors.muted)),
          const SizedBox(height: 10),
          Text(goal, style: text.bodyLarge),
          const SizedBox(height: 14),
          FilledButton(
            onPressed: onComplete,
            child: const Text('Skip for now'),
          ),
        ],
      ),
    );
  }
}
