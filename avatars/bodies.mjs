// Builds resident bodies from a recipe: MakeHuman exports become VRMs (convert.py), source VRMs are copied,
// then each is tinted (tint.mjs) into body-<key>.vrm and compressed (compress.mjs) into the recipe's ktx folder.
// usage: node bodies.mjs <recipe.json> [key ...]
// Recipe paths are relative to the recipe. A "makehuman" body needs mpfb-<key>.glb next to the recipe first:
// run mpfb_build.py in Blender with RECIPE and OUT set. Bodies marked "unused" are skipped unless named.
// Set BLENDER to the Blender binary when it isn't at the macOS default.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const blender = process.env.BLENDER ?? '/Applications/Blender.app/Contents/MacOS/Blender';
const [recipePath, ...only] = process.argv.slice(2);
const folder = path.dirname(path.resolve(recipePath));
const recipe = JSON.parse(fs.readFileSync(recipePath, 'utf8'));
const bones = recipe.bones === 'mpfb' ? JSON.parse(fs.readFileSync(path.join(here, 'mpfb_bones.json'), 'utf8')) : recipe.bones;
const ktx = path.join(folder, recipe.ktx ?? 'ktx');
fs.mkdirSync(ktx, { recursive: true });

for (const body of recipe.bodies) {
	if (only.length > 0 ? !only.includes(body.key) : body.unused) continue;
	const target = path.join(folder, `body-${body.key}.vrm`);
	if (body.makehuman) {
		const job = { source: path.join(folder, `mpfb-${body.key}.glb`), target, name: body.name ?? body.key, height: body.height, author: recipe.author ?? '', bones };
		const output = execFileSync(blender, ['-b', '-noaudio', '--python', path.join(here, 'convert.py'), '--', JSON.stringify(job)], { encoding: 'utf8', maxBuffer: 1 << 26 });
		if (!output.includes('RESULT')) throw new Error(`${body.key}: conversion failed\n${output.slice(-2000)}`);
	} else {
		fs.copyFileSync(path.join(folder, body.source), target);
	}
	if (body.tint) execFileSync('node', [path.join(here, 'tint.mjs'), target, target, JSON.stringify(body.tint)], { stdio: 'inherit' });
	execFileSync('node', [path.join(here, 'compress.mjs'), target, path.join(ktx, `body-${body.key}.vrm`)], { stdio: 'inherit' });
	console.log('built', body.key);
}
