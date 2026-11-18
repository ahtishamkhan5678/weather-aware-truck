import { expect, test, type Page } from '@playwright/test'
import { mockApi, planFixture } from './fixtures'

async function choosePlace(page: Page, label: 'Origin' | 'Destination', text: string, option: string) {
  const input = page.getByLabel(label, { exact: true })
  await input.fill(text)
  await page.getByRole('option', { name: option }).click()
  await expect(input).toHaveValue(option)
}

async function planTrip(page: Page) {
  await choosePlace(page, 'Origin', 'Denver', 'Denver, Colorado, US')
  await choosePlace(page, 'Destination', 'Salt Lake', 'Salt Lake City, Utah, US')
  await page.getByLabel('Load weight (lb)').fill('42000')
  await page.getByRole('radio', { name: '25 mi' }).click()
  await page.getByRole('button', { name: /Find the safest route/ }).click()
}

test('complete flow: inputs → 3 routes → recommendation → checkpoints → heatmap', async ({ page }) => {
  await mockApi(page)
  await page.goto('/planner')
  await planTrip(page)

  // Three route options, ranked, with the recommendation explained.
  await expect(page.locator('.route-card')).toHaveCount(3)
  await expect(page.locator('.recommendation__title')).toContainText('Route B')
  await expect(page.locator('.recommendation')).toContainText('fewest Severe miles')
  await expect(page.locator('.recommendation__reasons li')).toHaveCount(2)
  await expect(page.locator('.route-card').first()).toContainText('Best')

  // Map: one summary chip per route, recommended one starred.
  await expect(page.locator('.route-chip')).toHaveCount(3)
  await expect(page.locator('.route-chip.is-recommended')).toContainText('B')

  // Checkpoints every 25 mi with ETAs (500 mi + 20 → 21 rows + header).
  await expect(page.locator('.cp-row:not(.cp-row--head)')).toHaveCount(21)
  await expect(page.locator('.cp-row').nth(2)).toContainText('25')

  // Heatmap ready; slider starts at departure; layers switch.
  const slider = page.getByRole('slider', { name: 'Forecast hour' })
  await expect(slider).toBeVisible()
  await expect(page.locator('.forecast__time')).toContainText('Departure hour')
  await slider.fill('12')
  await expect(page.locator('.forecast__time')).toContainText('+12 h after departure hour')
  await page.getByRole('radio', { name: 'Wind' }).click()
  await expect(page.locator('.legend__label')).toContainText('Wind')

  // Clicking a checkpoint row syncs the slider to that checkpoint's ETA.
  await page.locator('.cp-row').nth(5).click() // mile 100 → ~1.7 h after departure
  await expect(page.locator('.forecast__time')).toContainText('+2 h after departure hour')
  await expect(page.locator('.cp-popup')).toContainText('Route B')

  // Selecting another route swaps the table.
  await page.locator('.route-card', { hasText: 'A' }).filter({ hasText: '#2 of 3' }).click()
  await expect(page.locator('.checkpoints h3')).toContainText('Route A')

  // Play animates the hour forward.
  const before = await slider.inputValue()
  await page.getByRole('button', { name: 'Play forecast' }).click()
  await expect.poll(() => slider.inputValue()).not.toBe(before)
  await page.getByRole('button', { name: 'Pause' }).click()
})

test('every route blocked → No-Travel warning is shown', async ({ page }) => {
  await mockApi(page, planFixture('blocked'))
  await page.goto('/planner')
  await planTrip(page)
  await expect(page.locator('.recommendation')).toHaveClass(/is-blocked/)
  await expect(page.locator('.recommendation')).toContainText('fewest No-Travel miles')
  await expect(page.getByRole('status').filter({ hasText: 'Consider delaying departure' })).toBeVisible()
})

test('rate limit → friendly error → retry succeeds', async ({ page }) => {
  await mockApi(page, (call) =>
    call === 1
      ? { status: 503, body: { error: { code: 'rate_limited', message: 'The free weather quota is busy right now. Please retry in about a minute.' } } }
      : { status: 200, body: planFixture() },
  )
  await page.goto('/planner')
  await planTrip(page)
  const alert = page.getByRole('alert').filter({ hasText: 'quota is busy' })
  await expect(alert).toBeVisible()
  await alert.getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.route-card')).toHaveCount(3)
})

test('very long trip (100+ checkpoints) never overflows sideways', async ({ page }) => {
  await mockApi(page, planFixture('long'))
  await page.goto('/planner')
  await planTrip(page)
  await expect(page.locator('.cp-row:not(.cp-row--head)')).toHaveCount(117)
  const panelOverflow = await page.locator('.panel').evaluate((el) => el.scrollWidth - el.clientWidth)
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(panelOverflow).toBeLessThanOrEqual(0)
  expect(pageOverflow).toBeLessThanOrEqual(0)
})

test('validation: submit is disabled until origin and destination are set', async ({ page }) => {
  await mockApi(page)
  await page.goto('/planner')
  const submit = page.getByRole('button', { name: /Find the safest route/ })
  await expect(submit).toBeDisabled()
  await page.getByLabel('Origin', { exact: true }).fill('Denver')
  await expect(submit).toBeDisabled()
  await page.getByLabel('Destination', { exact: true }).fill('Salt Lake')
  await expect(submit).toBeEnabled()
})
