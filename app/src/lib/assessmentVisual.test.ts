import { describe, expect, it } from 'vitest'
import { cardFace, showsSituationImage, showsStemImage } from './assessmentVisual'

describe('card faces', () => {
  it('replaces the back with a diagram and leaves the front as text', () => {
    expect(cardFace('front', 'back')).toBe('text')
    expect(cardFace('back', 'back')).toBe('image')
  })

  it('replaces the front when the picture is the prompt', () => {
    expect(cardFace('front', 'front')).toBe('image')
    expect(cardFace('back', 'front')).toBe('text')
  })

  it('keeps the text beside the picture', () => {
    expect(cardFace('front', 'beside')).toBe('both')
    expect(cardFace('back', 'beside')).toBe('both')
  })

  it('puts the image and the label on the front and the description on the back', () => {
    expect(cardFace('front', 'front_with_label')).toBe('both')
    expect(cardFace('back', 'front_with_label')).toBe('text')
  })

  it('stays text when there is no placement', () => {
    expect(cardFace('back', null)).toBe('text')
  })

  it('uses a stem on questions and a situation on scenarios', () => {
    expect(showsStemImage('stem')).toBe(true)
    expect(showsStemImage('back')).toBe(false)
    expect(showsSituationImage('situation')).toBe(true)
    expect(showsSituationImage('stem')).toBe(false)
  })
})
