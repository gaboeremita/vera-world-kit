import fs from 'node:fs';
for (const file of process.argv.slice(2)) {
	const b = fs.readFileSync(file);
	const len = b.readUInt32LE(12);
	const json = JSON.parse(b.subarray(20, 20 + len).toString());
	const bin = b.subarray(20 + len + 8);
	const out = (json.images ?? []).map((img) => {
		const v = json.bufferViews[img.bufferView];
		const d = bin.subarray(v.byteOffset ?? 0, (v.byteOffset ?? 0) + v.byteLength);
		let dim = '?';
		if (img.mimeType === 'image/png') dim = `${d.readUInt32BE(16)}x${d.readUInt32BE(20)}`;
		return `${dim}:${img.mimeType.split('/')[1]}:${Math.round(v.byteLength / 1024)}k`;
	});
	console.log(file.split('/').pop(), Math.round(b.length / 1048576) + 'MB', out.join(' '));
}
