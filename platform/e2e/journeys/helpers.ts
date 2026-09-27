import { execSync } from 'node:child_process'
import path from 'node:path'
import type { Locator, Page, TestInfo } from '@playwright/test'

/**
 * Presentation helpers for the recorded journeys.
 *
 * The journeys are tests first: every step asserts what the screen must show,
 * so a video can only be produced by a platform that actually behaves the way
 * its caption says. The helpers below add what a viewer needs and a headless
 * browser does not provide: captions, a visible cursor, and a highlight on the
 * thing being talked about.
 */

export const PASSWORD = 'changeme123'

/** Fresh database, standard seed, then the scope-aware demo (e2e/seed_scope_demo.py). */
export function resetDemo() {
  const script = path.resolve(__dirname, '..', 'reset-demo.sh')
  execSync(`sh "${script}"`, {
    stdio: 'inherit',
    env: { ...process.env, PROJECT: process.env.E2E_PROJECT ?? 'platform' },
  })
}

/** Pace, so a viewer can read what is on screen. E2E_FAST=1 skips it. */
export async function pause(page: Page, ms: number) {
  if (process.env.E2E_FAST) return
  await page.waitForTimeout(ms)
}

/** A fake cursor that follows Playwright's mouse, and pulses on click. */
export async function installCursor(page: Page) {
  await page.addInitScript(() => {
    const install = () => {
      if (document.getElementById('__journey_cursor')) return
      const dot = document.createElement('div')
      dot.id = '__journey_cursor'
      Object.assign(dot.style, {
        position: 'fixed', zIndex: '2147483647', width: '22px', height: '22px',
        marginLeft: '-11px', marginTop: '-11px', borderRadius: '50%',
        background: 'rgba(245, 158, 11, 0.35)', border: '2px solid rgb(217, 119, 6)',
        pointerEvents: 'none', transition: 'transform 120ms ease', left: '-50px', top: '-50px',
      })
      document.body.appendChild(dot)
      window.addEventListener('mousemove', (e) => {
        dot.style.left = e.clientX + 'px'
        dot.style.top = e.clientY + 'px'
      }, true)
      window.addEventListener('mousedown', () => (dot.style.transform = 'scale(0.6)'), true)
      window.addEventListener('mouseup', () => (dot.style.transform = 'scale(1)'), true)
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', install)
    } else {
      install()
    }
  })
}

/** A caption bar across the bottom of the frame. Survives in-app navigation. */
export async function caption(page: Page, step: string, text: string, readMs = 3200) {
  await page.evaluate(
    ([step, text]) => {
      let bar = document.getElementById('__journey_caption')
      if (!bar) {
        bar = document.createElement('div')
        bar.id = '__journey_caption'
        Object.assign(bar.style, {
          position: 'fixed', left: '50%', bottom: '28px', transform: 'translateX(-50%)',
          zIndex: '2147483646', maxWidth: '1100px', width: 'calc(100% - 120px)',
          background: 'rgba(15, 23, 42, 0.94)', color: 'white', borderRadius: '14px',
          padding: '16px 22px', font: '500 19px/1.45 Inter, system-ui, sans-serif',
          boxShadow: '0 12px 32px rgba(0,0,0,0.35)', pointerEvents: 'none',
        })
        document.body.appendChild(bar)
      }
      bar.innerHTML = ''
      const tag = document.createElement('div')
      tag.textContent = step
      Object.assign(tag.style, {
        font: '700 12px/1 Inter, system-ui, sans-serif', letterSpacing: '0.08em',
        textTransform: 'uppercase', color: 'rgb(251, 191, 36)', marginBottom: '6px',
      })
      const body = document.createElement('div')
      body.textContent = text
      bar.append(tag, body)
    },
    [step, text],
  )
  await pause(page, readMs)
}

export async function clearCaption(page: Page) {
  await page.evaluate(() => document.getElementById('__journey_caption')?.remove())
}

/** A full-frame title card, for the start and end of a journey. */
export async function titleCard(page: Page, title: string, lines: string[], readMs = 5000) {
  await page.evaluate(
    ([title, lines]) => {
      const card = document.createElement('div')
      card.id = '__journey_title'
      Object.assign(card.style, {
        position: 'fixed', inset: '0', zIndex: '2147483646', display: 'flex',
        flexDirection: 'column', justifyContent: 'center', padding: '0 140px',
        background: 'linear-gradient(135deg, rgb(15, 23, 42), rgb(30, 41, 59))', color: 'white',
        font: '400 22px/1.5 Inter, system-ui, sans-serif',
      })
      const h = document.createElement('div')
      h.textContent = title as string
      Object.assign(h.style, { font: '700 44px/1.2 Inter, system-ui, sans-serif', marginBottom: '28px' })
      card.appendChild(h)
      for (const line of lines as string[]) {
        const p = document.createElement('div')
        p.textContent = line
        Object.assign(p.style, { marginTop: '10px', color: 'rgb(203, 213, 225)', maxWidth: '1000px' })
        card.appendChild(p)
      }
      document.body.appendChild(card)
    },
    [title, lines] as const,
  )
  await pause(page, readMs)
  await page.evaluate(() => document.getElementById('__journey_title')?.remove())
}

/** Outline the element being discussed, and bring it into view. */
export async function highlight(target: Locator, holdMs = 2200) {
  // Centre it, so the caption bar across the bottom never covers it.
  await target.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }))
  await target.evaluate((el) => {
    const e = el as HTMLElement
    e.dataset.journeyOutline = e.style.outline
    e.style.outline = '3px solid rgb(245, 158, 11)'
    e.style.outlineOffset = '3px'
    e.style.borderRadius = e.style.borderRadius || '8px'
  })
  await pause(target.page(), holdMs)
  await target.evaluate((el) => {
    const e = el as HTMLElement
    e.style.outline = e.dataset.journeyOutline ?? ''
  })
}

/** A screenshot per step, kept beside the video for review. */
export async function shot(page: Page, info: TestInfo, name: string) {
  await page.screenshot({ path: info.outputPath(name + '.png') })
}

/** Sign in through the real login form, as the named demo user. */
export async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.locator('input[type=email]').fill(email)
  await page.locator('input[type=password]').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.getByRole('heading', { name: 'Governance posture' }).waitFor()
}

export async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('heading', { name: 'Sign in' }).waitFor()
}

export async function nav(page: Page, name: string) {
  await page.getByRole('link', { name, exact: true }).click()
}
