#!/usr/bin/env node

/**
 * AdNova 광고 레퍼런스를 무드, 포맷, 사물 연출로 재분류한다.
 * 원본을 건드리지 않고 하드링크를 만들며, 불가능하면 파일 복사로 폴백한다.
 */

import fs from "node:fs";
import path from "node:path";

const [sourceRoot, corpusPath, outputRoot] = process.argv.slice(2);
if (!sourceRoot || !corpusPath || !outputRoot) {
  console.error("사용법: node build_reference_library.mjs <광고레퍼런스> <design_corpus.jsonl> <출력폴더>");
  process.exit(2);
}

const STYLE_MAP = {
  "01_에디토리얼": "editorial",
  "02_팝_pop": "pop",
  "03_리얼리즘": "realism",
  "04_파스텔": "pastel",
  "05_모노톤": "monotone",
  "06_웜빈티지": "warm_organic",
};

const normalize = (value) => value.normalize("NFC").toLowerCase();
const slug = (value) => value.replaceAll(/[\\/:*?"<>|]/g, "_");
const textOf = (row) => [
  row.subject,
  row.composition,
  row.lighting,
  ...(row.style_tokens || []),
  ...(row.colors || []),
].filter(Boolean).join(" ").toLowerCase();

function findDirectory(prefix) {
  return fs.readdirSync(sourceRoot, { withFileTypes: true })
    .find((entry) => entry.isDirectory() && normalize(entry.name).startsWith(normalize(prefix)))?.name;
}

function fileIndex(directory) {
  const result = new Map();
  if (!directory) return result;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.isFile()) result.set(normalize(entry.name), path.join(directory, entry.name));
  }
  return result;
}

const croppedDir = path.join(sourceRoot, findDirectory("_크롭됨") || "_크롭됨");
const objectDir = path.join(sourceRoot, findDirectory("10_") || "10_사물_최신");
const guideDir = path.join(sourceRoot, findDirectory("11_") || "11_사물_가이드");
const croppedFiles = fileIndex(croppedDir);
const objectFiles = fileIndex(objectDir);

function domainFor(row) {
  const t = textOf(row);
  // 음식 장면에 손이나 사람이 등장해도 패션으로 분류하지 않는다.
  if (/\b(food|meat|beef|pork|chicken|rice|noodles?|dish|plate|bread|cake|dessert|tart|olive|egg|melon|steak|ribs?|omelet|seafood|soup|pot|grill|fried|cooking)\b/.test(t)) return "food";
  if (/\b(coffee|latte|drink|beverage|tea|juice|cup|mug)\b/.test(t)) return "drink";
  if (/\b(serum|cosmetic|skincare|cream|lip|nail|perfume|shampoo|conditioner|ampoule|makeup|cleanser)\b/.test(t)) return "beauty";
  if (/\b(handbag|shoe|sneaker|glasses|sunglasses|shirt|clothing|fashion|jacket|boots?)\b/.test(t)) return "fashion";
  if (/interior|sofa|chair|room|furniture/.test(t)) return "interior";
  return "general_object";
}

function styleArchetype(style, row) {
  const t = textOf(row);
  switch (style) {
    case "editorial":
      if (/top-down|grid|side by side|multiple|arranged/.test(t)) return "01_story_grid";
      if (/hand|pour|held|droplet|close-up/.test(t)) return "02_action_detail";
      if (row.text_space && row.text_space !== "none") return "03_asymmetric_copyspace";
      return "04_clean_hero";
    case "pop":
      if (/tennis|sport|court|ball|racket|locker|dynamic/.test(t)) return "01_sports_concept";
      if (/dessert|tart|macaron|pudding|cake|custard|jelly|ice cream/.test(t)) return "02_food_metaphor";
      if (/floating|levitat|mid-air|splash/.test(t)) return "03_dynamic_float";
      return "04_saturated_color_block";
    case "realism":
      if (/raw|uncooked|marbling/.test(t)) return "01_raw_texture";
      if (/hand|pour|cook|steam|grill|cutting|action/.test(t)) return "02_cooking_action";
      if (/close-up|macro/.test(t)) return "03_macro_texture";
      if (/top-down|multiple|spread|arranged/.test(t)) return "04_table_spread";
      return "05_food_hero";
    case "pastel":
      if (/interior|sofa|chair|room|furniture/.test(t)) return "01_soft_lifestyle";
      if (/floating|levitat|dream|cloud|mist/.test(t)) return "02_dreamy_float";
      if (/pedestal|geometric|platform|shape/.test(t)) return "03_soft_pedestal";
      return "04_pastel_product_hero";
    case "monotone":
      {
        const colors = (row.colors || []).join(" ").toLowerCase();
        if (/black|dark|navy/.test(colors)) return "01_dark_color_lock";
        if (/red|orange|green|blue|yellow|pink|purple/.test(colors)) return "03_brand_color_lock";
        if (/white|beige|cream|gray|grey|pale/.test(colors)) return "02_pale_color_lock";
      }
      return "03_brand_color_lock";
    case "warm_organic":
      if (/gift|wrapped|linen|fabric|cloth|knot/.test(t)) return "01_linen_gift";
      if (/coffee|food|plate|table|cup/.test(t)) return "02_warm_tabletop";
      if (/close-up|macro|texture|foam|drop/.test(t)) return "03_organic_macro";
      return "04_neutral_stilllife";
    default:
      return "unclassified";
  }
}

