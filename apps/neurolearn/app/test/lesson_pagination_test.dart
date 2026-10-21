import 'package:flutter_test/flutter_test.dart';
import 'package:neurolearn/features/learn/lesson_pagination.dart';
import 'package:neurolearn/models/content.dart';

void main() {
  test('splits markdown at headings and keeps each heading with its text', () {
    expect(
      splitMarkdownSections('## One\n\nA\n\n## Two\n\nB'),
      ['## One\n\nA', '## Two\n\nB'],
    );
    expect(splitMarkdownSections('Intro only'), ['Intro only']);
    expect(splitMarkdownSections('### Small\n\ntext'), ['### Small\n\ntext']);
  });

  test('one page per section; extras stay with their section', () {
    const hook = HookBlock(text: 'hook');
    const tip = CalloutBlock(kind: 'tip', text: 'tip');
    const sim = SimBlock(id: 'artifact-detective', goal: 'goal');
    final pages = paginateLesson([
      hook,
      const MarkdownBlock(markdown: '## A\n\na'),
      tip,
      const MarkdownBlock(markdown: '## B\n\nb\n\n## C\n\nc'),
      sim,
      CheckBlock(passScore: 0.7, items: []),
    ]);

    expect(pages, hasLength(3));
    expect(pages[0].first, same(hook));
    expect(pages[0].last, same(tip));
    expect((pages[1].single as MarkdownBlock).markdown, '## B\n\nb');
    expect(pages[2].last, same(sim));
    expect(pages.expand((p) => p).whereType<CheckBlock>(), isEmpty);
  });

  test('text that continues after a callout stays on the same page', () {
    final pages = paginateLesson([
      const MarkdownBlock(markdown: '## A\n\na'),
      const CalloutBlock(kind: 'myth', text: 'm'),
      const MarkdownBlock(markdown: 'more about A'),
    ]);
    expect(pages, hasLength(1));
  });

  test('a lesson with no theory has no pages', () {
    expect(paginateLesson([CheckBlock(passScore: 1, items: [])]), isEmpty);
  });
}
