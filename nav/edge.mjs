// usage: node edge.mjs glb layout x z y  -> explains the edges out of the node nearest (x, y, z) in glTF coordinates
import fs from 'node:fs';
const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { GLTFLoader } = await import(`${REPO}/node_modules/three/examples/jsm/loaders/GLTFLoader.js`);
const { WorldCollision } = await import(`${REPO}/resources/js/components/world/collisionCheck.js`);
const { buildNavigationGrid } = await import(`${REPO}/resources/js/components/world/worldNavigation.js`);
const { floorBounds } = await import(`${REPO}/resources/js/components/world/worldMapProjection.js`);
const [glbPath, layoutPath, xs, zs, ys] = process.argv.slice(2);
const buffer = fs.readFileSync(glbPath); const jl = buffer.readUInt32LE(12);
const json = JSON.parse(buffer.subarray(20, 20 + jl).toString('utf8')); delete json.images; delete json.textures; delete json.samplers;
let text = JSON.stringify(json); while (text.length % 4) text += ' ';
const jc = Buffer.from(text); const rest = buffer.subarray(20 + jl);
const header = Buffer.alloc(20); header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + jc.length + rest.length, 8); header.writeUInt32LE(jc.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
const out = Buffer.concat([header, jc, rest]);
const gltf = await new Promise((res, rej) => new GLTFLoader().parse(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength), '', res, rej));
const layout = JSON.parse(fs.readFileSync(layoutPath, 'utf8')).layout;
const collision = new WorldCollision(gltf.scene);
const grid = buildNavigationGrid(collision, { bounds: floorBounds(layout, null), minY: Math.min(...layout.floors.map((f) => f.minY)), maxY: Math.max(...layout.floors.map((f) => f.maxY)) });
const node = grid.nearestNode({ x: +xs, y: +ys, z: +zs });
const p = grid.nodePosition(node);
console.log('node', node, p);
const names = ['+x', '-x', '+z', '-z'];
for (let d = 0; d < 4; d++) {
	const t = grid.neighbour(node, d);
	if (t === -1) { console.log(names[d], 'no neighbour'); continue; }
	const q = grid.nodePosition(t);
	console.log(names[d], 'to', q, 'open', grid.edgeOpen(node, d), 'dropBeside target', grid.dropBeside(t, d), 'node', grid.dropBeside(node, d), 'sweep', grid.sweepBlocked(p, q));
}
