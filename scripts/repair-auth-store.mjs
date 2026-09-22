/**
 * Diagnose and repair the better-auth MongoDB store (production P0: sign-up
 * returns FAILED_TO_CREATE_USER while sign-in reads work).
 *
 * Root cause class: a stale UNIQUE index (or schema validator) on an auth
 * collection blocks every new-user insert. The email unique index works
 * (duplicate emails get USER_ALREADY_EXISTS), so the blocker is a different
 * constraint, typically left over from an early schema iteration.
 *
 * Default mode is READ-ONLY: it prints indexes and validators for the
 * better-auth collections and lists drop candidates. Nothing is modified.
 *
 *   node scripts/repair-auth-store.mjs                 # inspect only
 *   node scripts/repair-auth-store.mjs --drop-stale    # dry-run drop plan
 *   node scripts/repair-auth-store.mjs --drop-stale --yes
 *
 * --drop-stale removes ONLY single- or multi-field UNIQUE indexes that are
 * not part of the better-auth schema whitelist below. It never drops _id_,
 * never touches documents, and never modifies validators. If a collection
 * has a schema validator, it is reported and left untouched.
 */
import 'dotenv/config';
import mongoose from 'mongoose';

const COLLECTIONS = ['user', 'account', 'session', 'verification', 'twoFactor'];

// Indexes that belong to the current better-auth schema and must be kept.
const KEEP = {
    user: new Set(['_id_', 'email_1']),
    account: new Set(['_id_']),
    session: new Set(['_id_', 'token_1']),
    verification: new Set(['_id_', 'identifier_1']),
    twoFactor: new Set(['_id_', 'userId_1']),
};

const args = process.argv.slice(2);
const dropStale = args.includes('--drop-stale');
const yes = args.includes('--yes');

async function main() {
    const uri = process.env.MONGODB_URI;
    if (!uri) {
        console.error('ERROR: MONGODB_URI must be set in .env');
        process.exit(1);
    }

    await mongoose.connect(uri, { bufferCommands: false });
    const db = mongoose.connection.db;
    console.log(`Connected to db="${mongoose.connection.name}" host="${mongoose.connection.host}"\n`);

    let candidates = 0;

    for (const name of COLLECTIONS) {
        const [info] = await db.listCollections({ name }).toArray();
        if (!info) {
            console.log(`== ${name}: (collection does not exist yet)`);
            continue;
        }
        console.log(`== ${name}`);
        if (info.options?.validator) {
            console.log('   ⚠ schema validator present (can block inserts):');
            console.log('   ' + JSON.stringify(info.options.validator));
        }
        const indexes = await db.collection(name).indexes();
        for (const idx of indexes) {
            const keep = KEEP[name]?.has(idx.name) ?? false;
            const flag = idx.unique ? 'UNIQUE' : '      ';
            const mark = idx.unique && !keep ? '  <-- DROP CANDIDATE (stale unique index)' : '';
            if (idx.unique && !keep) candidates++;
            console.log(`   ${flag} ${idx.name} ${JSON.stringify(idx.key)}${mark}`);
        }
        console.log('');
    }

    if (!dropStale) {
        console.log(candidates
            ? `${candidates} drop candidate(s) found. Re-run with --drop-stale (dry-run) or --drop-stale --yes (execute).`
            : 'No stale unique indexes found. If sign-up still fails, check the validators above and the Atlas cluster user permissions.');
    } else {
        for (const name of COLLECTIONS) {
            const [info] = await db.listCollections({ name }).toArray();
            if (!info) continue;
            const indexes = await db.collection(name).indexes();
            for (const idx of indexes) {
                if (!idx.unique || (KEEP[name]?.has(idx.name) ?? false)) continue;
                if (!yes) {
                    console.log(`DRY-RUN: would drop ${name}.${idx.name}`);
                } else {
                    await db.collection(name).dropIndex(idx.name);
                    console.log(`DROPPED ${name}.${idx.name}`);
                }
            }
        }
        console.log(yes ? 'Done. Re-run without flags to verify.' : '\nDry-run only. Add --yes to execute the drops.');
    }

    await mongoose.connection.close();
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
