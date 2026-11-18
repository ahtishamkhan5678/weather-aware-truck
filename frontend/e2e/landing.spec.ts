import { expect, test } from '@playwright/test'
import { mockApi } from './fixtures'

test.beforeEach(async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
})

test('hero, sticky header and section highlighting', async ({ page, isMobile }) => {
  await expect(page.getByRole('heading', { level: 1 })).toContainText('WEATHER')
  const nav = page.getByRole('navigation', { name: 'Primary' })
  await expect(nav).toBeVisible()

  await page.evaluate(() => window.scrollTo(0, document.getElementById('rules')!.offsetTop))
  await expect(nav).toBeInViewport()
  const top = await nav.evaluate((el) => el.getBoundingClientRect().top)
  expect(top).toBeLessThan(30)
  await expect(nav.locator('a.is-active')).toHaveText('Rules')

  if (!isMobile) {
    await page.evaluate(() => window.scrollTo(0, 0))
    const date = await page.locator('.topbar__date').boundingBox()
    const cta = await page.locator('.topbar__cta').boundingBox()
    expect(date!.x + date!.width).toBeLessThanOrEqual(cta!.x)
  }
})

test('statement fills, counters and live risk matrix', async ({ page }) => {
  const lastWord = page.locator('.statement .word').last()
  const fillBefore = await lastWord.evaluate((el) => getComputedStyle(el).getPropertyValue('--fill'))
  await page.locator('#rules').scrollIntoViewIfNeeded()
  await expect.poll(async () => lastWord.evaluate((el) => getComputedStyle(el).getPropertyValue('--fill').trim())).not.toBe(fillBefore.trim())
  await expect(page.locator('.tcard__num').first()).toHaveText('49', { timeout: 5000 })
  const table = page.locator('.rules-table')
  await expect(table).toContainText('25 – 34')
  await expect(table).toContainText('> 1')
  await expect(page.locator('.load-rules')).toContainText('Wind 35–44 mph with load >40,000 lb')
})

test('no horizontal scrolling', async ({ page }) => {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
})
