import fs from "node:fs/promises";
import path from "node:path";
import { Client } from "pg";
import { e2eDatabaseUrls } from "./database-url";

export default async function globalSetup() {
  const { adminUrl, testUrl, testDatabaseName } = e2eDatabaseUrls();
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
