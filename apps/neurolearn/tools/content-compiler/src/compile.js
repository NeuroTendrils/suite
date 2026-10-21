import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import matter from "gray-matter";
import yaml from "js-yaml";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkMdx from "remark-mdx";
import { toString } from "mdast-util-to-string";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../..");
const courseDir = path.join(repoRoot, "content/courses/bci-foundations");
const outDir = path.join(repoRoot, "packs/bci-foundations");
const flutterPackDir = path.join(repoRoot, "app/assets/packs/bci-foundations");

const checkOnly = process.argv.includes("--check");

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

function readCourse() {
  const coursePath = path.join(courseDir, "course.yaml");
  if (!fs.existsSync(coursePath)) fail(`missing ${coursePath}`);
  return yaml.load(fs.readFileSync(coursePath, "utf8"));
}

function attrMap(node) {
  const attrs = {};
  for (const attr of node.attributes ?? []) {
    if (attr.type !== "mdxJsxAttribute") continue;
    if (typeof attr.value === "string") {
      attrs[attr.name] = attr.value;
    } else if (attr.value == null) {
      attrs[attr.name] = true;
    } else if (attr.value.type === "mdxJsxAttributeValueExpression") {
      const raw = attr.value.value.trim();
      if (raw === "true") attrs[attr.name] = true;
      else if (raw === "false") attrs[attr.name] = false;
      else if (!Number.isNaN(Number(raw))) attrs[attr.name] = Number(raw);
      else attrs[attr.name] = raw.replace(/^['"]|['"]$/g, "");
    }
  }
  return attrs;
}

function childText(node) {
  return toString(node).trim();
}

// Re-serialize inline formatting. `toString` alone drops **strong**,
// *emphasis* and `code`, so authored emphasis never reached the app.
function inlineMarkdown(node) {
  switch (node.type) {
    case "text":
      return node.value;
    case "strong":
      return `**${(node.children ?? []).map(inlineMarkdown).join("")}**`;
    case "emphasis":
      return `*${(node.children ?? []).map(inlineMarkdown).join("")}*`;
    case "inlineCode":
      return `\`${node.value}\``;
    case "break":
      return "\n";
    default:
      return node.children
        ? node.children.map(inlineMarkdown).join("")
        : toString(node);
  }
}

function inlineText(node) {
  return inlineMarkdown(node).trim();
}

function flattenMarkdown(nodes) {
  return nodes
    .map((n) => {
      if (n.type === "paragraph") return inlineText(n);
      if (n.type === "heading") return `${"#".repeat(n.depth)} ${inlineText(n)}`;
      if (n.type === "list") {
        return n.children
          .map((item, i) =>
            `${n.ordered ? `${(n.start ?? 1) + i}.` : "-"} ${inlineText(item)}`,
          )
          .join("\n");
      }
      return inlineText(n);
    })
    .filter(Boolean)
    .join("\n\n");
}

function walkJsx(node, name, out = []) {
  if (!node || typeof node !== "object") return out;
  if (
    (node.type === "mdxJsxFlowElement" || node.type === "mdxJsxTextElement") &&
    node.name === name
  ) {
    out.push(node);
  }
  for (const child of node.children ?? []) walkJsx(child, name, out);
  return out;
}

function parseChoice(node) {
  const attrs = attrMap(node);
  return {
    text: childText(node),
    correct: Object.prototype.hasOwnProperty.call(attrs, "correct")
      ? Boolean(attrs.correct)
      : false,
  };
}

function parseMcq(node) {
  const attrs = attrMap(node);
  if (!attrs.id) fail("MCQ missing id");
  if (!attrs.prompt) fail(`MCQ ${attrs.id} missing prompt`);
  const choices = walkJsx(node, "Choice").map(parseChoice);
  if (choices.length < 2) fail(`MCQ ${attrs.id} needs at least 2 choices`);
  if (!choices.some((c) => c.correct)) fail(`MCQ ${attrs.id} needs a correct choice`);
  return {
    type: "mcq",
    id: String(attrs.id),
    prompt: String(attrs.prompt),
    explain: attrs.explain ? String(attrs.explain) : undefined,
    choices,
  };
}

function parseCheck(node) {
  const attrs = attrMap(node);
  const passScore =
    typeof attrs.passScore === "number" ? attrs.passScore : 0.7;
  const items = walkJsx(node, "MCQ").map(parseMcq);
  if (items.length === 0) fail("Check needs at least one MCQ");
  return { type: "check", passScore, items };
}

function parseComponent(node) {
  const attrs = attrMap(node);
  switch (node.name) {
    case "Hook":
      return { type: "hook", text: childText(node) };
    case "Figure":
      if (!attrs.src || !attrs.alt) fail("Figure requires src and alt");
      return {
        type: "figure",
        src: String(attrs.src),
        alt: String(attrs.alt),
        caption: attrs.caption ? String(attrs.caption) : undefined,
      };
    case "Callout":
      if (!attrs.kind) fail("Callout requires kind");
      return {
        type: "callout",
        kind: String(attrs.kind),
        text: childText(node),
      };
    case "Sim":
      if (!attrs.id || !attrs.goal) fail("Sim requires id and goal");
      return {
        type: "sim",
        id: String(attrs.id),
        goal: String(attrs.goal),
      };
    case "Check":
      return parseCheck(node);
    default:
      fail(`unknown MDX component <${node.name}>`);
  }
}

function compileLessonMdx(source, filePath) {
  const { data, content } = matter(source);
  for (const key of ["id", "title", "unit", "objective", "estMinutes"]) {
    if (data[key] == null || data[key] === "") {
      fail(`${filePath}: missing front matter field "${key}"`);
    }
  }

  const tree = unified().use(remarkParse).use(remarkMdx).parse(content);
  const blocks = [];
  let markdownBuffer = [];

  const flushMarkdown = () => {
    if (markdownBuffer.length === 0) return;
    const markdown = flattenMarkdown(markdownBuffer).trim();
    markdownBuffer = [];
    if (markdown) blocks.push({ type: "markdown", markdown });
  };

  for (const node of tree.children) {
    if (node.type === "mdxJsxFlowElement") {
      flushMarkdown();
      blocks.push(parseComponent(node));
    } else if (
      node.type === "mdxjsEsm" ||
      node.type === "mdxFlowExpression"
    ) {
      fail(`${filePath}: unsupported MDX construct ${node.type}`);
    } else {
      markdownBuffer.push(node);
    }
  }
  flushMarkdown();

  if (blocks.length === 0) fail(`${filePath}: lesson has no blocks`);
  if (!blocks.some((b) => b.type === "check")) {
    fail(`${filePath}: lesson must include a <Check>`);
  }

  return {
    id: String(data.id),
    title: String(data.title),
    unit: String(data.unit),
    objective: String(data.objective),
    estMinutes: Number(data.estMinutes),
    blocks,
  };
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return;
  ensureDir(dest);
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(from, to);
    else fs.copyFileSync(from, to);
  }
}

function main() {
  const courseMeta = readCourse();
  const lessonsDir = path.join(courseDir, "lessons");
  const lessonFiles = fs
    .readdirSync(lessonsDir)
    .filter((f) => f.endsWith(".mdx"));

  const lessons = {};
  for (const file of lessonFiles) {
    const filePath = path.join(lessonsDir, file);
    const lesson = compileLessonMdx(fs.readFileSync(filePath, "utf8"), file);
    if (lessons[lesson.id]) fail(`duplicate lesson id ${lesson.id}`);
    lessons[lesson.id] = lesson;
  }

  const units = [];
  for (const unit of courseMeta.units) {
    for (const lessonId of unit.lessons) {
      if (!lessons[lessonId]) fail(`unit ${unit.id} references missing lesson ${lessonId}`);
      if (lessons[lessonId].unit !== unit.id) {
        fail(`lesson ${lessonId} unit front matter "${lessons[lessonId].unit}" != "${unit.id}"`);
      }
    }
    units.push({
      id: unit.id,
      title: unit.title,
      section: unit.section,
      lessonIds: unit.lessons,
    });
  }

  const pack = {
    schemaVersion: 1,
    course: {
      id: courseMeta.id,
      title: courseMeta.title,
      version: courseMeta.version,
      units,
      lessons,
    },
  };

  if (checkOnly) {
    console.log(`ok: ${Object.keys(lessons).length} lessons validated`);
    return;
  }

  fs.rmSync(outDir, { recursive: true, force: true });
  ensureDir(path.join(outDir, "lessons"));
  ensureDir(path.join(outDir, "assets"));
  fs.writeFileSync(
    path.join(outDir, "manifest.json"),
    JSON.stringify(
      {
        schemaVersion: pack.schemaVersion,
        courseId: pack.course.id,
        title: pack.course.title,
        version: pack.course.version,
        units: pack.course.units,
      },
      null,
      2,
    ) + "\n",
  );
  fs.writeFileSync(
    path.join(outDir, "course.json"),
    JSON.stringify(pack, null, 2) + "\n",
  );
  for (const lesson of Object.values(lessons)) {
    fs.writeFileSync(
      path.join(outDir, "lessons", `${lesson.id}.json`),
      JSON.stringify(lesson, null, 2) + "\n",
    );
  }
  copyDir(path.join(courseDir, "assets"), path.join(outDir, "assets"));

  // Mirror into Flutter assets
  fs.rmSync(flutterPackDir, { recursive: true, force: true });
  copyDir(outDir, flutterPackDir);

  console.log(
    `compiled ${Object.keys(lessons).length} lessons → ${path.relative(repoRoot, outDir)} and app assets`,
  );
}

main();
