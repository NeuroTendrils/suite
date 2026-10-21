import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_theme.dart';

/// Loads pack/brand images. Supports PNG/JPEG via [Image.asset] and SVG via
/// [SvgPicture.asset]. Always takes explicit layout bounds from the parent.
class ContentImage extends StatelessWidget {
  const ContentImage({
    super.key,
    required this.assetPath,
    this.semanticLabel,
    this.fit = BoxFit.contain,
    this.width,
    this.height,
  });

  final String assetPath;
  final String? semanticLabel;
  final BoxFit fit;
  final double? width;
  final double? height;

  bool get _isSvg => assetPath.toLowerCase().endsWith('.svg');

  double? get _safeWidth =>
      width == null || width!.isInfinite || width!.isNaN ? null : width;

  double? get _safeHeight =>
      height == null || height!.isInfinite || height!.isNaN ? null : height;

  @override
  Widget build(BuildContext context) {
    if (_isSvg) {
      return SvgPicture.asset(
        assetPath,
        width: _safeWidth,
        height: _safeHeight,
        fit: fit,
        semanticsLabel: semanticLabel,
        placeholderBuilder: (_) => ColoredBox(
          color: NeuroColors.sand,
          child: SizedBox(
            width: _safeWidth,
            height: _safeHeight,
            child: const Center(
              child: SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          ),
        ),
      );
    }

    return Image.asset(
      assetPath,
      width: _safeWidth,
      height: _safeHeight,
      fit: fit,
      semanticLabel: semanticLabel,
      filterQuality: FilterQuality.medium,
      errorBuilder: (context, error, stackTrace) {
        return ColoredBox(
          color: NeuroColors.sand,
          child: SizedBox(
            width: _safeWidth,
            height: _safeHeight,
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  semanticLabel ?? 'Image unavailable',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: NeuroColors.muted,
                      ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
