/** Knowledge term questions practice in Flashcards, not Quiz. */
export function isWikiTermQuiz(quiz: { origin?: Record<string, unknown> | null }): boolean {
  return quiz.origin?.source === 'wiki_term'
}
