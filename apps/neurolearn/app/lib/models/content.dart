class CoursePack {
  CoursePack({
    required this.schemaVersion,
    required this.course,
  });

  final int schemaVersion;
  final Course course;

  factory CoursePack.fromJson(Map<String, dynamic> json) {
    return CoursePack(
      schemaVersion: json['schemaVersion'] as int,
      course: Course.fromJson(json['course'] as Map<String, dynamic>),
    );
  }
}

class Course {
  Course({
    required this.id,
    required this.title,
    required this.version,
    required this.units,
    required this.lessons,
  });

  final String id;
  final String title;
  final String version;
  final List<Unit> units;
  final Map<String, Lesson> lessons;

  factory Course.fromJson(Map<String, dynamic> json) {
    final lessonsJson = json['lessons'] as Map<String, dynamic>;
    return Course(
      id: json['id'] as String,
      title: json['title'] as String,
      version: json['version'] as String,
      units: (json['units'] as List<dynamic>)
          .map((e) => Unit.fromJson(e as Map<String, dynamic>))
          .toList(),
      lessons: lessonsJson.map(
        (key, value) => MapEntry(
          key,
          Lesson.fromJson(value as Map<String, dynamic>),
        ),
      ),
    );
  }

  Lesson? lessonById(String id) => lessons[id];
}

class Unit {
  Unit({
    required this.id,
    required this.title,
    required this.section,
    required this.lessonIds,
  });

  final String id;
  final String title;
  final String section;
  final List<String> lessonIds;

  factory Unit.fromJson(Map<String, dynamic> json) {
    return Unit(
      id: json['id'] as String,
      title: json['title'] as String,
      section: json['section'] as String,
      lessonIds: (json['lessonIds'] as List<dynamic>)
          .map((e) => e as String)
          .toList(),
    );
  }
}

class Lesson {
  Lesson({
    required this.id,
    required this.title,
    required this.unit,
    required this.objective,
    required this.estMinutes,
    required this.blocks,
  });

  final String id;
  final String title;
  final String unit;
  final String objective;
  final int estMinutes;
  final List<LessonBlock> blocks;

  factory Lesson.fromJson(Map<String, dynamic> json) {
    return Lesson(
      id: json['id'] as String,
      title: json['title'] as String,
      unit: json['unit'] as String,
      objective: json['objective'] as String,
      estMinutes: json['estMinutes'] as int,
      blocks: (json['blocks'] as List<dynamic>)
          .map((e) => LessonBlock.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  bool get hasSim => blocks.any((b) => b is SimBlock);
}

sealed class LessonBlock {
  const LessonBlock();

  factory LessonBlock.fromJson(Map<String, dynamic> json) {
    switch (json['type'] as String) {
      case 'hook':
        return HookBlock(text: json['text'] as String);
      case 'markdown':
        return MarkdownBlock(markdown: json['markdown'] as String);
      case 'figure':
        return FigureBlock(
          src: json['src'] as String,
          alt: json['alt'] as String,
          caption: json['caption'] as String?,
        );
      case 'callout':
        return CalloutBlock(
          kind: json['kind'] as String,
          text: json['text'] as String,
        );
      case 'sim':
        return SimBlock(
          id: json['id'] as String,
          goal: json['goal'] as String,
        );
      case 'check':
        return CheckBlock(
          passScore: (json['passScore'] as num).toDouble(),
          items: (json['items'] as List<dynamic>)
              .map((e) => CheckItem.fromJson(e as Map<String, dynamic>))
              .toList(),
        );
      default:
        throw FormatException('Unknown block type: ${json['type']}');
    }
  }
}

class HookBlock extends LessonBlock {
  const HookBlock({required this.text});
  final String text;
}

class MarkdownBlock extends LessonBlock {
  const MarkdownBlock({required this.markdown});
  final String markdown;
}

class FigureBlock extends LessonBlock {
  const FigureBlock({
    required this.src,
    required this.alt,
    this.caption,
  });
  final String src;
  final String alt;
  final String? caption;
}

class CalloutBlock extends LessonBlock {
  const CalloutBlock({required this.kind, required this.text});
  final String kind;
  final String text;
}

class SimBlock extends LessonBlock {
  const SimBlock({required this.id, required this.goal});
  final String id;
  final String goal;
}

class CheckBlock extends LessonBlock {
  const CheckBlock({required this.passScore, required this.items});
  final double passScore;
  final List<CheckItem> items;
}

class CheckItem {
  CheckItem({
    required this.id,
    required this.prompt,
    required this.choices,
    this.explain,
  });

  final String id;
  final String prompt;
  final String? explain;
  final List<Choice> choices;

  factory CheckItem.fromJson(Map<String, dynamic> json) {
    return CheckItem(
      id: json['id'] as String,
      prompt: json['prompt'] as String,
      explain: json['explain'] as String?,
      choices: (json['choices'] as List<dynamic>)
          .map((e) => Choice.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class Choice {
  Choice({required this.text, required this.correct});
  final String text;
  final bool correct;

  factory Choice.fromJson(Map<String, dynamic> json) {
    return Choice(
      text: json['text'] as String,
      correct: json['correct'] as bool,
    );
  }
}

enum LessonStatus { locked, available, inProgress, complete }

class LessonProgress {
  LessonProgress({
    required this.lessonId,
    this.status = LessonStatus.available,
    this.bestScore,
    this.simCompleted = false,
    this.theoryCompleted = false,
  });

  final String lessonId;
  LessonStatus status;
  double? bestScore;
  bool simCompleted;
  bool theoryCompleted;

  Map<String, dynamic> toJson() => {
        'lessonId': lessonId,
        'status': status.name,
        'bestScore': bestScore,
        'simCompleted': simCompleted,
        'theoryCompleted': theoryCompleted,
      };

  factory LessonProgress.fromJson(Map<String, dynamic> json) {
    return LessonProgress(
      lessonId: json['lessonId'] as String,
      status: LessonStatus.values.firstWhere(
        (e) => e.name == json['status'],
        orElse: () => LessonStatus.available,
      ),
      bestScore: (json['bestScore'] as num?)?.toDouble(),
      simCompleted: json['simCompleted'] as bool? ?? false,
      theoryCompleted: json['theoryCompleted'] as bool? ?? false,
    );
  }
}
