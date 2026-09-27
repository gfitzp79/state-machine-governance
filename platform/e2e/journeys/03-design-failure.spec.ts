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
  titleCard,
} from './helpers'

/**
 * Journey 3. The contrast: a design failure.
 *
 * Same control, fresh state. This time the test finds the control does not
 * work as designed. DL-1 takes the objective into Failure, and scope no longer
 * limits anything: every framework and every risk the control carries moves.
 */
test('Journey 3: a design failure, for contrast', async ({ page }, info) => {
  resetDemo()
  const app = page.locator('#root')
  await installCursor(page)
  await page.goto('/login')
  await titleCard(page, 'Journey 3: a design failure, for contrast', [
    'Same control, same starting point as journey 1.',
    'This time the test on Card Vault finds the conditional access policy itself is wrong:',
    'the control does not work as designed, anywhere. Scope cannot contain that.',
  ], 7000)

  await caption(page, 'Sign in', 'Jonah Weiss records the Card Vault test.', 1600)
  await signIn(page, 'control@example.com')
  await nav(page, 'Controls')
  await app.getByText('Multi-factor authentication for all interactive access').click()
  await app.getByRole('button', { name: /Card Vault/ }).click()
  await expect(app.getByText('Record a control test')).toBeVisible()
  await app.getByRole('button', { name: 'Fail', exact: true }).click()
  const design = app.getByRole('button', { name: /Design failure/ })
  await expect(design).toHaveAttribute('aria-pressed', 'true')
  await caption(page, 'What failed?', 'Design failure, the default and the widest reading: the policy exempts a legacy sign-in flow on every system.', 1000)
  await highlight(design, 3000)
  await app.getByText('Evidence reference').last().locator('..').locator('input').fill(
    'Q4 test: conditional access policy exempts the legacy sign-in flow on all apps.',
  )
  await pause(page, 600)
  await shot(page, info, '01-record-design-failure')
  await app.getByRole('button', { name: 'Record fail' }).click()

  await expect(app.getByTestId('impact-report')).toBeVisible()
  const banner = app.getByText(/Design failure\./)
  await caption(page, 'What it changed', 'Design failure: CTL-006 entered Failure everywhere it runs (DL-1). Scope did not limit this.', 800)
  await highlight(banner.locator('..'), 3600)
  const iso = app.getByTestId('impact-framework-ISO-27001-2022')
  await expect(iso).toContainText('lost coverage')
  await caption(page, 'ISO 27001', 'This time ISO 27001 loses both requirements too, 75% to 25%. Compare journey 1, where it did not move.', 800)
  await highlight(iso, 4000)
  await shot(page, info, '02-design-frameworks')
  const r7 = app.getByTestId('impact-risk-RISK-007')
  await expect(r7).toContainText('affected')
  await caption(page, 'Risks', 'And every risk relying on CTL-006 is frozen, including RISK-007, whose scope has nothing to do with the asset tested.', 800)
  await highlight(r7, 3800)
  await highlight(app.getByTestId('impact-risk-RISK-001'), 3200)
  await shot(page, info, '03-design-risks')
  await app.getByRole('button', { name: 'Close', exact: true }).click()

  const failure = app.getByText('This control is in Failure')
  await expect(failure).toBeVisible()
  await caption(page, 'The control', 'CTL-006 is in Failure. Escalation to the CISO is automatic if it stays there without a remediation plan.', 1000)
  await highlight(failure.locator('xpath=ancestor::div[2]'), 3600)
  await shot(page, info, '04-control-failure')

  await nav(page, 'Compliance')
  const coverage = app.locator('p', { hasText: /^\d+%$/ }).first()
  await expect(coverage).toHaveText('25%')
  await caption(page, 'Compliance', 'ISO 27001 at 25%.', 1000)
  await highlight(coverage, 2200)
  await app.getByRole('button', { name: /PCI Data Security Standard/ }).click()
  await expect(coverage).toHaveText('0%')
  await caption(page, 'Compliance', 'PCI DSS at 0%.', 1000)
  await highlight(coverage, 2200)
  await shot(page, info, '05-compliance-design')
  await clearCaption(page)

  await titleCard(page, 'Design versus operating', [
    'Operating failure on Checkout Web (journey 1): PCI 67% to 0%, ISO unchanged, one risk affected.',
    'Design failure on Card Vault (this journey): PCI 67% to 0%, ISO 75% to 25%, every linked risk frozen.',
    'The tester says which it was. An unclassified failure is read as Design, the widest reading.',
  ], 8000)
})
