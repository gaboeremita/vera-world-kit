// Runs the app's own collision and navigation code on a region GLB.
// usage: node check.mjs <file.glb> <layout.json> [mapDir]
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { GLTFLoader } = await import(`${REPO}/node_modules/three/examples/jsm/loaders/GLTFLoader.js`);
const { Vector3 } = await import(`${REPO}/node_modules/three/build/three.module.js`);
const { WorldCollision } = await import(`${REPO}/resources/js/components/world/collisionCheck.js`);
const { buildNavigationGrid } = await import(`${REPO}/resources/js/components/world/worldNavigation.js`);
const { floorBounds } = await import(`${REPO}/resources/js/components/world/worldMapProjection.js`);

const [glbPath, layoutPath, mapDir] = process.argv.slice(2);

function withoutTextures(buffer) {
	const jsonLength = buffer.readUInt32LE(12);
	const json = JSON.parse(buffer.subarray(20, 20 + jsonLength).toString('utf8'));
	const rest = buffer.subarray(20 + jsonLength);
	delete json.images;
	delete json.textures;
	delete json.samplers;
	for (const material of json.materials ?? []) {
		const pbr = material.pbrMetallicRoughness ?? {};
		delete pbr.baseColorTexture;
		delete pbr.metallicRoughnessTexture;
		delete material.normalTexture;
		delete material.emissiveTexture;
		delete material.occlusionTexture;
	}
	let text = JSON.stringify(json);
	while (text.length % 4) text += ' ';
	const jsonChunk = Buffer.from(text, 'utf8');
	const header = Buffer.alloc(20);
	header.writeUInt32LE(0x46546c67, 0);
	header.writeUInt32LE(2, 4);
	header.writeUInt32LE(20 + jsonChunk.length + rest.length, 8);
	header.writeUInt32LE(jsonChunk.length, 12);
	header.writeUInt32LE(0x4e4f534a, 16);
	const out = Buffer.concat([header, jsonChunk, rest]);
	return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength);
}

const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(withoutTextures(fs.readFileSync(glbPath)), '', resolve, reject));
const layout = JSON.parse(fs.readFileSync(layoutPath, 'utf8')).layout;
const collision = new WorldCollision(gltf.scene);
const bounds = floorBounds(layout, null);
const minY = Math.min(...layout.floors.map((floor) => floor.minY));
const maxY = Math.max(...layout.floors.map((floor) => floor.maxY));
const started = performance.now();
const grid = buildNavigationGrid(collision, { bounds, minY, maxY });
console.log(`grid ${grid.columns}x${grid.rows} built in ${Math.round(performance.now() - started)} ms, ${collision.triangleCount} triangles`);

const center = collision.bounds.getCenter(new Vector3()).setY(0);
const spawn = collision.findSpawn(center);
console.log('spawn', spawn && [spawn.x, spawn.y, spawn.z].map((v) => v.toFixed(2)).join(', '));

const reached = new Uint8Array(grid.heights.length);
{
	const startNode = grid.nearestNode(spawn);
	const queue = [startNode];
	reached[startNode] = 1;
	while (queue.length) {
		const node = queue.pop();
		for (let direction = 0; direction < 8; direction++) {
			if (!grid.edgeOpen(node, direction)) continue;
			const next = grid.neighbour(node, direction);
			if (next === -1 || reached[next]) continue;
			reached[next] = 1;
			queue.push(next);
		}
	}
	let total = 0;
	let count = 0;
	for (let n = 0; n < grid.heights.length; n++) {
		if (!Number.isNaN(grid.heights[n])) total++;
		if (reached[n]) count++;
	}
	console.log(`${count} of ${total} nodes reachable from spawn`);
}
const reachedNear = (point) => {
	const node = grid.nearestNode(point);
	return node !== -1 && reached[node] === 1;
};

