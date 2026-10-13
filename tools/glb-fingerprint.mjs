// Prints a stable summary of a GLB: every node with its mesh, primitive counts, materials and extras, and a hash of each accessor's bytes.
// usage: node glb-fingerprint.mjs <file.glb> [--hashes]
import fs from 'node:fs';
import crypto from 'node:crypto';

const [file, flag] = process.argv.slice(2);
const buffer = fs.readFileSync(file);
const jsonLength = buffer.readUInt32LE(12);
const gltf = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString());
const binStart = 20 + jsonLength + 8;

function accessorHash(index) {
	const accessor = gltf.accessors[index];
	const view = gltf.bufferViews[accessor.bufferView];
	const start = binStart + (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
	return crypto.createHash('sha1').update(buffer.subarray(start, start + view.byteLength)).digest('hex').slice(0, 10);
}

const lines = [];
for (const node of gltf.nodes ?? []) {
	let line = node.name ?? '(unnamed)';
	if (node.extras && Object.keys(node.extras).length > 0) line += ` extras=${JSON.stringify(node.extras)}`;
	if (node.translation) line += ` at=${node.translation.map((v) => v.toFixed(3)).join(',')}`;
	if (node.mesh !== undefined) {
		for (const primitive of gltf.meshes[node.mesh].primitives) {
			const count = gltf.accessors[primitive.attributes.POSITION].count;
			const material = primitive.material !== undefined ? gltf.materials[primitive.material].name : '-';
			line += ` [${material} v${count}${flag === '--hashes' ? ` ${accessorHash(primitive.attributes.POSITION)}` : ''}]`;
		}
	}
	lines.push(line);
}
lines.sort();
const images = (gltf.images ?? []).map((image) => `${image.name} ${crypto.createHash('sha1').update(buffer.subarray(binStart + (gltf.bufferViews[image.bufferView].byteOffset ?? 0), binStart + (gltf.bufferViews[image.bufferView].byteOffset ?? 0) + gltf.bufferViews[image.bufferView].byteLength)).digest('hex').slice(0, 10)}`);
console.log([...lines, '--- images', ...images.sort(), `--- ${gltf.nodes.length} nodes, ${gltf.meshes?.length ?? 0} meshes, ${gltf.materials?.length ?? 0} materials`].join('\n'));
