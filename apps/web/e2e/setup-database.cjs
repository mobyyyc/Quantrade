/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require("node:fs/promises");
const path = require("node:path");
const { Client } = require("pg");
const { e2eDatabaseUrls } = require("./database-url.cjs");

async function setupDatabase() {
  const { adminUrl, testUrl, testDatabaseName } = e2eDatabaseUrls();
  if (!testDatabaseName.endsWith("_e2e")) throw new Error("Refusing to reset a database without the _e2e suffix.");
  const admin = new Client({ connectionString: adminUrl });
  await admin.connect();
  try {
    await admin.query(`DROP DATABASE IF EXISTS ${testDatabaseName} WITH (FORCE)`);
    await admin.query(`CREATE DATABASE ${testDatabaseName}`);
  } finally {
    await admin.end();
  }

  const database = new Client({ connectionString: testUrl });
  await database.connect();
  try {
    const migrationsDirectory = path.resolve(process.cwd(), "../../services/research/db/migrations");
    const migrations = (await fs.readdir(migrationsDirectory))
      .filter((file) => /^\d{4}_.+\.sql$/.test(file))
      .sort();
    for (const migration of migrations) {
      await database.query(await fs.readFile(path.join(migrationsDirectory, migration), "utf8"));
    }
    await database.query(await fs.readFile(path.join(process.cwd(), "e2e/seed.sql"), "utf8"));
  } finally {
    await database.end();
  }
}

setupDatabase().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
