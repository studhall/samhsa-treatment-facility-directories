import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [sourcePath, outputPath, previewDir] = process.argv.slice(2);
if (!sourcePath || !outputPath || !previewDir) {
  throw new Error("Usage: build_gold_workbook.mjs SOURCE_JSON OUTPUT_XLSX PREVIEW_DIR");
}

const rows = JSON.parse(await fs.readFile(sourcePath, "utf8"));
const workbook = Workbook.create();
const instructions = workbook.worksheets.add("Instructions");
instructions.showGridLines = false;
instructions.getRange("A1").values = [["SAMHSA Historical Directory Gold Review"]];
instructions.getRange("A1:H1").format = {
  fill: "#0F4C5C",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  verticalAlignment: "center",
};
instructions.getRange("A3:B10").values = [
  ["Purpose", "Compare each parsed listing to the linked PDF page image."],
    ["Checks", "Use yes only when the parsed value is accurate; use no when a correction is needed; use uncertain when the PDF cannot resolve it."],
  ["Corrections", "Enter corrected values only when the parsed value is wrong."],
  ["Boundary errors", "Any boundary or column-bleed error requires a parser correction and reparse."],
  ["Unreviewable", "Mark checks uncertain and explain why in notes; the record will be replaced within its stratum."],
  ["Completion", "Set review_complete to yes only after all four checks are filled."],
  ["Reviewer", "Enter reviewer name or initials and reviewed_at as YYYY-MM-DD."],
  ["Source anchors", "Do not edit sample_id or source_anchor_id."],
];
instructions.getRange("A3:A10").format = {
  fill: "#DCEAF0",
  font: { bold: true, color: "#16343E" },
};
instructions.getRange("A3:B10").format.wrapText = true;
instructions.getRange("A:A").format.columnWidth = 22;
instructions.getRange("B:B").format.columnWidth = 86;
instructions.getRange("1:1").format.rowHeight = 30;

const headers = Object.keys(rows[0] ?? {});
const parsedStart = headers.indexOf("parsed_name1");
const rawStart = headers.indexOf("raw_record_text");
const reviewStart = headers.indexOf("corrected_name1");
const checkStart = headers.indexOf("name_check");

for (const year of [...new Set(rows.map((row) => row.directory_year))].sort()) {
  const sheet = workbook.worksheets.add(String(year));
  sheet.showGridLines = false;
  const yearRows = rows.filter((row) => row.directory_year === year);
  const values = [headers, ...yearRows.map((row) => headers.map((header) => row[header] ?? ""))];
  const range = sheet.getRangeByIndexes(0, 0, values.length, headers.length);
  range.values = values;
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(2);
  sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
    fill: "#0F4C5C",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRangeByIndexes(1, parsedStart, yearRows.length, rawStart - parsedStart).format.fill = "#E8F1F5";
  sheet.getRangeByIndexes(1, rawStart, yearRows.length, reviewStart - rawStart).format.fill = "#F2F2F2";
  sheet.getRangeByIndexes(1, reviewStart, yearRows.length, headers.length - reviewStart).format.fill = "#FFF4CC";
  sheet.getRangeByIndexes(0, 0, values.length, headers.length).format = {
    ...sheet.getRangeByIndexes(0, 0, values.length, headers.length).format,
    verticalAlignment: "top",
  };
  sheet.getRangeByIndexes(1, 0, yearRows.length, headers.length).format.wrapText = true;

  const pageImageColumn = headers.indexOf("page_image");
  for (let rowIndex = 0; rowIndex < yearRows.length; rowIndex += 1) {
    const image = yearRows[rowIndex].page_image;
    if (image) {
      const escaped = String(image).replaceAll('"', '""');
      sheet.getCell(rowIndex + 1, pageImageColumn).formulas = [[`=HYPERLINK("${escaped}","Open page image")`]];
    }
  }

  const validationRows = Math.max(yearRows.length, 1);
  for (const columnName of ["name_check", "address_check", "services_check", "boundary_check"]) {
    const columnIndex = headers.indexOf(columnName);
    sheet.getRangeByIndexes(1, columnIndex, validationRows, 1).dataValidation = {
      rule: { type: "list", values: ["yes", "no", "uncertain"] },
    };
  }
  const completeColumn = headers.indexOf("review_complete");
  sheet.getRangeByIndexes(1, completeColumn, validationRows, 1).dataValidation = {
    rule: { type: "list", values: ["yes", "no"] },
  };
  const checkRange = sheet.getRangeByIndexes(
    1,
    checkStart,
    validationRows,
    headers.length - checkStart,
  );
  checkRange.conditionalFormats.add("containsText", {
    text: "no",
    format: { fill: "#F8D7DA", font: { color: "#842029", bold: true } },
  });
  checkRange.conditionalFormats.add("containsText", {
    text: "uncertain",
    format: { fill: "#FFE69C", font: { color: "#664D03" } },
  });
  checkRange.conditionalFormats.add("containsText", {
    text: "yes",
    format: { fill: "#D1E7DD", font: { color: "#0F5132" } },
  });
  const table = sheet.tables.add(
    sheet.getRangeByIndexes(0, 0, values.length, headers.length),
    true,
    `Gold${year}`,
  );
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;

  const widths = {
    sample_id: 18,
    source_anchor_id: 23,
    listing_id_at_sampling: 20,
    directory_year: 11,
    survey_year: 11,
    source_pdf: 28,
    source_page: 10,
    source_column: 9,
    source_record_order: 11,
    sample_stratum: 20,
    page_quantile: 10,
    parsed_name1: 34,
    parsed_name2: 30,
    parsed_address1: 30,
    parsed_city: 20,
    parsed_state: 8,
    parsed_zip: 10,
    parsed_service_codes: 34,
    raw_record_text: 52,
    raw_service_text: 42,
    parser_warnings: 28,
    unknown_service_tokens: 26,
    page_image: 18,
    corrected_name1: 34,
    corrected_name2: 30,
    corrected_address1: 30,
    corrected_city: 20,
    corrected_state: 10,
    corrected_zip: 12,
    corrected_service_codes: 34,
    name_check: 12,
    address_check: 13,
    services_check: 13,
    boundary_check: 13,
    review_complete: 15,
    reviewer: 15,
    reviewed_at: 14,
    notes: 42,
  };
  headers.forEach((header, columnIndex) => {
    sheet.getRangeByIndexes(0, columnIndex, values.length, 1).format.columnWidth =
      widths[header] ?? 16;
  });
  sheet.getRange("1:1").format.rowHeight = 42;
  if (yearRows.length) {
    sheet.getRangeByIndexes(1, 0, yearRows.length, headers.length).format.rowHeight = 58;
  }
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["Instructions", ...[...new Set(rows.map((row) => String(row.directory_year)))].sort()]) {
  const preview = await workbook.render({
    sheetName,
    range: sheetName === "Instructions" ? "A1:B10" : "A1:Q12",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}${sheetName === "Instructions" ? "" : "-source"}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
  if (sheetName !== "Instructions") {
    const reviewPreview = await workbook.render({
      sheetName,
      range: "W1:AN12",
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      path.join(previewDir, `${sheetName}-review.png`),
      new Uint8Array(await reviewPreview.arrayBuffer()),
    );
  }
}
const check = await workbook.inspect({
  kind: "table",
  range: "Instructions!A1:B10",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 4,
});
console.log(check.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "gold workbook formula error scan",
});
console.log(errors.ndjson);
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
