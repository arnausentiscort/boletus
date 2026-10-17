// Xifra tools/llocs.json (privat, no es puja) a data/llocs.enc.json amb la clau de l'enllaç.
// Ús: node tools/encrypt_llocs.mjs <clau>   (sense clau en genera una de nova)
import { readFileSync, writeFileSync } from 'node:fs';
import { webcrypto as c, randomBytes } from 'node:crypto';
const key = process.argv[2] || randomBytes(12).toString('base64url');
const enc = new TextEncoder(), b64 = b => Buffer.from(b).toString('base64');
const salt = randomBytes(16), iv = randomBytes(12);
const base = await c.subtle.importKey('raw', enc.encode(key), 'PBKDF2', false, ['deriveKey']);
const k = await c.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 150000, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
const data = await c.subtle.encrypt({ name: 'AES-GCM', iv }, k, enc.encode(readFileSync('tools/llocs.json', 'utf8')));
writeFileSync('data/llocs.enc.json', JSON.stringify({ v: 1, salt: b64(salt), iv: b64(iv), data: b64(new Uint8Array(data)) }));
writeFileSync('tools/.clau', key);
console.log('fet');
