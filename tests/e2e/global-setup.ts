import * as fs from 'fs';
import * as path from 'path';

/**
 * Global setup for Playwright E2E tests
 *
 * This runs once before all tests start.
 * Sets up log directories and symlinks.
 */

async function globalSetup() {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const logBaseDir = path.join(process.cwd(), '.test-logs');
  const logDir = path.join(logBaseDir, timestamp);

  // Create log directories
  const dirs = [
    path.join(logDir, 'docker'),
    path.join(logDir, 'tests'),
    path.join(logDir, 'browser', 'screenshots'),
    path.join(logDir, 'browser', 'videos'),
    path.join(logDir, 'errors'),
    path.join(logDir, 'reports'),
    // Auth storage directory for Playwright storageState
    path.join(process.cwd(), 'playwright', '.auth'),
  ];

  for (const dir of dirs) {
    fs.mkdirSync(dir, { recursive: true });
  }

  // Update 'latest' symlink
  const latestLink = path.join(logBaseDir, 'latest');
  try {
    if (fs.existsSync(latestLink)) {
      fs.unlinkSync(latestLink);
    }
    fs.symlinkSync(logDir, latestLink);
  } catch (error) {
    console.warn('Could not create latest symlink:', error);
  }

  // Write initial metadata
  const metadata = {
    startTime: new Date().toISOString(),
    timestamp,
    nodeVersion: process.version,
    platform: process.platform,
    cwd: process.cwd(),
  };

  fs.writeFileSync(
    path.join(logDir, 'metadata.json'),
    JSON.stringify(metadata, null, 2)
  );

  // Store log directory in environment for other tests to use
  process.env.TEST_LOG_DIR = logDir;
  process.env.TEST_TIMESTAMP = timestamp;

  console.log(`\n📁 Test logs directory: ${logDir}\n`);
}

export default globalSetup;
