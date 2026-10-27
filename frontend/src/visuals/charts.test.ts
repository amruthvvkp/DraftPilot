import { describe, expect, it } from 'vitest'
import { actStarts, circleLayout, edgeWidth, formatIntensity, intensityColor, intensityY, linePath, pacingByAct, sceneX, tensionRuns } from './charts'
import { sampleVisuals } from './fixtures'

describe('chart helpers', () => {
  it('maps intensity to height with +5 at the top, clamped', () => {
    expect(intensityY(5, 100, 10)).toBe(10)
    expect(intensityY(0, 100, 10)).toBe(50)
    expect(intensityY(-9, 100, 10)).toBe(90)
    expect(sceneX(0, 1, 200)).toBe(100)
    expect(sceneX(3, 4, 200, 20)).toBe(180)
  })

  it('splits the curve where a scene has no rated events', () => {
    const runs = tensionRuns(sampleVisuals().scenes, 300, 100)
    expect(runs.map(run => run.map(point => point.scene.id))).toEqual([[21, 22], [24]])
    expect(linePath([{ x: 0, y: 1 }, { x: 2.25, y: 3 }])).toBe('M0.0,1.0 L2.3,3.0')
    expect(actStarts(sampleVisuals())).toEqual([{ id: 4, title: 'Act One', index: 0 }, { id: 5, title: 'Act Two', index: 2 }])
  })

  it('formats and colours intensities', () => {
    expect([formatIntensity(2.25), formatIntensity(-1), formatIntensity(0), formatIntensity(null)]).toEqual(['+2.3', '-1', '0', '—'])
    expect(intensityColor(null)).toBe('var(--surface-3)')
    expect(intensityColor(5)).toContain('85%')
    expect(intensityColor(-2)).toContain('chart-low')
  })

  it('weights each act’s pacing by runtime', () => {
    const [one, two] = pacingByAct(sampleVisuals())
    expect([one.runtime, one.share, one.scenes.map(item => item.share)]).toEqual([180, 0.6, [1 / 3, 2 / 3]])
    expect(one.intensity).toBe(3)
    expect([two.intensity, two.peak]).toEqual([-3, -3])
  })

  it('lays the cast on a ring and scales edges by shared moments', () => {
    const [top, , bottom] = circleLayout(4, 50, 50, 10).map(point => ({ x: Math.round(point.x), y: Math.round(point.y) }))
    expect([top, bottom]).toEqual([{ x: 50, y: 40 }, { x: 50, y: 60 }])
    const [son, wife, named] = sampleVisuals().edges
    expect(edgeWidth(wife, 2.25)).toBe(8)
    expect(edgeWidth(son, 2.25)).toBeCloseTo(1 + 7 * 1.5 / 2.25)
    expect(edgeWidth(named, 2.25)).toBe(1)
  })
})
