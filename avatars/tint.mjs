// Recolours a VRM by multiplying chosen materials' base and shade colours; also renames it.
// usage: node tint.mjs list a.vrm ...            -> material names per file
//        node tint.mjs in.vrm out.vrm '<json>'   -> {"name": "...", "tints": [["regex", [r, g, b]], ...]}
import fs from 'node:fs';

function read(file) {
	const buffer = fs.readFileSync(file);
	const length = buffer.readUInt32LE(12);
	return { json: JSON.parse(buffer.subarray(20, 20 + length).toString('utf8')), rest: buffer.subarray(20 + length) };
}

function write(file, json, rest) {
	let text = JSON.stringify(json);
	while (text.length % 4) text += ' ';
	const chunk = Buffer.from(text);
	const header = Buffer.alloc(20);
	header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + chunk.length + rest.length, 8);
	header.writeUInt32LE(chunk.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
	fs.writeFileSync(file, Buffer.concat([header, chunk, rest]));
}

const [mode, ...args] = process.argv.slice(2);
if (mode === 'list') {
	for (const file of args) {
		const { json } = read(file);
		console.log(file.split('/').pop(), json.extensions?.VRMC_vrm ? 'vrm1' : 'vrm0', JSON.stringify((json.materials ?? []).map((m) => m.name)));
	}
	process.exit(0);
}

const [out, spec] = args;
const { json, rest } = read(mode);
const { name, tints = [], alpha = [] } = JSON.parse(spec);
let replacing = false;
const mix = (factor, colour) => (replacing ? [colour[0], colour[1], colour[2], factor[3] ?? 1] : [factor[0] * colour[0], factor[1] * colour[1], factor[2] * colour[2], factor[3] ?? 1]);
const hits = [];
for (const [pattern, colour, how] of tints) {
	const regex = new RegExp(pattern, 'i');
	replacing = how === 'set';
	json.materials.forEach((material, index) => {
		if (!regex.test(material.name ?? '')) return;
		hits.push(material.name);
		const pbr = (material.pbrMetallicRoughness ??= {});
		pbr.baseColorFactor = mix(pbr.baseColorFactor ?? [1, 1, 1, 1], colour);
		const mtoon = material.extensions?.VRMC_materials_mtoon;
		if (mtoon) mtoon.shadeColorFactor = mix(mtoon.shadeColorFactor ?? [1, 1, 1], colour).slice(0, 3);
		const legacy = json.extensions?.VRM?.materialProperties?.find((p) => p.name === material.name) ?? json.extensions?.VRM?.materialProperties?.[index];
		if (legacy?.vectorProperties) {
			for (const key of ['_Color', '_ShadeColor']) {
				if (legacy.vectorProperties[key]) legacy.vectorProperties[key] = mix(legacy.vectorProperties[key], colour);
			}
		}
	});
}
for (const material of json.materials ?? []) {
	const rule = alpha.find(([pattern]) => new RegExp(pattern, 'i').test(material.name ?? ''));
	if (!rule) continue;
	const [, mode, cutoff] = rule;
	material.alphaMode = mode;
	if (mode === 'MASK') material.alphaCutoff = cutoff ?? 0.5;
	else delete material.alphaCutoff;
}
if (name) {
	if (json.extensions?.VRMC_vrm?.meta) json.extensions.VRMC_vrm.meta.name = name;
	if (json.extensions?.VRM?.meta) json.extensions.VRM.meta.title = name;
}
write(out, json, rest);
console.log('tinted', out.split('/').pop(), JSON.stringify(hits));