function objectArchetype(row) {
  const t = textOf(row);
  if (/woman|man |person|model|wearing|held|holding|hand /.test(t)) return "01_lifestyle_editorial";
  if (/ice|water|foam|bubble|liquid|splash|sand|smoke|flower|fruit|food|dessert|tart/.test(t)) return "02_material_metaphor";
  if (/floating|levitat|mid-air|suspended/.test(t)) return "03_dynamic_float";
  if (/close-up|macro|extreme close/.test(t)) return "04_macro_texture";
  if (/set of|several|multiple|two |three |group/.test(t)) return "05_product_group";
  if (/minimalist|platform|pedestal|centered|studio/.test(t)) return "06_minimal_studio";
  return "07_commercial_hero";
}

function resolveImage(row) {
  if (row.source === "style_ref") return croppedFiles.get(normalize(row.image));
  const wanted = normalize(row.image);
  return objectFiles.get(wanted)
    || objectFiles.get(wanted.replace(/\.png$/, ".jpg"))
    || objectFiles.get(wanted.replace(/\.jpg$/, ".png"));
}

function linkFile(source, destination) {
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  if (fs.existsSync(destination)) return;
  try {
    fs.linkSync(source, destination);
  } catch {
    fs.copyFileSync(source, destination);
  }
}

function libraryPlacement(row) {
  const folder = normalize(row.style_folder || "");
  const styleEntry = Object.entries(STYLE_MAP).find(([prefix]) => folder.startsWith(normalize(prefix)));
  if (styleEntry) {
    const style = styleEntry[1];
    return { layer: "mood", style, archetype: styleArchetype(style, row) };
  }
  if (folder.startsWith("07_")) return { layer: "format", style: "summer_split", archetype: "01_equal_split" };
  if (folder.startsWith("08_")) return { layer: "format", style: "typography", archetype: "01_lettering_reference" };
  if (folder.startsWith("09_")) return { layer: "format", style: "closeup", archetype: "01_closeup_overlay" };
  if (row.source === "sku") return { layer: "object", style: "object_scene", archetype: objectArchetype(row) };
  return { layer: "review", style: "unclassified", archetype: "unclassified" };
}

function outputDirectory(placement) {
  if (placement.layer === "mood") return path.join("01_스타일무드", placement.style, placement.archetype);
  if (placement.layer === "format") return path.join("02_구도포맷", placement.style, placement.archetype);
  if (placement.layer === "object") return path.join("03_사물연출", placement.archetype);
  return path.join("90_검토필요", placement.archetype);
}

if (fs.existsSync(outputRoot)) {
  const marker = path.join(outputRoot, "README.md");
  const isGeneratedLibrary = fs.existsSync(marker)
    && fs.readFileSync(marker, "utf8").startsWith("# AdNova 광고 레퍼런스 v3 재분류본");
  if (!isGeneratedLibrary) throw new Error(`기존 폴더를 덮어쓸 수 없습니다: ${outputRoot}`);
  fs.rmSync(outputRoot, { recursive: true });
}
fs.mkdirSync(outputRoot, { recursive: true });
const rows = fs.readFileSync(corpusPath, "utf8").split(/\r?\n/).filter(Boolean).map(JSON.parse);
const manifest = [];
const missing = [];

for (const row of rows) {
  const source = resolveImage(row);
  if (!source) {
    missing.push(row.image);
    continue;
  }
  const placement = libraryPlacement(row);
  const relDir = outputDirectory(placement);
  const filename = slug(row.image.replace(/\.png$/i, path.extname(source)));
  const destination = path.join(outputRoot, relDir, filename);
  linkFile(source, destination);

  const isSkuScreenshot = row.source === "sku";
  const qualityTier = isSkuScreenshot ? "R" : row.tier;
  manifest.push({
    id: path.parse(row.image).name,
    image: filename,
    library_path: path.relative(outputRoot, destination),
    source_path: source,
    source: row.source,
    layer: placement.layer,
    style: placement.style,
    archetype: placement.archetype,
    domain: domainFor(row),
    quality_tier: qualityTier,
    original_tier: row.tier,
    training_eligible: qualityTier === "A" && placement.layer === "mood",
    reference_eligible: placement.layer !== "review",
    quality_note: isSkuScreenshot
      ? "인스타그램 UI가 포함된 원본. 검색·기획 참고용이며 크롭 전 학습 금지"
      : qualityTier === "B" ? "UI 또는 텍스트 잔재가 있어 생성 학습 제외" : "정제된 스타일 레퍼런스",
    identity_risk: /logo|label|text|brand/.test(textOf(row)) ? "high" : "medium",
    subject: row.subject,
    lighting: row.lighting,
    composition: row.composition,
    text_space: row.text_space,
    style_tokens: row.style_tokens,
    colors: row.colors,
    designer_text_regions: row.designer_text_regions || [],
  });
}

