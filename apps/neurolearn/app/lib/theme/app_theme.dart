import 'package:flutter/material.dart';

class NeuroColors {
  static const ink = Color(0xFF172B3A);
  static const moss = Color(0xFF557564);
  static const tide = Color(0xFF176BC1);
  static const deepBlue = Color(0xFF114A87);
  static const brainPink = Color(0xFFFFB8CB);
  static const brainWash = Color(0xFFFFF0F4);
  static const brainLine = Color(0xFFF0CDD8);
  static const brainRoute = Color(0xFFCC8FA7);
  static const signal = Color(0xFF19A9D4);
  static const blush = Color(0xFFF8E3E8);
  static const softTide = Color(0xFFEAF6FA);
  static const sand = Color(0xFFF0F4F6);
  static const mist = Color(0xFFF7F9FB);
  static const line = Color(0xFFD6E3E8);
  static const muted = Color(0xFF536676);
  static const clay = Color(0xFF6B4A2B);
  static const danger = Color(0xFFBA3535);
  static const myth = Color(0xFF79538A);
  static const limit = Color(0xFF8A5B15);
  static const tip = tide;
  static const locked = line;
}

/// Shared geometry for the learner shell and course track.
class NeuroLayout {
  static const contentWidth = 460.0;
  static const pagePadding = 20.0;
  static const surfaceRadius = 24.0;
  static const cardRadius = 16.0;
  static const gap = 16.0;
  static const motion = Duration(milliseconds: 150);
}

ThemeData buildNeuroTheme() {
  final base = ThemeData(
    useMaterial3: true,
    fontFamily: 'Source Sans 3',
    brightness: Brightness.light,
    colorScheme: ColorScheme.fromSeed(
      seedColor: NeuroColors.tide,
      brightness: Brightness.light,
      primary: NeuroColors.tide,
      onPrimary: Colors.white,
      secondary: NeuroColors.moss,
      surface: Colors.white,
      onSurface: NeuroColors.ink,
      onSurfaceVariant: NeuroColors.muted,
      outline: NeuroColors.muted,
      outlineVariant: NeuroColors.line,
    ),
    scaffoldBackgroundColor: NeuroColors.mist,
  );
  final body = base.textTheme;
  final label = body.labelLarge!.copyWith(
    fontSize: 15,
    fontWeight: FontWeight.w600,
  );
  return base.copyWith(
    textTheme: body.copyWith(
      displayMedium: const TextStyle(
        fontFamily: 'Source Sans 3',
        fontSize: 32,
        height: 1.15,
        fontWeight: FontWeight.w600,
        color: NeuroColors.ink,
      ),
      displaySmall: const TextStyle(
        fontFamily: 'Source Sans 3',
        fontSize: 28,
        height: 1.15,
        fontWeight: FontWeight.w600,
        color: NeuroColors.tide,
      ),
      headlineLarge: body.headlineLarge!.copyWith(
        fontSize: 30,
        height: 1.2,
        fontWeight: FontWeight.w700,
      ),
      titleLarge: body.titleLarge!.copyWith(
        fontSize: 20,
        height: 1.3,
        fontWeight: FontWeight.w600,
      ),
      bodyLarge: body.bodyLarge!.copyWith(fontSize: 17, height: 1.45),
      bodyMedium: body.bodyMedium!.copyWith(fontSize: 16, height: 1.4),
      labelLarge: label,
      labelMedium: body.labelMedium!.copyWith(
        fontSize: 14,
        fontWeight: FontWeight.w600,
      ),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: NeuroColors.mist,
      foregroundColor: NeuroColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      elevation: 0,
      indicatorColor: NeuroColors.softTide,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? NeuroColors.tide
              : NeuroColors.muted,
        ),
      ),
      labelTextStyle: WidgetStatePropertyAll(
        label.copyWith(color: NeuroColors.ink),
      ),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: Colors.white,
      indicatorColor: NeuroColors.softTide,
      selectedIconTheme: const IconThemeData(color: NeuroColors.tide),
      unselectedIconTheme: const IconThemeData(color: NeuroColors.muted),
      selectedLabelTextStyle: label.copyWith(color: NeuroColors.tide),
      unselectedLabelTextStyle: label.copyWith(color: NeuroColors.muted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(NeuroLayout.cardRadius),
        ),
        textStyle: label,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: NeuroColors.tide,
        minimumSize: const Size(48, 48),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        side: const BorderSide(color: NeuroColors.muted),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(NeuroLayout.cardRadius),
        ),
        textStyle: label,
      ),
    ),
  );
}
