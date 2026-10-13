// usage: node probe.mjs glb layout "x0,z0,y0,x1,z1,y1" ...  (glTF coordinates: x, z = -blender y, y up)
import fs from 'node:fs';
const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { GLTFLoader } = await import(`${REPO}/node_modules/three/examples/jsm/loaders/GLTFLoader.js`);
const { Vector3 } = await import(`${REPO}/node_modules/three/build/three.module.js`);
const { WorldCollision } = await import(`${REPO}/resources/js/components/world/collisionCheck.js`);
const { buildNavigationGrid } = await import(`${REPO}/resources/js/components/world/worldNavigation.js`);
const { floorBounds } = await import(`${REPO}/resources/js/components/world/worldMapProjection.js`);
const [glbPath, layoutPath, ...segments] = process.argv.slice(2);
const buffer = fs.readFileSync(glbPath);
const jl = buffer.readUInt32LE(12);
const json = JSON.parse(buffer.subarray(20, 20 + jl).toString('utf8'));
delete json.images; delete json.textures; delete json.samplers;
let text = JSON.stringify(json); while (text.length % 4) text += ' ';
const jc = Buffer.from(text); const rest = buffer.subarray(20 + jl);
const header = Buffer.alloc(20); header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + jc.length + rest.length, 8); header.writeUInt32LE(jc.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
const out = Buffer.concat([header, jc, rest]);
const gltf = await new Promise((res, rej) => new GLTFLoader().parse(out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength), '', res, rej));
const layout = JSON.parse(fs.readFileSync(layoutPath, 'utf8')).layout;
const collision = new WorldCollision(gltf.scene);
const grid = buildNavigationGrid(collision, { bounds: floorBounds(layout, null), minY: Math.min(...layout.floors.map((f) => f.minY)), maxY: Math.max(...layout.floors.map((f) => f.maxY)) });
const spawn = collision.findSpawn(collision.bounds.getCenter(new Vector3()).setY(0));
const reached = new Uint8Array(grid.heights.length);
const start = grid.nearestNode(spawn); reached[start] = 1; const queue = [start];
while (queue.length) { const n = queue.pop(); for (let d = 0; d < 8; d++) { if (!grid.edgeOpen(n, d)) continue; const m = grid.neighbour(n, d); if (m === -1 || reached[m]) continue; reached[m] = 1; queue.push(m); } }
for (const segment of segments) {
	const [x0, z0, y0, x1, z1, y1] = segment.split(',').map(Number);
	const length = Math.hypot(x1 - x0, z1 - z0);
	const steps = Math.max(1, Math.round(length / 0.4));
	const row = [];
	for (let k = 0; k <= steps; k++) {
		const t = k / steps;
		const p = { x: x0 + (x1 - x0) * t, y: y0 + (y1 - y0) * t, z: z0 + (z1 - z0) * t };
		const i = Math.round((p.x - grid.minX) / grid.cellSize), j = Math.round((p.z - grid.minZ) / grid.cellSize);
		const column = j * grid.columns + i;
		const hs = [];
		for (let n = grid.columnStart[column]; n < grid.columnStart[column + 1]; n++) hs.push(`${grid.heights[n].toFixed(2)}${reached[n] ? '*' : ''}`);
		row.push(`${p.y.toFixed(1)}:[${hs.join(' ')}]`);
	}
	console.log(segment); console.log('  ' + row.join(' '));
}
