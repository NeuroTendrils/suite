import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../data/content_repository.dart';
import '../models/content.dart';
import '../theme/app_theme.dart';
import '../sims/sim_registry.dart';
import 'content_image.dart';

class LessonBlockView extends StatelessWidget {
  const LessonBlockView({
    super.key,
    required this.block,
    required this.content,
    this.onSimComplete,
    this.compactTheory = false,
  });

  final LessonBlock block;
  final ContentRepository content;
  final VoidCallback? onSimComplete;
  final bool compactTheory;

  @override
  Widget build(BuildContext context) {
    return switch (block) {
      HookBlock(:final text) => compactTheory
          ? Text(
              text,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    height: 1.25,
                  ),
            )
          : _HookView(text: text),
      MarkdownBlock(:final markdown) => MarkdownBody(
          data: markdown,
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(context).textTheme.bodyLarge,
            strong: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
            listBullet: Theme.of(context).textTheme.bodyLarge,
          ),
        ),
      FigureBlock(:final src, :final alt, :final caption) => _FigureView(
          path: content.assetPathForFigure(src),
          alt: alt,
          caption: compactTheory ? null : caption,
          large: compactTheory,
        ),
      CalloutBlock(:final kind, :final text) => _CalloutView(
          kind: kind,
          text: text,
        ),
      SimBlock(:final id, :final goal) => buildSim(
          id: id,
          goal: goal,
          onComplete: onSimComplete,
        ),
      CheckBlock() => const SizedBox.shrink(),
    };
  }
}

class _HookView extends StatelessWidget {
  const _HookView({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(18, 20, 18, 20),
      decoration: BoxDecoration(
        color: NeuroColors.tide,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Text(
        text,
        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              color: Colors.white,
              height: 1.25,
            ),
      ),
    );
  }
}

class _FigureView extends StatelessWidget {
  const _FigureView({
    required this.path,
    required this.alt,
    this.caption,
    this.large = false,
  });

  final String path;
  final String alt;
  final String? caption;
  final bool large;

  @override
  Widget build(BuildContext context) {
    final height = large ? 220.0 : 180.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(large ? 24 : 16),
          child: ColoredBox(
            color: NeuroColors.sand,
            child: SizedBox(
              width: double.infinity,
              height: height,
              child: ContentImage(
                assetPath: path,
                semanticLabel: alt,
                fit: BoxFit.contain,
                height: height,
              ),
            ),
          ),
        ),
        if (caption != null) ...[
          const SizedBox(height: 8),
          Text(
            caption!,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: NeuroColors.muted,
                  fontStyle: FontStyle.italic,
                ),
          ),
        ],
      ],
    );
  }
}

class _CalloutView extends StatelessWidget {
  const _CalloutView({required this.kind, required this.text});
  final String kind;
  final String text;

  Color get _color => switch (kind) {
        'myth' => NeuroColors.myth,
        'limit' => NeuroColors.limit,
        'tip' => NeuroColors.tip,
        _ => NeuroColors.moss,
      };

  String get _label => switch (kind) {
        'myth' => 'Myth',
        'limit' => 'Limit',
        'tip' => 'Tip',
        'glossary' => 'Glossary',
        _ => kind,
      };

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border(left: BorderSide(color: _color, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _label.toUpperCase(),
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: _color,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8,
                ),
          ),
          const SizedBox(height: 6),
          Text(text, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}
