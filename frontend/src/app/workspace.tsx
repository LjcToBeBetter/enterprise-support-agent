import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { allPages, api, jsonBody, tokenStore } from '../api/client';
import type { Membership, Organization, Role, User } from '../types';

interface Workspace {
  user: User | null; authLoading: boolean; sessionNotice: string;
  organizations: Organization[]; organizationId: string; organization?: Organization;
  memberships: Membership[]; role?: Role; organizationsLoading: boolean; membershipsLoading: boolean;
  workspaceError: unknown; setOrganizationId: (id: string) => void;
  login: (email: string, password: string) => Promise<void>; logout: () => void;
  refreshOrganizations: () => Promise<void>; refreshMembers: () => void;
}
const Context = createContext<Workspace | null>(null);
export function useWorkspace() { const value = useContext(Context); if (!value) throw new Error('WorkspaceProvider is missing'); return value; }

/** 登录身份和当前组织集中管理；换组织时清掉旧组织成员，避免权限或数据闪回。 */
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [sessionNotice, setSessionNotice] = useState('');
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrgId] = useState('');
  const [memberships, setMembers] = useState<Membership[]>([]);
  const [membersOrg, setMembersOrg] = useState('');
  const [organizationsLoading, setOrgsLoading] = useState(false);
  const [membershipsLoading, setMembersLoading] = useState(false);
  const [workspaceError, setError] = useState<unknown>();
  const [memberRevision, setMemberRevision] = useState(0);
  const userIdRef = useRef<string | null>(null);
  const organizationRequest = useRef(0);
  userIdRef.current = user?.id || null;

  const logout = useCallback(() => {
    userIdRef.current = null; organizationRequest.current += 1;
    tokenStore.clear(); setUser(null); setOrganizations([]); setOrgId(''); setMembers([]); setMembersOrg(''); setError(undefined);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    if (!tokenStore.get()) { setAuthLoading(false); return; }
    api<User>('/auth/me', { signal: controller.signal }).then(setUser).catch(error => {
      if (error.name !== 'AbortError') { logout(); setSessionNotice(error.message); }
    }).finally(() => { if (!controller.signal.aborted) setAuthLoading(false); });
    return () => controller.abort();
  }, [logout]);
  useEffect(() => {
    const expired = () => { logout(); setSessionNotice('登录已过期，请重新登录。'); };
    window.addEventListener('session-expired', expired);
    return () => window.removeEventListener('session-expired', expired);
  }, [logout]);

  const login = async (email: string, password: string) => {
    const result = await api<{ access_token: string }>('/auth/login', { method: 'POST', body: jsonBody({ email, password }) });
    tokenStore.set(result.access_token);
    try { setUser(await api<User>('/auth/me')); setSessionNotice(''); }
    catch (error) { tokenStore.clear(); throw error; }
  };

  const refreshOrganizations = useCallback(async () => {
    if (!user) return;
    const requestNumber = ++organizationRequest.current;
    const isCurrent = () => requestNumber === organizationRequest.current && userIdRef.current === user.id;
    setOrgsLoading(true); setError(undefined);
    try {
      const values = await allPages<Organization>('/organizations');
      if (!isCurrent()) return;
      setOrganizations(values);
      setOrgId(current => {
        const remembered = localStorage.getItem(`support.org.${user.id}`);
        return values.some(org => org.id === current) ? current : values.some(org => org.id === remembered) ? remembered! : values[0]?.id || '';
      });
    } catch (error) { if (isCurrent()) setError(error); }
    finally { if (isCurrent()) setOrgsLoading(false); }
  }, [user]);
  useEffect(() => { if (user) void refreshOrganizations(); }, [user, refreshOrganizations]);
  const setOrganizationId = useCallback((id: string) => {
    setMembers([]); setMembersOrg(''); setOrgId(id);
    if (user) localStorage.setItem(`support.org.${user.id}`, id);
  }, [user]);

  useEffect(() => {
    setMembers([]); setMembersOrg('');
    if (!organizationId || !user) return;
    const controller = new AbortController(); setMembersLoading(true);
    api<Membership[]>(`/organizations/${organizationId}/members`, { signal: controller.signal })
      .then(values => { setMembers(values); setMembersOrg(organizationId); })
      .catch(error => { if (error.name !== 'AbortError') setError(error); })
      .finally(() => { if (!controller.signal.aborted) setMembersLoading(false); });
    return () => controller.abort();
  }, [organizationId, user, memberRevision]);

  const role = membersOrg === organizationId ? memberships.find(member => member.user_id === user?.id)?.role : undefined;
  return <Context.Provider value={{ user, authLoading, sessionNotice, organizations, organizationId, organization: organizations.find(org => org.id === organizationId), memberships, role, organizationsLoading, membershipsLoading, workspaceError, setOrganizationId, login, logout, refreshOrganizations, refreshMembers: () => setMemberRevision(value => value + 1) }}>{children}</Context.Provider>;
}
