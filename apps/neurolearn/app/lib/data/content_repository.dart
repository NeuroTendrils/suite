import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/content.dart';

class ContentRepository {
  CoursePack? _pack;

  CoursePack get pack {
    final pack = _pack;
    if (pack == null) {
      throw StateError('Content pack not loaded');
    }
    return pack;
  }

  Course get course => pack.course;

  Future<CoursePack> load() async {
    if (_pack != null) return _pack!;
    final raw = await rootBundle.loadString(
      'assets/packs/bci-foundations/course.json',
    );
    _pack = CoursePack.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    return _pack!;
  }

  String assetPathForFigure(String src) {
    return 'assets/packs/bci-foundations/assets/$src';
  }
}