const guideFiles = fs.existsSync(guideDir)
  ? fs.readdirSync(guideDir, { withFileTypes: true }).filter((entry) => entry.isFile() && /\.(png|jpe?g)$/i.test(entry.name))
  : [];
for (const entry of guideFiles) {
  const source = path.join(guideDir, entry.name);
  const destination = path.join(outputRoot, "91_디자인가이드_학습금지", entry.name);
  linkFile(source, destination);
}

const manifestPath = path.join(outputRoot, "reference_manifest.jsonl");
fs.writeFileSync(manifestPath, manifest.map((row) => JSON.stringify(row)).join("\n") + "\n");

const csvColumns = ["id", "library_path", "layer", "style", "archetype", "domain", "quality_tier", "training_eligible", "reference_eligible", "identity_risk"];
const csvValue = (value) => `"${String(value).replaceAll('"', '""')}"`;
fs.writeFileSync(
  path.join(outputRoot, "reference_manifest.csv"),
  [csvColumns.join(","), ...manifest.map((row) => csvColumns.map((column) => csvValue(row[column])).join(","))].join("\n") + "\n",
);

const counts = manifest.reduce((acc, row) => {
  const key = `${row.layer}/${row.style}/${row.archetype}`;
  acc[key] = (acc[key] || 0) + 1;
  return acc;
}, {});
const countLines = Object.entries(counts).sort().map(([key, count]) => `- ${key}: ${count}장`).join("\n");
const readme = `# AdNova 광고 레퍼런스 v3 재분류본\n\n원본 폴더는 변경하지 않았다. 이미지 파일은 원본과 하드링크되어 디스크를 중복 사용하지 않으며, 하드링크가 불가능한 경우에만 복사한다.\n\n## 계층\n\n- \`01_스타일무드\`: 6개 사용자 스타일. 생성 시 색, 조명, 소재 분위기를 결정한다.\n- \`02_구도포맷\`: 스플릿, 타이포, 클로즈업처럼 스타일과 독립적인 레이아웃 규칙이다.\n- \`03_사물연출\`: 상품 형태에 맞춰 고르는 사물 광고 장면 아키타입이다.\n- \`91_디자인가이드_학습금지\`: 조판 규칙 참고 자료. 생성 학습이나 이미지 검색 후보에 넣지 않는다.\n\n## 티어\n\n- A: 정제된 스타일 레퍼런스. 무드 검색과 제한적인 학습에 사용 가능.\n- B: UI 또는 텍스트 잔재가 있어 검색·평가 참고만 가능.\n- R: 사물 기획 참고용. 현재 원본이 인스타그램 전체 스크린샷이므로 콘텐츠 크롭 전 학습 금지.\n- G: 디자인 원칙 문서. 이미지 생성 데이터로 사용 금지.\n\n## 사용 규칙\n\n1. 먼저 domain과 상품 형태로 호환 가능한 아키타입을 고른다.\n2. mood와 format을 독립적으로 선택한다. 예: pop + equal_split.\n3. 생성 저지는 같은 style_folder 전체가 아니라 선택한 아키타입의 레퍼런스 2~3장과 비교한다.\n4. identity_risk=high인 레퍼런스는 구도와 조명만 참고하고 로고·제품 형태는 모사하지 않는다.\n5. training_eligible=false인 이미지는 LoRA나 이미지 어댑터 학습에 넣지 않는다.\n\n## 분류 결과\n\n${countLines}\n\n## 누락\n\n${missing.length ? missing.map((name) => `- ${name}`).join("\n") : "- 없음"}\n`;
fs.writeFileSync(path.join(outputRoot, "README.md"), readme);

const cards = manifest.map((row) => `
  <article data-layer="${row.layer}" data-style="${row.style}" data-domain="${row.domain}" data-tier="${row.quality_tier}">
    <img loading="lazy" src="${encodeURI(row.library_path)}" alt="${row.id}">
    <strong>${row.style} / ${row.archetype}</strong>
    <span>${row.domain} · Tier ${row.quality_tier}</span>
  </article>`).join("");
fs.writeFileSync(path.join(outputRoot, "gallery.html"), `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AdNova Reference Library</title><style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:24px;background:#f5f5f3;color:#161616}h1{font-size:24px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}article{background:#fff;border:1px solid #ddd;padding:8px}img{width:100%;height:210px;object-fit:contain;background:#eee}strong,span{display:block;margin-top:6px;font-size:12px}span{color:#666}</style></head><body><h1>AdNova Reference Library v3</h1><p>${manifest.length}장 · 무드/포맷/사물 연출 재분류</p><section class="grid">${cards}</section></body></html>`);

console.log(JSON.stringify({ outputRoot, records: manifest.length, guides: guideFiles.length, missing }, null, 2));
