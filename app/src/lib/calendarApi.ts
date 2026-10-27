import { apiRequest, apiRequestVoid } from './apiClient'

export type CalendarEventKind = 'deadline' | 'class' | 'prac_app' | 'evaluation'

export interface CalendarEvent {
  id: string
  workspace_id: string
  title: string
  kind: CalendarEventKind
  /** Local calendar date, `YYYY-MM-DD`. */
  event_date: string
  /** `HH:MM:SS`, or null for an all-day item. */
  start_time: string | null
  end_time: string | null
  location: string | null
  notes: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface CalendarEventInput {
  title: string
  kind: CalendarEventKind
  event_date: string
  start_time: string | null
  end_time: string | null
  location: string | null
  notes: string | null
}

export async function listCalendarEvents(
  workspaceId: string,
  range: { start?: string; end?: string } = {},
): Promise<CalendarEvent[]> {
  const params = new URLSearchParams()
  if (range.start) params.set('start', range.start)
  if (range.end) params.set('end', range.end)
  const query = params.toString()
  return apiRequest<CalendarEvent[]>(
    `/workspaces/${workspaceId}/calendar-events${query ? `?${query}` : ''}`,
  )
}

export async function createCalendarEvent(
  workspaceId: string,
  payload: CalendarEventInput,
): Promise<CalendarEvent> {
  return apiRequest<CalendarEvent>(`/workspaces/${workspaceId}/calendar-events`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateCalendarEvent(
  workspaceId: string,
  eventId: string,
  payload: Partial<CalendarEventInput>,
): Promise<CalendarEvent> {
  return apiRequest<CalendarEvent>(`/workspaces/${workspaceId}/calendar-events/${eventId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteCalendarEvent(workspaceId: string, eventId: string): Promise<void> {
  await apiRequestVoid(`/workspaces/${workspaceId}/calendar-events/${eventId}`, {
    method: 'DELETE',
  })
}
