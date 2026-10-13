// Makes the low-detail version of a VRM: meshes simplified to a triangle budget, morph targets and the
// expression binds that use them removed, textures shrunk and stored as KTX2. The skeleton, skinning,
// humanoid mapping, materials and metadata are kept, so the same poses and animations play on it.
// usage: node lod.mjs in.vrm out.vrm [--triangles 12000] [--error 0.005] [--max 256]
// --error caps how far any mesh may drift from its shape, as a fraction of its size; it wins over --triangles.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { MeshoptSimplifier } from 'meshoptimizer';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const option = (name, fallback) => {
	const index = args.indexOf(`--${name}`);
	return index === -1 ? fallback : Number(args[index + 1]);
};
const [input, output] = args.filter((arg, index) => !arg.startsWith('--') && !args[index - 1]?.startsWith('--'));
const TRIANGLES = option('triangles', 12000);
const MAX = option('max', 256);
const ERROR = option('error', 0.005);

const COMPONENT_BYTES = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
const COMPONENT_ARRAYS = { 5120: Int8Array, 5121: Uint8Array, 5122: Int16Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };
const TYPE_SIZE = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };

const buffer = fs.readFileSync(input);
const jsonLength = buffer.readUInt32LE(12);
const json = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString('utf8'));
const bin = buffer.subarray(20 + jsonLength + 8, 20 + jsonLength + 8 + buffer.readUInt32LE(20 + jsonLength));
const views = json.bufferViews.map((view) => bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength));

function readAccessor(index) {
	const accessor = json.accessors[index];
	const size = TYPE_SIZE[accessor.type];
	const bytes = COMPONENT_BYTES[accessor.componentType];
	const Values = COMPONENT_ARRAYS[accessor.componentType];
	const out = new Values(accessor.count * size);
	if (accessor.bufferView === undefined) return out;
	const view = json.bufferViews[accessor.bufferView];
	const data = views[accessor.bufferView];
	const stride = view.byteStride ?? size * bytes;
	const reader = new DataView(data.buffer, data.byteOffset, data.byteLength);
	const read = {
		5120: (at) => reader.getInt8(at),
		5121: (at) => reader.getUint8(at),
		5122: (at) => reader.getInt16(at, true),
		5123: (at) => reader.getUint16(at, true),
		5125: (at) => reader.getUint32(at, true),
		5126: (at) => reader.getFloat32(at, true),
	}[accessor.componentType];
	for (let element = 0; element < accessor.count; element++) {
		for (let component = 0; component < size; component++) {
			out[element * size + component] = read((accessor.byteOffset ?? 0) + element * stride + component * bytes);
		}
	}
	return out;
}

function addAccessor(template, values, count, extra = {}) {
	views.push(Buffer.from(values.buffer, values.byteOffset, values.byteLength));
	json.bufferViews.push({ buffer: 0, byteLength: values.byteLength, ...(extra.target ? { target: extra.target } : {}) });
	const accessor = { bufferView: json.bufferViews.length - 1, componentType: extra.componentType ?? template.componentType, count, type: template.type };
	if (template.normalized) accessor.normalized = true;
	if (extra.bounds) Object.assign(accessor, extra.bounds);
	json.accessors.push(accessor);
	return json.accessors.length - 1;
}

function bounds(values, size) {
	const min = new Array(size).fill(Infinity);
	const max = new Array(size).fill(-Infinity);
	for (let index = 0; index < values.length; index++) {
		const component = index % size;
		min[component] = Math.min(min[component], values[index]);
		max[component] = Math.max(max[component], values[index]);
	}
	return { min, max };
}

// ---------- geometry ----------

await MeshoptSimplifier.ready;
const triangleCount = (primitive) => (primitive.indices !== undefined ? json.accessors[primitive.indices].count : json.accessors[primitive.attributes.POSITION].count) / 3;
const primitives = (json.meshes ?? []).flatMap((mesh) => mesh.primitives.filter((primitive) => (primitive.mode ?? 4) === 4));
const before = primitives.reduce((sum, primitive) => sum + triangleCount(primitive), 0);
const ratio = Math.min(1, TRIANGLES / before);

