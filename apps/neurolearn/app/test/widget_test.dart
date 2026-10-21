import 'package:flutter_test/flutter_test.dart';

import 'package:neurolearn/models/content.dart';

void main() {
  test('CoursePack parses compiled JSON shape', () {
    final pack = CoursePack.fromJson({
      'schemaVersion': 1,
      'course': {
        'id': 'bci-foundations',
        'title': 'BCI Foundations',
        'version': '0.1.0',
        'units': [
          {
            'id': 'spark-01',
            'title': 'What is a BCI?',
            'section': 'spark',
            'lessonIds': ['spark-01-what-is-bci'],
          }
        ],
        'lessons': {
          'spark-01-what-is-bci': {
            'id': 'spark-01-what-is-bci',
            'title': 'What is a BCI?',
            'unit': 'spark-01',
            'objective': 'Define a BCI',
            'estMinutes': 8,
            'blocks': [
              {'type': 'hook', 'text': 'Hello'},
              {
                'type': 'check',
                'passScore': 0.7,
                'items': [
                  {
                    'type': 'mcq',
                    'id': 'q1',
                    'prompt': 'Prompt?',
                    'choices': [
                      {'text': 'A', 'correct': true},
                      {'text': 'B', 'correct': false},
                    ],
                  }
                ],
              }
            ],
          }
        },
      },
    });

    expect(pack.course.title, 'BCI Foundations');
    expect(pack.course.lessons['spark-01-what-is-bci']?.blocks.first, isA<HookBlock>());
  });
}
