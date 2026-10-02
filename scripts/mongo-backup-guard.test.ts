/**
 * Guarda de los scripts de backup de MongoDB: solo lectura sobre Atlas, cifrado
 * obligatorio, URI fuera de logs/ps y restauracion solo en local desechable.
 * Ejecución: node --experimental-strip-types --test scripts/mongo-backup-guard.test.ts
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const backup = readFileSync(join(here, 'mongo-backup.sh'), 'utf8');
const drill = readFileSync(join(here, 'mongo-restore-drill.sh'), 'utf8');

describe('mongo-backup.sh', () => {
  it('cifra con age y exige clave publica', () => {
    assert.match(backup, /age -r "\$\{AGE_RECIPIENT\}"/);
    assert.match(backup, /age1\*/);
  });
  it('no restaura ni borra nada en Atlas', () => {
    assert.doesNotMatch(backup, /mongorestore/);
    assert.doesNotMatch(backup, /dropDatabase|--drop/);
  });
  it('no pasa la URI por argumentos ni la imprime', () => {
    assert.doesNotMatch(backup, /--uri\s+"\$\{MONGODB_URI\}"/);
    assert.doesNotMatch(backup, /echo[^\n]*MONGODB_URI/);
    assert.match(backup, /--config <\(/);
  });
  it('no deja el dump en claro', () => {
    assert.doesNotMatch(backup, />\s*"?\$\{?OUT\}?"?\s*$/m);
    assert.match(backup, /\| age /);
  });
});

describe('mongo-restore-drill.sh', () => {
  it('restaura solo en un contenedor efimero en loopback', () => {
    assert.match(drill, /127\.0\.0\.1:27099:27017/);
    assert.doesNotMatch(drill, /MONGODB_URI/);
    assert.doesNotMatch(drill, /mongodb\+srv/);
  });
  it('limpia el contenedor al salir', () => {
    assert.match(drill, /trap cleanup EXIT/);
  });
});
