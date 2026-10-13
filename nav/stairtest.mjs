const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { BoxGeometry, Group, Mesh, MeshBasicMaterial, PlaneGeometry } = await import(`${REPO}/node_modules/three/build/three.module.js`);
const { WorldCollision } = await import(`${REPO}/resources/js/components/world/collisionCheck.js`);
const { buildNavigationGrid } = await import(`${REPO}/resources/js/components/world/worldNavigation.js`);
function box(w, h, d, x, y, z) { const m = new Mesh(new BoxGeometry(w, h, d), new MeshBasicMaterial()); m.position.set(x, y, z); return m; }
function floorPlane(w, d, x, y, z) { const m = new Mesh(new PlaneGeometry(w, d), new MeshBasicMaterial()); m.rotation.x = -Math.PI / 2; m.position.set(x, y, z); return m; }
function run(label, { width = 1.2, tread = 0.25, rise = 0.2, total = 4, wallSide = true, offsetX = 0, walled = false, beside = true }) {
	const scene = new Group();
	const run = Math.round(total / rise) * tread;
	// floor around, with a hole under the stair footprint: stair occupies x in [offsetX, offsetX+width], z from 0 to -run
	scene.add(floorPlane(10, 10, 0, 0, 5)); // z 0..10 in front of stair
	if (beside) scene.add(floorPlane(4, run, offsetX + width + 2, 0, -run / 2));
	if (walled) scene.add(box(0.25, total + 3, run, offsetX + width + 0.125, (total + 3) / 2, -run / 2));
	const steps = Math.round(total / rise);
	for (let k = 0; k < steps; k++) {
		const top = rise * (k + 1);
		scene.add(box(width, top, tread, offsetX + width / 2, top / 2, -(k + 0.5) * tread));
	}
	scene.add(floorPlane(10, 6, 0, total, -run - 3)); // upper floor beyond the top
	if (wallSide) scene.add(box(0.25, total + 3, run + 6, offsetX - 0.125, (total + 3) / 2, -run / 2));
	scene.updateMatrixWorld(true);
	const world = new WorldCollision(scene);
	const grid = buildNavigationGrid(world, { bounds: { minX: -5, maxX: 5, minZ: -run - 6, maxZ: 10 }, minY: -1, maxY: total + 2 });
	const path = grid.findPath({ x: offsetX + width / 2, y: 0, z: 3 }, { x: offsetX + width / 2, y: total, z: -run - 2 });
	const treadNodes = [];
	for (let k = 0; k < steps; k += 4) {
		const n = grid.nearestNode({ x: offsetX + width / 2, y: rise * (k + 1), z: -(k + 0.5) * tread });
		treadNodes.push(n === -1 ? 'x' : grid.nodePosition(n).y.toFixed(1));
	}
	const up = grid.findPath({ x: offsetX + width / 2, y: 0, z: 3 }, { x: offsetX + width / 2, y: rise * 6, z: -5.5 * tread });
	console.log(label.padEnd(40), path ? 'OK' : 'FAIL', 'part', up ? 'ok' : 'fail', treadNodes.join(' '));
}
for (const width of [1.2, 1.6, 2.0, 2.4, 2.8, 3.0]) {
	for (const tread of [0.25, 0.3, 0.4]) run(`w ${width} tread ${tread} open side`, { width, tread, wallSide: false });
}
run('w 1.2 tread 0.25 walled both sides', { walled: true });
run('w 1.2 tread 0.25 walled, no floor beside', { walled: true, beside: false });
run('w 1.2 tread 0.25 open, no floor beside', { beside: false });
run('w 1.6 tread 0.3 walled both sides', { width: 1.6, tread: 0.3, walled: true });