let failures = 0;
const fmt = (p) => `(${p.x.toFixed(1)}, ${p.y.toFixed(1)}, ${p.z.toFixed(1)})`;
for (const zone of layout.zones) {
	const route = grid.findPath(spawn, zone.entry);
	const node = grid.nearestNode(zone.entry);
	if (!route) {
		failures++;
		console.log(`ZONE FAIL ${zone.id} entry ${fmt(zone.entry)}${node === -1 ? ' (no node near entry)' : reachedNear(zone.entry) ? ' (connected, search gave up)' : ' (not connected)'}`);
	}
}
for (const object of layout.objects) {
	for (const spot of object.spots) {
		const route = grid.findPathNear(spawn, spot.position);
		if (!route) {
			failures++;
			console.log(`SPOT FAIL ${object.id}/${spot.id} at ${fmt(spot.position)}`);
		}
	}
}
for (const passage of layout.passages ?? []) {
	if (!grid.findPath(spawn, passage.arrival)) {
		failures++;
		console.log(`PASSAGE FAIL ${passage.id}`);
	}
}
let longFails = 0;
let longest = 0;
for (const zone of layout.zones) {
	const far = [...layout.zones].sort((a, b) => Math.hypot(b.entry.x - zone.entry.x, b.entry.z - zone.entry.z) - Math.hypot(a.entry.x - zone.entry.x, a.entry.z - zone.entry.z)).slice(0, 3);
	for (const other of far) {
		const route = grid.findPath(zone.entry, other.entry);
		if (!route) {
			longFails++;
			failures++;
			console.log(`ROUTE FAIL ${zone.id} -> ${other.id}${reachedNear(zone.entry) && reachedNear(other.entry) ? ' (both connected: search gave up)' : ''}`);
		} else {
			let length = 0;
			for (let k = 1; k < route.length; k++) length += Math.hypot(route[k].x - route[k - 1].x, route[k].z - route[k - 1].z);
			longest = Math.max(longest, length);
		}
	}
}
console.log(`long routes: ${layout.zones.length * 3 - longFails} ok, ${longFails} failed, longest ${longest.toFixed(0)} m`);
const BLOCKERS = ['speakeasy-door', 'vault-door', 'tunnel-grate', 'dead-letter-door', 'clock-tower-door', 'loft-hatch'];
{
	const sealed = new WorldCollision(gltf.scene, { blockingObjectIds: BLOCKERS });
	const crosses = (world, from, dx, dz) => {
		const position = new Vector3(from.x, from.y, from.z);
		const steps = Math.ceil(Math.hypot(dx, dz) / 0.05);
		for (let k = 0; k < steps; k++) world.move(position, dx / steps, dz / steps, { withBlockers: true });
		return Math.hypot(position.x - (from.x + dx), position.z - (from.z + dz)) < 0.3;
	};
	for (const id of BLOCKERS) {
		const object = layout.objects.find((candidate) => candidate.id === id);
		if (!object) { failures++; console.log(`BLOCKER FAIL ${id}: no object`); continue; }
		const triangles = sealed.blockers.has(id) ? 1 : 0;
		const results = [];
		let blockedSomewhere = false;
		for (const [ax, az] of [[1, 0], [0, 1]]) {
			for (const sign of [1, -1]) {
				const from = { x: object.position.x - ax * sign * 0.9, y: object.position.y, z: object.position.z - az * sign * 0.9 };
				const ground = collision.groundBelow ? collision.groundBelow(new Vector3(from.x, from.y + 0.5, from.z)) : null;
				if (ground) from.y = ground.y;
				const open = crosses(collision, from, ax * sign * 1.8, az * sign * 1.8);
				const shut = crosses(sealed, from, ax * sign * 1.8, az * sign * 1.8);
				results.push(`${ax ? 'x' : 'z'}${sign > 0 ? '+' : '-'}:${open ? 'open' : 'wall'}/${shut ? 'open' : 'sealed'}`);
				if (open && !shut) blockedSomewhere = true;
			}
		}
		if (!triangles || !blockedSomewhere) failures++;
		console.log(`${!triangles || !blockedSomewhere ? 'BLOCKER FAIL' : 'blocker ok'} ${id} ${triangles ? 'sealed' : 'no seal'} ${results.join(' ')}`);
	}
}
const spotCount = layout.objects.reduce((sum, object) => sum + object.spots.length, 0);
console.log(`${layout.zones.length} zones, ${layout.objects.length} objects, ${spotCount} spots, ${failures} failures`);

function png(width, height, rgb) {
	const raw = Buffer.alloc((width * 3 + 1) * height);
	for (let y = 0; y < height; y++) {
		raw[y * (width * 3 + 1)] = 0;
		rgb.copy(raw, y * (width * 3 + 1) + 1, y * width * 3, (y + 1) * width * 3);
	}
	const chunk = (type, data) => {
		const length = Buffer.alloc(4);
		length.writeUInt32BE(data.length);
		const body = Buffer.concat([Buffer.from(type), data]);
		const crc = Buffer.alloc(4);
		crc.writeUInt32BE(zlib.crc32(body) >>> 0);
		return Buffer.concat([length, body, crc]);
	};
	const ihdr = Buffer.alloc(13);
	ihdr.writeUInt32BE(width, 0);
	ihdr.writeUInt32BE(height, 4);
	ihdr[8] = 8;
	ihdr[9] = 2;
	return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

if (mapDir) {
	fs.mkdirSync(mapDir, { recursive: true });
	for (const floor of layout.floors) {
		const rgb = Buffer.alloc(grid.columns * grid.rows * 3, 20);
		for (let column = 0; column < grid.columns * grid.rows; column++) {
			for (let node = grid.columnStart[column]; node < grid.columnStart[column + 1]; node++) {
				const h = grid.heights[node];
				if (h < floor.minY || h >= floor.maxY) continue;
				const o = column * 3;
				const ok = reached[node] === 1;
				rgb[o] = ok ? 120 : 230;
				rgb[o + 1] = ok ? 220 : 160;
				rgb[o + 2] = ok ? 120 : 60;
			}
		}
		const mark = (p, r, g, b) => {
			const i = Math.round((p.x - grid.minX) / grid.cellSize);
			const j = Math.round((p.z - grid.minZ) / grid.cellSize);
			for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
				const ii = i + di, jj = j + dj;
				if (ii < 0 || jj < 0 || ii >= grid.columns || jj >= grid.rows) continue;
				const o = (jj * grid.columns + ii) * 3;
				rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b;
			}
		};
		for (const zone of layout.zones) if (zone.floorId === floor.id) mark(zone.entry, 40, 90, 255);
		for (const object of layout.objects) for (const spot of object.spots) if (spot.position.y >= floor.minY && spot.position.y < floor.maxY) mark(spot.position, 255, 60, 60);
		fs.writeFileSync(path.join(mapDir, `nav-${floor.id}.png`), png(grid.columns, grid.rows, rgb));
	}
	console.log('maps written to', mapDir);
}
process.exit(failures ? 1 : 0);
