import { readdir, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const schemaDirectory = join(root, "docs", "schemas");
const outputDirectory = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "src",
  "api",
  "generated",
);

await mkdir(outputDirectory, { recursive: true });

for (const fileName of (await readdir(schemaDirectory)).filter((name) =>
  name.endsWith(".json"),
)) {
  const schema = JSON.parse(
    await readFile(join(schemaDirectory, fileName), "utf8"),
  );
  const typeScript = await compile(schema, schema.title, {
    bannerComment: "/* Generated from docs/schemas. Do not edit by hand. */",
    style: { singleQuote: true },
  });
  const outputName = fileName.replace(/\.json$/, ".ts");
  await writeFile(join(outputDirectory, outputName), typeScript);
}
