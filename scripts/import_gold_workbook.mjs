import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, outputPath] = process.argv.slice(2);
if (!workbookPath || !outputPath) {
  throw new Error("Usage: import_gold_workbook.mjs WORKBOOK_XLSX OUTPUT_JSON");
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const records = [];
for (const year of [
  1998, 2000, 2001, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
  2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021,
]) {
  const sheet = workbook.worksheets.getItem(String(year));
  const used = sheet.getUsedRange(true);
  const values = used.values;
  if (!values?.length) continue;
  const headers = values[0].map((value) => String(value ?? ""));
  for (const row of values.slice(1)) {
    if (!row.some((value) => value !== null && value !== "")) continue;
    records.push(Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
  }
}
await fs.writeFile(outputPath, JSON.stringify(records, null, 2), "utf8");
