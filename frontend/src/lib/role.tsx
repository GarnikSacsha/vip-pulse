import { createContext, type ReactNode, useContext, useState } from "react";

/**
 * Demo roles: a switcher that shapes the views, NOT authorisation. The API serves everything to
 * everyone; the choice only filters what the browser shows (decision 0015).
 */
export type Role = { kind: "all" } | { kind: "manager"; id: string } | { kind: "lead" } | { kind: "head" };

export const ROLE_KEY = "vip-pulse-role";

export function parseRole(value: string | null): Role {
  if (value === "lead" || value === "head") return { kind: value };
  if (value?.startsWith("manager:") && value.length > "manager:".length) {
    return { kind: "manager", id: value.slice("manager:".length) };
  }
  return { kind: "all" };
}

export function roleValue(role: Role): string {
  return role.kind === "manager" ? `manager:${role.id}` : role.kind;
}

/** Sections a role sees, in nav order. */
const SECTIONS: Record<Role["kind"], string[]> = {
  all: ["/queue", "/winback", "/lead", "/overview"],
  manager: ["/queue", "/winback"],
  lead: ["/queue", "/lead"],
  head: ["/overview", "/lead"],
};

export function sectionsOf(role: Role): string[] {
  return SECTIONS[role.kind];
}

/** The manager whose data a role is limited to, if any. */
export function managerOf(role: Role): string | null {
  return role.kind === "manager" ? role.id : null;
}

function readStored(): Role {
  try {
    return parseRole(localStorage.getItem(ROLE_KEY));
  } catch {
    return { kind: "all" };
  }
}

function store(role: Role) {
  try {
    localStorage.setItem(ROLE_KEY, roleValue(role));
  } catch {
    // Storage blocked (private mode): the role still applies until the page reloads.
  }
}

interface RoleState {
  role: Role;
  setRole: (role: Role) => void;
}

const RoleContext = createContext<RoleState>({ role: { kind: "all" }, setRole: () => {} });

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(readStored);
  function setRole(next: Role) {
    store(next);
    setRoleState(next);
  }
  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleState {
  return useContext(RoleContext);
}
