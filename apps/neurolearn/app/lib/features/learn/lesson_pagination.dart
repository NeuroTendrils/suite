import '../../models/content.dart';

/// Split a lesson's theory blocks into pages, one page per markdown section.
///
/// A page starts at each `#` or `##` heading. Hooks, callouts, figures and
/// simulations stay on the page of the section they follow, so a sim sits
/// next to the instructions written for it. Check blocks are excluded; they
/// run on the practice screen.
List<List<LessonBlock>> paginateLesson(List<LessonBlock> blocks) {
  final pages = <List<LessonBlock>>[];
  var current = <LessonBlock>[];
  var hasSection = false;

  for (final block in blocks) {
    if (block is CheckBlock) continue;
    if (block is! MarkdownBlock) {
      current.add(block);
      continue;
    }
    for (final section in splitMarkdownSections(block.markdown)) {
      if (hasSection && _startsWithHeading(section)) {
        pages.add(current);
        current = <LessonBlock>[];
      }
      current.add(MarkdownBlock(markdown: section));
      hasSection = true;
    }
  }
  if (current.isNotEmpty) pages.add(current);
  return pages;
}

/// Split markdown at top- and second-level headings, keeping each heading
/// with the text below it.
List<String> splitMarkdownSections(String markdown) {
  final sections = <String>[];
  final buffer = <String>[];

  void flush() {
    final text = buffer.join('\n').trim();
    if (text.isNotEmpty) sections.add(text);
    buffer.clear();
  }

  for (final line in markdown.split('\n')) {
    if (_startsWithHeading(line)) flush();
    buffer.add(line);
  }
  flush();
  return sections;
}

bool _startsWithHeading(String text) =>
    text.startsWith('# ') || text.startsWith('## ');
