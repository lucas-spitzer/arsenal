export function isMultipleSelect(kind: string | null | undefined): boolean {
  return kind === 'multiple_select'
}

export function listPhrase(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

export function answerLabels(correctOptions: string[] | undefined, rightAnswer: string | undefined): string[] {
  if (correctOptions && correctOptions.length > 0) return correctOptions
  return (rightAnswer ?? '')
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
}
