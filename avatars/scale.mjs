// Scales a VRM 0.x to a target height: vertices, morph targets, bone positions, bind matrices, first-person offset, spring bone and collider sizes.
// usage: node scale.mjs in.vrm out.vrm <height in metres>
import fs from 'node:fs';

function read(file) {
	const buffer = fs.readFileSync(file);
	const length = buffer.readUInt32LE(12);
	const json = JSON.parse(buffer.subarray(20, 20 + length).toString('utf8'));
	const binLength = buffer.readUInt32LE(20 + length);
	const bin = Buffer.from(buffer.subarray(28 + length, 28 + length + binLength));
	return { json, bin };
}

function write(file, json, bin) {
	let text = JSON.stringify(json);
	while (text.length % 4) text += ' ';
	const chunk = Buffer.from(text);
	const binHeader = Buffer.alloc(8);
	binHeader.writeUInt32LE(bin.length, 0); binHeader.writeUInt32LE(0x004e4942, 4);
	const header = Buffer.alloc(20);
	header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + chunk.length + 8 + bin.length, 8);
	header.writeUInt32LE(chunk.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
	fs.writeFileSync(file, Buffer.concat([header, chunk, binHeader, bin]));
}

function floats(json, bin, accessorIndex) {
	const accessor = json.accessors[accessorIndex];
	if (accessor.componentType !== 5126 || accessor.sparse) throw new Error(`accessor ${accessorIndex} is not plain float data`);
	const view = json.bufferViews[accessor.bufferView];
	const width = { SCALAR: 1, VEC3: 3, MAT4: 16 }[accessor.type];
	const stride = (view.byteStride ?? width * 4) / 4;
	const start = (bin.byteOffset + (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0)) / 4;
	const data = new Float32Array(bin.buffer, 0, bin.buffer.byteLength >> 2);
	return { accessor, data, start, stride, count: accessor.count };
}

function scaleVectors(json, bin, accessorIndex, factor) {
	const { accessor, data, start, stride, count } = floats(json, bin, accessorIndex);
	for (let k = 0; k < count; k++) {
		for (let c = 0; c < 3; c++) data[start + k * stride + c] *= factor;
	}
	if (accessor.min) accessor.min = accessor.min.map((value) => value * factor);
	if (accessor.max) accessor.max = accessor.max.map((value) => value * factor);
}

function scaleBindTranslations(json, bin, accessorIndex, factor) {
	const { data, start, stride, count } = floats(json, bin, accessorIndex);
	for (let k = 0; k < count; k++) {
		for (let c = 12; c < 15; c++) data[start + k * stride + c] *= factor;
	}
}

const [source, target, heightArgument] = process.argv.slice(2);
const height = Number(heightArgument);
if (!source || !target || !(height > 0)) throw new Error('usage: node scale.mjs in.vrm out.vrm <height in metres>');
const { json, bin } = read(source);
if (!json.extensions?.VRM) throw new Error('only VRM 0.x is supported');

const positions = new Set();
for (const mesh of json.meshes) {
	for (const primitive of mesh.primitives) {
		positions.add(primitive.attributes.POSITION);
		for (const morph of primitive.targets ?? []) {
			if (morph.POSITION !== undefined) positions.add(morph.POSITION);
		}
	}
}
const bodyPositions = json.meshes.flatMap((mesh) => mesh.primitives.map((primitive) => json.accessors[primitive.attributes.POSITION]));
const low = Math.min(...bodyPositions.map((accessor) => accessor.min[1]));
const high = Math.max(...bodyPositions.map((accessor) => accessor.max[1]));
const factor = height / (high - low);

for (const accessorIndex of positions) scaleVectors(json, bin, accessorIndex, factor);
for (const accessorIndex of new Set(json.skins.map((skin) => skin.inverseBindMatrices))) scaleBindTranslations(json, bin, accessorIndex, factor);
for (const node of json.nodes) {
	if (node.matrix) throw new Error(`node ${node.name} uses a matrix transform`);
	if (node.translation) node.translation = node.translation.map((value) => value * factor);
}

const vrm = json.extensions.VRM;
const offset = vrm.firstPerson?.firstPersonBoneOffset;
if (offset) for (const axis of ['x', 'y', 'z']) offset[axis] *= factor;
for (const group of vrm.secondaryAnimation?.boneGroups ?? []) group.hitRadius *= factor;
for (const group of vrm.secondaryAnimation?.colliderGroups ?? []) {
	for (const collider of group.colliders) {
		collider.radius *= factor;
		for (const axis of ['x', 'y', 'z']) collider.offset[axis] *= factor;
	}
}

write(target, json, bin);
console.log(`${source.split('/').pop()}: ${(high - low).toFixed(3)} m -> ${height} m (x${factor.toFixed(4)})`);
