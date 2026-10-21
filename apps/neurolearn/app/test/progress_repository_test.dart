import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/data/progress_repository.dart';
import 'package:neurolearn/models/content.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const key = 'neurolearn.progress.v1';

  Future<ProgressRepository> loadWith(Map<String, Object> values) async {
    SharedPreferences.setMockInitialValues(values);
    final repo = ProgressRepository(await SharedPreferences.getInstance());
    await repo.load();
    return repo;
  }

  test('unreadable progress starts fresh instead of crashing', () async {
    final repo = await loadWith({key: '{not json'});
    expect(repo.recoveredFromCorruption, isTrue);
    expect(repo.progressFor('a').status, LessonStatus.available);

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString(key), isNull);
    expect(prefs.getString('$key.corrupt'), '{not json');
  });

  test('wrongly shaped progress also starts fresh', () async {
    final repo = await loadWith({key: '[1, 2, 3]'});
    expect(repo.recoveredFromCorruption, isTrue);
  });

  test('progress saved before theory tracking still loads', () async {
    final repo = await loadWith({
      key: '{"a":{"lessonId":"a","status":"complete","bestScore":0.75,'
          '"simCompleted":false}}',
    });
    final p = repo.progressFor('a');
    expect(p.status, LessonStatus.complete);
    expect(p.bestScore, 0.75);
    expect(p.theoryCompleted, isFalse);
    expect(repo.recoveredFromCorruption, isFalse);
  });

  test('theory completion and best score persist across reloads', () async {
    final repo = await loadWith({});
    await repo.markTheoryCompleted('a');
    await repo.recordCheckResult(lessonId: 'a', score: 0.5, passed: false);
    await repo.recordCheckResult(lessonId: 'a', score: 0.25, passed: false);

    final reloaded =
        ProgressRepository(await SharedPreferences.getInstance());
    await reloaded.load();
    final p = reloaded.progressFor('a');
    expect(p.theoryCompleted, isTrue);
    expect(p.bestScore, 0.5);
    expect(p.status, LessonStatus.inProgress);
  });
}
