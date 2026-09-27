import { expect, test } from '@playwright/test'
import {
  caption,
  clearCaption,
  highlight,
  installCursor,
  nav,
  pause,
  resetDemo,
  shot,
  signIn,
  signOut,
  titleCard,
} from './helpers'

/**
 * Journey 1. An operating failure on an asset two frameworks share.
 *
 * Checkout Web sits inside PCI DSS (configured all_in_scope) and ISO 27001
 * (configured any_in_scope). One failed test on it should cost PCI its
 * requirements and ISO nothing, and should reach only the risk whose scope
 * includes Checkout Web.
 */
test('Journey 1: an operating failure on Checkout Web', async ({ page }, info) => {
  resetDemo()
  const app = page.locator('#root')
  await installCursor(page)
  await page.goto('/login')
  await titleCard(page, 'Journey 1: an operating failure on Checkout Web', [
    'CTL-006 enforces multi-factor authentication on five assets.',
    'Checkout Web is in scope for PCI DSS and for ISO 27001.',
    'PCI DSS is configured all_in_scope: every in-scope asset must carry the control.',
    'ISO 27001 is configured any_in_scope: covered while any in-scope asset carries it.',
    'One failed test. Watch where its consequences stop.',
  ], 9000)

  // -- before ---------------------------------------------------------------
  await caption(page, 'Sign in', 'Jonah Weiss, the control owner, signs in to record this quarter\'s test result.', 2000)
  await signIn(page, 'control@example.com')

  await nav(page, 'Compliance')
  await caption(page, 'Before the test', 'ISO 27001 stands at 75% coverage across five in-scope assets.', 1500)
  const coverage = app.locator('p', { hasText: /^\d+%$/ }).first()
  await expect(coverage).toHaveText('75%')
  await highlight(coverage, 2600)
  await app.getByRole('button', { name: /PCI Data Security Standard/ }).click()
  await expect(coverage).toHaveText('67%')
  await caption(page, 'Before the test', 'PCI DSS stands at 67%: two requirements covered by CTL-006, one honest gap. Its rule is all_in_scope.', 1200)
  await highlight(coverage, 2600)
  await highlight(app.getByText('all in scope', { exact: true }), 2400)
  await shot(page, info, '01-pci-before')

  // -- the test --------------------------------------------------------------
  await nav(page, 'Controls')
  await app.getByText('Multi-factor authentication for all interactive access').click()
  await expect(app.getByRole('heading', { name: 'Multi-factor authentication for all interactive access' })).toBeVisible()
  await caption(page, 'The control', 'CTL-006 is Operating with CE-High on all five deployments.', 1200)
  await highlight(app.getByText('Operating', { exact: true }).first(), 2000)
  await shot(page, info, '02-ctl006-before')

  await caption(page, 'The test', 'The quarterly test on Checkout Web found an admin console that accepted a password alone.', 1500)
  await app.getByRole('button', { name: /Checkout Web/ }).click()
  await expect(app.getByText('Record a control test')).toBeVisible()
  await app.getByRole('button', { name: 'Fail', exact: true }).click()
  await caption(page, 'What failed?', 'The recorder now says what failed. A design failure breaks the control everywhere; an operating failure breaks it here.', 1500)
  const operating = app.getByRole('button', { name: /Operating failure/ })
  await highlight(app.getByText('What failed?'), 1200)
  await operating.click()
  await expect(operating).toHaveAttribute('aria-pressed', 'true')
  await caption(page, 'What failed?', 'This one is operating: the control is designed properly, it did not run on Checkout Web.', 2000)
  await app.getByText('Evidence reference').last().locator('..').locator('input').fill(
    'Q4 test: checkout admin console accepted a password-only login.',
  )
  await pause(page, 600)
  await shot(page, info, '03-record-operating-failure')
  await app.getByRole('button', { name: 'Record fail' }).click()

  // -- the impact record -------------------------------------------------
  const report = app.getByTestId('impact-report')
  await expect(report).toBeVisible()
  await caption(page, 'What it changed', 'The impact is computed in the same transaction as the cascade and kept on the test record, as lineage.', 2600)
  await shot(page, info, '04-impact-top')

  const pci = app.getByTestId('impact-framework-PCI-DSS-4.0')
  await expect(pci).toContainText('lost coverage under all_in_scope')
  await caption(page, 'PCI DSS', 'PCI DSS loses both requirements: under all_in_scope, one in-scope asset without the control is enough. Coverage 67% to 0%.', 1000)
  await highlight(pci, 4200)

  const iso = app.getByTestId('impact-framework-ISO-27001-2022')
  await expect(iso).toContainText('Still covered under any_in_scope')
  await caption(page, 'ISO 27001', 'ISO 27001 is untouched: four of its five in-scope assets still carry the control, and its rule is any_in_scope.', 1000)
  await highlight(iso, 4200)
  await shot(page, info, '05-impact-frameworks')

  const r6 = app.getByTestId('impact-risk-RISK-006')
  await expect(r6).toContainText('affected')
  await expect(r6).toContainText('above appetite')
  await caption(page, 'RISK-006', 'RISK-006 is scoped to Checkout Web and Card Vault. Its control effectiveness falls from CE-High to CE-Unvalidated, so the residual 8 is proposed back to 16 High, above appetite.', 1000)
  await highlight(r6, 5000)
  await shot(page, info, '06-impact-risk-006')

  for (const ref of ['RISK-007', 'RISK-001']) {
    await expect(app.getByTestId('impact-risk-' + ref)).toContainText('not affected')
  }
  await caption(page, 'Other risks', 'RISK-007 (workforce identity) and RISK-001 (Payments API) do not include Checkout Web in their scope, so nothing moves for them.', 1000)
  await highlight(app.getByTestId('impact-risk-RISK-007'), 2400)
  await highlight(app.getByTestId('impact-risk-RISK-001'), 2400)
  await shot(page, info, '07-impact-risks-unaffected')
  await caption(page, 'Proposed, not applied', 'The proposed residual is never written. The residual stays locked until someone passes the validation gate (RINV-1).', 3200)
  await app.getByRole('button', { name: 'Close', exact: true }).click()

  await caption(page, 'The control', 'CTL-006 stays Operating. An operating failure does not take the whole control down (DL-1).', 1200)
  await highlight(app.getByText('Operating', { exact: true }).first(), 2400)
  await expect(app.getByRole('button', { name: /Checkout Web/ })).toContainText('Failed')
  await highlight(app.getByRole('button', { name: /Checkout Web/ }), 2400)
  await shot(page, info, '08-ctl006-after')

  // -- downstream records ------------------------------------------------
  await nav(page, 'Compliance')
  await app.getByRole('button', { name: /PCI Data Security Standard/ }).click()
  await expect(coverage).toHaveText('0%')
  await caption(page, 'Compliance', 'The PCI DSS register now reads 0%, and each gap says which control failed, on which asset, under which rule.', 1200)
  await highlight(coverage, 2000)
  const gapRow = app.locator('tr', { hasText: '8.4.2' })
  await expect(gapRow).toContainText('Checkout Web')
  await highlight(gapRow, 3800)
  await shot(page, info, '09-pci-after')
  await app.getByRole('button', { name: /ISO\/IEC 27001/ }).click()
  await expect(coverage).toHaveText('75%')
  await caption(page, 'Compliance', 'ISO 27001 still reads 75%.', 1000)
  await highlight(coverage, 2200)

  await nav(page, 'Risks')
  await app.getByText('Card data exposed through a hijacked checkout session').click()
  const banner = app.getByText(/failed its test on Checkout Web/)
  await expect(banner).toBeVisible()
  await caption(page, 'RISK-006', 'RISK-006 carries the flag, names the asset, and states the proposed residual. Its owner has been notified.', 1200)
  await highlight(banner.locator('..'), 4500)
  await shot(page, info, '10-risk-006-banner')

  // -- alerts ------------------------------------------------------------
  await caption(page, 'Alerts', 'Tomas Lindqvist owns the PCI requirements. He signs in to see what reached him.', 1600)
  await signOut(page)
  await signIn(page, 'grc@example.com')
  await app.getByRole('link', { name: 'Notifications' }).click()
  const lost = app.getByText('PCI-DSS-4.0 8.4.2 lost coverage')
  await expect(lost).toBeVisible()
  await caption(page, 'Alerts', 'One alert per requirement lost, to its owner, and one posture alert because PCI DSS fell below the 90% floor. Nothing about ISO, because nothing happened to ISO.', 1000)
  await highlight(lost.locator('xpath=ancestor::li[1]'), 3000)
  const posture = app.getByText(/pulled coverage below 90%/)
  await expect(posture).toBeVisible()
  await highlight(posture.locator('xpath=ancestor::li[1]'), 3200)
  await shot(page, info, '11-grc-notifications')
  await clearCaption(page)

  await titleCard(page, 'One test, scoped consequences', [
    'PCI DSS (all_in_scope): 67% to 0%, both requirements lost, owner and posture alerts.',
    'ISO 27001 (any_in_scope): 75%, unchanged. Four of five in-scope assets still carry the control.',
    'RISK-006 (scope includes Checkout Web): CE-High to CE-Unvalidated, proposed residual 16, above appetite.',
    'RISK-007 and RISK-001 (scopes elsewhere): not affected.',
    'CTL-006 stays Operating: an operating failure is not a design failure.',
  ], 9000)
})
