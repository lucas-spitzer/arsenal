import { apiRequest } from './apiClient'

export type ExamType = 'full_practice' | 'subject' | 'practice'
export type SubjectKind = 'source' | 'lesson'

export interface ExamQuestion {
  quiz_id: string
  question: string
  options: string[]
  subject_kind?: SubjectKind | null
  subject_id?: string | null
  subject_name?: string | null
  visual?: Record<string, unknown> | null
}

export interface ExamAttempt {
  id: string
  exam_type: ExamType
  subject_kind?: SubjectKind | null
  subject_id?: string | null
  subject_name?: string | null
  status: string
  sequence_number: number
  started_at: string
  completed_at?: string | null
  question_count: number
  correct_count: number
  points_earned: number
  quota_snapshot: Record<string, unknown>
  questions: ExamQuestion[]
  answered_quiz_ids: string[]
}

export interface PointsAwarded {
  event_type: 'first_correct' | 'repeat_correct' | 'mastery_bonus'
  points: number
}

export interface AnswerSubmitResult {
  correct: boolean
  right_answer: string
  explanation?: string | null
  feedback?: string | null
  points_awarded: PointsAwarded[]
  points_total: number
  correct_count: number
  mastered: boolean
  newly_mastered: boolean
  lifetime_ap: number
  attempt_correct_count: number
  attempt_points_earned: number
}

export interface AtlasMe {
  lifetime_ap: number
  concepts_mastered: number
  accuracy: number | null
  questions_answered: number
  correct_answers: number
}

export interface LeaderboardEntry {
  rank: number
  user_id: string
  name: string
  rank_title?: string | null
  lifetime_ap: number
  concepts_mastered: number
  accuracy: number | null
}

export interface Leaderboard {
  platoon_total_ap: number
  platoon_goal: number | null
  ends_at: string
  finalized: boolean
  student_access: boolean
  entries: LeaderboardEntry[]
}

export interface CompetitionSettings {
  workspace_id: string
  starts_at: string
  ends_at: string
  platoon_goal: number | null
  student_access: boolean
  finalized_at: string | null
  final_standings: LeaderboardEntry[] | null
  updated_at: string
}

export interface SubjectBreakdown {
  subject_kind: SubjectKind
  subject_id: string
  subject_name: string
  lifetime_ap: number
  concepts_mastered: number
  accuracy: number | null
  questions_answered: number
}

export interface PlatoonDashboard {
  platoon_total_ap: number
  concepts_mastered: number
  accuracy: number | null
  participants: number
  completed_exams: number
  student_access: boolean
  ends_at: string
  finalized: boolean
  leaderboard: LeaderboardEntry[]
  by_subject: SubjectBreakdown[]
}

export interface AtlasAccess {
  student_access: boolean
  ends_at: string
  finalized: boolean
}

export interface DashboardSubject {
  subject_kind: SubjectKind
  subject_id: string
  subject_name: string
}

export interface DashboardSummary {
  lifetime_ap: number
  concepts_mastered: number
  total_questions: number
  accuracy: number | null
  questions_answered: number
  correct_answers: number
}

export interface DashboardWeakQuestion extends DashboardSubject {
  quiz_id: string
  question: string
  correct_count: number
  incorrect_count: number
}

export interface DashboardDay {
  day: string
  answered: number
  correct: number
  points: number
}

export interface Dashboard {
  user_id: string
  subjects: DashboardSubject[]
  summary: DashboardSummary
  weak_questions: DashboardWeakQuestion[]
  activity: DashboardDay[]
  active_days: number
  ends_at: string
}

export async function getDashboard(
  workspaceId: string,
  options: {
    userId?: string | null
    subjectKind?: SubjectKind | null
    subjectId?: string | null
    tz?: string | null
  } = {},
): Promise<Dashboard> {
  const params = new URLSearchParams()
  if (options.userId) params.set('user_id', options.userId)
  if (options.subjectKind && options.subjectId) {
    params.set('subject_kind', options.subjectKind)
    params.set('subject_id', options.subjectId)
  }
  if (options.tz) params.set('tz', options.tz)
  const query = params.toString()
  return apiRequest<Dashboard>(`/workspaces/${workspaceId}/atlas/dashboard${query ? `?${query}` : ''}`)
}

export async function getAtlasAccess(workspaceId: string): Promise<AtlasAccess> {
  return apiRequest<AtlasAccess>(`/workspaces/${workspaceId}/atlas/access`)
}

export async function getAtlasMe(workspaceId: string): Promise<AtlasMe> {
  return apiRequest<AtlasMe>(`/workspaces/${workspaceId}/atlas/me`)
}

export async function getLeaderboard(workspaceId: string): Promise<Leaderboard> {
  return apiRequest<Leaderboard>(`/workspaces/${workspaceId}/atlas/leaderboard`)
}

export async function startExam(
  workspaceId: string,
  body: {
    exam_type: 'full_practice' | 'subject'
    subject_kind?: SubjectKind | null
    subject_id?: string | null
  },
): Promise<ExamAttempt> {
  return apiRequest<ExamAttempt>(`/workspaces/${workspaceId}/atlas/exams`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function submitExamAnswer(
  workspaceId: string,
  attemptId: string,
  body: {
    quiz_id: string
    question: string
    options: string[]
    selected_index: number
  },
): Promise<AnswerSubmitResult> {
  return apiRequest<AnswerSubmitResult>(
    `/workspaces/${workspaceId}/atlas/exams/${attemptId}/answers`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export async function completeExam(workspaceId: string, attemptId: string): Promise<ExamAttempt> {
  return apiRequest<ExamAttempt>(`/workspaces/${workspaceId}/atlas/exams/${attemptId}/complete`, {
    method: 'POST',
  })
}

export async function submitPracticeAnswer(
  workspaceId: string,
  body: {
    quiz_id: string
    question: string
    options?: string[]
    selected_index?: number
    response?: string
  },
): Promise<AnswerSubmitResult> {
  return apiRequest<AnswerSubmitResult>(`/workspaces/${workspaceId}/atlas/practice/answers`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function getCompetition(workspaceId: string): Promise<CompetitionSettings> {
  return apiRequest<CompetitionSettings>(`/workspaces/${workspaceId}/atlas/competition`)
}

export async function updateCompetition(
  workspaceId: string,
  body: {
    starts_at?: string
    ends_at?: string
    platoon_goal?: number | null
    student_access?: boolean
  },
): Promise<CompetitionSettings> {
  return apiRequest<CompetitionSettings>(`/workspaces/${workspaceId}/atlas/competition`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function finalizeCompetition(workspaceId: string): Promise<CompetitionSettings> {
  return apiRequest<CompetitionSettings>(`/workspaces/${workspaceId}/atlas/competition/finalize`, {
    method: 'POST',
  })
}

export async function getPlatoonDashboard(workspaceId: string): Promise<PlatoonDashboard> {
  return apiRequest<PlatoonDashboard>(`/workspaces/${workspaceId}/atlas/platoon`)
}
