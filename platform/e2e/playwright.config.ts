import { defineConfig } from '@playwright/test'

/**
 * Recorded user journeys. Each journey is a test that also produces a video.
 *
 *   E2E_BASE_URL   where the UI is served (default http://localhost:8080)
 *   E2E_PROJECT    the docker compose project to reset (default "platform")
 *   E2E_FAST=1     drop the reading pauses, for a quick functional run
 *
 * Journeys run in file order on one worker, because journey 2 continues from
 * the state journey 1 leaves behind, and every other journey resets first.
 */
export default defineConfig({
  testDir: './journeys',
  fullyParallel: false,
  workers: 1,
  timeout: 10 * 60 * 1000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  outputDir: './test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    viewport: { width: 1440, height: 900 },
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    launchOptions: { slowMo: process.env.E2E_FAST ? 0 : 90 },
    actionTimeout: 20_000,
  },
})
