import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/content.dart';

class ProgressRepository {
  ProgressRepository(this._prefs);

  final SharedPreferences _prefs;
  static const _key = 'neurolearn.progress.v1';
  static const _corruptKey = 'neurolearn.progress.v1.corrupt';
  final Map<String, LessonProgress> _byLesson = {};

  /// True when saved progress could not be read and the app started fresh.
  bool recoveredFromCorruption = false;

  Future<void> load() async {
    final raw = _prefs.getString(_key);
    if (raw == null) return;
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      final parsed = map.map(
        (key, value) => MapEntry(
          key,
          LessonProgress.fromJson(value as Map<String, dynamic>),
        ),
      );
      _byLesson
        ..clear()
        ..addAll(parsed);
    } catch (error) {
      // Unreadable progress must never stop the app from opening. Keep the
      // raw value aside so it can be inspected, then start fresh.
      debugPrint('NeuroLearn: discarding unreadable progress: $error');
      recoveredFromCorruption = true;
      _byLesson.clear();
      await _prefs.setString(_corruptKey, raw);
      await _prefs.remove(_key);
    }
  }

  LessonProgress progressFor(String lessonId) {
    return _byLesson.putIfAbsent(
      lessonId,
      () => LessonProgress(lessonId: lessonId),
    );
  }

  Future<void> markInProgress(String lessonId) async {
    final p = progressFor(lessonId);
    if (p.status != LessonStatus.complete) {
      p.status = LessonStatus.inProgress;
    }
    await _persist();
  }

  Future<void> markSimCompleted(String lessonId) async {
    progressFor(lessonId).simCompleted = true;
    await _persist();
  }

  Future<void> markTheoryCompleted(String lessonId) async {
    progressFor(lessonId).theoryCompleted = true;
    await _persist();
  }

  Future<void> recordCheckResult({
    required String lessonId,
    required double score,
    required bool passed,
  }) async {
    final p = progressFor(lessonId);
    final prev = p.bestScore;
    p.bestScore = prev == null ? score : (score > prev ? score : prev);
    if (passed) {
      p.status = LessonStatus.complete;
    } else if (p.status != LessonStatus.complete) {
      p.status = LessonStatus.inProgress;
    }
    await _persist();
  }

  LessonStatus statusForLesson({
    required Course course,
    required String lessonId,
  }) {
    final stored = _byLesson[lessonId];
    if (stored?.status == LessonStatus.complete) {
      return LessonStatus.complete;
    }
    if (stored?.status == LessonStatus.inProgress) {
      return LessonStatus.inProgress;
    }

    // Soft lock: first lesson always available; later lessons unlock after
    // previous unit's first lesson is complete, or any prior lesson complete.
    final ordered = <String>[
      for (final unit in course.units) ...unit.lessonIds,
    ];
    final index = ordered.indexOf(lessonId);
    if (index <= 0) return LessonStatus.available;

    final previousId = ordered[index - 1];
    final prev = _byLesson[previousId];
    if (prev?.status == LessonStatus.complete) {
      return LessonStatus.available;
    }
    // Soft lock still allows open — UI can warn. Keep available for MVP.
    return LessonStatus.available;
  }

  String? continueLessonId(Course course) {
    for (final unit in course.units) {
      for (final id in unit.lessonIds) {
        final status = statusForLesson(course: course, lessonId: id);
        if (status != LessonStatus.complete) return id;
      }
    }
    return course.units.isEmpty ? null : course.units.first.lessonIds.first;
  }

  Future<void> _persist() async {
    final encoded = jsonEncode(
      _byLesson.map((key, value) => MapEntry(key, value.toJson())),
    );
    await _prefs.setString(_key, encoded);
  }
}
