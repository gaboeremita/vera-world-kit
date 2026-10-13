import fs from 'node:fs';
const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { GLTFLoader } = await import(`${REPO}/node_modules/three/examples/jsm/loaders/GLTFLoader.js`);
const { Vector3, Triangle } = await import(`${REPO}/node_modules/three/build/three.module.js`);
const buffer = fs.readFileSync(process.argv[2]);
const jsonLength = buffer.readUInt32LE(12);
const json = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString('utf8'));
delete json.images; delete json.textures; delete json.samplers;
for (const m of json.materials ?? []) { delete m.pbrMetallicRoughness?.baseColorTexture; }
let text = JSON.stringify(json); while (text.length % 4) text += ' ';
const jc = Buffer.from(text); const rest = buffer.subarray(20 + jsonLength);
const header = Buffer.alloc(20); header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + jc.length + rest.length, 8); header.writeUInt32LE(jc.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
const out = Buffer.concat([header, jc, rest]);
const gltf = await new Promise((res, rej) => new GLTFLoader().parse(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength), '', res, rej));
gltf.scene.updateWorldMatrix(true, true);
let tris = 0; const big = [];
const a = new Vector3(), b = new Vector3(), c = new Vector3();
gltf.scene.traverse((node) => {
	if (!node.isMesh) return;
	const pos = node.geometry.attributes.position; const index = node.geometry.index;
	const count = index ? index.count / 3 : pos.count / 3;
	tris += count;
	let longest = 0;
	for (let t = 0; t < count; t++) {
		const i0 = index ? index.getX(t * 3) : t * 3, i1 = index ? index.getX(t * 3 + 1) : t * 3 + 1, i2 = index ? index.getX(t * 3 + 2) : t * 3 + 2;
		a.fromBufferAttribute(pos, i0).applyMatrix4(node.matrixWorld); b.fromBufferAttribute(pos, i1).applyMatrix4(node.matrixWorld); c.fromBufferAttribute(pos, i2).applyMatrix4(node.matrixWorld);
		longest = Math.max(longest, a.distanceTo(b), b.distanceTo(c), c.distanceTo(a));
	}
	if (longest > 20) big.push([node.name, Math.round(longest), count]);
});
console.log('meshes triangles', tris);
big.sort((x, y) => y[1] - x[1]);
console.log(big.length, 'meshes with an edge over 20 m'); for (const row of big.slice(0, 40)) console.log(row.join('  '));