for (const mesh of json.meshes ?? []) {
	delete mesh.weights;
	if (mesh.extras) delete mesh.extras.targetNames;
	const groups = new Map();
	for (const primitive of mesh.primitives) {
		delete primitive.targets;
		if (primitive.extras) delete primitive.extras.targetNames;
		if ((primitive.mode ?? 4) !== 4) continue;
		const key = JSON.stringify(primitive.attributes);
		if (!groups.has(key)) groups.set(key, []);
		groups.get(key).push(primitive);
	}
	for (const group of groups.values()) {
		const attributes = group[0].attributes;
		const positions = Float32Array.from(readAccessor(attributes.POSITION));
		const vertexCount = positions.length / 3;
		const simplified = group.map((primitive) => {
			const indices = primitive.indices !== undefined ? Uint32Array.from(readAccessor(primitive.indices)) : Uint32Array.from({ length: vertexCount }, (_, index) => index);
			const target = Math.max(3, Math.floor((indices.length * ratio) / 3) * 3);
			const [result] = MeshoptSimplifier.simplify(indices, positions, 3, target, ERROR, ['LockBorder']);
			return result;
		});

		const remap = new Int32Array(vertexCount).fill(-1);
		let used = 0;
		for (const indices of simplified) {
			for (const vertex of indices) {
				if (remap[vertex] === -1) remap[vertex] = used++;
			}
		}
		const newAttributes = {};
		for (const [name, accessorIndex] of Object.entries(attributes)) {
			const template = json.accessors[accessorIndex];
			const size = TYPE_SIZE[template.type];
			const source = readAccessor(accessorIndex);
			const compacted = new source.constructor(used * size);
			for (let vertex = 0; vertex < vertexCount; vertex++) {
				if (remap[vertex] === -1) continue;
				compacted.set(source.subarray(vertex * size, vertex * size + size), remap[vertex] * size);
			}
			newAttributes[name] = addAccessor(template, compacted, used, { target: 34962, bounds: name === 'POSITION' ? bounds(compacted, 3) : null });
		}
		group.forEach((primitive, index) => {
			const Indices = used > 65535 ? Uint32Array : Uint16Array;
			const indices = Indices.from(simplified[index], (vertex) => remap[vertex]);
			primitive.attributes = { ...newAttributes };
			primitive.indices = addAccessor({ type: 'SCALAR' }, indices, indices.length, { target: 34963, componentType: used > 65535 ? 5125 : 5123 });
		});
	}
}
const after = primitives.reduce((sum, primitive) => sum + triangleCount(primitive), 0);

const vrm1 = json.extensions?.VRMC_vrm?.expressions;
for (const expression of [...Object.values(vrm1?.preset ?? {}), ...Object.values(vrm1?.custom ?? {})]) {
	delete expression.morphTargetBinds;
}
for (const group of json.extensions?.VRM?.blendShapeMaster?.blendShapeGroups ?? []) {
	group.binds = [];
}

// ---------- unreferenced accessors and buffer views ----------

const keptAccessors = new Set();
for (const mesh of json.meshes ?? []) {
	for (const primitive of mesh.primitives) {
		Object.values(primitive.attributes).forEach((index) => keptAccessors.add(index));
		if (primitive.indices !== undefined) keptAccessors.add(primitive.indices);
	}
}
for (const skin of json.skins ?? []) {
	if (skin.inverseBindMatrices !== undefined) keptAccessors.add(skin.inverseBindMatrices);
}
for (const animation of json.animations ?? []) {
	for (const sampler of animation.samplers) {
		keptAccessors.add(sampler.input);
		keptAccessors.add(sampler.output);
	}
}
const accessorMap = new Map();
json.accessors = json.accessors.filter((_, index) => keptAccessors.has(index) && accessorMap.set(index, accessorMap.size));
const remapAccessor = (index) => accessorMap.get(index);
for (const mesh of json.meshes ?? []) {
	for (const primitive of mesh.primitives) {
		primitive.attributes = Object.fromEntries(Object.entries(primitive.attributes).map(([name, index]) => [name, remapAccessor(index)]));
		if (primitive.indices !== undefined) primitive.indices = remapAccessor(primitive.indices);
	}
}
for (const skin of json.skins ?? []) {
	if (skin.inverseBindMatrices !== undefined) skin.inverseBindMatrices = remapAccessor(skin.inverseBindMatrices);
}
for (const animation of json.animations ?? []) {
	for (const sampler of animation.samplers) {
		sampler.input = remapAccessor(sampler.input);
		sampler.output = remapAccessor(sampler.output);
	}
}

