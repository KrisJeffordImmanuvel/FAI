import type { Role } from "./types";

export interface NavItem { to: string; label: string; icon: string; roles: Role[]; group: "Library" | "Agent" | "Insight" | "System" }

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "LayoutDashboard", roles: ["admin", "librarian", "member"], group: "Library" },
  { to: "/catalog", label: "Catalog", icon: "BookOpen", roles: ["admin", "librarian", "member"], group: "Library" },
  { to: "/members", label: "Members", icon: "Users", roles: ["admin", "librarian"], group: "Library" },
  { to: "/circulation", label: "Circulation", icon: "ArrowLeftRight", roles: ["admin", "librarian"], group: "Library" },
  { to: "/my-loans", label: "My loans", icon: "ArrowLeftRight", roles: ["member"], group: "Library" },
  { to: "/reservations", label: "Reservations", icon: "BookmarkCheck", roles: ["admin", "librarian", "member"], group: "Library" },
  { to: "/fines", label: "Fines", icon: "Receipt", roles: ["admin", "librarian", "member"], group: "Library" },
  { to: "/approvals", label: "Approvals", icon: "ShieldCheck", roles: ["admin", "librarian"], group: "Library" },
  { to: "/notifications", label: "Notifications", icon: "Bell", roles: ["admin", "librarian", "member"], group: "Agent" },
  { to: "/agent", label: "Agent control", icon: "Cpu", roles: ["admin", "librarian"], group: "Agent" },
  { to: "/explain", label: "Explainability", icon: "Lightbulb", roles: ["admin", "librarian"], group: "Agent" },
  { to: "/knowledge-base", label: "Knowledge base", icon: "Network", roles: ["admin", "librarian"], group: "Agent" },
  { to: "/ml", label: "ML insights", icon: "BrainCircuit", roles: ["admin", "librarian"], group: "Insight" },
  { to: "/analytics", label: "Analytics", icon: "ChartLine", roles: ["admin", "librarian"], group: "Insight" },
  { to: "/about", label: "About the agent", icon: "Info", roles: ["admin", "librarian", "member"], group: "Insight" },
  { to: "/admin", label: "Administration", icon: "Settings", roles: ["admin"], group: "System" },
  { to: "/audit", label: "Audit log", icon: "ScrollText", roles: ["admin", "librarian"], group: "System" },
];

export function navFor(role: Role): NavItem[] {
  return NAV.filter((n) => n.roles.includes(role));
}

/** Can a role open a route path? Detail routes inherit their section's rules. */
export function canAccess(role: Role, path: string): boolean {
  const section = "/" + (path.split("/")[1] ?? "");
  const item = NAV.find((n) => n.to === section);
  return item ? item.roles.includes(role) : section === "/";
}

export const can = {
  manageCirculation: (r: Role) => r === "admin" || r === "librarian",
  editKnowledgeBase: (r: Role) => r === "admin",
  retrainModel: (r: Role) => r === "admin",
  editSettings: (r: Role) => r === "admin",
  decideApprovals: (r: Role) => r === "admin" || r === "librarian",
};
