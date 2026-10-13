// Shrinks a GLB/VRM: every embedded PNG/JPEG texture becomes a mipmapped KTX2 (basisu) of at most MAX px a side.
// usage: node compress.mjs in.vrm out.vrm [max=1024]
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const [input, output, maxArg] = process.argv.slice(2);
const MAX = Number(maxArg ?? 1024);
const buffer = fs.readFileSync(input);
const jsonLength = buffer.readUInt32LE(12);
const json = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString('utf8'));
const bin = buffer.subarray(20 + jsonLength + 8, 20 + jsonLength + 8 + buffer.readUInt32LE(20 + jsonLength));
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'ktx-'));

const linearTextures = new Set();
for (const material of json.materials ?? []) {
	for (const key of ['normalTexture', 'occlusionTexture']) {
		if (material[key]) linearTextures.add(material[key].index);
	}
	const pbr = material.pbrMetallicRoughness;
	if (pbr?.metallicRoughnessTexture) linearTextures.add(pbr.metallicRoughnessTexture.index);
}
const normalImages = new Set();
const linearImages = new Set();
for (const material of json.materials ?? []) {
	if (material.normalTexture) normalImages.add(json.textures[material.normalTexture.index].source);
}
for (const index of linearTextures) linearImages.add(json.textures[index].source);

function dimensions(data, mime) {
	if (mime === 'image/png') return [data.readUInt32BE(16), data.readUInt32BE(20)];
	let offset = 2;
	while (offset < data.length) {
		const marker = data.readUInt16BE(offset);
		const length = data.readUInt16BE(offset + 2);
		if (marker >= 0xffc0 && marker <= 0xffc3) return [data.readUInt16BE(offset + 7), data.readUInt16BE(offset + 5)];
		offset += 2 + length;
	}
	return [0, 0];
}

function fit(size) {
	let side = 4;
	while (side * 2 <= Math.min(size, MAX)) side *= 2;
	return side;
}

const views = json.bufferViews.map((view) => bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength));
const report = [];
json.images?.forEach((image, index) => {
	if (image.bufferView === undefined || !['image/png', 'image/jpeg'].includes(image.mimeType)) return;
	const data = views[image.bufferView];
	const [width, height] = dimensions(data, image.mimeType);
	const source = path.join(work, `${index}.${image.mimeType === 'image/png' ? 'png' : 'jpg'}`);
	const target = path.join(work, `${index}.ktx2`);
	fs.writeFileSync(source, data);
	const args = ['-ktx2', '-mipmap', '-output_file', target, '-resample', String(fit(width)), String(fit(height))];
	if (normalImages.has(index)) args.push('-uastc', '-linear', '-normal_map');
	else if (linearImages.has(index)) args.push('-linear');
	execFileSync('basisu', [...args, source], { stdio: 'pipe' });
	views[image.bufferView] = fs.readFileSync(target);
	image.mimeType = 'image/ktx2';
	report.push(`${width}->${fit(width)}`);
});

for (const texture of json.textures ?? []) {
	if (json.images[texture.source]?.mimeType !== 'image/ktx2') continue;
	texture.extensions = { ...texture.extensions, KHR_texture_basisu: { source: texture.source } };
	delete texture.source;
}
for (const list of ['extensionsUsed', 'extensionsRequired']) {
	json[list] = [...new Set([...(json[list] ?? []), 'KHR_texture_basisu'])];
}

const chunks = [];
let offset = 0;
json.bufferViews.forEach((view, index) => {
	const padding = (8 - (offset % 8)) % 8;
	if (padding) chunks.push(Buffer.alloc(padding));
	offset += padding;
	view.byteOffset = offset;
	view.byteLength = views[index].length;
	chunks.push(views[index]);
	offset += views[index].length;
});
const binPadding = (4 - (offset % 4)) % 4;
if (binPadding) chunks.push(Buffer.alloc(binPadding));
const binChunk = Buffer.concat(chunks);
json.buffers = [{ byteLength: binChunk.length }];

let text = JSON.stringify(json);
while (text.length % 4) text += ' ';
const jsonChunk = Buffer.from(text);
const header = Buffer.alloc(12);
header.writeUInt32LE(0x46546c67, 0);
header.writeUInt32LE(2, 4);
header.writeUInt32LE(12 + 8 + jsonChunk.length + 8 + binChunk.length, 8);
const jsonHeader = Buffer.alloc(8);
jsonHeader.writeUInt32LE(jsonChunk.length, 0);
jsonHeader.writeUInt32LE(0x4e4f534a, 4);
const binHeader = Buffer.alloc(8);
binHeader.writeUInt32LE(binChunk.length, 0);
binHeader.writeUInt32LE(0x004e4942, 4);
fs.writeFileSync(output, Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binChunk]));
fs.rmSync(work, { recursive: true });
console.log(path.basename(output), `${Math.round(buffer.length / 1048576)}MB -> ${(fs.statSync(output).size / 1048576).toFixed(1)}MB`, report.length, 'textures');