const keptViews = new Set([...json.accessors.map((accessor) => accessor.bufferView), ...(json.images ?? []).map((image) => image.bufferView)].filter((index) => index !== undefined));
const viewMap = new Map();
const keptViewData = [];
json.bufferViews = json.bufferViews.filter((_, index) => {
	if (!keptViews.has(index)) return false;
	viewMap.set(index, viewMap.size);
	keptViewData.push(views[index]);
	return true;
});
for (const accessor of json.accessors) {
	if (accessor.bufferView !== undefined) accessor.bufferView = viewMap.get(accessor.bufferView);
}
for (const image of json.images ?? []) {
	if (image.bufferView !== undefined) image.bufferView = viewMap.get(image.bufferView);
}

// ---------- textures: KTX2 back to PNG at the mip level nearest the target size ----------

const work = fs.mkdtempSync(path.join(os.tmpdir(), 'lod-'));
json.images?.forEach((image, index) => {
	if (image.mimeType !== 'image/ktx2' || image.bufferView === undefined) return;
	const source = path.join(work, `${index}.ktx2`);
	fs.writeFileSync(source, keptViewData[image.bufferView]);
	execFileSync('basisu', ['-unpack', '-no_ktx', '-output_path', work, source], { stdio: 'pipe' });
	const levels = fs.readdirSync(work)
		.map((name) => name.match(new RegExp(`^${index}_unpacked_rgba_BC7_RGBA_level_(\\d+)_face_0_layer_0000\\.png$`)))
		.filter(Boolean)
		.map((match) => ({ level: Number(match[1]), file: path.join(work, match[0]) }))
		.sort((a, b) => a.level - b.level);
	if (levels.length === 0) throw new Error(`basisu could not unpack image ${index}`);
	const width = (file) => fs.readFileSync(file).readUInt32BE(16);
	const chosen = [...levels].reverse().find(({ file }) => width(file) >= MAX) ?? levels[0];
	keptViewData[image.bufferView] = fs.readFileSync(chosen.file);
	image.mimeType = 'image/png';
	for (const name of fs.readdirSync(work)) {
		if (name.startsWith(`${index}_unpacked_`)) fs.rmSync(path.join(work, name));
	}
});
for (const texture of json.textures ?? []) {
	const basisu = texture.extensions?.KHR_texture_basisu;
	if (basisu === undefined) continue;
	texture.source = basisu.source;
	delete texture.extensions.KHR_texture_basisu;
	if (Object.keys(texture.extensions).length === 0) delete texture.extensions;
}

// ---------- write, then compress the textures to KTX2 at the target size ----------

const chunks = [];
let offset = 0;
json.bufferViews.forEach((view, index) => {
	const padding = (8 - (offset % 8)) % 8;
	if (padding) chunks.push(Buffer.alloc(padding));
	offset += padding;
	view.byteOffset = offset;
	view.byteLength = keptViewData[index].length;
	chunks.push(keptViewData[index]);
	offset += keptViewData[index].length;
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
const intermediate = path.join(work, 'simplified.vrm');
fs.writeFileSync(intermediate, Buffer.concat([header, jsonHeader, jsonChunk, binHeader, binChunk]));
execFileSync('node', [path.join(here, 'compress.mjs'), intermediate, output, String(MAX)], { stdio: 'pipe' });
fs.rmSync(work, { recursive: true });
console.log(path.basename(output), `${Math.round(before)} -> ${Math.round(after)} triangles,`, `${(buffer.length / 1048576).toFixed(1)}MB -> ${(fs.statSync(output).size / 1048576).toFixed(1)}MB`);
