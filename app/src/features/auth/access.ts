export function isAdminAccess(role: string | null | undefined): boolean {
  return role === 'admin'
}
