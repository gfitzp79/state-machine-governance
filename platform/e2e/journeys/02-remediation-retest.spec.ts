import { expect, test } from '@playwright/test'
import {
  caption,
  clearCaption,
  highlight,
  installCursor,
  nav,
  pause,
  shot,
  signIn,
  signOut,
  titleCard,
} from './helpers'

/**
 * Journey 2. The fix, the retest, and coverage re-asserted through the gate.
 *
 * Continues from the state journey 1 leaves: Checkout Web Failed, both PCI
 * requirements a Gap, RISK-006 frozen. A passing retest with evidence is a
 * remediation retest (TST-4): it returns the deployment to Active through the
 * DL-4 gate. Coverage does not come back by itself. A person re-asserts it,
 * and the AINV-2 and AINV-11 gate re-checks it.
 */
test('Journey 2: remediation retest and re-asserted coverage', async ({ page }, info) => {
  const app = page.locator('#root')
  await installCursor(page)
  await page.goto('/login')
  await titleCard(page, 'Journey 2: the fix, and the retest', [
    'Picks up where journey 1 left off: Checkout Web failed, PCI DSS at 0%, RISK-006 frozen.',
    'The admin console has been fixed. A passing retest with evidence is a remediation retest.',
    'Watch what comes back automatically, and what a person has to re-assert.',
  ], 7000)

  await caption(page, 'Sign in', 'Jonah Weiss retests Checkout Web after the fix.', 1800)
  await signIn(page, 'control@example.com')
  await nav(page, 'Controls')
  await app.getByText('Multi-factor authentication for all interactive access').click()
  const checkout = app.getByRole('button', { name: /Checkout Web/ })
  await expect(checkout).toContainText('Failed')
  await highlight(checkout, 2000)
  await checkout.click()
  await expect(app.getByText('Record a control test')).toBeVisible()

  await caption(page, 'The retest', 'Pass, with evidence. On a Failed deployment that makes it a remediation retest, which attempts the DL-4 gate back to Active.', 1500)
  await app.getByRole('button', { name: 'Pass', exact: true }).click()
  await app.getByText('Evidence reference').last().locator('..').locator('input').fill(
    'Retest: admin console now enforces the second factor; sign-in log sample attached.',
  )
  await pause(page, 600)
  await shot(page, info, '01-retest')
  await app.getByRole('button', { name: 'Record pass' }).click()

  await expect(app.getByTestId('impact-report')).toBeVisible()
  const pci = app.getByTestId('impact-framework-PCI-DSS-4.0')
  await expect(pci).toContainText('Coverage can be re-asserted')
  await caption(page, 'What it changed', 'PCI DSS: the gap is now restorable, but still a gap. Coverage is a claim, and a claim is re-asserted, not assumed.', 1000)
  await highlight(pci, 4200)
  const r6 = app.getByTestId('impact-risk-RISK-006')
  await expect(r6).toContainText('CE-High')
  await caption(page, 'What it changed', 'RISK-006: control effectiveness is back to CE-High. The residual becomes eligible for update; it does not update itself.', 1000)
  await highlight(r6, 4200)
  await shot(page, info, '02-retest-impact')
  await app.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(checkout).toContainText('Active')
  await highlight(checkout, 2000)

  await caption(page, 'Handover', 'Tomas Lindqvist owns the PCI requirements. The platform has told him coverage can be re-asserted.', 1800)
  await signOut(page)
  await signIn(page, 'grc@example.com')
  await app.getByRole('link', { name: 'Notifications' }).click()
  const restorable = app.getByText('PCI-DSS-4.0 8.4.2 can be re-asserted as Covered')
  await expect(restorable).toBeVisible()
  await highlight(restorable.locator('xpath=ancestor::li[1]'), 3200)
  await shot(page, info, '03-restorable-notification')

  await nav(page, 'Compliance')
  await app.getByRole('button', { name: /PCI Data Security Standard/ }).click()
  const coverage = app.locator('p', { hasText: /^\d+%$/ }).first()
  await expect(coverage).toHaveText('0%')
  for (const ref of ['8.4.2', '8.4.3']) {
    const row = app.locator('tr', { hasText: ref })
    await caption(page, 'Re-assert ' + ref, 'Assess, then Covered. The gate re-checks that CTL-006 is live on every PCI in-scope asset (AINV-11) before it accepts.', 800)
    await row.getByRole('button', { name: 'Assess' }).click()
    await app.locator('select').last().selectOption('Covered')
    await pause(page, 800)
    await app.getByRole('button', { name: 'Record position' }).click()
    await expect(row).toContainText('Covered')
    await highlight(row, 1800)
  }
  await expect(coverage).toHaveText('67%')
  await caption(page, 'Restored', 'PCI DSS is back to 67%, each requirement re-asserted by its owner and each one gated.', 1000)
  await highlight(coverage, 2600)
  await shot(page, info, '04-pci-restored')

  await nav(page, 'Risks')
  await app.getByText('Card data exposed through a hijacked checkout session').click()
  const banner = app.getByText(/restored/)
  await expect(banner.first()).toBeVisible()
  await caption(page, 'RISK-006', 'RISK-006 is flagged Control Improved: the residual is eligible for update, and the validation gate still decides (RINV-1).', 1000)
  await highlight(banner.first().locator('..'), 4000)
  await shot(page, info, '05-risk-006-improved')
  await clearCaption(page)

  await titleCard(page, 'Recovery is gated, too', [
    'A passing retest with evidence returned Checkout Web to Active through the DL-4 gate.',
    'Coverage did not return by itself: the requirement owner was told it could, and re-asserted it.',
    'The Covered gate re-checked AINV-11 across every PCI in-scope asset before accepting.',
    'RISK-006 is eligible for re-evaluation; its residual still moves only through the gate.',
  ], 8000)
})
