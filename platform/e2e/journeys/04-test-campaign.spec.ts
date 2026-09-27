import { expect, test } from '@playwright/test'
import {
  caption,
  clearCaption,
  highlight,
  installCursor,
  pause,
  resetDemo,
  shot,
  signIn,
  signOut,
  titleCard,
  nav,
} from './helpers'

/**
 * Journey 4. A test campaign, read against its population, alerting once.
 *
 * Four of five deployments tested, one failure. The campaign reports, per
 * framework, which in-scope assets were tested, which failed, and which were
 * never tested at all. Owners receive one digest each rather than one alert
 * per cascade.
 */
test('Journey 4: a test campaign across the estate', async ({ page }, info) => {
  resetDemo()
  const app = page.locator('#root')
  await installCursor(page)
  await page.goto('/login')
  await titleCard(page, 'Journey 4: a test campaign across the estate', [
    'Quarterly testing of CTL-006, recorded as one campaign rather than five separate results.',
    'Four deployments tested; HR Portal was not reached this quarter; Checkout Web fails.',
    'Watch the population per framework, and how many alerts each owner receives.',
  ], 7000)

  await caption(page, 'Sign in', 'Jonah Weiss records the quarter\'s results for CTL-006.', 1600)
  await signIn(page, 'control@example.com')
  await nav(page, 'Controls')
  await app.getByText('Multi-factor authentication for all interactive access').click()
  await app.getByRole('button', { name: /Testing & impact/ }).click()
  await caption(page, 'Campaign', 'Testing & impact holds campaigns and the full test lineage for the control.', 1000)
  const run = app.getByRole('button', { name: 'Run a test campaign' })
  await highlight(run, 1800)
  await run.click()

  await app.getByPlaceholder('e.g. Q4 access control testing').fill('Q4 multi-factor authentication testing')
  const results: [string, string, string][] = [
    ['Payments API', 'Pass', 'Sign-in log sample, 200 sessions, all with a second factor.'],
    ['Card Vault', 'Pass', 'Vault console policy export and sign-in sample.'],
    ['Checkout Web', 'Fail', 'Admin console accepted a password-only login.'],
    ['Corporate Identity Provider', 'Pass', 'Conditional access export, no exclusions.'],
  ]
  await caption(page, 'Results', 'One result per deployment tested. HR Portal is left as Not tested, and the campaign will say so.', 800)
  for (const [asset, result, evidence] of results) {
    await app.getByLabel('Result for ' + asset).selectOption(result)
    if (result === 'Fail') {
      await app.getByLabel('Failure type for ' + asset).selectOption('Operating')
    }
    await app.getByLabel('Evidence for ' + asset).fill(evidence)
    await pause(page, 500)
  }
  await expect(app.getByText('4 of 5 deployments tested')).toBeVisible()
  await highlight(app.getByText('4 of 5 deployments tested'), 1800)
  await shot(page, info, '01-campaign-form')
  await app.getByRole('button', { name: 'Record campaign' }).click()

  await expect(app.getByTestId('impact-report')).toBeVisible()
  await caption(page, 'Population', 'Read against each framework\'s scope. PCI DSS: all three in-scope assets tested, Checkout Web failed.', 800)
  const pop = app.getByText('Population tested').locator('..')
  await highlight(pop, 3600)
  await expect(pop).toContainText('Not tested: HR Portal')
  await caption(page, 'Population', 'ISO 27001: four of five tested. HR Portal carries no assurance this quarter, a finding a pass rate would hide.', 800)
  await highlight(pop.getByText('Not tested: HR Portal').locator('..'), 3600)
  await shot(page, info, '02-campaign-population')
  await caption(page, 'Impact', 'The same scoped outcome as a single test: PCI loses its requirements, ISO holds, RISK-006 alone is affected.', 1000)
  await highlight(app.getByTestId('impact-framework-PCI-DSS-4.0'), 2600)
  await highlight(app.getByTestId('impact-risk-RISK-006'), 2600)
  await shot(page, info, '03-campaign-impact')
  await app.getByRole('button', { name: 'Close', exact: true }).click()

  const row = app.getByText('Q4 multi-factor authentication testing')
  await expect(row).toBeVisible()
  await caption(page, 'Lineage', 'The campaign and every test in it are kept, each with what it changed. The record is append-only.', 1000)
  await highlight(row.locator('xpath=ancestor::li[1]'), 2600)
  await highlight(app.getByText('Test lineage').locator('xpath=ancestor::section[1]'), 3000)
  await shot(page, info, '04-lineage')

  await caption(page, 'Alerts', 'Elena Vasquez owns RISK-006. One campaign, one digest.', 1600)
  await signOut(page)
  await signIn(page, 'owner@example.com')
  await app.getByRole('link', { name: 'Notifications' }).click()
  const digest = app.getByText(/CMP-001 \(CTL-006\): 1 item for you/)
  await expect(digest).toBeVisible()
  await highlight(digest.locator('xpath=ancestor::li[1]'), 3600)
  await shot(page, info, '05-owner-digest')

  await caption(page, 'Alerts', 'Tomas Lindqvist owns the PCI requirements: one digest for both, plus the posture alert, because PCI fell below the 90% floor.', 1000)
  await signOut(page)
  await signIn(page, 'grc@example.com')
  await app.getByRole('link', { name: 'Notifications' }).click()
  const grcDigest = app.getByText(/CMP-001 \(CTL-006\): 2 items for you/)
  await expect(grcDigest).toBeVisible()
  await expect(app.getByText(/lost coverage$/)).toHaveCount(0)
  await highlight(grcDigest.locator('xpath=ancestor::li[1]'), 3600)
  await highlight(app.getByText(/pulled coverage below 90%/).locator('xpath=ancestor::li[1]'), 3000)
  await shot(page, info, '06-grc-digest')
  await clearCaption(page)

  await titleCard(page, 'A campaign, not five alerts', [
    'Population per framework: PCI 3 of 3 tested, ISO 4 of 5, with HR Portal named as untested.',
    'Scoped outcome: PCI requirements lost, ISO held, only RISK-006 affected.',
    'Each owner received one digest for the campaign, not one alert per cascade.',
  ], 8000)
})
