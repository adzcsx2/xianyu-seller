import { rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';


const frontendDir = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const projectRoot = path.resolve(frontendDir, '..');
const defaultArtifactDir = path.resolve(projectRoot, 'logs', 'test-artifacts', 'frontend-static');
const outputDir = path.resolve(process.env.TEST_ARTIFACT_DIR || defaultArtifactDir);
const safeRoot = path.resolve(projectRoot, 'logs', 'test-artifacts');
const relativeOutput = path.relative(safeRoot, outputDir);

if (!relativeOutput || relativeOutput.startsWith('..') || path.isAbsolute(relativeOutput)) {
  throw new Error(`Refusing test build outside ${safeRoot}: ${outputDir}`);
}

await rm(outputDir, { recursive: true, force: true });
process.env.VITE_OUT_DIR = outputDir;
process.chdir(frontendDir);

const { build } = await import('vite');
await build({ root: frontendDir });

console.log(`Detached frontend build written to ${outputDir}`);
