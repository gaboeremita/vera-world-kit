// Loads VRM files with the app's three-vrm and reports meta, humanoid and size. usage: node vrmcheck.mjs a.vrm ...
import fs from 'node:fs';
const REPO = process.env.VERA_APP;
if (!REPO) throw new Error('Set VERA_APP to the app checkout.');
const { GLTFLoader } = await import(`${REPO}/node_modules/three/examples/jsm/loaders/GLTFLoader.js`);
const THREE = await import(`${REPO}/node_modules/three/build/three.module.js`);
const { VRMLoaderPlugin } = await import(`${REPO}/node_modules/@pixiv/three-vrm/lib/three-vrm.module.js`);
globalThis.self = globalThis;
globalThis.createImageBitmap = async () => ({ width: 1, height: 1, close() {} });
function stripTextures(buffer) {
	const length = buffer.readUInt32LE(12);
	const json = JSON.parse(buffer.subarray(20, 20 + length).toString('utf8'));
	const rest = buffer.subarray(20 + length);
	const pixel = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';
	json.images = (json.images ?? []).map(() => ({ uri: pixel, mimeType: 'image/png' }));
	for (const texture of json.textures ?? []) {
		const basisu = texture.extensions?.KHR_texture_basisu;
		if (basisu) {
			texture.source = basisu.source;
			delete texture.extensions.KHR_texture_basisu;
		}
	}
	for (const list of ['extensionsUsed', 'extensionsRequired']) {
		if (json[list]) json[list] = json[list].filter((name) => name !== 'KHR_texture_basisu');
	}
	let text = JSON.stringify(json); while (text.length % 4) text += ' ';
	const chunk = Buffer.from(text);
	const header = Buffer.alloc(20);
	header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + chunk.length + rest.length, 8);
	header.writeUInt32LE(chunk.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
	const out = Buffer.concat([header, chunk, rest]);
	return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength);
}
for (const file of process.argv.slice(2)) {
	const loader = new GLTFLoader();
	loader.register((parser) => new VRMLoaderPlugin(parser));
	try {
		const gltf = await new Promise((res, rej) => loader.parse(stripTextures(fs.readFileSync(file)), '', res, rej));
		const vrm = gltf.userData.vrm;
		const box = new THREE.Box3().setFromObject(vrm.scene);
		const head = vrm.humanoid.getNormalizedBoneNode('head').getWorldPosition(new THREE.Vector3());
		const leftHand = vrm.humanoid.getNormalizedBoneNode('leftHand')?.getWorldPosition(new THREE.Vector3());
		console.log(file.split('/').pop(), JSON.stringify({ meta: vrm.meta?.metaVersion, name: vrm.meta?.name, bones: Object.keys(vrm.humanoid.humanBones).length, height: +(box.max.y - box.min.y).toFixed(2), headY: +head.y.toFixed(2), leftHandX: leftHand && +leftHand.x.toFixed(2), expressions: vrm.expressionManager?.expressions.length ?? 0 }));
	} catch (error) {
		console.log(file.split('/').pop(), 'FAILED', error.message);
	}
}
